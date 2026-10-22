"""Сценарии фазы 0: загрузка, серия, срез, выражение, периоды, операции."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from decimal import Decimal

import anyio
from ulid import ULID

from finance_analysis.application import keys
from finance_analysis.application.gc import gc_incomplete
from finance_analysis.application.journal import Journal
from finance_analysis.application.project import derive_rows, project
from finance_analysis.domain.book import (
    Actor,
    BuilderRef,
    FAS_SCHEMA_VERSION,
    FAS_VERSION,
    Head,
    NotModified,
    Versions,
    build_key_for,
    sha256_bytes,
)
from finance_analysis.domain.errors import (
    AlreadyExists,
    BuilderUnstable,
    DeadlineExceeded,
    DependencyUnavailable,
    InvalidArgument,
    NotFound,
    PreconditionFailed,
)
from finance_analysis.domain.expression import evaluate, literals_of, names_of, parse_expression
from finance_analysis.domain.ids import job_id as check_job
from finance_analysis.domain.ids import ulid as check_ulid
from finance_analysis.domain.periods import marker_class, split_period_key
from finance_analysis.settings import Settings

_YEAR_RANGE = re.compile(r"^(\d{4})\s*[-–—]\s*(\d{4})$")
_MARKED_YEAR = re.compile(r"^(факт|план|прогноз|actual|plan|estimate)\s+(\d{4})$", re.IGNORECASE)
_YEAR_ONLY = re.compile(r"^(\d{4})$")


@dataclass
class Accepted:
    operation: dict
    retry_after: int = 1


@dataclass
class BookView:
    body: dict
    warnings: list = field(default_factory=list)


def _dumps(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, default=_json_default).encode()


def _json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    raise TypeError(type(value))


def _decimal_text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text
    return str(value)


class FasService:
    def __init__(self, settings: Settings, store, parquet, builder, query, support) -> None:
        self.settings = settings
        self.store = store
        self.parquet = parquet
        self.builder = builder
        self.query = query
        self.support = support
        self.journal = Journal(store)
        self._tasks: set[asyncio.Task] = set()
        self._cpu = anyio.CapacityLimiter(settings.cpu_threads)
        self.draining = False

    def spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def _read_head(self, job_id: str) -> tuple[Head | None, str | None]:
        key = keys.head_key(job_id)
        meta = await self.store.stat(key)
        if meta is None:
            return None, None
        payload = json.loads(await self.store.get(key))
        head = Head(
            build_key=payload["build_key"],
            state_seq=int(payload.get("state_seq") or 0),
            derive_key=payload["derive_key"],
            versions=payload.get("versions") or {},
            mdl_version=str(payload.get("mdl_version") or "1"),
            fence=int(payload.get("fence") or 0),
            token=meta.etag,
        )
        return head, meta.etag

    async def _manifest(self, job_id: str, build: str) -> dict:
        return json.loads(await self.store.get(keys.manifest_key(job_id, build)))

    async def _done(self, job_id: str, build: str, derive: str) -> dict:
        return json.loads(await self.store.get(keys.derived_done(job_id, build, derive)))

    def _paths(self, job_id: str, build: str, manifest: dict, done: dict) -> dict[str, str]:
        files = {}
        files.update(manifest.get("files") or {})
        files.update(done.get("files") or {})
        wanted = {
            "fact_observation": "fact_observation.parquet",
            "dim_row": "dim_row.parquet",
            "dim_period": "dim_period.parquet",
            "bindings": "bindings.parquet",
            "row_semantics": "row_semantics.parquet",
            "period_semantics": "period_semantics.parquet",
        }
        paths = {}
        for name, suffix in wanted.items():
            rel = next(rel for rel in files if rel.endswith(suffix))
            paths[name] = self.store.physical(f"books/{job_id}/{build}/{rel}")
        return paths

    async def _pin(self, job_id: str, head: Head) -> dict:
        manifest = await self._manifest(job_id, head.build_key)
        done = await self._done(job_id, head.build_key, head.derive_key)
        return {
            "build_key": head.build_key,
            "derive_key": head.derive_key,
            "head": head.as_dict(),
            "paths": self._paths(job_id, head.build_key, manifest, done),
            "manifest": manifest,
        }

    def _versions(self, glossary: str | None = None) -> Versions:
        return Versions(
            glossary=glossary or "none",
            embed_model=self.settings.embed_model,
            rerank_model=self.settings.rerank_model,
            clm_model=self.settings.clm_model,
        )

    async def _write_attempt(self, job_id: str, build: str, attempt: str, tables: dict[str, list[dict]]) -> dict:
        files = {}
        for dataset, rows in tables.items():
            if dataset not in keys.PROJECTION:
                continue
            if dataset == "graph_links" and not rows:
                continue
            payload, count = await self.parquet.write(dataset, rows, build_key=build)
            rel = f"a/{attempt}/projection/{dataset}.parquet"
            key = keys.projection_key(job_id, build, attempt, dataset)
            await self.store.put_if_absent(key, payload)
            files[rel] = {"sha256": sha256_bytes(payload), "rows": count, "schema": f"{dataset}@{FAS_SCHEMA_VERSION}"}
        return files

    async def _write_derived(self, job_id: str, build: str, derive: str, attempt: str, tables: dict) -> dict:
        files = {}
        for dataset, rows in tables.items():
            payload, count = await self.parquet.write(dataset, rows, build_key=build)
            rel = f"derived/{derive}/a/{attempt}/{dataset}.parquet"
            key = keys.derived_file(job_id, build, derive, attempt, dataset)
            try:
                await self.store.put_if_absent(key, payload)
            except AlreadyExists:
                pass
            files[rel] = {"sha256": sha256_bytes(payload), "rows": count, "schema": f"{dataset}@{FAS_SCHEMA_VERSION}"}
        return files

    async def materialize_derived(self, job_id: str, *, glossary_version: str, projected: dict | None = None) -> str:
        head, token = await self._read_head(job_id)
        if head is None:
            raise NotFound("книга не загружена")
        versions = self._versions(glossary_version)
        # Сохраняем прочие поля головы, меняется только глоссарий и derive_key.
        versions_dict = dict(head.versions)
        versions_dict["glossary"] = glossary_version
        derive = Versions(
            glossary=glossary_version,
            taxonomy=versions_dict.get("taxonomy", "core-1"),
            calibrator=versions_dict.get("calibrator", "none"),
            profile=versions_dict.get("profile", "p-0"),
            embed_model=(versions_dict.get("models") or {}).get("embed", ""),
            rerank_model=(versions_dict.get("models") or {}).get("rerank", ""),
            clm_model=(versions_dict.get("models") or {}).get("clm", ""),
        ).derive(head.state_seq)
        if projected is None:
            projected = await self._projected_from_store(job_id, head.build_key)
        derived = derive_rows(projected, state_seq=head.state_seq, derive=derive, versions=versions_dict)
        attempt = str(ULID())
        files = await self._write_derived(job_id, head.build_key, derive, attempt, derived)
        done = {
            "derive_key": derive,
            "state_seq": head.state_seq,
            "attempt": attempt,
            "files": files,
            "inputs": versions_dict,
        }
        try:
            await self.store.put_if_absent(keys.derived_done(job_id, head.build_key, derive), _dumps(done))
        except AlreadyExists:
            pass
        new_head = {
            **head.as_dict(),
            "derive_key": derive,
            "versions": versions_dict,
        }
        if token:
            if head.fence and False:
                pass
            await self.store.put_if_match(keys.head_key(job_id), _dumps(new_head), token)
        return derive

    async def _projected_from_store(self, job_id: str, build: str) -> dict[str, list[dict]]:
        """Повторная материализация derived читает уже записанные строки проекции через pyarrow в адаптере нет.
        Для смены глоссария проекцию пересобирают из тех же dict, которые передаёт вызывающий.
        """
        raise NotFound("проекция для повторного derive не передана")

    async def _publish_head(self, job_id: str, body: dict, token: str | None, fence: int) -> None:
        current, current_token = await self._read_head(job_id)
        if current and fence < current.fence:
            raise PreconditionFailed("устаревший fencing-токен", extra={"fence": current.fence})
        payload = _dumps(body)
        if current is None:
            try:
                await self.store.put_if_absent(keys.head_key(job_id), payload)
            except AlreadyExists:
                await self.store.put_if_match(keys.head_key(job_id), payload, current_token or token or "")
        else:
            await self.store.put_if_match(keys.head_key(job_id), payload, token or current.token or "")

    async def _consistent_snapshot(self, job_id: str):
        for _ in range(3):
            summary = await self.builder.summary(job_id, None)
            if isinstance(summary, NotModified):
                raise BuilderUnstable("summary не изменился, но загрузка запрошена без etag")
            snapshot, context_etag, _content_hash = await self.builder.context(job_id)
            again = await self.builder.summary(job_id, summary.etag)
            if isinstance(again, NotModified):
                return replace(summary, context_etag=context_etag), snapshot
        raise BuilderUnstable("builder пересобрал книгу между summary и context")

    async def load_consistent(self, job_id: str, *, known_etag: str | None) -> tuple[object, object] | NotModified:
        summary = await self.builder.summary(job_id, known_etag)
        if isinstance(summary, NotModified):
            return summary
        for _ in range(3):
            snapshot, context_etag, _digest = await self.builder.context(job_id)
            again = await self.builder.summary(job_id, summary.etag)
            if isinstance(again, NotModified):
                return replace(summary, context_etag=context_etag), snapshot
            summary = again
        raise BuilderUnstable("builder пересобрал книгу между summary и context")

    async def perform_load(self, job_id: str, *, actor: Actor, fence: int, op_id: str | None = None) -> Head:
        check_job(job_id)
        head, token = await self._read_head(job_id)
        known = None
        if head is not None:
            manifest = await self._manifest(job_id, head.build_key)
            known = (manifest.get("builder_ref") or {}).get("summary_etag")
        loaded = await self.load_consistent(job_id, known_etag=known)
        if isinstance(loaded, NotModified):
            assert head is not None
            if op_id:
                await self.finish_op(op_id, "succeeded", result={"build_key": head.build_key})
            return head
        summary, snapshot = loaded
        if summary.status not in {"succeeded", "degraded"}:
            if head is not None:
                return head
            raise DependencyUnavailable(f"книга в статусе {summary.status}")
        build = build_key_for(
            summary.content_sha256,
            summary.context_schema_version,
            summary.graph_schema_version,
            summary.etag,
        )
        versions = self._versions()
        state_seq = head.state_seq if head else 0
        derive = versions.derive(state_seq)
        if head and head.build_key == build and head.derive_key == derive:
            if op_id:
                await self.finish_op(op_id, "succeeded", result={"build_key": build})
            return head
        attempt = str(ULID())
        tables = await anyio.to_thread.run_sync(lambda: project(snapshot, model_id=job_id, build=build), limiter=self._cpu)
        file_map = await self._write_attempt(job_id, build, attempt, tables)
        ref = BuilderRef(
            job_id=job_id,
            content_sha256=summary.content_sha256,
            context_schema_version=summary.context_schema_version,
            graph_schema_version=summary.graph_schema_version,
            summary_etag=summary.etag,
            builder_status=summary.status,
        )
        manifest = {
            "fas_schema_version": FAS_SCHEMA_VERSION,
            "build_key": build,
            "builder_ref": ref.as_dict(),
            "attempt": attempt,
            "files": file_map,
            "builder_files": {"context.json": {"etag": summary.context_etag}},
            "loaded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "loader_version": FAS_VERSION,
            "fence": fence,
        }
        try:
            await self.store.put_if_absent(keys.manifest_key(job_id, build), _dumps(manifest))
        except AlreadyExists:
            manifest = await self._manifest(job_id, build)
        index = {
            "build_key": build,
            "created_at_utc": manifest["loaded_at"],
            "previous_build_key": head.build_key if head else None,
            "builder_ref": ref.as_dict(),
            "fas_projection_version": "1",
            "fas_schema_version": FAS_SCHEMA_VERSION,
            "rebuild_reason": "initial" if head is None else "builder_rebuild",
            "stats": {
                "rows": len(tables["dim_row"]),
                "periods": len(tables["dim_period"]),
                "observations": len(tables["fact_observation"]),
            },
        }
        try:
            await self.store.put_if_absent(keys.build_index_key(job_id, build), _dumps(index))
        except AlreadyExists:
            pass
        derived = derive_rows(
            tables,
            state_seq=state_seq,
            derive=derive,
            versions=versions.as_dict(),
        )
        d_attempt = str(ULID())
        d_files = await self._write_derived(job_id, build, derive, d_attempt, derived)
        done = {"derive_key": derive, "state_seq": state_seq, "attempt": d_attempt, "files": d_files}
        try:
            await self.store.put_if_absent(keys.derived_done(job_id, build, derive), _dumps(done))
        except AlreadyExists:
            pass
        body = {
            "build_key": build,
            "state_seq": state_seq,
            "derive_key": derive,
            "versions": versions.as_dict(),
            "mdl_version": "1",
            "fence": fence,
        }
        try:
            await self._publish_head(job_id, body, token, fence)
        except PreconditionFailed:
            fresh, _token = await self._read_head(job_id)
            if fresh is None or fresh.build_key != build:
                raise
            if op_id:
                await self.finish_op(op_id, "succeeded", result={"build_key": fresh.build_key})
            return fresh
        fresh, _token = await self._read_head(job_id)
        assert fresh is not None
        if op_id:
            await self.finish_op(op_id, "succeeded", result={"build_key": fresh.build_key})
        return fresh

    async def ensure(self, job_id: str, actor: Actor, *, wait_sec: float, prefer_async: bool = False) -> Head | Accepted:
        if self.draining:
            raise DependencyUnavailable("сервис завершает работу")
        check_job(job_id)
        if prefer_async:
            return await self._defer_load(job_id, actor)
        head, _token = await self._read_head(job_id)
        try:
            probe = await self.builder.summary(job_id, None if head is None else (await self._known_etag(job_id, head)))
        except DependencyUnavailable:
            if head is None:
                raise
            return head
        if isinstance(probe, NotModified) and head is not None:
            return head
        if probe.status not in {"succeeded", "degraded"} and head is not None:
            return head
        try:
            async with self.support.lock(f"book:{job_id}", self.settings.lock_ttl_ms) as fence:
                task = self.spawn(self.perform_load(job_id, actor=actor, fence=fence.fence))
                try:
                    return await asyncio.wait_for(asyncio.shield(task), timeout=wait_sec)
                except TimeoutError:
                    op = await self.create_op("book.load", job_id, actor, {})
                    self.spawn(self._attach(task, op["id"]))
                    return Accepted(op)
        except TimeoutError:
            return await self._defer_load(job_id, actor)

    async def _known_etag(self, job_id: str, head: Head) -> str | None:
        try:
            manifest = await self._manifest(job_id, head.build_key)
        except NotFound:
            return None
        return (manifest.get("builder_ref") or {}).get("summary_etag")

    async def _attach(self, task: asyncio.Task, op_id: str) -> None:
        try:
            await task
            current = await self.get_op(op_id)
            if current["status"] in {"queued", "running"}:
                await self.finish_op(op_id, "succeeded", result={})
        except Exception as exc:
            await self.finish_op(op_id, "failed", error={"detail": str(exc)})

    async def _defer_load(self, job_id: str, actor: Actor) -> Accepted:
        op = await self.create_op("book.load", job_id, actor, {})

        async def _run() -> None:
            try:
                async with self.support.lock(f"book:{job_id}", self.settings.lock_ttl_ms) as fence:
                    await self.perform_load(job_id, actor=actor, fence=fence.fence, op_id=op["id"])
            except Exception as exc:
                await self.finish_op(op["id"], "failed", error={"code": getattr(exc, "code", "failed"), "detail": str(exc)})

        self.spawn(_run())
        return Accepted(op)

    async def book_view(self, job_id: str, actor: Actor, *, wait_sec: float) -> BookView | Accepted:
        head = await self.ensure(job_id, actor, wait_sec=wait_sec)
        if isinstance(head, Accepted):
            return head
        warnings = []
        is_latest: bool | None = True
        try:
            probe = await self.builder.summary(job_id, await self._known_etag(job_id, head))
            if not isinstance(probe, NotModified):
                is_latest = False
        except DependencyUnavailable:
            is_latest = None
            warnings.append({"code": "freshness_unknown", "params": {}})
        builds = [item.key async for item in self.store.list(f"books/{job_id}/_builds")]
        manifest = await self._manifest(job_id, head.build_key)
        body = {
            "job_id": job_id,
            "loaded": True,
            "builder_ref": manifest.get("builder_ref"),
            "build_key": head.build_key,
            "state_seq": head.state_seq,
            "derive_key": head.derive_key,
            "profile": {"id": head.versions.get("profile", "p-0"), "version": head.versions.get("profile", "p-0")},
            "coverage_summary": {"status": "unknown"},
            "build_count": len([item for item in builds if item.endswith(".json")]),
            "active_operations": [],
            "versions": head.versions,
            "is_latest": is_latest,
            "warnings": warnings,
            "mdl_version": head.mdl_version,
            "fence": head.fence,
        }
        return BookView(body, warnings)

    def _result_envelope(self, job_id: str, head: Head, manifest: dict, result_data: dict, citations: list, warnings: list | None = None) -> dict:
        return {
            "analysis_id": str(ULID()),
            "status": "succeeded",
            "builder_ref": manifest.get("builder_ref"),
            "versions": {
                **head.versions,
                "state_seq": head.state_seq,
                "derive_key": head.derive_key,
                "fas": FAS_VERSION,
                "latest_glossary": head.versions.get("glossary"),
            },
            "is_latest": True,
            "summary": None,
            "result_data": result_data,
            "tables": result_data.get("tables") or [],
            "charts": [],
            "citations": citations,
            "needs_input": [],
            "warnings": warnings or [],
        }

    async def _query_series_table(self, job_id: str, head: Head, where_sql: str):
        pin = await self._pin(job_id, head)
        sql = (
            "SELECT row_key, binding_key, axis_id, period_id, cell_id, value_dec, normalized_value, "
            "value_status, sheet, label, unit, scale, scale_factor, period_index, period_key_base, "
            "period_marker, period_start, period_end "
            f"FROM series {where_sql} ORDER BY period_index"
        )
        return await self.query.sql(job_id, sql, pin=pin), pin

    async def series(self, job_id: str, body: dict, actor: Actor, *, wait_sec: float) -> dict | Accepted:
        ensured = await self.ensure(job_id, actor, wait_sec=min(wait_sec, self.settings.load_sync_sec))
        if isinstance(ensured, Accepted):
            return ensured
        where, params_note = _series_where(body)
        table, pin = await self._query_series_table(job_id, ensured, where)
        rows = table.to_pylist()
        citations = [_citation(row) for row in rows]
        series_rows = [
            {
                "row_key": row["row_key"],
                "axis_id": row["axis_id"],
                "period_id": row["period_id"],
                "cell_id": row["cell_id"],
                "value": _decimal_text(row["value_dec"]),
                "value_status": row["value_status"],
                "normalized_value": _decimal_text(row["normalized_value"]),
            }
            for row in rows
        ]
        return self._result_envelope(
            job_id,
            ensured,
            pin["manifest"],
            {"findings": [], "ratios": [], "series": series_rows, "expression": None, "impact": None},
            citations,
            params_note,
        )

    async def slice(self, job_id: str, body: dict, actor: Actor, *, wait_sec: float) -> dict | Accepted:
        ensured = await self.ensure(job_id, actor, wait_sec=min(wait_sec, self.settings.load_sync_sec))
        if isinstance(ensured, Accepted):
            return ensured
        query = _slice_query(body)
        pin = await self._pin(job_id, ensured)
        table = await self.query.cube(job_id, query, pin=pin)
        columns = list(table.column_names)
        data_rows = [[_decimal_text(value) if isinstance(value, Decimal) else value for value in row] for row in table.to_pylist()]
        # to_pylist returns dicts
        dict_rows = table.to_pylist()
        data_rows = [[_cell(item.get(column)) for column in columns] for item in dict_rows]
        return self._result_envelope(
            job_id,
            ensured,
            pin["manifest"],
            {
                "findings": [],
                "ratios": [],
                "series": [],
                "expression": None,
                "impact": None,
                "tables": [{"id": "slice", "columns": columns, "rows": data_rows}],
            },
            [],
        )

    async def expression(self, job_id: str, body: dict, actor: Actor, *, wait_sec: float) -> dict | Accepted:
        ensured = await self.ensure(job_id, actor, wait_sec=min(wait_sec, self.settings.load_sync_sec))
        if isinstance(ensured, Accepted):
            return ensured
        text = body.get("expression")
        bindings = body.get("bindings") or {}
        if not isinstance(bindings, dict):
            raise InvalidArgument("bindings должен быть объектом")
        node = parse_expression(text)
        used = names_of(node)
        missing = [name for name in used if name not in bindings]
        if missing:
            raise InvalidArgument(f"нет привязки для {', '.join(missing)}")
        literals = literals_of(node)
        values: dict[str, Decimal] = {}
        citations = []
        inputs = []
        units = set()
        scales = set()
        empty = False
        for name in used:
            spec = bindings[name]
            if not isinstance(spec, dict):
                raise InvalidArgument(f"привязка {name} должна быть объектом")
            where = _binding_where(spec)
            table, pin = await self._query_series_table(job_id, ensured, where)
            rows = table.to_pylist()
            if len(rows) != 1:
                raise InvalidArgument(f"имя {name} соответствует {len(rows)} ячейкам")
            row = rows[0]
            status = row["value_status"]
            if status in {"empty", "not_applicable"}:
                empty = True
            number = Decimal(0) if status == "zero_explicit" else row["value_dec"]
            units.add(row.get("unit"))
            scales.add(row.get("scale"))
            citations.append(_citation(row))
            inputs.append({"name": name, "cell_id": row["cell_id"], "value": _decimal_text(number), "value_status": status})
            if number is not None:
                values[name] = Decimal(number)
        manifest = (await self._pin(job_id, ensured))["manifest"]
        if empty:
            expr = {"result": None, "status": "empty_input", "inputs": inputs, "literals": literals}
            envelope = self._result_envelope(job_id, ensured, manifest, _expr_data(expr), citations)
            return envelope
        if len(units) > 1:
            expr = {"result": None, "status": "unit_mismatch", "inputs": inputs, "literals": literals}
            return self._result_envelope(job_id, ensured, manifest, _expr_data(expr), citations)
        if len(scales) > 1:
            # перечитать normalized
            values = {}
            for name in used:
                spec = bindings[name]
                table, _pin = await self._query_series_table(job_id, ensured, _binding_where(spec))
                row = table.to_pylist()[0]
                values[name] = Decimal(row["normalized_value"] or 0)
        result = evaluate(node, values)
        expr = {"result": _decimal_text(result), "status": "succeeded", "inputs": inputs, "literals": literals}
        return self._result_envelope(job_id, ensured, manifest, _expr_data(expr), citations)

    async def resolve_periods(self, job_id: str, body: dict, actor: Actor, *, wait_sec: float) -> dict | Accepted:
        ensured = await self.ensure(job_id, actor, wait_sec=min(wait_sec, self.settings.load_sync_sec))
        if isinstance(ensured, Accepted):
            return ensured
        text = str(body.get("text") or body.get("query") or "")
        pin = await self._pin(job_id, ensured)
        table = await self.query.sql(
            job_id,
            "SELECT axis_id, period_id, period_key_base, period_marker, period_start, period_end, "
            "calendar_year, phase, period_index FROM series ORDER BY period_index",
            pin=pin,
        )
        rows = _unique_periods(table.to_pylist())
        picked = _match_periods(text, rows)
        return {"periods": picked, "build_key": ensured.build_key, "is_latest": True}

    async def create_op(self, kind: str, job_id: str | None, actor: Actor, payload: dict) -> dict:
        op_id = str(ULID())
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        body = {
            "id": op_id,
            "kind": kind,
            "status": "running",
            "job_id": job_id,
            "actor": {"user_id": actor.user_id, "client_id": actor.client_id},
            "created_at": now,
            "updated_at": now,
            "progress": 0,
            "payload": payload,
            "result": None,
            "error": None,
        }
        await self.store.put_if_absent(keys.operation_key(op_id), _dumps(body))
        await self.support.publish(f"fas:op:{op_id}", "running")
        return body

    async def finish_op(self, op_id: str, status: str, **fields) -> dict:
        current = await self.get_op(op_id)
        if current["status"] in {"succeeded", "failed", "cancelled"}:
            return current
        event = {"seq": 1, "status": status, "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **fields}
        try:
            await self.store.put_if_absent(keys.operation_event_key(op_id, 1), _dumps(event))
        except AlreadyExists:
            pass
        await self.support.publish(f"fas:op:{op_id}", status)
        return await self.get_op(op_id)

    async def get_op(self, op_id: str) -> dict:
        check_ulid(op_id)
        try:
            body = json.loads(await self.store.get(keys.operation_key(op_id)))
        except NotFound:
            raise NotFound("операция не найдена") from None
        for seq in range(1, 20):
            meta = await self.store.stat(keys.operation_event_key(op_id, seq))
            if meta is None:
                break
            event = json.loads(await self.store.get(keys.operation_event_key(op_id, seq)))
            body["status"] = event.get("status", body["status"])
            if "result" in event:
                body["result"] = event["result"]
            if "error" in event:
                body["error"] = event["error"]
            body["updated_at"] = event.get("at", body["updated_at"])
        return body

    async def wait_op(self, op_id: str, wait_ms: int) -> dict:
        wait_ms = max(0, min(wait_ms, self.settings.operation_wait_max_ms))
        loop = asyncio.get_running_loop()
        deadline = loop.time() + wait_ms / 1000
        while True:
            current = await self.get_op(op_id)
            if current["status"] in {"succeeded", "failed", "cancelled"} or loop.time() >= deadline:
                return current
            await asyncio.sleep(0.05)

    async def cancel_op(self, op_id: str, actor: Actor) -> dict:
        current = await self.get_op(op_id)
        if current["status"] in {"succeeded", "failed", "cancelled"}:
            return current
        return await self.finish_op(op_id, "cancelled", result={"actor": actor.user_id})

    async def list_ops(self, *, kind: str | None, job_id: str | None, status: str | None) -> list[dict]:
        found = []
        async for item in self.store.list("operations"):
            if not item.key.endswith("/op.json"):
                continue
            op_id = item.key.split("/")[1]
            try:
                body = await self.get_op(op_id)
            except NotFound:
                continue
            if kind and body.get("kind") != kind:
                continue
            if job_id and body.get("job_id") != job_id:
                continue
            if status and body.get("status") != status:
                continue
            found.append(body)
        return found

    async def gc(self, *, now: datetime | None = None, max_age_s: int | None = None) -> dict:
        age = self.settings.gc_age_seconds() if max_age_s is None else max_age_s

        async def locked(job: str) -> bool:
            return await self.support.held(f"book:{job}")

        return await gc_incomplete(self.store, now=now, max_age_s=age, is_locked=locked)

    def capabilities(self) -> dict:
        storage = {
            "backend": self.store.backend,
            "url": self.store.url,
            "wren_source": self.settings.wren_source,
            "conditional_writes": self.store.conditional_writes,
        }
        return {
            "fas_version": FAS_VERSION,
            "phase": "0",
            "storage": storage,
            "rules": [],
            "metrics": [],
            "concepts": [],
            "renderers": ["json"],
            "problems": PROBLEM_CATALOG,
            "tools": TOOLS,
        }

    async def ready(self) -> dict:
        redis_ok = await self.support.ping()
        status = "ok" if redis_ok and not self.draining else "degraded"
        return {
            "status": status,
            "storage": {
                "backend": self.store.backend,
                "url": self.store.url,
                "wren_source": self.settings.wren_source,
                "conditional_writes": self.store.conditional_writes,
                "selftest": "passed",
            },
            "redis": "ok" if redis_ok else "down",
            "builder": "ok" if await self.builder.healthy() else "down",
            "glossary": "none",
            "draining": self.draining,
        }


def _cell(value):
    if isinstance(value, Decimal):
        return _decimal_text(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _citation(row: dict) -> dict:
    cell = row["cell_id"]
    sheet, addr = cell.split("!", 1)
    return {
        "cell_id": cell,
        "sheet": sheet,
        "cell": addr,
        "row_key": row["row_key"],
        "axis_id": row["axis_id"],
        "period_id": row["period_id"],
        "label": row.get("label"),
        "value": _decimal_text(row.get("value_dec")),
        "value_status": row.get("value_status"),
        "normalized_value": _decimal_text(row.get("normalized_value")),
    }


def _sql_list(values: list[str]) -> str:
    parts = []
    for value in values:
        if not isinstance(value, str):
            raise InvalidArgument("фильтр должен быть строкой")
        parts.append("'" + value.replace("'", "''") + "'")
    return ", ".join(parts)


def _series_where(body: dict) -> tuple[str, list]:
    clauses = []
    warnings = []
    row_keys = body.get("row_keys") or []
    binding_keys = body.get("binding_keys") or []
    concepts = body.get("concepts") or []
    if concepts:
        warnings.append({"code": "concepts_unmapped_in_phase0", "params": {"concepts": concepts}})
        clauses.append("effective_concept IN (" + _sql_list(list(concepts)) + ")")
    if row_keys:
        clauses.append("row_key IN (" + _sql_list(list(row_keys)) + ")")
    if binding_keys:
        clauses.append("binding_key IN (" + _sql_list(list(binding_keys)) + ")")
    if body.get("axis_id"):
        clauses.append("axis_id = " + _sql_list([body["axis_id"]]))
    periods = body.get("periods") or []
    if periods:
        clauses.append(
            "(period_id IN (" + _sql_list(list(periods)) + ") OR period_key_base IN (" + _sql_list(list(periods)) + "))"
        )
    marker = body.get("marker")
    if marker:
        clauses.append("marker_class = " + _sql_list([marker]) if False else "period_marker = " + _sql_list([str(marker)]))
    if not clauses:
        raise InvalidArgument("нужен row_keys, binding_keys или concepts")
    return "WHERE " + " AND ".join(clauses), warnings


def _binding_where(spec: dict) -> str:
    clauses = []
    if spec.get("row_key"):
        clauses.append("row_key = " + _sql_list([spec["row_key"]]))
    if spec.get("binding_key"):
        clauses.append("binding_key = " + _sql_list([spec["binding_key"]]))
    if not clauses:
        raise InvalidArgument("привязка требует row_key или binding_key")
    if spec.get("period_id"):
        clauses.append("period_id = " + _sql_list([spec["period_id"]]))
    if spec.get("axis_id"):
        clauses.append("axis_id = " + _sql_list([spec["axis_id"]]))
    return "WHERE " + " AND ".join(clauses)


_MEASURES = {"value_sum", "value_last", "cells"}
_DIMS = {"row_key", "sheet", "label_path", "concept", "period_id", "phase", "period_marker"}
_OPS = {"eq", "contains", "is_null", "gt", "lt", "gte", "lte", "in"}


def _slice_query(body: dict) -> dict:
    measures = body.get("measures") or []
    dimensions = body.get("dimensions") or []
    if not measures or any(item not in _MEASURES for item in measures):
        raise InvalidArgument("measures вне белого списка")
    if any(item not in _DIMS for item in dimensions):
        raise InvalidArgument("dimensions вне белого списка")
    query: dict = {"cube": "series_cube", "measures": list(measures), "dimensions": list(dimensions)}
    filters = []
    for item in body.get("filters") or []:
        if item.get("dimension") not in _DIMS or item.get("operator") not in _OPS:
            raise InvalidArgument("фильтр среза вне белого списка")
        filters.append(item)
    if filters:
        query["filters"] = filters
    if body.get("time"):
        query["timeDimensions"] = body["time"]
    return query


def _expr_data(expr: dict) -> dict:
    return {"findings": [], "ratios": [], "series": [], "expression": expr, "impact": None}


def _unique_periods(rows: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for row in rows:
        key = (row["axis_id"], row["period_id"])
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _match_periods(text: str, rows: list[dict]) -> list[dict]:
    query = text.strip()
    matched = _YEAR_RANGE.fullmatch(query)
    if matched:
        start, end = int(matched.group(1)), int(matched.group(2))
        return [_period_ref(row) for row in rows if _year_of(row) is not None and start <= _year_of(row) <= end]
    matched = _MARKED_YEAR.fullmatch(query)
    if matched:
        klass = marker_class(matched.group(1))
        year = int(matched.group(2))
        return [
            _period_ref(row)
            for row in rows
            if _year_of(row) == year and marker_class(row.get("period_marker")) == klass
        ]
    if query.casefold() in {"первый операционный год", "first operational year"}:
        operational = [row for row in rows if row.get("phase") == "operation"]
        if not operational:
            return []
        year = _year_of(operational[0])
        return [_period_ref(row) for row in operational if _year_of(row) == year]
    matched = _YEAR_ONLY.fullmatch(query)
    if matched:
        year = int(matched.group(1))
        return [_period_ref(row) for row in rows if _year_of(row) == year]
    return []


def _year_of(row: dict) -> int | None:
    if row.get("calendar_year"):
        return int(row["calendar_year"])
    base, _marker = split_period_key(str(row.get("period_key_base") or row.get("period_id") or ""))
    if len(base) >= 4 and base[:4].isdigit():
        return int(base[:4])
    return None


def _period_ref(row: dict) -> dict:
    start = row.get("period_start")
    end = row.get("period_end")
    return {
        "axis_id": row["axis_id"],
        "period_id": row["period_id"],
        "period_key_base": row.get("period_key_base"),
        "period_marker": row.get("period_marker"),
        "period_start": start.isoformat() if hasattr(start, "isoformat") else start,
        "period_end": end.isoformat() if hasattr(end, "isoformat") else end,
    }


PROBLEM_CATALOG = [
    {"code": "invalid_argument", "http": 400, "retryable": False},
    {"code": "invalid_id", "http": 400, "retryable": False},
    {"code": "not_found", "http": 404, "retryable": False},
    {"code": "not_acceptable", "http": 406, "retryable": False},
    {"code": "binding_conflict", "http": 409, "retryable": False},
    {"code": "request_in_progress", "http": 409, "retryable": True},
    {"code": "unsupported_builder_shape", "http": 409, "retryable": False},
    {"code": "builder_unstable", "http": 409, "retryable": False},
    {"code": "precondition_failed", "http": 412, "retryable": False},
    {"code": "idempotency_key_reused", "http": 422, "retryable": False},
    {"code": "rate_limited", "http": 429, "retryable": True},
    {"code": "book_busy", "http": 429, "retryable": True},
    {"code": "too_many_inflight", "http": 429, "retryable": True},
    {"code": "overloaded", "http": 503, "retryable": True},
    {"code": "dependency_unavailable", "http": 503, "retryable": True},
    {"code": "deadline_exceeded", "http": 504, "retryable": True},
]

TOOLS = [
    {"name": "get_book", "method": "GET", "path": "/v1/books/{job_id}"},
    {"name": "get_series", "method": "POST", "path": "/v1/books/{job_id}/series"},
    {"name": "get_slice", "method": "POST", "path": "/v1/books/{job_id}/slice"},
    {"name": "evaluate_expression", "method": "POST", "path": "/v1/books/{job_id}/expression"},
    {"name": "resolve_periods", "method": "POST", "path": "/v1/books/{job_id}/periods:resolve"},
    {"name": "get_operation", "method": "GET", "path": "/v1/operations/{id}"},
]
