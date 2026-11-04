"""Сценарии фаз 0–1: загрузка, серия, срез, выражение, периоды, операции, аудит."""

from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import anyio
from ulid import ULID

from finance_analysis.application import keys
from finance_analysis.application.analyses import RATIO_METRICS, Analyses
from finance_analysis.application.builds import (
    index_document,
    projection_of,
    rebuild_reason,
)
from finance_analysis.application.calibrators import CalibratorStore
from finance_analysis.application.catalog import load_catalog, load_identities
from finance_analysis.application.compare import Comparisons
from finance_analysis.application.evaluation import Evaluator
from finance_analysis.application.examples import ExampleStore
from finance_analysis.application.gc import gc_incomplete
from finance_analysis.application.glossary_store import GlossaryStore, state_of
from finance_analysis.application.learning import Learning
from finance_analysis.application.mapping_pipeline import MappingPipeline
from finance_analysis.application.metrics import (
    BUILDER_INCONSISTENT,
    GLOSSARY_AUTO_ROLLBACK,
    GLOSSARY_REVIEW_OPEN,
    GLOSSARY_UNKNOWN_SHARE,
)
from finance_analysis.application.model_types import load_model_types
from finance_analysis.application.operations import append_event, create_op, read_op
from finance_analysis.application.ports import Models
from finance_analysis.application.project import derive_rows, prepare_rows, project
from finance_analysis.application.semantic_guard import SemanticWriteGuard
from finance_analysis.application.sheet_roles import sheet_roles_version
from finance_analysis.application.tools import build_tools
from finance_analysis.domain.book import (
    FAS_PROJECTION_VERSION,
    FAS_SCHEMA_VERSION,
    FAS_VERSION,
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
    question_digest,
    sha256_bytes,
    with_links,
)
from finance_analysis.domain.calibration import Calibrator
from finance_analysis.domain.deadline import bind_request_deadline, effective
from finance_analysis.domain.errors import (
    AlreadyExists,
    BuilderUnstable,
    DependencyUnavailable,
    FasError,
    GlossaryBusy,
    Interrupted,
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
from finance_analysis.domain.glossary import normalize_label, with_profile
from finance_analysis.domain.glossary_release import (
    glossary_for_job,
    package_of,
    summarize_stats,
)
from finance_analysis.domain.ids import job_id as check_job
from finance_analysis.domain.ids import ulid as check_ulid
from finance_analysis.domain.mapping import decide
from finance_analysis.domain.metrics import _primaries
from finance_analysis.domain.model_type import (
    assignment_error,
    contradicts_signals,
    decision_labels,
    infer,
)
from finance_analysis.domain.model_type import (
    effective as model_type_effective,
)
from finance_analysis.domain.operational_year import resolve_operational_year
from finance_analysis.domain.periods import marker_class, split_period_key
from finance_analysis.domain.phases import phase_target, split_phase_target
from finance_analysis.domain.questions import concept_questions, question_id_problem
from finance_analysis.domain.signals import lf_accuracy
from finance_analysis.domain.state import fold
from finance_analysis.settings import Settings

LOG = logging.getLogger("fas.service")
_YEAR_RANGE = re.compile(r"^(\d{4})\s*[-–—]\s*(\d{4})$")
_MARKED_YEAR = re.compile(r"^(факт|план|прогноз|actual|plan|estimate)\s+(\d{4})$", re.IGNORECASE)
_YEAR_ONLY = re.compile(r"^(\d{4})$")


@dataclass
class Accepted:
    operation: dict
    retry_after: int = 1


def _operation_problem(exc: BaseException) -> dict:
    """Собирает тело ошибки операции в той же форме, что ответ problem+json.

    `exc` — исключение, которым завершился фоновый шаг. Если это ошибка
    домена, словарь получает поля `type`, `title`, `status`, `detail`,
    `code`, `retryable` и дополнительные поля исключения. Для любого другого
    исключения остаются `code` со значением `failed` и текст ошибки.
    Вызывающий код записывает словарь в поле `error` операции со статусом
    `failed`.
    """

    if not isinstance(exc, FasError):
        return {"code": "failed", "detail": str(exc)}
    body = {
        "type": f"urn:fas:problem:{exc.code}",
        "title": exc.title,
        "status": exc.status,
        "detail": exc.detail,
        "code": exc.code,
        "retryable": exc.retryable,
    }
    for key, value in exc.extra.items():
        if key not in body:
            body[key] = value
    return body


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
    "model_type.set": "model_type.set",
}
_BOOK_KINDS = frozenset({"concept.absent", "profile.set", "model_type.set"})
_CONCEPT_VALUE = frozenset({"concept.set", "concept.confirmed", "concept.rejected", "concept.absent"})


def _model_type_seq(events: list[dict]) -> int:
    found = 0
    for event in fold(events).values():
        if event.get("type") == "model_type.set" and isinstance(event.get("seq"), int):
            found = int(event["seq"])
    return found


def _model_type_value(events: list[dict]) -> dict | None:
    for event in fold(events).values():
        if event.get("type") == "model_type.set" and isinstance(event.get("value"), dict):
            return {**event["value"], "seq": event.get("seq")}
    return None


def _acked(item: dict, code: str) -> bool:
    acks = item.get("warnings_ack")
    return item.get("confirm") is True and isinstance(acks, list) and code in acks


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
    for event in fold(events).values():
        if event.get("type") != "phase.set":
            continue
        found = split_phase_target(str(event.get("target") or ""))
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
    def __init__(
        self,
        settings: Settings,
        store,
        parquet,
        builder,
        query,
        support,
        *,
        models: Models | None = None,
        vector_index=None,
        cluster=None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.parquet = parquet
        self.builder = builder
        self.query = query
        self.support = support
        self.catalog = load_catalog()
        self.model_types = load_model_types(concepts=self.catalog.ids)
        self.sheet_roles_version = sheet_roles_version()
        self.guard = SemanticWriteGuard(
            store,
            catalog=self.catalog.ids,
            model_types=self.model_types.ids,
            max_labels=settings.model_type_max_labels,
        )
        self.glossary = GlossaryStore(store, support, lock_ttl_ms=settings.lock_ttl_ms)
        self.fold_runs = 0
        self._fold_locks: dict[str, asyncio.Lock] = {}
        self._tasks: set[asyncio.Task] = set()
        self._cpu = anyio.CapacityLimiter(settings.cpu_threads)
        self.draining = False
        self.instance_id = str(ULID())
        self._owner_held = False
        self.jobs = None
        self.glossary_seen = ""
        self.analyses = Analyses(self)
        self.compare = Comparisons(self.analyses)
        self.models = models or Models()
        self.examples = ExampleStore(
            store, parquet, vector_index, model=settings.embed_model if self.models.embed else "", refresh_sec=settings.examples_refresh_sec
        )
        self.calibrators = CalibratorStore(store)
        self.pipeline = MappingPipeline(self.models, self.examples, support, settings=settings)
        self.learning = Learning(store, parquet, self.glossary, self.examples, self.models, cluster, settings)
        self.identities = load_identities()
        self.evaluator = Evaluator(self)
        self.glossary.gate = self.evaluator.shadow
        self.glossary.canary_share = settings.glossary_canary_share
        self.learning.calibrators = self.calibrators
        self.learning.recal_gate = self._calibrator_ok
        self.learning.on_release = self.begin_remap

    def spawn(self, coro) -> asyncio.Task:
        # Фоновая работа не наследует дедлайн запроса, который её запустил.
        context = contextvars.copy_context()
        context.run(bind_request_deadline, None)
        task = asyncio.create_task(coro, context=context)
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

    async def _use_active_catalog(self) -> None:
        state = await self.glossary.peek()
        version = (state or {}).get("active")
        ids = self.catalog.ids
        if version and str(version).startswith("g-"):
            try:
                ids = package_of(await self.glossary.document(version)).ids
            except NotFound:
                pass
        self.guard._catalog = frozenset(ids)

    async def _versions_for(self, head: Head | None, events: list[dict], job_id: str | None = None) -> Versions:
        current_g = head.versions.get("glossary", "none") if head else "none"
        if current_g in (None, "", "none"):
            state = await self.glossary.peek()
            chosen = glossary_for_job(state, job_id) if state and job_id else (state or {}).get("active")
            if chosen:
                current_g = chosen
        current_p = head.versions.get("profile", "p-0") if head else "p-0"
        await self.calibrators.active()
        base = self._versions(None if current_g == "none" else current_g)
        return Versions(
            glossary=base.glossary,
            taxonomy=base.taxonomy,
            calibrator=base.calibrator,
            profile=await self._profile_version(events, current_p),
            embed_model=base.embed_model,
            rerank_model=base.rerank_model,
            clm_model=base.clm_model,
            model_types=self.model_types.version,
            model_type_seq=_model_type_seq(events),
            sheet_roles=self.sheet_roles_version,
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

    async def _book_package(self, version: str, events: list[dict]):
        package = await self._package_for(version)
        profile = _profile_name(events)
        if not profile or not str(version or "").startswith("g-"):
            return package
        try:
            return with_profile(package, await self.glossary.document(version), profile)
        except NotFound:
            return package

    def _versions(self, glossary: str | None = None) -> Versions:
        return Versions(
            glossary=glossary or "none",
            calibrator=self.calibrators.version,
            embed_model=self.settings.embed_model,
            rerank_model=self.settings.rerank_model,
            clm_model=self.settings.clm_model,
            model_types=self.model_types.version,
            sheet_roles=self.sheet_roles_version,
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
        events = await self.guard.read_all(job_id)
        versions_dict["model_types"] = versions_dict.get("model_types") or self.model_types.version
        versions_dict["model_type_seq"] = _model_type_seq(events)
        versions_dict["sheet_roles"] = versions_dict.get("sheet_roles") or self.sheet_roles_version
        derive = Versions(
            glossary=glossary_version,
            taxonomy=versions_dict.get("taxonomy", "core-1"),
            calibrator=versions_dict.get("calibrator", "none"),
            profile=versions_dict.get("profile", "p-0"),
            embed_model=(versions_dict.get("models") or {}).get("embed", ""),
            rerank_model=(versions_dict.get("models") or {}).get("rerank", ""),
            clm_model=(versions_dict.get("models") or {}).get("clm", ""),
            model_types=versions_dict.get("model_types") or self.model_types.version,
            model_type_seq=_model_type_seq(events),
            sheet_roles=versions_dict["sheet_roles"],
        ).derive(head.state_seq)
        if projected is None:
            projected = await self._projected_from_store(job_id, head.build_key)
        derived = await self._derive(
            job_id,
            projected,
            state_seq=head.state_seq,
            derive=derive,
            versions=versions_dict,
            events=events,
            facts=projected.get("fact_observation"),
            links=projected.get("graph_links"),
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

    async def derive_for_build(self, job_id: str, head: Head, build: str) -> str:
        """Производное состояние прошлой сборки на текущем `state_seq` (§3.2 «Выбор сборки»).

        Подтверждения хранятся по `binding_key`, поэтому журнал книги
        применяется к строкам той сборки. `derive_key` от сборки не зависит:
        папка `derived/{derive_key}` пишется в каталог прошлой сборки,
        `_head.json` не меняется.
        """

        past = Head(
            build_key=build,
            state_seq=head.state_seq,
            derive_key=head.derive_key,
            versions=head.versions,
            mdl_version=head.mdl_version,
            fence=head.fence,
        )
        projected = {
            "dim_row": await self._dataset_rows(job_id, past, "dim_row"),
            "dim_period": await self._dataset_rows(job_id, past, "dim_period"),
        }
        facts = await self._dataset_rows(job_id, past, "fact_observation")
        events = [event for event in await self.guard.read_all(job_id) if int(event["seq"]) <= head.state_seq]
        derived = await self._derive(
            job_id,
            projected,
            state_seq=head.state_seq,
            derive=head.derive_key,
            versions=dict(head.versions),
            events=events,
            facts=facts,
            links=None,
            learn=False,
        )
        attempt = str(ULID())
        files = await self.guard.persist_derived(
            job_id=job_id,
            build=build,
            derive=head.derive_key,
            attempt=attempt,
            tables=derived,
            parquet=self.parquet,
            row_keys=frozenset(row["row_key"] for row in projected["dim_row"]),
        )
        done = {"derive_key": head.derive_key, "state_seq": head.state_seq, "attempt": attempt, "files": files}
        try:
            await self.store.put_if_absent(keys.derived_done(job_id, build, head.derive_key), _dumps(done))
        except AlreadyExists:
            pass
        return head.derive_key

    async def _derive(
        self,
        job_id: str,
        projected: dict,
        *,
        state_seq: int,
        derive: str,
        versions: dict,
        events: list[dict],
        facts: list[dict] | None,
        links: list[dict] | None,
        learn: bool = True,
    ) -> dict[str, list[dict]]:
        """Привязка книги: правила + стадии моделей (§5.5). Сбор сигналов и unknown-строк — в фоне.

        `learn=False` — свёртка на прошлой сборке: сигналы этой сборки уже собраны при её загрузке.
        """

        package = await self._book_package(versions.get("glossary", "none"), events)
        calibrator = await self.calibrators.active()
        prepared = prepare_rows(projected, events, package, facts)
        scored = None
        if self.pipeline.enabled:
            scored = await self.pipeline.score(
                job_id,
                derive,
                prepared,
                package,
                glossary_version=versions.get("glossary", "none"),
                deadline=effective(self.settings.mapping_deadline_ms),
                skip=_human_keys(events),
                calibrator=calibrator,
            )
        derived = derive_rows(
            projected,
            state_seq=state_seq,
            derive=derive,
            versions=versions,
            events=events,
            glossary=package,
            facts=facts,
            evidence=None if scored is None else scored.evidence,
            calibrator=calibrator,
            prepared=prepared,
        )
        if not learn:
            return derived
        nearest = {}
        if scored is not None:
            for key, found in scored.evidence.items():
                ranked = sorted((c for c in found.candidates if c.recall_cos is not None), key=lambda c: -(c.recall_cos or 0))
                nearest[key] = ranked[0].concept if ranked else None
        self.spawn(
            self._after_derive(
                job_id,
                prepared=prepared,
                bindings=derived["bindings"],
                facts=facts or [],
                links=links or [],
                embeddings={} if scored is None else scored.embeddings,
                nearest=nearest,
                package=package,
                versions=versions,
                events=events,
            )
        )
        return derived

    async def _after_derive(self, job_id: str, *, versions: dict, events: list[dict], **kwargs) -> None:
        try:
            await self.learning.after_derive(
                job_id,
                glossary_version=versions.get("glossary", "none"),
                profile=_profile_id(events),
                identities=self.identities,
                **kwargs,
            )
        except Exception:
            LOG.exception("after_derive %s", job_id)

    async def settle(self) -> None:
        """Дождаться фоновых задач (тесты, drain)."""

        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

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
                fresh = await self._fold_derived(job_id, head, token, fence)
                if op_id:
                    await self.finish_op(
                        op_id,
                        "succeeded",
                        result={"build_key": fresh.build_key, "derive_key": fresh.derive_key},
                    )
                return fresh
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
        versions = await self._versions_for(head, events, job_id)
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
        derived = await self._derive(
            job_id,
            tables,
            state_seq=state_seq,
            derive=derive,
            versions=versions.as_dict(),
            events=events,
            facts=tables.get("fact_observation"),
            links=tables.get("graph_links"),
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
            if await self._current_derive(job_id, head) == head.derive_key:
                return head
            task = self.spawn(self._rederive_under_lock(job_id))
        elif isinstance(probe, ReportNotReady) or not isinstance(probe, Summary) or probe.status != "succeeded":
            return Freshness(head)
        else:
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

    async def _current_derive(self, job_id: str, head: Head) -> str:
        events = await self.guard.read_all(job_id)
        versions = await self._versions_for(head, events, job_id)
        state_seq = int(events[-1]["seq"]) if events else head.state_seq
        return versions.derive(state_seq)

    async def _rederive_under_lock(self, job_id: str) -> Head:
        try:
            async with self.support.lock(f"book:{job_id}", self.settings.lock_ttl_ms) as fence:
                head, token = await self._read_head(job_id)
                if head is None:
                    raise NotFound("книга не загружена")
                return await self._fold_derived(job_id, head, token, fence.fence)
        except TimeoutError as exc:
            raise _LockTimeout(job_id) from exc

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
            self.spawn(self._record_decisions(job_id, head, list(result["records"])))
            head = await self._fold_coalesced(job_id)
        result["pending_state_seq"] = head.state_seq
        return result

    async def _record_decisions(self, job_id: str, head: Head, records: list[dict]) -> None:
        """Решения людей → сигналы S и examples/ по привязкам той сборки, на которой решали (§4.5)."""

        try:
            rows = {row["binding_key"]: row for row in await self._dataset_rows(job_id, head, "dim_row")}
            try:
                bindings = {row["binding_key"]: row for row in await self._dataset_rows(job_id, head, "bindings")}
            except (NotFound, StopIteration):
                bindings = {}
            events = await self.guard.read_all(job_id)
            version = head.versions.get("glossary", "none")
            await self.learning.record_decisions(
                job_id,
                records,
                rows=rows,
                bindings=bindings,
                events=events,
                profile=_profile_id(events),
                glossary_version=version,
                package=await self._book_package(version, events),
            )
        except Exception:
            LOG.exception("record_decisions %s", job_id)

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
        followed: dict[tuple[str, str], int] = {}
        await self._use_active_catalog()
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
            seq = supersedes.get("seq") if supersedes else None
            if supersedes is not None and "seq" in supersedes and (isinstance(seq, bool) or not isinstance(seq, int)):
                supersedes = None
            if event_type == "model_type.set":
                problem = assignment_error(
                    item.get("value"),
                    known=self.model_types.ids,
                    max_labels=self.settings.model_type_max_labels,
                )
                if problem:
                    results.append(_rejected(index, problem[0], problem[1]))
                    continue
                previous = _model_type_value(events)
                if previous and (not supersedes or supersedes.get("seq") != previous.get("seq")):
                    results.append(_rejected(index, "supersede_required", "тип модели уже задан"))
                    continue
                guessed = await self._type_guess(job_id, head)
                if contradicts_signals(guessed.scores, str(item["value"]["primary"])) and not _acked(
                    item, "model_type_contradicts_signals"
                ):
                    results.append(
                        {
                            "index": index,
                            "status": "needs_confirm",
                            "record_seq": None,
                            "duplicate": False,
                            "errors": [],
                            "warnings": [
                                {
                                    "code": "model_type_contradicts_signals",
                                    "requires_confirm": True,
                                    "params": {"scores": guessed.scores, "primary": item["value"]["primary"]},
                                }
                            ],
                        }
                    )
                    continue
                if supersedes and item.get("expected_seq") is None:
                    item = {**item, "expected_seq": supersedes.get("seq")}
            slot = (target, event_type)
            expected = followed[slot] if slot in followed else item.get("expected_seq")
            given_id = item.get("question_id")
            id_problem = question_id_problem(event_type, item.get("value"), job_id, given_id)
            if id_problem:
                results.append(_rejected(index, "schema_invalid", id_problem))
                continue
            written = await self.guard.write_decision(
                job_id,
                event_type=event_type,
                target=target,
                value=item.get("value"),
                actor=actor,
                expected_seq=expected,
                request_id=f"{actor.user_id}:{index}:{target}:{event_type}:{item.get('value')}",
                concept=concept if isinstance(concept, str) else None,
                known_targets=known | {"book"} if event_type in _BOOK_KINDS else known,
                phase_order=order,
                concept_taken=taken,
                binding_key=None if target == "book" else target,
                supersedes=supersedes,
                question_id=given_id if isinstance(given_id, str) else None,
            )
            if not written.accepted:
                results.append(_rejected(index, written.code or "schema_invalid", written.detail))
                continue
            if isinstance(concept, str) or event_type in {"phase.set", "model_type.set"}:
                events = await self.guard.read_all(job_id)
            record = written.event or {}
            if isinstance(record.get("seq"), int):
                followed[slot] = record["seq"]
            records.append(record)
            accepted = {
                "index": index,
                "status": "accepted",
                "record_seq": record.get("seq"),
                "duplicate": written.duplicate,
                "errors": [],
                "warnings": [],
            }
            if record.get("question_id"):
                accepted["question_id"] = record["question_id"]
            results.append(accepted)
        return {"results": results, "records": records}

    async def _fold_derived(self, job_id: str, head: Head, token: str | None, fence: int) -> Head:
        await self._use_active_catalog()
        events = await self.guard.read_all(job_id)
        state_seq = int(events[-1]["seq"]) if events else head.state_seq
        versions = await self._versions_for(head, events, job_id)
        derive = versions.derive(state_seq)
        if state_seq == head.state_seq and derive == head.derive_key:
            return head
        projected = {
            "dim_row": await self._dataset_rows(job_id, head, "dim_row"),
            "dim_period": await self._dataset_rows(job_id, head, "dim_period"),
        }
        facts = await self._dataset_rows(job_id, head, "fact_observation")
        try:
            links = await self._dataset_rows(job_id, head, "graph_links")
        except (NotFound, StopIteration):
            links = []
        derived = await self._derive(
            job_id,
            projected,
            state_seq=state_seq,
            derive=derive,
            versions=versions.as_dict(),
            events=events,
            facts=facts,
            links=links,
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
        body = await create_op(self.store, kind, job_id, actor, payload, owner=self.instance_id)
        await self.support.publish(f"fas:op:{body['id']}", "running")
        return body

    async def refresh_owner_lease(self) -> None:
        ttl = max(int(self.settings.op_heartbeat_sec) * 3, 5)
        await self.support.cache_set(f"fas:api:{self.instance_id}", b"1", ttl)

    def hold_owner(self) -> None:
        if self._owner_held:
            return
        self._owner_held = True
        self.spawn(self.owner_lease())

    async def owner_lease(self) -> None:
        while not self.draining:
            try:
                await self.refresh_owner_lease()
            except Exception:  # noqa: BLE001, S110 — аренда обновится на следующем круге
                pass
            for _ in range(max(int(self.settings.op_heartbeat_sec), 1)):
                if self.draining:
                    return
                await asyncio.sleep(1)

    async def sweep_orphans(self) -> int:
        """Закрывает операции, которые остались в работе после смерти процесса API.

        Метод обходит незавершённые операции один раз при старте. Если у
        операции есть очередь Taskiq, свежая метка живости или живая
        аренда владельца, её не трогает: её доделает воркер или другой
        процесс API. Остальные помечает проваленными с ошибкой
        `interrupted` («операция прервана перезапуском», её можно
        повторить). Возвращает число закрытых операций. Периодическая
        проверка зависших операций повторяет это правило позже.
        Истёкшая аренда или пропавшая метка живости либо продолжает
        операцию, у которой в нагрузке есть шаг, либо закрывает её.
        Повтор без шага успехом не считается.
        """

        closed = 0
        for op in await self.list_ops(kind=None, job_id=None, status=None):
            if op.get("status") in {"succeeded", "failed", "cancelled"}:
                continue
            if await self._worker_or_live_owner(op):
                continue
            await self.finish_op(op["id"], "failed", error=_operation_problem(Interrupted()))
            closed += 1
        return closed

    async def _worker_or_live_owner(self, op: dict) -> bool:
        payload = op.get("payload") or {}
        if payload.get("queue"):
            return True
        if await self.support.cache_get(f"fas:op:{op['id']}:hb"):
            return True
        owner = op.get("owner")
        if owner == self.instance_id:
            return True
        return bool(owner and await self.support.cache_get(f"fas:api:{owner}"))

    async def progress_op(self, op_id: str, stage: str) -> None:
        current = await self.get_op(op_id)
        if current["status"] in {"succeeded", "failed", "cancelled"}:
            return
        # status здесь переписал бы отмену, если событие село позже финального.
        await append_event(self.store, op_id, {"type": "progress", "stage": stage})
        await self.support.publish(f"fas:op:{op_id}", stage)

    async def finish_op(self, op_id: str, status: str, **fields) -> dict:
        current = await self.get_op(op_id)
        if current["status"] in {"succeeded", "failed", "cancelled"}:
            return current
        if status == "succeeded" and await self.support.cache_get(f"fas:op:{op_id}:cancel"):
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

    async def mapping_view(self, job_id: str, actor: Actor, *, wait_sec: float, query: dict | None = None) -> dict | Accepted:
        head = await self._head_ready(job_id, actor, wait_sec)
        if isinstance(head, Accepted):
            return head
        rows = await self._rows_or_accepted(job_id, head, "bindings", actor, "mapping")
        if isinstance(rows, Accepted):
            return rows
        counts: dict[str, int] = {}
        for row in rows:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        return {"build_key": head.build_key, "rows": filter_bindings(rows, query), "counts": counts}

    async def _type_guess(self, job_id: str, head: Head):
        """Score типов по привязанным понятиям и именам листов. `other` не голосует."""

        try:
            bindings = await self._dataset_rows(job_id, head, "bindings")
        except (NotFound, StopIteration):
            bindings = []
        try:
            rows = await self._dataset_rows(job_id, head, "dim_row")
        except (NotFound, StopIteration):
            rows = []
        return infer(
            self.model_types,
            bound=frozenset(_primaries(bindings)),
            sheets=frozenset(str(row["sheet"]) for row in rows if row.get("sheet")),
            accept=self.settings.model_type_accept,
            gap=self.settings.model_type_gap,
        )

    async def resolve_model_type(self, job_id: str, head: Head):
        """Действующий тип: факт книги, вывод по правилам, профиль. Score пишется в лог."""

        guessed = await self._type_guess(job_id, head)
        events = await self.guard.read_all(job_id)
        profile_id = _profile_id(events)
        body = await self.glossary.profile_body(profile_id) if profile_id else None
        default = body.get("model_type_default") if isinstance(body, dict) else None
        if not isinstance(default, dict):
            default = None
        verdict = model_type_effective(
            guessed,
            confirmed=_model_type_value(events),
            profile_default=default,
            profile_version=head.versions.get("profile"),
        )
        LOG.info(
            "model_type job=%s scores=%s source=%s primary=%s",
            job_id,
            guessed.scores,
            verdict.source,
            verdict.primary,
        )
        return verdict

    async def questions_view(self, job_id: str, actor: Actor, *, wait_sec: float) -> dict | Accepted:
        head = await self._head_ready(job_id, actor, wait_sec)
        if isinstance(head, Accepted):
            return head
        mapped = await self.mapping_view(job_id, actor, wait_sec=wait_sec)
        if isinstance(mapped, Accepted):
            return mapped
        verdict = await self.resolve_model_type(job_id, head)
        labels = decision_labels(verdict)
        events = await self.guard.read_all(job_id)
        try:
            dim_rows = await self._dataset_rows(job_id, head, "dim_row")
        except (NotFound, StopIteration):
            dim_rows = []
        package = await self._book_package(str(head.versions.get("glossary") or "none"), events)
        questions = concept_questions(
            job_id=job_id,
            bindings=mapped["rows"],
            rows=dim_rows,
            events=events,
            catalog=self.model_types,
            labels=labels,
            concepts=package.concepts,
            limit=self.settings.question_max_candidates,
        )
        if verdict.source == "unresolved":
            digest = question_digest("model_type", "book", job_id)
            questions.insert(
                0,
                {
                    "question_id": digest,
                    "kind": "model_type",
                    "subject": "book",
                    "scope": job_id,
                    "reason": verdict.reason or "unknown",
                    "candidates": [
                        {"label": item.type_id, "score": item.score, "reasons": list(item.reasons)}
                        for item in verdict.candidates
                    ],
                },
            )
        return {"questions": questions, "build_key": mapped["build_key"], "model_type": verdict.as_dict()}

    async def coverage_view(self, job_id: str, actor: Actor, *, wait_sec: float) -> dict | Accepted:
        head = await self._head_ready(job_id, actor, wait_sec)
        if isinstance(head, Accepted):
            return head
        rows = await self._rows_or_accepted(job_id, head, "coverage", actor, "coverage")
        if isinstance(rows, Accepted):
            return rows
        public = await self._coverage_public(job_id, head)
        return {"build_key": head.build_key, "rows": rows, **public}

    async def _submit(self, kind: str, queue: str, actor: Actor, payload: dict) -> Accepted:
        """Ставит операцию в очередь Taskiq и возвращает её как принятую.

        `kind` — вид операции. `queue` — имя очереди, которую передал маршрут.
        `actor` — пользователь и клиент, от имени которых записывается операция.
        `payload` — аргументы шага: воркер прочитает их сам. Метод не выполняет
        шаг. Если очередь на сервисе не настроена, метод поднимает ошибку
        `dependency_unavailable` с текстом «очередь задач не настроена».
        Возвращает `Accepted`: тело операции. HTTP-слой отвечает 202.
        """

        if self.jobs is None:
            raise DependencyUnavailable("очередь задач не настроена")
        operation = await self.jobs.submit(kind, payload, queue=queue, actor=actor)
        return Accepted(operation)

    async def begin_glossary_transition(
        self,
        version: str,
        status: str,
        if_match: str | None,
        *,
        force: bool,
        reason: str | None,
        actor: Actor,
        queue: str,
    ) -> Accepted:
        """Ставит переход релиза глоссария в очередь и сразу возвращает операцию.

        Теневая проверка (сравнение нового глоссария с активным на загруженных
        книгах) и запись нового статуса не укладываются в синхронный предел
        запроса. Метод не выполняет переход сам. Он создаёт операцию
        `glossary.validate` и ставит её в очередь `queue`. Шаг исполняет воркер
        Taskiq. Пока шаг выполняется, воркер обновляет метку живости в Redis
        (heartbeat, ключ `fas:op:{id}:hb`) с интервалом `OP_HEARTBEAT_SEC`.
        Если проверка зависших операций уже закрыла операцию или клиент
        поставил флаг отмены `fas:op:{id}:cancel`, голова глоссария не меняется
        и успех в операцию не пишется. Эту проверку делает воркер непосредственно
        перед записью.

        `version` — версия релиза. `status` — целевой статус: `canary`,
        `active` или `rejected`. `if_match` — заголовок If-Match; сверка
        повторяется уже внутри шага, под замком, в момент записи.
        Если `force` равен истине, активация разрешена даже когда теневая
        проверка нашла регресс, но только вместе с непустым `reason`.
        `actor` — пользователь и клиент, от имени которых записывается операция.
        `queue` — имя очереди Taskiq.

        Возвращает `Accepted`: тело операции. HTTP-слой отвечает 202 и
        заголовками `Operation-Location` и `Retry-After`. Успешная операция
        записывает новый статус релиза и запускает пересчёт книг
        (`glossary.remap`). Регресс без `force` завершает операцию со статусом
        `failed` и ошибкой `glossary_regression`. Устаревший родитель релиза
        (`stale_parent`) тоже завершает операцию со статусом `failed`. Любая
        другая ошибка перехода закрывает операцию со статусом `failed`.
        Если очередь не настроена, метод поднимает `dependency_unavailable`.
        """

        return await self._submit(
            "glossary.validate",
            queue,
            actor,
            {
                "stage": "glossary.transition",
                "stage_args": {
                    "version": version,
                    "status": status,
                    "if_match": if_match,
                    "force": force,
                    "reason": reason,
                },
            },
        )

    async def perform_glossary_transition(
        self,
        version: str,
        status: str,
        if_match: str | None,
        *,
        force: bool,
        reason: str | None,
        op_id: str | None = None,
    ) -> dict:
        """Выполняет переход релиза. Этот метод вызывает воркер, не HTTP-запрос.

        `version`, `status`, `if_match`, `force` и `reason` — те же значения,
        что принял запрос. `op_id` — идентификатор операции `glossary.validate`.
        Если идентификатора нет, запись разрешена: прямой вызов из обучения и
        теста хранилища не зависит от очереди.

        Перед записью головы метод ещё раз проверяет, что операция не отменена
        и не закрыта. Если запись пропущена, операция помечается отменённой,
        когда она ещё выполняется, и метод возвращает `{"skipped": True}`.
        Иначе метод записывает статус, запускает пересчёт книг и возвращает
        результат перехода вместе с идентификатором операции `glossary.remap`.
        Повтор после уже записанной головы не считается провалом. Подтверждение
        задачи приходит только когда метод вернулся, поэтому воркер может
        умереть между записью и ответом. Второй запуск видит старый If-Match и
        получил бы ошибку `precondition_failed`. Если голова уже стоит на
        запрошенных версии и статусе, метод возвращает это состояние как успех
        и не пишет голову ещё раз. Регресс без `force` поднимает ошибку
        `glossary_regression`. Устаревший родитель поднимает `stale_parent`.
        Успех операции записывает воркер, не этот метод: пропущенную запись
        нельзя закрыть как успех.
        """

        may_commit = (lambda: self._glossary_writable(op_id)) if op_id else None
        if op_id and not await self._glossary_writable(op_id):
            await self._close_cancelled_glossary(op_id)
            return {"skipped": True}
        try:
            result = await self.glossary.transition(
                version,
                status,
                if_match,
                force=force,
                reason=reason,
                may_commit=may_commit,
            )
        except PreconditionFailed:
            result = await self._transition_already_applied(version, status)
            if result is None:
                raise
        if result.get("skipped"):
            if op_id:
                await self._close_cancelled_glossary(op_id)
            return {"skipped": True}
        remap = await self.begin_remap()
        ref = remap.get("operation")
        return {**result, "remap": ref.get("id") if isinstance(ref, dict) else ref}

    async def _transition_already_applied(self, version: str, status: str) -> dict | None:
        """Возвращает текущую голову, если запрошенный переход уже записан.

        `version` — версия релиза. `status` — статус, который просил первый
        запуск: `canary`, `active` или `rejected`. Метод читает голову и не
        меняет её. Если именно эта версия уже в запрошенном статусе, словарь
        совпадает с обычным ответом перехода. Если голова в другом состоянии,
        метод возвращает `None`: вызывающий код поднимает исходную ошибку
        предусловия, потому что писать поверх чужого изменения нельзя.
        """

        head = await self.glossary.ensure()
        applied = False
        if status == "active":
            applied = head.get("active") == version
        elif status == "canary":
            applied = head.get("canary") == version
        elif status == "rejected":
            found = None
            for item in head.get("history") or []:
                if item.get("version") == version:
                    found = item.get("status")
            applied = found == "rejected"
        if not applied:
            return None
        return {"version": version, "status": status, "state": state_of(head), "etag": f"h-{head['seq']}"}

    async def begin_proposal_decision(self, decisions: list, actor: Actor, *, queue: str) -> Accepted:
        """Ставит принятие пакета предложений в ту же очередь, что и переход релиза.

        `decisions` — список решений. В каждом элементе указаны идентификатор
        предложения и решение `accept` или `reject`. Новый текст метки и
        понятие можно не передавать. `actor` — пользователь и клиент, от имени
        которых записывается операция. `queue` — имя очереди Taskiq. Сюда
        попадает только пакет, в котором есть хотя бы одно принятие. Пакет из
        одних отказов маршрут обрабатывает синхронно и этот метод не вызывает.
        Заголовок If-Match для решения предложений не сверяется.

        Возвращает `Accepted`: тело операции `glossary.validate`. HTTP-слой
        отвечает 202 и заголовками `Operation-Location` и `Retry-After`.
        Воркер проводит теневую проверку принятых правок: сравнивает новый
        глоссарий с активным на загруженных книгах и обновляет метку живости.
        Если проверка зависших операций уже закрыла операцию или стоит флаг
        отмены `fas:op:{id}:cancel`, релиз не активируется и успех не пишется.
        Если проверка прошла, активируется один общий релиз и запускается
        пересчёт книг. Если проверка нашла регресс, предложения остаются
        открытыми с пометкой `blocked: glossary_regression`, а операция
        завершается успешно: отказ записан в результате, а не как провал.
        Ошибка решения, например отсутствующее или уже решённое предложение,
        закрывает операцию со статусом `failed`. Если очередь не настроена,
        метод поднимает `dependency_unavailable`.
        """

        return await self._submit(
            "glossary.validate",
            queue,
            actor,
            {"stage": "glossary.decide", "stage_args": {"decisions": decisions}},
        )

    async def perform_proposal_decision(self, decisions: list, *, op_id: str | None = None) -> dict:
        """Решает пакет предложений. Этот метод вызывает воркер, не HTTP-запрос.

        `decisions` — тот же список, что принял запрос. `op_id` — идентификатор
        операции `glossary.validate`. Если идентификатора нет, запись разрешена.

        Перед записью метод проверяет, что операция не отменена и не закрыта.
        Если запись пропущена, метод возвращает `{"skipped": True}` и не
        активирует релиз. Кандидат, уже записанный до теневой проверки, при
        этом остаётся. Иначе метод сохраняет отрицательные примеры, при
        активном релизе запускает пересчёт книг и возвращает результат решения.
        Успех операции записывает воркер. Ошибку отсутствующего или уже
        решённого предложения метод поднимает наружу.
        """

        may_commit = (lambda: self._glossary_writable(op_id)) if op_id else None
        if op_id and not await self._glossary_writable(op_id):
            await self._close_cancelled_glossary(op_id)
            return {"skipped": True}
        result = await self.glossary.decide_proposals(decisions, may_commit=may_commit)
        if result.get("skipped"):
            if op_id:
                await self._close_cancelled_glossary(op_id)
            return {"skipped": True}
        await self.learning.proposals_rejected(result.pop("rejected", []))
        release = result.get("release") or {}
        if release.get("status") == "active":
            remap = await self.begin_remap()
            ref = remap.get("operation")
            result = {**result, "remap": ref.get("id") if isinstance(ref, dict) else ref}
        return result

    async def _glossary_writable(self, op_id: str) -> bool:
        """Можно ли ещё менять глоссарий от имени этой операции.

        Проверка зависших операций могла уже записать статус `failed`.
        Клиент мог поставить флаг `fas:op:{id}:cancel`. В обоих случаях
        поздняя активация оставила бы новый релиз при закрытой операции.
        """

        if await self.support.cache_get(f"fas:op:{op_id}:cancel"):
            return False
        current = await self.get_op(op_id)
        return current["status"] not in {"succeeded", "failed", "cancelled"}

    async def reject_glossary_busy(self) -> None:
        """Не пускает второй переход, пока идёт операция по глоссарию.

        `glossary.validate` и `glossary.remap` видны без замка хранилища.
        Если такая операция уже выполняется, метод поднимает ошибку 409
        `glossary_busy`. Запрос возвращается сразу и не ждёт, пока теневая
        проверка отпустит замок.
        """

        for kind in ("glossary.validate", "glossary.remap"):
            if await self.list_ops(kind=kind, job_id=None, status="running"):
                raise GlossaryBusy("уже идёт операция по глоссарию")

    async def _close_cancelled_glossary(self, op_id: str) -> None:
        """Закрывает операцию как отменённую, если запись глоссария уже пропущена.

        Отмена сначала ставит флаг, и только потом помечает операцию. Если
        статус ещё `running`, здесь он становится `cancelled`. Уже закрытую
        операцию, в том числе проваленную проверкой зависания, метод не трогает.
        """

        current = await self.get_op(op_id)
        if current["status"] == "running":
            await self.finish_op(op_id, "cancelled")

    async def infer_mapping(self, job_id: str, actor: Actor, *, queue: str) -> Accepted:
        """Ставит подбор сопоставления книги в очередь и возвращает операцию.

        `job_id` — книга. `actor` — пользователь и клиент, от имени которых
        записывается операция. `queue` — имя очереди Taskiq. Метод не считает
        сопоставление сам. Воркер выполняет шаг и обновляет метку живости
        `fas:op:{id}:hb`. Возвращает `Accepted`: тело операции `mapping.infer`.
        HTTP-слой отвечает 202. Если очередь не настроена, метод поднимает
        `dependency_unavailable`. Если книга не загружена, воркер закрывает
        операцию со статусом `failed`.
        """

        return await self._submit(
            "mapping.infer",
            queue,
            actor,
            {"stage": "mapping.infer", "stage_args": {"job_id": job_id}, "job_id": job_id},
        )

    async def perform_mapping_infer(self, job_id: str) -> dict:
        """Подбирает сопоставление загруженной книги и возвращает ключи сборки.

        `job_id` — книга. Метод держит замок книги, чтобы два подбора одной
        книги не писали голову одновременно. Если голова не найдена, метод
        поднимает ошибку `not_found` с текстом «книга не загружена». Иначе
        пересчитывает производные строки и возвращает `build_key` и
        `derive_key`. Успех операции записывает воркер.
        """

        async with self.support.lock(f"book:{job_id}", self.settings.lock_ttl_ms) as held:
            head, token = await self._read_head(job_id)
            if head is None:
                raise NotFound("книга не загружена")
            fresh = await self._fold_derived(job_id, head, token, held.fence)
        return {"build_key": fresh.build_key, "derive_key": fresh.derive_key}

    async def catch_glossary(self, version: str) -> bool:
        if not version or version == self.glossary_seen:
            return False
        await self.remap_glossary()
        self.glossary_seen = version
        return True

    async def remap_glossary(self, *, limit: int | None = None, cursor: str | None = None) -> dict:
        """Без limit проходит все книги. С limit отдаёт хвост в remaining, курсор — последняя изменённая."""

        state = await self.glossary.ensure()
        package_of(await self.glossary.document(state["active"]))
        jobs = await self.glossary.jobs()
        if cursor:
            jobs = [job for job in jobs if job > cursor]
        changed = []
        remaining = []
        for job_id in jobs:
            if limit is not None and len(changed) >= limit:
                remaining.append(job_id)
                continue
            target = glossary_for_job(state, job_id)
            async with self.support.lock(f"book:{job_id}", self.settings.lock_ttl_ms) as held:
                head, token = await self._read_head(job_id)
                if head is None or head.versions.get("glossary") == target:
                    continue
                pinned = {**head.as_dict(), "versions": {**head.versions, "glossary": target}}
                await self._publish_head(job_id, pinned, token, held.fence)
                head, token = await self._read_head(job_id)
                if head is None:
                    continue
                await self._fold_derived(job_id, head, token, held.fence)
            changed.append(job_id)
        self.glossary_seen = state["active"]
        return {"jobs": changed, "remaining": remaining, "glossary": state["active"], "cursor": changed[-1] if changed else cursor}

    async def begin_remap(self) -> dict:
        """Запускает пересчёт книг на новый глоссарий и возвращает первую пачку.

        Если пересчёт уже выполняется, метод возвращает эту операцию и новую
        не создаёт. Иначе создаёт операцию `glossary.remap`. В полезной
        нагрузке лежит шаг `glossary.remap` и очередь `fas:glossary`, чтобы
        проверка зависших операций смогла продолжить работу, а не засчитать
        пустой повтор успехом. Первая пачка не длиннее `REMAP_BATCH_BOOKS`.
        Если книги ещё остались, метод записывает курсор в нагрузку и
        продолжает в фоне. Успех пишется только когда хвоста больше нет.
        Пока идёт пачка, обновляется метка живости `fas:op:{id}:hb`.
        """

        running = await self.list_ops(kind="glossary.remap", job_id=None, status="running")
        if running:
            return {"operation": running[0], "jobs": [], "remaining": None, "busy": True}
        op = await self.create_op(
            "glossary.remap",
            None,
            Actor(user_id="system"),
            {"stage": "glossary.remap", "stage_args": {}, "queue": "fas:glossary"},
        )
        stop = asyncio.Event()
        beater = asyncio.create_task(self._beat_op(op["id"], stop))
        handed = False
        try:
            try:
                batch = await self.remap_glossary(limit=self.settings.remap_batch_books)
            except Exception as exc:
                await self.finish_op(op["id"], "failed", error={"detail": str(exc)})
                raise
            if not batch["remaining"]:
                await self.finish_op(
                    op["id"], "succeeded", result={"jobs": batch["jobs"], "glossary": batch["glossary"]}
                )
                return {**batch, "operation": op["id"], "busy": False}
            await self._note_remap_cursor(op["id"], batch["cursor"], len(batch["remaining"]))
            self.spawn(self._remap_rest(op["id"]))
            handed = True
            return {**batch, "operation": op["id"], "busy": False}
        finally:
            stop.set()
            beater.cancel()
            await asyncio.gather(beater, return_exceptions=True)
            if not handed:
                await self.support.cache_delete(f"fas:op:{op['id']}:hb")

    async def _note_remap_cursor(self, op_id: str, cursor: str | None, remaining: int) -> None:
        """Записывает курсор пересчёта в результат и в полезную нагрузку.

        `op_id` — операция `glossary.remap`. `cursor` — последняя уже
        обработанная книга. `remaining` — сколько книг ещё не брали в эту
        пачку. Проверка зависших операций читает нагрузку и с этого курсора
        продолжает шаг, а не начинает пустой успех.
        """

        await append_event(
            self.store,
            op_id,
            {
                "result": {"cursor": cursor, "remaining": remaining},
                "payload": {
                    "stage": "glossary.remap",
                    "stage_args": {"cursor": cursor},
                    "queue": "fas:glossary",
                },
            },
        )

    async def _remap_rest(self, op_id: str) -> None:
        """Доделывает хвост пересчёта и закрывает операцию только в конце.

        `op_id` — операция `glossary.remap`. Метод продолжает с курсора,
        который записала первая пачка. Если операция уже закрыта, метод
        выходит и не пишет успех. Ошибка хвоста закрывает операцию со
        статусом `failed`.
        """

        try:
            result = await self.perform_glossary_remap(op_id=op_id)
            if result.get("skipped"):
                return
            await self.finish_op(
                op_id, "succeeded", result={"jobs": result.get("jobs"), "glossary": result.get("glossary")}
            )
        except Exception as exc:  # noqa: BLE001 — хвост ремапа закрывает операцию
            await self.finish_op(op_id, "failed", error={"detail": str(exc)})

    async def perform_glossary_remap(self, cursor: str | None = None, *, op_id: str | None = None) -> dict:
        """Доводит пересчёт книг до конца и возвращает итог.

        `cursor` — последняя уже обработанная книга. Если его нет, метод
        берёт курсор из полезной нагрузки операции или из последнего
        результата. `op_id` — операция `glossary.remap`. Пока в ответе пачки
        есть хвост, метод не возвращает управление и обновляет метку живости.
        Вызывающий код записывает успех только по этому возврату, когда
        хвоста уже нет. Если операция закрыта или отменена, метод возвращает
        `{"skipped": True}` и голову книг дальше не меняет. В конце проходит
        книги ещё раз без курсора: курсор не возвращается назад, и релиз
        посередине пачки иначе оставил бы ранние книги на старой цели.
        """

        if op_id and cursor is None:
            current = await self.get_op(op_id)
            args = ((current.get("payload") or {}).get("stage_args") or {})
            cursor = args.get("cursor") or (current.get("result") or {}).get("cursor")
        stop = asyncio.Event()
        beater = asyncio.create_task(self._beat_op(op_id, stop)) if op_id else None
        try:
            while True:
                if op_id:
                    current = await self.get_op(op_id)
                    if current["status"] != "running":
                        return {"skipped": True}
                batch = await self.remap_glossary(limit=self.settings.remap_batch_books, cursor=cursor)
                if not batch["remaining"]:
                    await self.remap_glossary()
                    return {"jobs": batch["jobs"], "glossary": batch["glossary"], "remaining": []}
                cursor = batch["cursor"]
                if op_id:
                    await self._note_remap_cursor(op_id, cursor, len(batch["remaining"]))
                rate = self.settings.remap_books_per_min
                if rate > 0:
                    await asyncio.sleep(self.settings.remap_batch_books / rate * 60)
        finally:
            stop.set()
            if beater is not None:
                beater.cancel()
                await asyncio.gather(beater, return_exceptions=True)
                if op_id:
                    await self.support.cache_delete(f"fas:op:{op_id}:hb")

    async def _beat_op(self, op_id: str, stop: asyncio.Event) -> None:
        """Обновляет метку живости операции, пока идёт пересчёт книг.

        `op_id` — операция. `stop` — событие, после которого цикл кончается.
        Проверка зависших операций закрывает операцию без ключа
        `fas:op:{id}:hb`, если с создания прошло больше `OP_STALE_SEC`.
        Пересчёт нескольких пачек длится дольше этого срока. Метод пишет ключ
        с интервалом `OP_HEARTBEAT_SEC`, чтобы живой пересчёт не поставили в
        очередь заново. Ничего не возвращает.
        """

        interval = max(float(self.settings.op_heartbeat_sec), 0.05)
        ttl = max(int(interval * 2), 1)
        key = f"fas:op:{op_id}:hb"
        while not stop.is_set():
            await self.support.cache_set(key, f"0:{time.time()}".encode(), ttl)
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except TimeoutError:
                continue

    async def _calibrator_ok(self, body: dict) -> bool:
        state = await self.glossary.peek()
        package = self.catalog
        if state and state.get("active"):
            try:
                package = package_of(await self.glossary.document(state["active"]))
            except NotFound:
                pass
        before = (await self.evaluator.run(package)).get("summary") or {}
        after = (await self.evaluator.run(package, calibrator=Calibrator.of(body))).get("summary") or {}
        old, new = before.get("false_binding_rate"), after.get("false_binding_rate")
        return new is not None and (old is None or new <= old)

    async def glossary_stats(self, *, start: str | None, end: str | None, profile_id: str | None) -> dict:
        for value in (start, end):
            if value and not _day(value):
                raise InvalidArgument("from и to: YYYY-MM-DD")
        coverage = [
            row
            for row in await self._stats_coverage()
            if _stat_keep(row, start, end, profile_id)
        ]
        proposals = (await self.glossary.proposals())["proposals"]
        auto_labels, auto_rejected = await self._auto_label_counts()
        body = summarize_stats(
            coverage=coverage,
            proposals=proposals,
            auto_labels=auto_labels,
            auto_rejected=auto_rejected,
            shadow=await self._last_shadow(),
            lf_accuracy=lf_accuracy(await self.learning.signals.rows()),
        )
        months = body["unknown_by_month"]
        if not start and not end and not profile_id and months:
            GLOSSARY_UNKNOWN_SHARE.set(list(months.values())[-1] or 0)
        if body["auto"]["rollback_rate"] is not None:
            GLOSSARY_AUTO_ROLLBACK.set(body["auto"]["rollback_rate"])
        GLOSSARY_REVIEW_OPEN.set(body["review"]["open"])
        return body

    async def _stats_coverage(self) -> list[dict]:
        rows = []
        async for item in self.store.list("books/"):
            parts = item.key.split("/")
            if len(parts) != 3 or parts[2] != "_head.json":
                continue
            job_id = parts[1]
            head = json.loads(await self.store.get(item.key))
            month = await self._first_month(job_id)
            profile = str((head.get("versions") or {}).get("profile") or "").split("@", 1)[0]
            if profile == "p-0":
                profile = ""
            build, derive = head.get("build_key"), head.get("derive_key")
            if not build or not derive:
                continue
            try:
                done = json.loads(await self.store.get(keys.derived_done(job_id, build, derive)))
            except NotFound:
                continue
            files = done.get("files") or {}
            names = list(files)
            rel = next((name for name in names if str(name).endswith("coverage.parquet")), None)
            if rel is None:
                continue
            for row in await self.parquet.read(await self.store.get(f"books/{job_id}/{build}/{rel}")):
                rows.append({"month": month, "profile": profile, "status": row.get("status"), "rows": row.get("rows")})
        return rows

    async def _first_month(self, job_id: str) -> str:
        earliest = ""
        async for item in self.store.list(f"books/{job_id}/_builds/"):
            if not item.key.endswith(".json"):
                continue
            body = json.loads(await self.store.get(item.key))
            stamp = str(body.get("created_at_utc") or "")
            if stamp and (not earliest or stamp < earliest):
                earliest = stamp
        return earliest[:7]

    async def _auto_label_counts(self) -> tuple[int, int]:
        head = await self.glossary.peek()
        if not head:
            return 0, 0
        when = {}
        async for item in self.store.list("glossary/events/"):
            if not item.key.endswith(".json"):
                continue
            event = json.loads(await self.store.get(item.key))
            if event.get("type") == "release" and event.get("version"):
                when[event["version"]] = event.get("at_utc") or ""
        labels = []
        seen: set[str] = set()
        for item in head.get("history") or []:
            version = item.get("version")
            if item.get("source") != "auto" or not version or version in seen:
                continue
            seen.add(version)
            try:
                record = json.loads(await self.store.get(f"glossary/releases/{item['version']}/release.json"))
            except NotFound:
                continue
            for change in record.get("ops") or []:
                if change.get("op") == "add_label" and change.get("text"):
                    labels.append((normalize_label(change["text"]).strip(), when.get(item["version"]) or ""))
        rejected = 0
        signals = await self.learning.signals.rows()
        for norm, at in labels:
            if not at:
                continue
            start = datetime.strptime(at[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=UTC)
            end = start + timedelta(days=30)
            for row in signals:
                if row.get("polarity") != "-" or row.get("kind") != "human.rejected" or row.get("at_utc") is None:
                    continue
                label = normalize_label(row.get("label_text") or row.get("label_norm") or "").strip()
                if label == norm and start <= _aware(row["at_utc"]) <= end:
                    rejected += 1
                    break
        return len(labels), rejected

    async def _last_shadow(self) -> dict | None:
        key = None
        async for item in self.store.list("glossary/releases/"):
            if item.key.endswith("/shadow.json") and (key is None or item.key > key):
                key = item.key
        if key is None:
            return None
        return json.loads(await self.store.get(key))

    async def resolve_concept(self, body: dict) -> dict:
        rank = self._rank_label if self.pipeline.enabled else None
        return await self.glossary.resolve(body, rank=rank)

    async def _rank_label(self, row: dict, package, version: str):
        scored = await self.pipeline.score(
            "resolve",
            "resolve",
            [row],
            package,
            glossary_version=version,
            deadline=effective(self.settings.mapping_deadline_ms),
            clm=False,
        )
        evidence = scored.evidence.get(row["binding_key"])
        if evidence is None:
            return None
        chosen = decide(row, evidence, package, await self.calibrators.active())
        return chosen, evidence

    def capabilities(self) -> dict:
        storage = {
            "backend": self.store.backend,
            "url": self.store.url,
            "wren_source": self.settings.wren_source,
            "conditional_writes": self.store.conditional_writes,
        }
        return {
            "fas_version": FAS_VERSION,
            "phase": "4",
            "storage": storage,
            "rules": self.analyses.capabilities(),
            "metrics": list(RATIO_METRICS),
            "concepts": sorted(self.catalog.ids),
            "renderers": ["json", "md"],
            "problems": PROBLEM_CATALOG,
            "tools": build_tools(
                decision_kinds=tuple(_DECISION_KINDS),
                measures=tuple(sorted(_MEASURES)),
                dims=tuple(sorted(_DIMS)),
                ops=tuple(sorted(_OPS)),
            ),
        }

    def model_states(self) -> dict[str, str]:
        """Состояние circuit breaker каждого сервера модели (информационно, на готовность не влияет)."""

        out = {}
        for name in ("embed", "rerank", "clm", "llm"):
            endpoint = getattr(getattr(self.models, name), "endpoint", None)
            out[name] = "absent" if endpoint is None else endpoint.breaker.state()
        return out

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
            "models": self.model_states(),
            "calibrator": self.calibrators.version,
            "glossary": (await self.glossary.peek() or {}).get("active") or "none",
            "draining": self.draining,
        }


def _human_keys(events: list[dict]) -> frozenset[str]:
    found = set()
    for event in fold(events).values():
        if event.get("type") in {"concept.set", "concept.confirmed", "concept.ignored"}:
            key = str(event.get("binding_key") or event.get("target") or "")
            if key and key != "book":
                found.add(key)
    return frozenset(found)


def _profile_id(events: list[dict]) -> str | None:
    chosen = None
    for event in fold(events).values():
        if event.get("type") == "profile.set" and isinstance(event.get("value"), str):
            chosen = event["value"]
    return chosen


def _profile_name(events: list[dict]) -> str | None:
    raw = _profile_id(events)
    if not isinstance(raw, str) or not raw:
        return None
    name = raw.split("@", 1)[0]
    if not name or name == "p-0":
        return None
    return name


def _day(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _stat_keep(row: dict, start: str | None, end: str | None, profile_id: str | None) -> bool:
    if profile_id and row.get("profile") != profile_id:
        return False
    month = str(row.get("month") or "")
    if start and month and month < start[:7]:
        return False
    return not (end and month and month > end[:7])


def _aware(value) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    return datetime.strptime(str(value)[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=UTC)


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
    {"code": "glossary_regression", "http": 409, "retryable": False},
    {"code": "invalid_transition", "http": 409, "retryable": False},
    {"code": "glossary_busy", "http": 409, "retryable": False},
    {"code": "idempotency_key_reused", "http": 422, "retryable": False},
    {"code": "rate_limited", "http": 429, "retryable": True},
    {"code": "book_busy", "http": 429, "retryable": True},
    {"code": "too_many_inflight", "http": 429, "retryable": True},
    {"code": "overloaded", "http": 503, "retryable": True},
    {"code": "interrupted", "http": 503, "retryable": True},
    {"code": "dependency_unavailable", "http": 503, "retryable": True},
    {"code": "deadline_exceeded", "http": 504, "retryable": True},
]

_MAPPING_QUERY = frozenset({"status", "concept", "importance", "q"})


def filter_bindings(rows: list[dict], query: dict | None) -> list[dict]:
    """Строки mapping по status, concept, importance и подстроке q. counts считаются до фильтра."""

    if not query:
        return rows
    unknown = sorted(set(query) - _MAPPING_QUERY)
    if unknown:
        raise InvalidArgument(
            "неизвестный фильтр mapping",
            extra={"fields": unknown, "supported": sorted(_MAPPING_QUERY)},
        )
    status = query.get("status") or None
    concept = query.get("concept") or None
    importance = query.get("importance") or None
    needle = str(query.get("q") or "").casefold()
    found = []
    for row in rows:
        if status and row.get("status") != status:
            continue
        if concept and concept not in {row.get("concept"), row.get("effective_concept")}:
            continue
        if importance and row.get("importance") != importance:
            continue
        if needle and needle not in str(row.get("label_path_text") or "").casefold():
            continue
        found.append(row)
    return found
