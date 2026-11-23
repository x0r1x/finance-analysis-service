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
    OBJECT_BYTE_LIMIT,
    fit_object,
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
    """Резервирует слот, пишет объект, держит замок, затем подтверждает указатель.

    Состояния: `pending_object`, `pending_retention`, `pending_commit`, `committed`.
    Сверка подтверждает только `pending_commit`. Тот же `execution_id` повторно
    слот не занимает. Сбой замка снимает объект и строку; если снять не удалось,
    строка остаётся `pending_retention`.
    """

    moment = now or datetime.now(UTC)
    view = view_from_evidence(evidence) if evidence is not None else limit_trace(periods or [], fact_uses=fact_uses)
    policy = retention_policy(retention, now=moment)
    dropped = list(view.pop("dropped_cells", []))
    key = _object_key(analysis_id, execution_id)
    envelope = {
        "analysis_id": analysis_id,
        "execution_id": execution_id,
        "dropped_cells": dropped,
    }
    body = fit_object(view, envelope, byte_limit=OBJECT_BYTE_LIMIT)
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
        return await read_trace(store, pointer, analysis_id=analysis_id, execution_id=execution_id)
    if slot in {"reserved", "pending_object", "pending"}:
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
        slot = "pending_retention" if policy is not None else "pending_commit"
        pointer.set_state(analysis_id, execution_id, slot)
    if slot == "pending_retention":
        if policy is None or retainer is None:
            await _drop_uncommitted(store, pointer, analysis_id, execution_id, key)
            raise InvalidArgument("для удержания нужен замок объекта")
        try:
            await retainer.hold(key, mode=policy.mode, until=policy.until)
        except Exception:
            await _drop_uncommitted(store, pointer, analysis_id, execution_id, key)
            raise
        slot = "pending_commit"
        pointer.set_state(analysis_id, execution_id, slot)
    row = {
        "analysis_id": analysis_id,
        "execution_id": execution_id,
        "object_key": key,
        "evidence_complete": view["evidence_complete"],
        "dropped_cell_count": view["dropped_cell_count"],
        "retained_until": retained,
        "state": "committed",
    }
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
    """Подтверждает только строку, у которой пройдены все обязательные стадии.

    `pending_retention` не становится `committed`: объект без замка замком не считается.
    Старый `pending` без `retained_until` — режим analysis, замок не требовался.
    """

    present = await _trace_keys(store)
    known = {row["object_key"] for row in pointer.list_all()}
    committed = []
    held = []
    for row in pointer.list_all():
        state = row.get("state") or "pending"
        exists = row["object_key"] in present
        if state == "pending_retention" or (state == "pending" and row.get("retained_until")):
            if exists:
                held.append(row["object_key"])
            continue
        if state == "pending_object" and row.get("retained_until"):
            if exists:
                held.append(row["object_key"])
            continue
        if exists and state in {"pending_commit", "pending", "pending_object"}:
            pointer.commit(row)
            committed.append(row["object_key"])
    return {"orphans": sorted(present - known), "committed": committed, "held": held}


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
