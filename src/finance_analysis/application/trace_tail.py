"""Хвост следа: объект в хранилище, указатель в DuckDB, журнал трёх счётчиков.

Запись объекта условная: S3 `PutObject` с `If-None-Match: *`
(https://docs.aws.amazon.com/AmazonS3/latest/API/API_PutObject.html).
Замок — GOVERNANCE, MinIO Object Lock
(https://www.min.io/docs/minio/linux/administration/object-management/object-retention.html).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from finance_analysis.domain.errors import AlreadyExists, InvalidArgument, NotFound
from finance_analysis.domain.trace_limit import (
    limit_trace,
    retention_policy,
    view_from_evidence,
)

LOG = logging.getLogger("fas.trace")
_MISSING = {
    "reason": "pointer_missing",
    "status": "truncated",
    "evidence_complete": False,
    "cited_cells": [],
    "dropped_cell_count": 0,
    "periods": [],
    "fact_uses": [],
}


def log_trace_metrics(*, cells: int, dropped: int, additions: int) -> None:
    LOG.info(
        "calculation_trace_cells=%s calculation_trace_dropped=%s sums_additions=%s",
        cells,
        dropped,
        additions,
    )


async def publish_trace(
    store,
    pointer,
    *,
    analysis_id: str,
    execution_id: str,
    periods: list[dict] | None = None,
    fact_uses: list[dict] | None = None,
    evidence=None,
    retention: str = "analysis",
    sums_additions: int = 0,
    now: datetime | None = None,
    retainer=None,
) -> dict:
    """Резервирует слот, пишет объект, затем подтверждает указатель.

    Тот же `execution_id` повторно слот не занимает. Сбой замка снимает объект
    и строку. Сбой подтверждения оставляет `pending`, чтобы сверка нашла объект.
    """

    moment = now or datetime.now(UTC)
    view = view_from_evidence(evidence) if evidence is not None else limit_trace(periods or [], fact_uses=fact_uses)
    policy = retention_policy(retention, now=moment)
    dropped = list(view.pop("dropped_cells"))
    key = _object_key(analysis_id, execution_id)
    body = json.dumps(
        {
            "analysis_id": analysis_id,
            "execution_id": execution_id,
            "dropped_cells": dropped,
            "trace": view,
        },
        ensure_ascii=False,
    ).encode()
    retained = None if policy is None else policy.until.isoformat()
    slot = pointer.reserve(
        analysis_id,
        execution_id,
        object_key=key,
        evidence_complete=view["evidence_complete"],
        dropped_cell_count=view["dropped_cell_count"],
        retained_until=retained,
    )
    if slot == "committed":
        stored = await read_trace(store, pointer, analysis_id=analysis_id, execution_id=execution_id)
        return stored
    row = {
        "analysis_id": analysis_id,
        "execution_id": execution_id,
        "object_key": key,
        "evidence_complete": view["evidence_complete"],
        "dropped_cell_count": view["dropped_cell_count"],
        "retained_until": retained,
        "state": "committed",
    }
    try:
        await store.put_if_absent(key, body)
    except AlreadyExists:
        found = await store.get(key)
        if found != body:
            raise InvalidArgument("след с этим execution_id уже записан другим телом") from None
    except Exception:
        if slot == "reserved":
            pointer.delete(analysis_id, execution_id)
        raise
    if policy is not None:
        if retainer is None:
            await _drop_uncommitted(store, pointer, analysis_id, execution_id, key)
            raise InvalidArgument("для удержания нужен замок объекта")
        try:
            await retainer.hold(key, mode=policy.mode, until=policy.until)
        except Exception:
            await _drop_uncommitted(store, pointer, analysis_id, execution_id, key)
            raise
    pointer.commit(row)
    additions = sums_additions if evidence is None else evidence.sums_additions
    log_trace_metrics(cells=len(view["cited_cells"]), dropped=view["dropped_cell_count"], additions=additions)
    return view


async def read_trace(store, pointer, *, analysis_id: str, execution_id: str) -> dict:
    """Компактный DTO. Отброшенные ячейки сюда не возвращаются."""

    payload = await _payload(store, pointer, analysis_id=analysis_id, execution_id=execution_id)
    trace = payload.get("trace")
    if not isinstance(trace, dict):
        return dict(_MISSING)
    return trace


async def read_trace_archive(store, pointer, *, analysis_id: str, execution_id: str) -> dict:
    """Полный объект, включая `dropped_cells`."""

    payload = await _payload(store, pointer, analysis_id=analysis_id, execution_id=execution_id)
    if not isinstance(payload.get("trace"), dict):
        return {"dropped_cells": [], "trace": dict(_MISSING)}
    return payload


async def reconcile_traces(store, pointer) -> dict:
    """Подтверждает `pending`, у которого объект уже есть, и называет объекты без указателя."""

    present = await _trace_keys(store)
    known = {row["object_key"] for row in pointer.list_all()}
    committed = []
    for row in pointer.list_all():
        if row.get("state") == "pending" and row["object_key"] in present:
            pointer.commit(row)
            committed.append(row["object_key"])
    return {"orphans": sorted(present - known), "committed": committed}


async def delete_analysis_traces(store, pointer, analysis_id: str, *, now: datetime | None = None) -> None:
    """До `retained_until` объект остаётся. После даты удаляются объект и строка."""

    moment = now or datetime.now(UTC)
    for row in pointer.list_analysis(analysis_id):
        if _still_held(row, moment):
            continue
        await store.delete_prefix(row["object_key"])
        pointer.delete(analysis_id, row["execution_id"])


async def sweep_expired_traces(store, pointer, *, now: datetime) -> None:
    """Отдельный проход: срок вышел, анализ ещё не удаляли."""

    for row in pointer.list_all():
        if _still_held(row, now) or not row.get("retained_until"):
            continue
        await store.delete_prefix(row["object_key"])
        pointer.delete(row["analysis_id"], row["execution_id"])


async def _payload(store, pointer, *, analysis_id: str, execution_id: str) -> dict:
    row = pointer.get(analysis_id, execution_id)
    if row is None:
        return {"trace": dict(_MISSING)}
    try:
        payload = json.loads(await store.get(row["object_key"]))
    except NotFound:
        return {"trace": dict(_MISSING)}
    if not isinstance(payload, dict):
        return {"trace": dict(_MISSING)}
    return payload


async def _trace_keys(store) -> set[str]:
    found = set()
    async for item in store.list("traces/"):
        found.add(item.key)
    return found


async def _drop_uncommitted(store, pointer, analysis_id: str, execution_id: str, key: str) -> None:
    try:
        await store.delete_prefix(key)
    except Exception:  # noqa: BLE001 — сбой удаления оставляет указатель, объект не теряется
        return
    pointer.delete(analysis_id, execution_id)


def _still_held(row: dict, now: datetime) -> bool:
    raw = row.get("retained_until")
    if not raw:
        return False
    moment = datetime.fromisoformat(raw)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment > now


def _object_key(analysis_id: str, execution_id: str) -> str:
    for value in (analysis_id, execution_id):
        if not isinstance(value, str) or not value or "/" in value or "\\" in value:
            raise InvalidArgument("идентификатор следа недопустим")
    return f"traces/{analysis_id}/{execution_id}.json"
