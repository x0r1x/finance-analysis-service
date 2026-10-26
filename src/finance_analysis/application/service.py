"""Сценарии фаз 0–1: загрузка, серия, срез, выражение, периоды, операции, аудит."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

import anyio
from ulid import ULID

from finance_analysis.application import keys
from finance_analysis.application.analyses import Analyses
from finance_analysis.application.builds import (
    index_document,
    projection_of,
    rebuild_reason,
)
from finance_analysis.application.catalog import load_catalog
from finance_analysis.application.gc import gc_incomplete
from finance_analysis.application.glossary_store import GlossaryStore
from finance_analysis.application.metrics import BUILDER_INCONSISTENT
from finance_analysis.application.operations import append_event, create_op, read_op
from finance_analysis.application.project import derive_rows, project
from finance_analysis.application.semantic_guard import SemanticWriteGuard
from finance_analysis.domain.book import (
    FAS_PROJECTION_VERSION,
    FAS_SCHEMA_VERSION,
    FAS_VERSION,
    SEP,
    Actor,
    BuilderRef,
    Head,
    NotModified,
    ReportNotReady,
    Summary,
    Versions,
    WorkbookSnapshot,
    build_key_for,
    publication_aligned,
    sha256_bytes,
    with_links,
)
from finance_analysis.domain.errors import (
    AlreadyExists,
    BuilderUnstable,
    DependencyUnavailable,
    InvalidArgument,
    NotFound,
    PreconditionFailed,
)
from finance_analysis.domain.expression import (
    evaluate,
    literals_of,
    names_of,
    parse_expression,
)
from finance_analysis.domain.glossary_release import package_of
from finance_analysis.domain.ids import job_id as check_job
from finance_analysis.domain.ids import ulid as check_ulid
from finance_analysis.domain.operational_year import resolve_operational_year
from finance_analysis.domain.periods import marker_class, split_period_key
from finance_analysis.domain.phases import phase_target, split_phase_target
from finance_analysis.domain.state import fold
from finance_analysis.settings import Settings

_YEAR_RANGE = re.compile(r"^(\d{4})\s*[-–—]\s*(\d{4})$")
_MARKED_YEAR = re.compile(r"^(факт|план|прогноз|actual|plan|estimate)\s+(\d{4})$", re.IGNORECASE)
_YEAR_ONLY = re.compile(r"^(\d{4})$")


@dataclass
class Accepted:
    operation: dict
    retry_after: int = 1


class _LockTimeout(Exception):
    """Замок книги не взят за отведённое время."""


@dataclass
class BookView:
    body: dict
    warnings: list = field(default_factory=list)


@dataclass
class Freshness:
    """Текущая сборка есть или её нет. ETag не сохранялся, свежесть неизвестна."""

    head: Head | None


def _dumps(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, default=_json_default).encode()


def _json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    raise TypeError(type(value))


_DECISION_KINDS = {
    "phase.set": "phase.set",
    "concept.set": "concept.set",
    "concept.confirm": "concept.confirmed",
    "concept.reject": "concept.rejected",
    "concept.ignore": "concept.ignored",
    "concept.absent": "concept.absent",
    "sign.set": "sign.set",
    "unit.set": "unit.set",
    "profile.set": "profile.set",
}
_BOOK_KINDS = frozenset({"concept.absent", "profile.set"})
_CONCEPT_VALUE = frozenset({"concept.set", "concept.confirmed", "concept.rejected", "concept.absent"})


def _rejected(index: int, code: str, detail: str) -> dict:
    return {
        "index": index,
        "status": "rejected",
        "record_seq": None,
        "duplicate": False,
        "errors": [{"code": code, "message": detail}],
        "warnings": [],
    }


def _decision_targets(periods: list[dict], rows: list[dict]) -> frozenset[str]:
    targets = {row["binding_key"] for row in rows if row.get("binding_key")}
    for period in periods:
        base = period.get("period_key_base") or period.get("period_id")
        if period.get("axis_id") and base:
            targets.add(phase_target(period["axis_id"], base))
    return frozenset(targets)


def _concept_taken(events: list[dict], target: str, concept: str) -> bool:
    for other, event in fold(events).items():
        binding = str(event.get("binding_key") or other)
        if binding == target:
            continue
        if event.get("type") in {"concept.set", "concept.confirmed"} and event.get("value") == concept:
            return True
    return False


def _phase_order(periods: list[dict], events: list[dict], target: str, value) -> list[tuple[int, str]] | None:
    parsed = split_phase_target(target)
    if parsed is None or not isinstance(value, str):
        return None
    axis_id, base = parsed
    current: dict[str, str] = {}
    for other, event in fold(events).items():
        if event.get("type") != "phase.set":
            continue
        found = split_phase_target(str(other))
        if found and found[0] == axis_id and isinstance(event.get("value"), str):
            current[found[1]] = event["value"]
    current[base] = value
    indexes: dict[str, int] = {}
    for period in periods:
        if period.get("axis_id") != axis_id:
            continue
        key = period.get("period_key_base") or period.get("period_id")
        index = int(period["period_index"])
        indexes[key] = min(indexes.get(key, index), index)
    if base not in indexes:
        return None
    return [(indexes[key], phase) for key, phase in current.items() if key in indexes]


def _builder_warnings(manifest: dict) -> list[dict]:
    warnings = []
    for message in manifest.get("builder_warnings") or []:
        warnings.append({"code": "builder_warning", "params": {"message": str(message)}})
    for item in manifest.get("warnings") or []:
        if isinstance(item, dict) and item.get("code"):
            warnings.append(item)
    return warnings


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
        self.catalog = load_catalog()
        self.guard = SemanticWriteGuard(store, catalog=self.catalog.ids)
        self.glossary = GlossaryStore(store, support, lock_ttl_ms=settings.lock_ttl_ms)
        self.fold_runs = 0
        self._fold_locks: dict[str, asyncio.Lock] = {}
        self._tasks: set[asyncio.Task] = set()
        self._cpu = anyio.CapacityLimiter(settings.cpu_threads)
        self.draining = False
        self.glossary_seen = ""
        self.analyses = Analyses(self)

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

    async def _dataset_rows(self, job_id: str, head: Head, dataset: str) -> list[dict]:
        suffix = f"{dataset}.parquet"
        if dataset in keys.PROJECTION:
            files = (await self._manifest(job_id, head.build_key)).get("files") or {}
        else:
            files = (await self._done(job_id, head.build_key, head.derive_key)).get("files") or {}
        rel = next(item for item in files if str(item).endswith("/" + suffix) or str(item).endswith(suffix))
        raw = await self.store.get(f"books/{job_id}/{head.build_key}/{rel}")
        return await self.parquet.read(raw)

    async def _versions_for(self, head: Head | None, events: list[dict]) -> Versions:
        current_g = head.versions.get("glossary", "none") if head else "none"
        current_p = head.versions.get("profile", "p-0") if head else "p-0"
        base = self._versions(None if current_g == "none" else current_g)
        return Versions(
            glossary=base.glossary,
            taxonomy=base.taxonomy,
            calibrator=base.calibrator,
            profile=await self._profile_version(events, current_p),
            embed_model=base.embed_model,
            rerank_model=base.rerank_model,
            clm_model=base.clm_model,
        )

    async def _profile_version(self, events: list[dict], current: str) -> str:
        chosen = None
        for event in fold(events).values():
            if event.get("type") == "profile.set" and isinstance(event.get("value"), str):
                chosen = event["value"]
        if not chosen:
            return current
        ref = await self.glossary.profile_ref(chosen)
        return ref or current

    async def _package_for(self, version: str):
        if not version or version == "none" or not str(version).startswith("g-"):
            return self.catalog
        try:
            return package_of(await self.glossary.document(version))
        except NotFound:
            return self.catalog

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
            files[rel] = {
                "sha256": sha256_bytes(payload),
                "rows": count,
                "bytes": len(payload),
                "schema": await self.parquet.schema_tag(dataset),
            }
        return files

    async def materialize_derived(self, job_id: str, *, glossary_version: str, projected: dict | None = None) -> str:
        head, token = await self._read_head(job_id)
        if head is None:
            raise NotFound("книга не загружена")
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
        events = await self.guard.read_all(job_id)
        derived = derive_rows(
            projected,
            state_seq=head.state_seq,
            derive=derive,
            versions=versions_dict,
            events=events,
            glossary=await self._package_for(glossary_version),
            facts=None if projected is None else projected.get("fact_observation"),
        )
        attempt = str(ULID())
        files = await self.guard.persist_derived(
            job_id=job_id,
            build=head.build_key,
            derive=derive,
            attempt=attempt,
            tables=derived,
            parquet=self.parquet,
            row_keys=frozenset(row["row_key"] for row in projected["dim_row"]),
        )
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

    async def _aligned_snapshot(self, job_id: str, etag: str) -> WorkbookSnapshot:
        for _ in range(3):
            context = await self.builder.context(job_id)
            if isinstance(context, ReportNotReady):
                continue
            links = await self.builder.graph(job_id)
            if isinstance(links, ReportNotReady):
                continue
            probed = await self.builder.head_summary(job_id, etag)
            if not isinstance(probed, NotModified):
                continue
            snapshot = with_links(context, links)
            if publication_aligned(snapshot):
                return snapshot
        BUILDER_INCONSISTENT.inc()
        raise BuilderUnstable("context.json и graph.json не согласованы")

    async def load_consistent(self, job_id: str, *, known_etag: str | None):
        summary = await self.builder.summary(job_id, known_etag)
        if not isinstance(summary, Summary) or summary.status != "succeeded":
            return summary
        snapshot = await self._aligned_snapshot(job_id, summary.etag)
        return summary, snapshot

    async def perform_load(
        self,
        job_id: str,
        *,
        actor: Actor,
        fence: int,
        op_id: str | None = None,
        summary: Summary | None = None,
    ) -> Head:
        check_job(job_id)
        head, token = await self._read_head(job_id)
        if summary is None:
            known = None if head is None else await self._known_etag(job_id, head)
            loaded = await self.load_consistent(job_id, known_etag=known)
            if isinstance(loaded, NotModified):
                assert head is not None
                if op_id:
                    await self.finish_op(op_id, "succeeded", result={"build_key": head.build_key})
                return head
            if not isinstance(loaded, tuple):
                if head is not None:
                    if op_id:
                        await self.finish_op(op_id, "succeeded", result={"build_key": head.build_key})
                    return head
                raise NotFound("книга не загружена")
            summary, snapshot = loaded
        else:
            snapshot = await self._aligned_snapshot(job_id, summary.etag)
        build = build_key_for(job_id, summary.etag, FAS_PROJECTION_VERSION)
        events = await self.guard.read_all(job_id)
        versions = await self._versions_for(head, events)
        state_seq = int(events[-1]["seq"]) if events else (head.state_seq if head else 0)
        derive = versions.derive(state_seq)
        if head and head.build_key == build and head.derive_key == derive:
            if op_id:
                await self.finish_op(op_id, "succeeded", result={"build_key": build})
            return head
        attempt = str(ULID())

        def _project():
            return project(snapshot, model_id=job_id, build=build)

        tables, projection_warnings = await anyio.to_thread.run_sync(_project, limiter=self._cpu)
        file_map = await self._write_attempt(job_id, build, attempt, tables)
        ref = BuilderRef(
            job_id=job_id,
            summary_etag=summary.etag,
            context_schema_version=summary.context_schema_version,
            graph_schema_version=summary.graph_schema_version,
        )
        manifest = {
            "fas_schema_version": FAS_SCHEMA_VERSION,
            "fas_projection_version": FAS_PROJECTION_VERSION,
            "build_key": build,
            "builder_ref": ref.as_dict(),
            "attempt": attempt,
            "files": file_map,
            "builder_warnings": [str(item) for item in summary.warnings],
            "builder_counters": summary.counters,
            "warnings": projection_warnings,
            "loaded_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "loader_version": FAS_VERSION,
            "fence": fence,
        }
        try:
            await self.store.put_if_absent(keys.manifest_key(job_id, build), _dumps(manifest))
        except AlreadyExists:
            manifest = await self._manifest(job_id, build)
        previous_manifest = None
        if head is not None:
            try:
                previous_manifest = await self._manifest(job_id, head.build_key)
            except NotFound:
                previous_manifest = None
        reason = rebuild_reason(previous_manifest, ref, projection=FAS_PROJECTION_VERSION)
        index = index_document(
            build,
            {**manifest, "files": {**manifest.get("files", {}), **file_map}},
            previous=head.build_key if head else None,
            reason=reason,
            projection=FAS_PROJECTION_VERSION,
        )
        fresh_stats = index["stats"]
        fresh_stats["rows"] = len(tables["dim_row"])
        fresh_stats["periods"] = len(tables["dim_period"])
        fresh_stats["observations"] = len(tables["fact_observation"])
        try:
            await self.store.put_if_absent(keys.build_index_key(job_id, build), _dumps(index))
        except AlreadyExists:
            pass
        derived = derive_rows(
            tables,
            state_seq=state_seq,
            derive=derive,
            versions=versions.as_dict(),
            events=events,
            glossary=await self._package_for(versions.glossary),
            facts=tables.get("fact_observation"),
        )
        d_attempt = str(ULID())
        d_files = await self.guard.persist_derived(
            job_id=job_id,
            build=build,
            derive=derive,
            attempt=d_attempt,
            tables=derived,
            parquet=self.parquet,
            row_keys=frozenset(row["row_key"] for row in tables["dim_row"]),
        )
        done = {"derive_key": derive, "state_seq": state_seq, "attempt": d_attempt, "files": d_files}
        try:
            await self.store.put_if_absent(keys.derived_done(job_id, build, derive), _dumps(done))
        except AlreadyExists:
            pass
        await self.glossary.note_bindings(job_id, derived["bindings"])
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

    async def ensure(
        self, job_id: str, actor: Actor, *, wait_sec: float, prefer_async: bool = False
    ) -> Head | Accepted | Freshness:
        if self.draining:
            raise DependencyUnavailable("сервис завершает работу")
        check_job(job_id)
        if prefer_async:
            return await self._defer_load(job_id, actor)
        head, _token = await self._read_head(job_id)
        known = None if head is None else await self._known_etag(job_id, head)
        try:
            probe = await self.builder.summary(job_id, known)
        except DependencyUnavailable:
            return Freshness(head)
        if isinstance(probe, NotModified) and head is not None:
            return head
        if isinstance(probe, ReportNotReady) or not isinstance(probe, Summary) or probe.status != "succeeded":
            return Freshness(head)
        task = self.spawn(self._load_under_lock(job_id, actor, probe))
        try:
            return await asyncio.wait_for(asyncio.shield(task), timeout=wait_sec)
        except TimeoutError:
            if not task.done():
                op = await self.create_op("book.load", job_id, actor, {})
                self.spawn(self._attach(task, op["id"]))
                return Accepted(op)
            if task.cancelled():
                raise
            exc = task.exception()
            if isinstance(exc, _LockTimeout):
                return await self._defer_load(job_id, actor)
            if exc is not None:
                raise exc
            return task.result()

    async def _load_under_lock(self, job_id: str, actor: Actor, probe: Summary):
        try:
            async with self.support.lock(f"book:{job_id}", self.settings.lock_ttl_ms) as fence:
                return await self.perform_load(job_id, actor=actor, fence=fence.fence, summary=probe)
        except TimeoutError as exc:
            raise _LockTimeout(job_id) from exc

    async def _known_etag(self, job_id: str, head: Head) -> str | None:
        """ETag для `If-None-Match`. Сборка старой проекции его не получает.

        Иначе builder ответит `304`, и сборка не перестроится, хотя версия
        проекции сменилась (§4.10). Manifest без поля — проекция 1.
        """

        try:
            manifest = await self._manifest(job_id, head.build_key)
        except NotFound:
            return None
        if projection_of(manifest) != FAS_PROJECTION_VERSION:
            return None
        return (manifest.get("builder_ref") or {}).get("summary_etag")

    async def _attach(self, task: asyncio.Task, op_id: str) -> None:
        try:
            await task
            current = await self.get_op(op_id)
            if current["status"] in {"queued", "running"}:
                await self.finish_op(op_id, "succeeded", result={})
        except Exception as exc:  # noqa: BLE001 — любая ошибка фоновой задачи закрывает операцию
            await self.finish_op(op_id, "failed", error={"detail": str(exc)})

    async def _defer_load(self, job_id: str, actor: Actor) -> Accepted:
        op = await self.create_op("book.load", job_id, actor, {})

        async def _run() -> None:
            try:
                async with self.support.lock(f"book:{job_id}", self.settings.lock_ttl_ms) as fence:
                    await self.perform_load(job_id, actor=actor, fence=fence.fence, op_id=op["id"])
            except Exception as exc:  # noqa: BLE001 — любая ошибка отложенной загрузки закрывает операцию
                await self.finish_op(op["id"], "failed", error={"code": getattr(exc, "code", "failed"), "detail": str(exc)})

        self.spawn(_run())
        return Accepted(op)

    async def book_view(
        self,
        job_id: str,
        actor: Actor,
        *,
        wait_sec: float,
        min_state_seq: int | None = None,
    ) -> BookView | Accepted:
        ensured = await self.ensure(job_id, actor, wait_sec=wait_sec)
        if isinstance(ensured, Accepted):
            return ensured
        fresh = isinstance(ensured, Freshness)
        head = ensured.head if fresh else ensured
        if min_state_seq is not None and (head is None or head.state_seq < min_state_seq):
            op = await self.create_op("book.read", job_id, actor, {"min_state_seq": min_state_seq})
            return Accepted(op)
        return await self.describe(job_id, head, fresh=fresh)

    async def describe(self, job_id: str, head: Head | None, *, fresh: bool) -> BookView:
        if head is None:
            return BookView(
                {
                    "job_id": job_id,
                    "loaded": False,
                    "builder_ref": None,
                    "build_key": None,
                    "state_seq": None,
                    "derive_key": None,
                    "profile": None,
                    "coverage_summary": {"status": "unknown"},
                    "build_count": 0,
                    "active_operations": [],
                    "versions": {},
                    "is_latest": None,
                    "warnings": [{"code": "freshness_unknown", "params": {}}],
                    "mdl_version": None,
                    "fence": None,
                }
            )
        warnings = [{"code": "freshness_unknown", "params": {}}] if fresh else []
        builds = [item.key async for item in self.store.list(f"books/{job_id}/_builds")]
        manifest = await self._manifest(job_id, head.build_key)
        warnings.extend(_builder_warnings(manifest))
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
            "is_latest": None if fresh else True,
            "warnings": warnings,
            "mdl_version": head.mdl_version,
            "fence": head.fence,
        }
        body.update(await self._coverage_public(job_id, head))
        return BookView(body, warnings)

    async def _coverage_public(self, job_id: str, head: Head) -> dict:
        try:
            bindings = await self._dataset_rows(job_id, head, "bindings")
        except (NotFound, StopIteration):
            bindings = []
        counts: dict[str, int] = {}
        critical_unknown = 0
        for row in bindings:
            status = str(row.get("status") or "unknown")
            counts[status] = counts.get(status, 0) + 1
            if status == "unknown" and row.get("importance") == "critical":
                critical_unknown += 1
        # shortcut: глубина critical/component не обходится, covered = 1 пока нет critical
        covered = 1.0 if critical_unknown == 0 else 0.0
        return {
            "row_coverage": counts,
            "critical_path": {"covered": covered},
            "critical_unknown": critical_unknown,
        }

    def _result_envelope(
        self,
        job_id: str,
        head: Head,
        manifest: dict,
        result_data: dict,
        citations: list,
        warnings: list | None = None,
        *,
        is_latest: bool | None = True,
    ) -> dict:
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
            "is_latest": is_latest,
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
        head, fresh = _serve(ensured)
        if head is None:
            return _unloaded_analysis()
        where, params_note = _series_where(body)
        table, pin = await self._query_series_table(job_id, head, where)
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
        notes = (_freshness_warning() if fresh else []) + params_note
        return self._result_envelope(
            job_id,
            head,
            pin["manifest"],
            {"findings": [], "ratios": [], "series": series_rows, "expression": None, "impact": None},
            citations,
            notes,
            is_latest=None if fresh else True,
        )

    async def slice(self, job_id: str, body: dict, actor: Actor, *, wait_sec: float) -> dict | Accepted:
        ensured = await self.ensure(job_id, actor, wait_sec=min(wait_sec, self.settings.load_sync_sec))
        if isinstance(ensured, Accepted):
            return ensured
        head, fresh = _serve(ensured)
        if head is None:
            return _unloaded_analysis()
        query = _slice_query(body)
        pin = await self._pin(job_id, head)
        table = await self.query.cube(job_id, query, pin=pin)
        columns = list(table.column_names)
        data_rows = [[_decimal_text(value) if isinstance(value, Decimal) else value for value in row] for row in table.to_pylist()]
        # to_pylist returns dicts
        dict_rows = table.to_pylist()
        data_rows = [[_cell(item.get(column)) for column in columns] for item in dict_rows]
        return self._result_envelope(
            job_id,
            head,
            pin["manifest"],
            {
                "findings": [],
                "ratios": [],
                "series": [],
                "expression": None,
                "impact": None,
                "tables": [{"id": "slice", "columns": columns, "rows": data_rows}],
            },
            _freshness_warning() if fresh else [],
            is_latest=None if fresh else True,
        )

    async def expression(self, job_id: str, body: dict, actor: Actor, *, wait_sec: float) -> dict | Accepted:
        ensured = await self.ensure(job_id, actor, wait_sec=min(wait_sec, self.settings.load_sync_sec))
        if isinstance(ensured, Accepted):
            return ensured
        head, fresh = _serve(ensured)
        if head is None:
            return _unloaded_analysis()
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
            table, _pin = await self._query_series_table(job_id, head, where)
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
        manifest = (await self._pin(job_id, head))["manifest"]
        notes = _freshness_warning() if fresh else []
        latest = None if fresh else True
        if empty:
            expr = {"result": None, "status": "empty_input", "inputs": inputs, "literals": literals}
            return self._result_envelope(job_id, head, manifest, _expr_data(expr), citations, notes, is_latest=latest)
        if len(units) > 1:
            expr = {"result": None, "status": "unit_mismatch", "inputs": inputs, "literals": literals}
            return self._result_envelope(job_id, head, manifest, _expr_data(expr), citations, notes, is_latest=latest)
        if len(scales) > 1:
            values = {}
            for name in used:
                spec = bindings[name]
                table, _pin = await self._query_series_table(job_id, head, _binding_where(spec))
                row = table.to_pylist()[0]
                values[name] = Decimal(row["normalized_value"] or 0)
        result = evaluate(node, values)
        expr = {"result": _decimal_text(result), "status": "succeeded", "inputs": inputs, "literals": literals}
        return self._result_envelope(job_id, head, manifest, _expr_data(expr), citations, notes, is_latest=latest)

    async def submit_decisions(
        self,
        job_id: str,
        body: dict,
        actor: Actor,
        *,
        wait_sec: float,
        if_match: str | None = None,
    ) -> dict | Accepted:
        ensured = await self.ensure(job_id, actor, wait_sec=min(wait_sec, self.settings.load_sync_sec))
        if isinstance(ensured, Accepted):
            return ensured
        async with self.support.lock(f"book:{job_id}", self.settings.lock_ttl_ms):
            head, _token = await self._read_head(job_id)
            if head is None:
                raise NotFound("книга не загружена")
            if if_match:
                token_h = if_match.strip().strip('"')
                if token_h != f"s-{head.state_seq}":
                    raise PreconditionFailed(
                        "If-Match не совпал",
                        extra={"state_seq": head.state_seq, "etag": f"s-{head.state_seq}"},
                    )
            result = await self._apply_decisions(job_id, head, body, actor)
            pending = bool(result["records"])
        if pending:
            head = await self._fold_coalesced(job_id)
        result["pending_state_seq"] = head.state_seq
        return result

    async def _fold_coalesced(self, job_id: str) -> Head:
        lock = self._fold_locks.setdefault(job_id, asyncio.Lock())
        await asyncio.sleep(0)
        async with lock, self.support.lock(f"book:{job_id}", self.settings.lock_ttl_ms) as held:
            head, token = await self._read_head(job_id)
            if head is None:
                raise NotFound("книга не загружена")
            return await self._fold_derived(job_id, head, token, held.fence)

    async def _apply_decisions(self, job_id: str, head: Head, body: dict, actor: Actor) -> dict:
        items = body.get("decisions")
        if items is None and body.get("kind"):
            items = [body]
        if not isinstance(items, list):
            raise InvalidArgument("decisions должен быть списком")
        periods = await self._dataset_rows(job_id, head, "dim_period")
        rows = await self._dataset_rows(job_id, head, "dim_row")
        known = _decision_targets(periods, rows)
        events = await self.guard.read_all(job_id)
        results = []
        records = []
        seen_concepts: set[str] = set()
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                results.append(_rejected(index, "schema_invalid", "элемент не объект"))
                continue
            kind = item.get("kind")
            event_type = _DECISION_KINDS.get(kind)
            if event_type is None:
                results.append(_rejected(index, "schema_invalid", "неизвестный вид решения"))
                continue
            target = item.get("target")
            if event_type in _BOOK_KINDS and (not isinstance(target, str) or not target):
                target = "book"
            if not isinstance(target, str) or not target:
                results.append(_rejected(index, "schema_invalid", "нет цели"))
                continue
            concept = item.get("value") if event_type in _CONCEPT_VALUE else None
            if event_type in _CONCEPT_VALUE and not isinstance(concept, str):
                results.append(_rejected(index, "schema_invalid", "понятие должно быть строкой"))
                continue
            if event_type == "sign.set" and item.get("value") not in {"inflow", "outflow"}:
                results.append(_rejected(index, "schema_invalid", "знак должен быть inflow или outflow"))
                continue
            if isinstance(concept, str) and concept in seen_concepts and event_type in {"concept.set", "concept.confirmed"}:
                results.append(_rejected(index, "duplicate_in_batch", "понятие повторяется в пакете"))
                continue
            taken = False
            if isinstance(concept, str) and event_type in {"concept.set", "concept.confirmed"}:
                taken = _concept_taken(events, target, concept)
                seen_concepts.add(concept)
            order = None
            if event_type == "phase.set":
                order = _phase_order(periods, events, target, item.get("value"))
            supersedes = item.get("supersedes") if isinstance(item.get("supersedes"), dict) else None
            written = await self.guard.write_decision(
                job_id,
                event_type=event_type,
                target=target,
                value=item.get("value"),
                actor=actor,
                expected_seq=item.get("expected_seq"),
                request_id=f"{actor.user_id}:{index}:{target}:{event_type}:{item.get('value')}",
                concept=concept if isinstance(concept, str) else None,
                known_targets=known | {"book"} if event_type in _BOOK_KINDS else known,
                phase_order=order,
                concept_taken=taken,
                binding_key=None if target == "book" else target,
                supersedes=supersedes,
            )
            if not written.accepted:
                results.append(_rejected(index, written.code or "schema_invalid", written.detail))
                continue
            if isinstance(concept, str) or event_type == "phase.set":
                events = await self.guard.read_all(job_id)
            record = written.event or {}
            records.append(record)
            results.append(
                {
                    "index": index,
                    "status": "accepted",
                    "record_seq": record.get("seq"),
                    "duplicate": written.duplicate,
                    "errors": [],
                    "warnings": [],
                }
            )
        return {"results": results, "records": records}

    async def _fold_derived(self, job_id: str, head: Head, token: str | None, fence: int) -> Head:
        events = await self.guard.read_all(job_id)
        state_seq = int(events[-1]["seq"]) if events else head.state_seq
        versions = await self._versions_for(head, events)
        derive = versions.derive(state_seq)
        if state_seq == head.state_seq and derive == head.derive_key:
            return head
        projected = {
            "dim_row": await self._dataset_rows(job_id, head, "dim_row"),
            "dim_period": await self._dataset_rows(job_id, head, "dim_period"),
        }
        facts = await self._dataset_rows(job_id, head, "fact_observation")
        derived = derive_rows(
            projected,
            state_seq=state_seq,
            derive=derive,
            versions=versions.as_dict(),
            events=events,
            glossary=await self._package_for(versions.glossary),
            facts=facts,
        )
        attempt = str(ULID())
        files = await self.guard.persist_derived(
            job_id=job_id,
            build=head.build_key,
            derive=derive,
            attempt=attempt,
            tables=derived,
            parquet=self.parquet,
            row_keys=frozenset(row["row_key"] for row in projected["dim_row"]),
        )
        done = {"derive_key": derive, "state_seq": state_seq, "attempt": attempt, "files": files}
        try:
            await self.store.put_if_absent(keys.derived_done(job_id, head.build_key, derive), _dumps(done))
        except AlreadyExists:
            pass
        body = {**head.as_dict(), "derive_key": derive, "state_seq": state_seq, "versions": versions.as_dict()}
        await self._publish_head(job_id, body, token, fence)
        await self.glossary.note_bindings(job_id, derived["bindings"])
        self.fold_runs += 1
        fresh, _token = await self._read_head(job_id)
        return fresh or head

    async def resolve_periods(self, job_id: str, body: dict, actor: Actor, *, wait_sec: float) -> dict | Accepted:
        ensured = await self.ensure(job_id, actor, wait_sec=min(wait_sec, self.settings.load_sync_sec))
        if isinstance(ensured, Accepted):
            return ensured
        head, fresh = _serve(ensured)
        text = str(body.get("text") or body.get("query") or "")
        if text.strip().casefold() in {"первый операционный год", "first operational year"}:
            if head is None:
                resolved = {
                    "periods": [],
                    "needs_input": [
                        {"kind": "concept", "reason": "concept_unknown", "subject": "debt_service"}
                    ],
                }
            else:
                resolved = resolve_operational_year(
                    await self._dataset_rows(job_id, head, "dim_period"),
                    await self._dataset_rows(job_id, head, "period_semantics"),
                    await self._dataset_rows(job_id, head, "bindings"),
                    await self._dataset_rows(job_id, head, "fact_observation"),
                    events=await self.guard.read_all(job_id),
                )
            payload = {
                **resolved,
                "build_key": None if head is None else head.build_key,
                "is_latest": None if fresh or head is None else True,
            }
            if fresh:
                payload["warnings"] = _freshness_warning()
            return payload
        if head is None:
            return {
                "periods": [],
                "build_key": None,
                "is_latest": None,
                "warnings": _freshness_warning(),
            }
        pin = await self._pin(job_id, head)
        table = await self.query.sql(
            job_id,
            "SELECT axis_id, period_id, period_key_base, period_marker, period_start, period_end, "
            "calendar_year, phase, period_index FROM series ORDER BY period_index",
            pin=pin,
        )
        rows = _unique_periods(table.to_pylist())
        picked = _match_periods(text, rows)
        payload = {"periods": picked, "build_key": head.build_key, "is_latest": None if fresh else True}
        if fresh:
            payload["warnings"] = _freshness_warning()
        return payload

    async def create_op(self, kind: str, job_id: str | None, actor: Actor, payload: dict) -> dict:
        body = await create_op(self.store, kind, job_id, actor, payload)
        await self.support.publish(f"fas:op:{body['id']}", "running")
        return body

    async def finish_op(self, op_id: str, status: str, **fields) -> dict:
        current = await self.get_op(op_id)
        if current["status"] in {"succeeded", "failed", "cancelled"}:
            return current
        await append_event(self.store, op_id, {"status": status, **fields})
        await self.support.publish(f"fas:op:{op_id}", status)
        return await self.get_op(op_id)

    async def get_op(self, op_id: str) -> dict:
        check_ulid(op_id)
        try:
            return await read_op(self.store, op_id)
        except NotFound:
            raise NotFound("операция не найдена") from None

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
        await self.support.cache_set(f"fas:op:{op_id}:cancel", b"1", 86_400)
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

    async def list_builds(self, job_id: str, *, page_size: int = 50, page_token: str | None = None) -> dict:
        prefix = f"books/{check_job(job_id)}/_builds/"
        records = []
        async for item in self.store.list(prefix):
            if not item.key.endswith(".json"):
                continue
            records.append(json.loads(await self.store.get(item.key)))
        records.sort(key=lambda row: (row.get("created_at_utc") or "", row.get("build_key") or ""), reverse=True)
        head, _token = await self._read_head(job_id)
        current = head.build_key if head else None
        views = []
        for record in records:
            view = dict(record)
            view["current"] = record.get("build_key") == current
            views.append(view)
        start = 0
        if page_token:
            identifiers = [row.get("build_key") for row in views]
            if page_token not in identifiers:
                raise InvalidArgument("неизвестный page_token")
            start = identifiers.index(page_token) + 1
        page = views[start : start + page_size]
        next_token = None
        if page and start + page_size < len(views):
            next_token = page[-1]["build_key"]
        return {"items": page, "next_page_token": next_token}

    async def get_build(self, job_id: str, build: str) -> dict:
        try:
            index = json.loads(await self.store.get(keys.build_index_key(job_id, build)))
        except NotFound:
            raise NotFound("сборка не найдена") from None
        manifest = await self._manifest(job_id, build)
        derived = []
        async for item in self.store.list(f"books/{job_id}/{build}/derived/"):
            if not item.key.endswith("/_done.json"):
                continue
            body = json.loads(await self.store.get(item.key))
            derived.append({"derive_key": body.get("derive_key"), "state_seq": body.get("state_seq")})
        analyses = []
        async for item in self.store.list(f"books/{job_id}/{build}/results/"):
            if item.key.endswith("/result.json") or item.key.endswith("/_done.json"):
                analyses.append({"key": item.key})
        head, _token = await self._read_head(job_id)
        index = dict(index)
        index["current"] = bool(head and head.build_key == build)
        return {"index": index, "manifest": manifest, "derived": derived, "analyses": analyses}

    async def gc(self, *, now: datetime | None = None, max_age_s: int | None = None) -> dict:
        age = self.settings.gc_age_seconds() if max_age_s is None else max_age_s

        async def locked(job: str) -> bool:
            return await self.support.held(f"book:{job}")

        return await gc_incomplete(self.store, now=now, max_age_s=age, is_locked=locked)

    async def list_decisions(self, job_id: str, *, page_size: int = 50, page_token: str | None = None) -> dict:
        if page_size < 1 or page_size > 1000:
            raise InvalidArgument("page_size должен быть от 1 до 1000")
        events = await self.guard.read_all(job_id)
        start = int(page_token) if page_token else 0
        page = events[start : start + page_size]
        nxt = str(start + page_size) if start + page_size < len(events) else None
        return {"items": page, "next_page_token": nxt}

    async def _head_ready(self, job_id: str, actor: Actor, wait_sec: float) -> Head | Accepted:
        ensured = await self.ensure(job_id, actor, wait_sec=min(wait_sec, self.settings.load_sync_sec))
        if isinstance(ensured, Accepted):
            return ensured
        head = ensured.head if isinstance(ensured, Freshness) else ensured
        if head is None:
            raise NotFound("книга не загружена")
        return head

    async def _rows_or_accepted(self, job_id: str, head: Head, dataset: str, actor: Actor, kind: str):
        try:
            return await self._dataset_rows(job_id, head, dataset)
        except (NotFound, StopIteration):
            op = await self.create_op(kind, job_id, actor, {"dataset": dataset})
            return Accepted(op)

    async def semantics_view(self, job_id: str, actor: Actor, *, wait_sec: float) -> dict | Accepted:
        head = await self._head_ready(job_id, actor, wait_sec)
        if isinstance(head, Accepted):
            return head
        rows = await self._rows_or_accepted(job_id, head, "row_semantics", actor, "semantics")
        if isinstance(rows, Accepted):
            return rows
        periods = await self._dataset_rows(job_id, head, "dim_period")
        try:
            semantics = await self._dataset_rows(job_id, head, "period_semantics")
        except (NotFound, StopIteration):
            semantics = []
        phase_of = {(row["axis_id"], row["period_id"]): row.get("phase") for row in semantics}
        return {
            "build_key": head.build_key,
            "rows": rows,
            "periods": [
                {
                    "axis_id": row["axis_id"],
                    "period_id": row["period_id"],
                    "marker_class": row.get("marker_class"),
                    "phase": phase_of.get((row["axis_id"], row["period_id"])),
                }
                for row in periods
            ],
        }

    async def mapping_view(self, job_id: str, actor: Actor, *, wait_sec: float) -> dict | Accepted:
        head = await self._head_ready(job_id, actor, wait_sec)
        if isinstance(head, Accepted):
            return head
        rows = await self._rows_or_accepted(job_id, head, "bindings", actor, "mapping")
        if isinstance(rows, Accepted):
            return rows
        counts: dict[str, int] = {}
        for row in rows:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        return {"build_key": head.build_key, "rows": rows, "counts": counts}

    async def questions_view(self, job_id: str, actor: Actor, *, wait_sec: float) -> dict | Accepted:
        mapped = await self.mapping_view(job_id, actor, wait_sec=wait_sec)
        if isinstance(mapped, Accepted):
            return mapped
        questions = []
        for row in mapped["rows"]:
            if row.get("status") != "unknown" or row.get("source") == "confirmed":
                continue
            kind, subject, scope = "concept", row["binding_key"], job_id
            digest = hashlib.sha1(SEP.join([kind, subject, scope]).encode()).hexdigest()
            questions.append(
                {
                    "question_id": digest,
                    "kind": kind,
                    "subject": subject,
                    "scope": scope,
                    "reason": "concept_unknown",
                    "candidates": [],
                }
            )
        return {"questions": questions[:], "build_key": mapped["build_key"]}

    async def coverage_view(self, job_id: str, actor: Actor, *, wait_sec: float) -> dict | Accepted:
        head = await self._head_ready(job_id, actor, wait_sec)
        if isinstance(head, Accepted):
            return head
        rows = await self._rows_or_accepted(job_id, head, "coverage", actor, "coverage")
        if isinstance(rows, Accepted):
            return rows
        public = await self._coverage_public(job_id, head)
        return {"build_key": head.build_key, "rows": rows, **public}

    async def infer_mapping(self, job_id: str, actor: Actor) -> Accepted:
        op = await self.create_op("mapping.infer", job_id, actor, {})
        self.spawn(self._infer_mapping(op["id"], job_id))
        return Accepted(op)

    async def _infer_mapping(self, op_id: str, job_id: str) -> None:
        try:
            async with self.support.lock(f"book:{job_id}", self.settings.lock_ttl_ms) as held:
                head, token = await self._read_head(job_id)
                if head is None:
                    await self.finish_op(op_id, "failed", error={"detail": "книга не загружена"})
                    return
                fresh = await self._fold_derived(job_id, head, token, held.fence)
            await self.finish_op(
                op_id,
                "succeeded",
                result={"build_key": fresh.build_key, "derive_key": fresh.derive_key},
            )
        except Exception as exc:  # noqa: BLE001 — любая ошибка прогона закрывает операцию
            await self.finish_op(op_id, "failed", error={"detail": str(exc)})

    async def catch_glossary(self, version: str) -> bool:
        if _glossary_seq(version) <= _glossary_seq(self.glossary_seen):
            return False
        await self.remap_glossary()
        self.glossary_seen = version
        return True

    async def remap_glossary(self) -> dict:
        state = await self.glossary.ensure()
        version = state["active"]
        package_of(await self.glossary.document(version))
        changed = []
        for job_id in await self.glossary.jobs():
            async with self.support.lock(f"book:{job_id}", self.settings.lock_ttl_ms) as held:
                head, token = await self._read_head(job_id)
                if head is None:
                    continue
                pinned = {**head.as_dict(), "versions": {**head.versions, "glossary": version}}
                await self._publish_head(job_id, pinned, token, held.fence)
                head, token = await self._read_head(job_id)
                if head is None:
                    continue
                await self._fold_derived(job_id, head, token, held.fence)
            changed.append(job_id)
        self.glossary_seen = version
        return {"jobs": changed, "glossary": version}

    def capabilities(self) -> dict:
        storage = {
            "backend": self.store.backend,
            "url": self.store.url,
            "wren_source": self.settings.wren_source,
            "conditional_writes": self.store.conditional_writes,
        }
        return {
            "fas_version": FAS_VERSION,
            "phase": "2",
            "storage": storage,
            "rules": self.analyses.capabilities(),
            "metrics": ["dscr", "icr"],
            "concepts": sorted(self.catalog.ids),
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
            "builder": await self.builder.breaker_state(),
            "glossary": (await self.glossary.peek() or {}).get("active") or "none",
            "draining": self.draining,
        }


def _glossary_seq(version: str) -> int:
    if not version.startswith("g-"):
        return 0
    number = version[2:].split(":", 1)[0]
    return int(number) if number.isdigit() else 0


def _serve(ensured: Head | Freshness) -> tuple[Head | None, bool]:
    if isinstance(ensured, Freshness):
        return ensured.head, True
    return ensured, False


def _freshness_warning() -> list[dict]:
    return [{"code": "freshness_unknown", "params": {}}]


def _unloaded_analysis() -> dict:
    return {
        "analysis_id": str(ULID()),
        "status": "succeeded",
        "builder_ref": None,
        "versions": {"fas": FAS_VERSION},
        "is_latest": None,
        "summary": None,
        "result_data": {
            "findings": [],
            "ratios": [],
            "series": [],
            "expression": None,
            "impact": None,
            "tables": [],
        },
        "tables": [],
        "charts": [],
        "citations": [],
        "needs_input": [],
        "warnings": _freshness_warning(),
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
    {"code": "no_audit", "http": 404, "retryable": False},
    {"code": "not_acceptable", "http": 406, "retryable": False},
    {"code": "binding_conflict", "http": 409, "retryable": False},
    {"code": "request_in_progress", "http": 409, "retryable": True},
    {"code": "unsupported_builder_shape", "http": 409, "retryable": False},
    {"code": "builder_unstable", "http": 409, "retryable": False},
    {"code": "precondition_required", "http": 428, "retryable": False},
    {"code": "precondition_failed", "http": 412, "retryable": False},
    {"code": "admin_token_required", "http": 403, "retryable": False},
    {"code": "stale_parent", "http": 409, "retryable": False},
    {"code": "proposal_decided", "http": 409, "retryable": False},
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
    {"name": "list_builds", "method": "GET", "path": "/v1/books/{job_id}/builds"},
    {"name": "get_build", "method": "GET", "path": "/v1/books/{job_id}/builds/{build_key}"},
    {"name": "get_series", "method": "POST", "path": "/v1/books/{job_id}/series"},
    {"name": "get_slice", "method": "POST", "path": "/v1/books/{job_id}/slice"},
    {"name": "evaluate_expression", "method": "POST", "path": "/v1/books/{job_id}/expression"},
    {"name": "resolve_periods", "method": "POST", "path": "/v1/books/{job_id}/periods:resolve"},
    {"name": "submit_decisions", "method": "POST", "path": "/v1/books/{job_id}/decisions"},
    {"name": "run_analysis", "method": "POST", "path": "/v1/books/{job_id}/analyses"},
    {"name": "list_analyses", "method": "GET", "path": "/v1/books/{job_id}/analyses"},
    {"name": "get_analysis", "method": "GET", "path": "/v1/books/{job_id}/analyses/{analysis_id}"},
    {"name": "list_findings", "method": "GET", "path": "/v1/books/{job_id}/findings"},
    {"name": "explain_finding", "method": "GET", "path": "/v1/books/{job_id}/findings/{fingerprint}"},
    {"name": "get_operation", "method": "GET", "path": "/v1/operations/{id}"},
]
