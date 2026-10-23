"""Wren MDL на книгу, RLAC и пул движков (§7, §4.13.3)."""

from __future__ import annotations

import asyncio
import base64
import json
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import anyio
import pyarrow as pa
from wren.config import WrenConfig
from wren.engine import WrenEngine
from wren.model.data_source import DataSource

from finance_analysis.domain.errors import BookBusy, InvalidArgument
from finance_analysis.domain.ids import job_id as check_job
from finance_analysis.settings import Settings

_SERIES_COLUMNS = [
    ("model_id", "varchar", True),
    ("row_key", "varchar", False),
    ("binding_key", "varchar", False),
    ("axis_id", "varchar", False),
    ("period_id", "varchar", False),
    ("cell_id", "varchar", False),
    ("value", "double", False),
    ("value_dec", "decimal", False),
    ("normalized_value", "decimal", False),
    ("value_status", "varchar", False),
    ("sheet", "varchar", False),
    ("label", "varchar", False),
    ("label_path_text", "varchar", False),
    ("kind", "varchar", False),
    ("unit", "varchar", False),
    ("currency", "varchar", False),
    ("scale", "varchar", False),
    ("scale_factor", "bigint", False),
    ("period_index", "integer", False),
    ("period_key_base", "varchar", False),
    ("period_marker", "varchar", False),
    ("period_start", "date", False),
    ("period_end", "date", False),
    ("calendar_year", "integer", False),
    ("concept", "varchar", False),
    ("effective_concept", "varchar", False),
    ("mapping_status", "varchar", False),
    ("is_primary", "boolean", False),
    ("concept_source", "varchar", False),
    ("concept_confidence", "double", False),
    ("phase", "varchar", False),
    ("sign", "varchar", False),
    ("aggregation", "varchar", False),
]


def _q(path: str) -> str:
    return path.replace("'", "''")


def series_ref_sql(paths: dict[str, str]) -> str:
    fact = _q(paths["fact_observation"])
    dim_row = _q(paths["dim_row"])
    dim_period = _q(paths["dim_period"])
    bindings = _q(paths["bindings"])
    row_sem = _q(paths["row_semantics"])
    period_sem = _q(paths["period_semantics"])
    return f"""
    SELECT
      f.model_id AS model_id,
      f.row_key AS row_key,
      r.binding_key AS binding_key,
      f.axis_id AS axis_id,
      f.period_id AS period_id,
      f.cell_id AS cell_id,
      CAST(f.value AS DOUBLE) AS value,
      f.value_dec AS value_dec,
      f.normalized_value AS normalized_value,
      f.value_status AS value_status,
      r.sheet AS sheet,
      r.label AS label,
      r.label_path_text AS label_path_text,
      r.kind AS kind,
      r.unit AS unit,
      r.currency AS currency,
      r.scale AS scale,
      r.scale_factor AS scale_factor,
      p.period_index AS period_index,
      p.period_key_base AS period_key_base,
      p.period_marker AS period_marker,
      p.period_start AS period_start,
      p.period_end AS period_end,
      p.calendar_year AS calendar_year,
      b.concept AS concept,
      b.effective_concept AS effective_concept,
      b.status AS mapping_status,
      b.is_primary AS is_primary,
      b.source AS concept_source,
      CAST(b.confidence AS DOUBLE) AS concept_confidence,
      ps.phase AS phase,
      rs.sign AS sign,
      rs.aggregation AS aggregation
    FROM read_parquet('{fact}') f
    JOIN read_parquet('{dim_row}') r
      ON f.model_id = r.model_id AND f.build_key = r.build_key AND f.row_key = r.row_key
    JOIN read_parquet('{dim_period}') p
      ON f.model_id = p.model_id AND f.build_key = p.build_key
     AND f.axis_id = p.axis_id AND f.period_id = p.period_id
    LEFT JOIN read_parquet('{bindings}') b
      ON f.model_id = b.model_id AND f.build_key = b.build_key AND f.row_key = b.row_key
    LEFT JOIN read_parquet('{row_sem}') rs
      ON f.model_id = rs.model_id AND f.build_key = rs.build_key AND f.row_key = rs.row_key
    LEFT JOIN read_parquet('{period_sem}') ps
      ON f.model_id = ps.model_id AND f.build_key = ps.build_key
     AND f.axis_id = ps.axis_id AND f.period_id = ps.period_id
    """


def build_mdl(job_id: str, paths: dict[str, str]) -> dict:
    checked = check_job(job_id)
    for name, path in paths.items():
        if checked not in path:
            raise InvalidArgument(f"путь {name} не принадлежит книге")
    columns = [
        {
            "name": name,
            "type": typ,
            **({"isHidden": True} if hidden else {}),
            **({"properties": {"owner": "fas"}} if name in {"phase", "sign", "aggregation"} else {}),
        }
        for name, typ, hidden in _SERIES_COLUMNS
    ]
    return {
        "catalog": "fas",
        "schema": "book",
        "models": [
            {
                "name": "series",
                "refSql": series_ref_sql(paths),
                "columns": columns,
                "primaryKey": "cell_id",
                "rowLevelAccessControls": [
                    {
                        "name": "one_workbook",
                        "requiredProperties": [{"name": "session_model_id", "required": True}],
                        "condition": "model_id = @session_model_id",
                    }
                ],
            },
        ],
        "cubes": [
            {
                "name": "series_cube",
                "baseObject": "series",
                "measures": [
                    {
                        "name": "value_sum",
                        "expression": "sum(CASE WHEN is_primary THEN normalized_value END)",
                        "type": "number",
                    },
                    {"name": "value_last", "expression": "max(value)", "type": "number"},
                    {"name": "cells", "expression": "count(cell_id)", "type": "number"},
                ],
                "dimensions": [
                    {"name": "row_key", "expression": "row_key", "type": "varchar"},
                    {"name": "sheet", "expression": "sheet", "type": "varchar"},
                    {"name": "label_path", "expression": "label_path_text", "type": "varchar"},
                    {"name": "concept", "expression": "CASE WHEN is_primary THEN effective_concept END", "type": "varchar"},
                    {"name": "period_id", "expression": "period_id", "type": "varchar"},
                    {"name": "phase", "expression": "phase", "type": "varchar"},
                    {"name": "period_marker", "expression": "period_marker", "type": "varchar"},
                ],
                "timeDimensions": [
                    {"name": "period_start", "expression": "period_start", "type": "date"}
                ],
            }
        ],
    }


def _source(settings: Settings):
    if settings.wren_source == "local_file":
        return DataSource.local_file, {
            "url": settings.fas_data_dir,
            "format": "parquet",
        }
    if settings.wren_source == "minio_file":
        endpoint = settings.fas_s3_endpoint or ""
        endpoint = endpoint.removeprefix("http://").removeprefix("https://").rstrip("/")
        return DataSource.minio_file, {
            "url": "/",
            "format": "parquet",
            "endpoint": endpoint,
            "ssl_enabled": settings.fas_s3_ssl,
            "bucket": settings.fas_s3_bucket,
            "access_key": settings.fas_s3_access_key,
            "secret_key": settings.fas_s3_secret_key,
        }
    return DataSource.s3_file, {
        "url": "/",
        "format": "parquet",
        "bucket": settings.fas_s3_bucket,
        "region": settings.fas_s3_region,
        "access_key": settings.fas_s3_access_key,
        "secret_key": settings.fas_s3_secret_key,
    }


class EngineStartInterrupted(Exception):
    """Создание движка прервано. Ожидающие запросы могут повторить попытку."""


def _apply_limits(engine: WrenEngine, settings: Settings) -> dict:
    connector = engine._get_connector()
    connection = connector.connection
    connection.execute(f"SET memory_limit='{int(settings.wren_duckdb_memory_mb)}MB'")
    connection.execute(f"SET threads={int(settings.wren_duckdb_threads)}")
    for statement in (
        "SET enable_http_metadata_cache=true",
        "SET parquet_metadata_cache=true",
    ):
        try:
            connection.execute(statement)
        except Exception:  # noqa: BLE001, S110 — необязательный SET не должен ронять пул
            pass
    row = connection.execute(
        "SELECT current_setting('memory_limit'), current_setting('threads')"
    ).fetchone()
    return {"memory_limit": row[0], "threads": int(row[1]), "set_ok": True}


@dataclass
class _Slot:
    engine: WrenEngine
    mdl_json: str
    refs: int = 0
    waiters: int = 0
    last_used: float = field(default_factory=time.monotonic)
    limits: dict = field(default_factory=dict)
    sem: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(1))


class EnginePool:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._slots: dict[tuple, list[_Slot]] = {}
        self._inflight: dict[tuple, asyncio.Future] = {}
        self._guard = asyncio.Lock()
        self.cold_starts: list[float] = []

    def _live(self) -> list[tuple[tuple, _Slot]]:
        return [(key, slot) for key, slots in self._slots.items() for slot in slots]

    async def _evict_if_needed(self) -> None:
        live = self._live()
        if len(live) < self.settings.engine_pool_size:
            return
        now = time.monotonic()
        idle = [
            (key, slot)
            for key, slot in live
            if slot.refs == 0 and slot.waiters == 0 and now - slot.last_used >= 0
        ]
        idle.sort(key=lambda item: item[1].last_used)
        while len(self._live()) >= self.settings.engine_pool_size and idle:
            key, slot = idle.pop(0)
            if slot.refs or slot.waiters:
                continue
            self._slots[key].remove(slot)
            if not self._slots[key]:
                del self._slots[key]
            await anyio.to_thread.run_sync(slot.engine.close)

    async def lease(self, key: tuple, factory):
        async with self._guard:
            slots = self._slots.get(key, [])
            chosen = None
            for slot in slots:
                if slot.waiters < self.settings.wren_engine_queue_max:
                    chosen = slot
                    break
            if chosen is None and slots and len(slots) < self.settings.wren_engines_per_book:
                if slots[0].waiters >= self.settings.wren_hot_queue:
                    chosen = None
                else:
                    raise BookBusy("очередь движка переполнена", extra={"retry_after": 1})
            elif chosen is None and slots:
                raise BookBusy("очередь движка переполнена", extra={"retry_after": 1})
            if chosen is None:
                await self._evict_if_needed()
                future = self._inflight.get(key)
                if future is None:
                    future = asyncio.get_running_loop().create_future()
                    self._inflight[key] = future
                    created_here = True
                else:
                    created_here = False
            else:
                created_here = False
                future = None
        if chosen is None:
            if created_here:
                started = time.perf_counter()
                try:
                    slot = await factory()
                    slot.last_used = time.monotonic()
                    async with self._guard:
                        self._slots.setdefault(key, []).append(slot)
                        self._inflight.pop(key, None)
                        if not future.done():
                            future.set_result(slot)
                    self.cold_starts.append(time.perf_counter() - started)
                    chosen = slot
                except BaseException as exc:
                    task = asyncio.current_task()
                    paused = 0
                    if task is not None:
                        while task.cancelling():
                            task.uncancel()
                            paused += 1
                    try:
                        async with self._guard:
                            self._inflight.pop(key, None)
                            if future is not None and not future.done():
                                err = exc if isinstance(exc, Exception) else EngineStartInterrupted()
                                future.set_exception(err)
                                future.exception()
                    finally:
                        if task is not None:
                            for _ in range(paused):
                                task.cancel()
                    raise
            else:
                chosen = await asyncio.shield(future)
        chosen.waiters += 1
        acquired = False
        try:
            await chosen.sem.acquire()
            acquired = True
            chosen.refs += 1
        except BaseException:
            if acquired:
                chosen.sem.release()
            raise
        finally:
            chosen.waiters -= 1

        @asynccontextmanager
        async def _cm():
            try:
                yield chosen
            finally:
                chosen.refs -= 1
                chosen.last_used = time.monotonic()
                chosen.sem.release()

        return _cm()


class WrenQuery:
    def __init__(self, settings: Settings, limiter: anyio.CapacityLimiter | None = None) -> None:
        self.settings = settings
        self.pool = EnginePool(settings)
        self._limiter = limiter or anyio.CapacityLimiter(settings.wren_threads)
        self._source_name, self._source_info = _source(settings)
        self.limit_notes: dict = {}

    def mdl_for(self, job_id: str, head: dict, paths: dict[str, str]) -> dict:
        del head
        return build_mdl(job_id, paths)

    async def _create(self, job_id: str, paths: dict[str, str]) -> _Slot:
        mdl = build_mdl(job_id, paths)
        encoded = base64.b64encode(json.dumps(mdl).encode()).decode()
        source_name = self._source_name
        info = self._source_info

        def _build() -> WrenEngine:
            return WrenEngine(
                encoded,
                source_name,
                info,
                config=WrenConfig(strict_mode=True),
            )

        engine = await anyio.to_thread.run_sync(_build, limiter=self._limiter)
        try:
            notes = await anyio.to_thread.run_sync(lambda: _apply_limits(engine, self.settings))
        except Exception:
            await anyio.to_thread.run_sync(engine.close)
            raise
        self.limit_notes = notes
        return _Slot(engine=engine, mdl_json=json.dumps(mdl), limits=notes)

    async def sql(self, job_id: str, sql: str, limit: int = 5000, pin: dict | None = None) -> pa.Table:
        checked = check_job(job_id)
        if not pin or "paths" not in pin:
            raise InvalidArgument("запрос без закреплённой книги не планируется")
        key = (checked, pin.get("build_key"), pin.get("derive_key"))

        async def factory() -> _Slot:
            return await self._create(checked, pin["paths"])

        async with await self.pool.lease(key, factory) as slot:
            def _run() -> pa.Table:
                return slot.engine.query(
                    sql,
                    limit=limit,
                    properties={"session_model_id": f"'{checked}'"},
                )

            return await anyio.to_thread.run_sync(_run, limiter=self._limiter)

    async def cube(self, job_id: str, query: dict, pin: dict | None = None) -> pa.Table:
        if not pin or "paths" not in pin:
            raise InvalidArgument("запрос без закреплённой книги не планируется")
        mdl = build_mdl(job_id, pin["paths"])
        from wren_core import cube_query_to_sql

        sql = cube_query_to_sql(json.dumps(query), json.dumps(mdl))
        return await self.sql(job_id, sql, pin=pin)
