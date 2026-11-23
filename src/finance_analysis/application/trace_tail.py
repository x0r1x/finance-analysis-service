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
    TraceLimitError,
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


class TracePublishError(Exception):
    """Сбой публикации следа. Стадия — `put`, `retention` или `pointer`."""

    def __init__(self, stage: str, execution_id: str) -> None:
        super().__init__(stage)
        self.stage = stage
        self.execution_id = execution_id


def record_trace_failure(analysis_id: str, execution_id: str, stage: str, exc: BaseException) -> None:
    """ERROR для повтора: идентификаторы, стадия и тип исключения. Значений нет."""

    from finance_analysis.application.metrics import TRACE_WRITE_FAILURES

    TRACE_WRITE_FAILURES.inc()
    LOG.error(
        "trace_write_failed analysis_id=%s execution_id=%s stage=%s exception_type=%s",
        analysis_id,
        execution_id,
        stage,
        type(exc).__name__,
    )


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
    execution_source: str | None = None,
    actor_fields: dict | None = None,
) -> dict:
    """Резервирует слот, пишет объект, держит замок, затем подтверждает указатель.

    Состояния: `pending_object`, `pending_retention`, `pending_commit`, `committed`.
    Тот же `execution_id` слот повторно не занимает. Сбой оставляет строку:
    без объекта — `pending_object`, без замка — `pending_retention`. Сверка
    не подтверждает строку, пока обязательный замок не пройден.
    """

    moment = now or datetime.now(UTC)
    view = view_from_evidence(evidence) if evidence is not None else limit_trace(periods or [], fact_uses=fact_uses)
    if execution_source is not None:
        view["execution_source"] = execution_source
    for key in ("actor_type", "actor_id", "confirmation_kind", "binding_key", "state_seq", "inputs"):
        if actor_fields is not None and key in actor_fields:
            view[key] = actor_fields[key]
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
    try:
        slot = pointer.reserve(
            analysis_id,
            execution_id,
            object_key=key,
            evidence_complete=view["evidence_complete"],
            dropped_cell_count=view["dropped_cell_count"],
            retained_until=retained,
        )
    except TraceLimitError:
        raise
    except Exception as exc:
        raise TracePublishError("pointer", execution_id) from exc
    if slot == "committed":
        return await read_trace(store, pointer, analysis_id=analysis_id, execution_id=execution_id)
    if slot in {"reserved", "pending_object", "pending"}:
        wrote = False
        try:
            await store.put_if_absent(key, body)
            wrote = True
        except AlreadyExists:
            wrote = False
        except Exception as exc:
            raise TracePublishError("put", execution_id) from exc
        if not wrote:
            try:
                found = await store.get(key)
            except Exception as exc:
                raise TracePublishError("put", execution_id) from exc
            if found != body:
                raise TracePublishError("put", execution_id) from InvalidArgument(
                    "след с этим execution_id уже записан другим телом"
                )
        slot = "pending_retention" if policy is not None else "pending_commit"
        try:
            pointer.set_state(analysis_id, execution_id, slot)
        except Exception as exc:
            raise TracePublishError("pointer", execution_id) from exc
    if slot in {"pending_retention", "pending_commit"}:
        await _require_same_body(
            store,
            key,
            body,
            execution_id,
            policy=policy,
            retainer=retainer,
        )
    if slot == "pending_retention":
        if policy is None or retainer is None:
            raise TracePublishError("retention", execution_id) from InvalidArgument("для удержания нужен замок объекта")
        try:
            await retainer.hold(key, mode=policy.mode, until=policy.until)
        except Exception as exc:
            raise TracePublishError("retention", execution_id) from exc
        slot = "pending_commit"
        try:
            pointer.set_state(analysis_id, execution_id, slot)
        except Exception as exc:
            raise TracePublishError("pointer", execution_id) from exc
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
        pointer.commit(row)
    except Exception as exc:
        raise TracePublishError("pointer", execution_id) from exc
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

    `pending_retention` и строка с `retained_until` без пройденного замка не становятся
    `committed`. Строка без объекта тоже не подтверждается: она в `unfinished`.
    Старый `pending` без `retained_until` — режим analysis, замок не требовался.
    """

    present = await _trace_keys(store)
    known = {row["object_key"] for row in pointer.list_all()}
    committed = []
    held = []
    unfinished = []
    for row in pointer.list_all():
        state = row.get("state") or "pending"
        if state == "committed":
            continue
        exists = row["object_key"] in present
        key = row["object_key"]
        lock_pending = state == "pending_retention" or (
            state in {"pending", "pending_object"} and row.get("retained_until")
        )
        if lock_pending or not exists:
            unfinished.append(key)
            if lock_pending and exists:
                held.append(key)
            continue
        if state in {"pending_commit", "pending", "pending_object"}:
            pointer.commit(row)
            committed.append(key)
    return {
        "orphans": sorted(present - known),
        "committed": committed,
        "held": held,
        "unfinished": unfinished,
    }


async def delete_analysis_traces(store, pointer, analysis_id: str, *, now: datetime | None = None) -> None:
    """До `retained_until` объект остаётся. После даты удаляются объект и строка."""

    moment = now or datetime.now(UTC)
    for row in pointer.list_analysis(analysis_id):
        if _still_held(row, moment):
            continue
        await store.delete_prefix(row["object_key"])
        pointer.delete(analysis_id, row["execution_id"])


async def sweep_expired_traces(store, pointer, *, now: datetime) -> int:
    """Отдельный проход: срок вышел, анализ ещё не удаляли."""

    from finance_analysis.application.metrics import TRACE_SWEPT

    removed = 0
    for row in pointer.list_all():
        if _still_held(row, now) or not row.get("retained_until"):
            continue
        await store.delete_prefix(row["object_key"])
        pointer.delete(row["analysis_id"], row["execution_id"])
        removed += 1
    if removed:
        TRACE_SWEPT.inc(removed)
    return removed


async def _require_same_body(store, key: str, body: bytes, execution_id: str, *, policy, retainer) -> None:
    """Чужое тело — конфликт. Пропавший объект на этой стадии восстанавливается, а не подтверждается."""

    try:
        found = await store.get(key)
    except NotFound:
        await _recover_missing_object(store, key, body, execution_id, policy=policy, retainer=retainer)
        return
    if found != body:
        raise TracePublishError("put", execution_id) from InvalidArgument(
            "след с этим execution_id уже записан другим телом"
        )


async def _recover_missing_object(store, key: str, body: bytes, execution_id: str, *, policy, retainer) -> None:
    """Пишет тело заново через put_if_absent, сверяет его и ставит замок, если он нужен.

    Возврат из этой функции значит, что объект уже лежит и совпадает с телом.
    Указатель подтверждается только после этого.
    """

    try:
        await store.put_if_absent(key, body)
    except AlreadyExists:
        pass
    except Exception as exc:
        raise TracePublishError("put", execution_id) from exc
    try:
        found = await store.get(key)
    except NotFound as exc:
        raise TracePublishError("put", execution_id) from exc
    if found != body:
        raise TracePublishError("put", execution_id) from InvalidArgument(
            "след с этим execution_id уже записан другим телом"
        )
    if policy is None:
        return
    if retainer is None:
        raise TracePublishError("retention", execution_id) from InvalidArgument("для удержания нужен замок объекта")
    try:
        await retainer.hold(key, mode=policy.mode, until=policy.until)
    except Exception as exc:
        raise TracePublishError("retention", execution_id) from exc


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
