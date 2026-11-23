"""Хвост следа: объект в хранилище, указатель в DuckDB, журнал трёх счётчиков."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from finance_analysis.domain.errors import InvalidArgument, NotFound
from finance_analysis.domain.trace_limit import (
    TRACE_LIMIT,
    TraceLimitError,
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
    """Пишет хвост и указатель. 65-й след анализа не пишется. Ячейки сверх 512 помечаются."""

    # shortcut: счётчик читается до записи. Два параллельных публикующих могут оба пройти. Поднять, когда следы одного анализа пишутся параллельно.
    if pointer.count(analysis_id) >= TRACE_LIMIT:
        raise TraceLimitError(f"следов больше {TRACE_LIMIT}")
    moment = now or datetime.now(UTC)
    view = view_from_evidence(evidence) if evidence is not None else limit_trace(periods or [], fact_uses=fact_uses)
    policy = retention_policy(retention, now=moment)
    dropped = view.pop("dropped_cells")
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
    await store.put(key, body)
    if policy is not None:
        if retainer is None:
            await store.delete_prefix(key)
            raise InvalidArgument("для удержания нужен замок объекта")
        await retainer.hold(key, mode=policy.mode, until=policy.until)
    pointer.put(
        {
            "analysis_id": analysis_id,
            "execution_id": execution_id,
            "object_key": key,
            "evidence_complete": view["evidence_complete"],
            "dropped_cell_count": view["dropped_cell_count"],
            "retained_until": None if policy is None else policy.until.isoformat(),
        }
    )
    log_trace_metrics(
        cells=len(view["cited_cells"]),
        dropped=view["dropped_cell_count"],
        additions=sums_additions,
    )
    return view


async def read_trace(store, pointer, *, analysis_id: str, execution_id: str) -> dict:
    """Читает DTO. Сломанный указатель не достраивает ячейки из хвоста."""

    row = pointer.get(analysis_id, execution_id)
    if row is None:
        return dict(_MISSING)
    try:
        payload = json.loads(await store.get(row["object_key"]))
    except NotFound:
        return dict(_MISSING)
    trace = payload.get("trace")
    if not isinstance(trace, dict):
        return dict(_MISSING)
    return trace


async def delete_analysis_traces(store, pointer, analysis_id: str) -> None:
    """Жизнь анализа: без замка объект и строка удаляются. С замком объект остаётся."""

    for row in pointer.list_analysis(analysis_id):
        if row.get("retained_until"):
            continue
        await store.delete_prefix(row["object_key"])
        pointer.delete(analysis_id, row["execution_id"])


def _object_key(analysis_id: str, execution_id: str) -> str:
    for value in (analysis_id, execution_id):
        if not isinstance(value, str) or not value or "/" in value or "\\" in value:
            raise InvalidArgument("идентификатор следа недопустим")
    return f"traces/{analysis_id}/{execution_id}.json"
