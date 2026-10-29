"""Анализы книги фазы 1: аудит, история, находки (§3.2, §4.2, §6.1).

Результат пишется в `{build_key}/results/{analysis_id}/`: `findings.parquet`,
`run.parquet`, затем маркер `result.json` (`put_if_absent`, последним). После
маркера — запись индекса `_reports/{analysis_id}.json`: по нему строятся
история анализов и поиск последнего аудита без листинга папок сборок.
"""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime

import anyio
from ulid import ULID

from finance_analysis.application import keys
from finance_analysis.application.explain import narrate, template_text
from finance_analysis.application.impact import impact_view
from finance_analysis.application.report import render_json, render_markdown
from finance_analysis.application.rule_engine import (
    load_rules,
    requirements,
    run_rules,
    select_rules,
)
from finance_analysis.domain.audit import AuditInput, Finding, Location
from finance_analysis.domain.book import (
    FAS_VERSION,
    Actor,
    Head,
    ReportNotReady,
    sha256_bytes,
)
from finance_analysis.domain.cover_metrics import (
    BASES,
    DIRECTIONS,
    LOAN_LIFE,
    METRIC_INPUTS,
    REDUCED,
    adscr,
    dscr_reductions,
    loan_life_ratio,
    ratio_cells,
)
from finance_analysis.domain.deadline import effective
from finance_analysis.domain.errors import (
    AlreadyExists,
    DependencyUnavailable,
    InvalidArgument,
    NoAudit,
    NotAcceptable,
    NotFound,
)
from finance_analysis.domain.ids import build_key as check_build
from finance_analysis.domain.ids import fingerprint as check_fingerprint
from finance_analysis.domain.ids import ulid as check_ulid
from finance_analysis.domain.mapping import absent_in_journal
from finance_analysis.domain.metrics import _primaries, coverage_ratio
from finance_analysis.plugins.rules.coverage import (
    MISSING_TOTAL_ROW,
    PERIOD_GRAIN_MISMATCH,
)

ANALYSIS_TYPES = ("audit", "ratios", "impact", "full")
RATIO_METRICS = ("dscr", "icr", "adscr", "dscr_min", "dscr_avg", "llcr", "plcr")
# Поля строки метрики, которые уходят в `inputs_json` результата.
RATIO_EXTRAS = ("variant", "direction", "basis", "window", "over", "inputs")
# `scope` из §3.2: списки и одиночные значения.
SCOPE_LISTS = ("sheets", "row_keys", "markers", "concepts")
SCOPE_TEXT = ("axis_id", "period_from", "period_to")
COUNTER_RULES_INPUT = "counters"
TRACE_CELLS = 4
TRACE_DEPTH = 8
TRACE_DEPTH_MAX = 32


def _now() -> datetime:
    return datetime.now(UTC)


def _stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dumps(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, default=str).encode()


def _decimal_text(value) -> str | None:
    if value is None:
        return None
    text = format(value, "f") if hasattr(value, "as_tuple") else str(value)
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _pinned(target) -> Head:
    derive = target.head.derive_key if target.build == target.head.build_key else target.derived
    if not derive:
        raise NotFound("производное состояние сборки не найдено")
    if target.build == target.head.build_key:
        return target.head
    return Head(
        build_key=target.build,
        state_seq=target.head.state_seq,
        derive_key=derive,
        versions=target.head.versions,
        mdl_version=target.head.mdl_version,
        fence=target.head.fence,
    )


@dataclass(frozen=True)
class Target:
    head: Head
    build: str
    manifest: dict
    fresh: bool
    derived: str | None = None

    @property
    def is_latest(self) -> bool | None:
        if self.fresh:
            return None
        return self.build == self.head.build_key

    @property
    def derive_key(self) -> str | None:
        """Производное состояние этой сборки на текущем `state_seq`, если оно построено."""

        return self.head.derive_key if self.build == self.head.build_key else self.derived


def _scope(body: dict) -> dict:
    raw = body.get("scope") or {}
    if not isinstance(raw, dict):
        raise InvalidArgument("scope должен быть объектом")
    unknown = sorted(set(raw) - set(SCOPE_LISTS) - set(SCOPE_TEXT))
    if unknown:
        raise InvalidArgument("неизвестные поля scope", extra={"fields": unknown, "supported": [*SCOPE_LISTS, *SCOPE_TEXT]})
    scope: dict = {}
    for key in SCOPE_LISTS:
        value = raw.get(key)
        if value in (None, []):
            continue
        if not (isinstance(value, list) and all(isinstance(item, str) for item in value)):
            raise InvalidArgument(f"scope.{key} должен быть списком строк")
        scope[key] = set(value)
    for key in SCOPE_TEXT:
        value = raw.get(key)
        if value in (None, ""):
            continue
        if not isinstance(value, str):
            raise InvalidArgument(f"scope.{key} должен быть строкой")
        scope[key] = value
    return scope


class _Periods:
    """Периоды проекции для среза: порядок на оси и маркеры."""

    def __init__(self, periods: list[dict]) -> None:
        self.by_id = {(item["axis_id"], item["period_id"]): item for item in periods}
        self.keys: dict[str, dict[str, list[int]]] = {}
        for item in periods:
            index = int(item.get("period_index") or 0)
            names = self.keys.setdefault(item["axis_id"], {})
            for name in {item["period_id"], item.get("period_key_base")}:
                if name:
                    names.setdefault(name, []).append(index)

    def index(self, axis_id: str, period_id: str) -> int | None:
        found = self.by_id.get((axis_id, period_id))
        return None if found is None else int(found.get("period_index") or 0)

    def bound(self, axis_id: str, name: str, *, upper: bool) -> int | None:
        indexes = self.keys.get(axis_id, {}).get(name)
        if not indexes:
            return None
        return max(indexes) if upper else min(indexes)


def _in_scope(finding: Finding, scope: dict, data: AuditInput, bound: set[str]) -> bool:
    """Находка в срезе, если хоть одно её место проходит все условия `scope`.

    Находка уровня книги (циклы без мест, счётчики R1, `no_master_check`)
    от среза не зависит. Место без периода не проходит условия по периоду.
    """

    if not scope:
        return True
    located = [item for item in finding.locations if item.row_key or item.cell_id]
    if not located:
        return True
    periods = _Periods(data.periods)
    return any(_location_in_scope(item, scope, data, periods, bound) for item in located)


def _location_in_scope(location: Location, scope: dict, data: AuditInput, periods: _Periods, bound: set[str]) -> bool:
    sheet = location.cell_id.split("!", 1)[0] if location.cell_id else None
    if not sheet and location.row_key:
        sheet = location.row_key.split("|", 1)[0]
    if "sheets" in scope and sheet not in scope["sheets"]:
        return False
    if "row_keys" in scope and location.row_key not in scope["row_keys"]:
        return False
    if "axis_id" in scope and location.axis_id != scope["axis_id"]:
        return False
    if "concepts" in scope:
        row = data.rows_by_key.get(location.row_key or "") or {}
        if row.get("binding_key") not in bound:
            return False
    if not ({"period_from", "period_to", "markers"} & set(scope)):
        return True
    if location.axis_id is None or location.period_id is None:
        return False
    index = periods.index(location.axis_id, location.period_id)
    if index is None:
        return False
    if "period_from" in scope:
        low = periods.bound(location.axis_id, scope["period_from"], upper=False)
        if low is None or index < low:
            return False
    if "period_to" in scope:
        high = periods.bound(location.axis_id, scope["period_to"], upper=True)
        if high is None or index > high:
            return False
    if "markers" in scope:
        period = periods.by_id.get((location.axis_id, location.period_id)) or {}
        if not {period.get("period_marker"), period.get("marker_class")} & scope["markers"]:
            return False
    return True


def _citation(data: AuditInput, location: Location) -> dict | None:
    fact = data.facts_by_cell.get(location.cell_id or "")
    if fact is None:
        return None
    sheet, cell = fact["cell_id"].split("!", 1)
    row = data.rows_by_key.get(fact["row_key"]) or {}
    return {
        "cell_id": fact["cell_id"],
        "sheet": sheet,
        "cell": cell,
        "row_key": fact["row_key"],
        "axis_id": fact["axis_id"],
        "period_id": fact["period_id"],
        "label": row.get("label"),
        "value": _decimal_text(fact.get("value_dec")),
        "value_status": fact.get("value_status"),
        "normalized_value": _decimal_text(fact.get("normalized_value")),
        "binding_key": row.get("binding_key"),
    }


def _fact_citation(fact: dict, row: dict) -> dict:
    """Цитата ячейки коэффициента: тот же конверт, что `_citation`, подпись — из привязки строки."""

    sheet, cell = fact["cell_id"].split("!", 1)
    return {
        "cell_id": fact["cell_id"],
        "sheet": sheet,
        "cell": cell,
        "row_key": fact["row_key"],
        "axis_id": fact["axis_id"],
        "period_id": fact["period_id"],
        "label": row.get("label"),
        "value": _decimal_text(fact.get("value_dec")),
        "value_status": fact.get("value_status"),
        "normalized_value": _decimal_text(fact.get("normalized_value")),
        "binding_key": row.get("binding_key"),
    }


def _citations(data: AuditInput, findings: list[Finding]) -> list[dict]:
    seen: set[str] = set()
    out = []
    for finding in findings:
        for location in finding.locations:
            if not location.cell_id or location.cell_id in seen:
                continue
            cited = _citation(data, location)
            if cited is not None:
                seen.add(location.cell_id)
                out.append(cited)
    return out


def _finding_row(job_id: str, build: str, state_seq: int, analysis_id: str, finding: Finding) -> dict:
    first = finding.locations[0] if finding.locations else Location(None, None, None, None)
    return {
        "analysis_id": analysis_id,
        "model_id": job_id,
        "build_key": build,
        "state_seq": state_seq,
        "code": finding.code,
        "rule_version": finding.version,
        "error_class": finding.error_class,
        "severity": finding.severity,
        "fingerprint": finding.fingerprint,
        "binding_key": finding.binding_key,
        "row_key": first.row_key,
        "axis_id": first.axis_id,
        "period_id": first.period_id,
        "cell_id": first.cell_id,
        "params_json": json.dumps(finding.params, ensure_ascii=False, sort_keys=True, default=str),
        "basis_json": json.dumps(list(finding.basis), ensure_ascii=False),
        "locations_json": json.dumps([item.as_dict() for item in finding.locations], ensure_ascii=False),
        "truncated": finding.truncated,
    }


def _page(items: list[dict], *, key: str, page_size: int, page_token: str | None) -> tuple[list[dict], str | None]:
    if page_size < 1 or page_size > 1000:
        raise InvalidArgument("page_size должен быть от 1 до 1000")
    start = 0
    if page_token:
        identifiers = [item.get(key) for item in items]
        if page_token not in identifiers:
            raise InvalidArgument("неизвестный page_token")
        start = identifiers.index(page_token) + 1
    page = items[start : start + page_size]
    token = page[-1][key] if page and start + page_size < len(items) else None
    return page, token


def _page_size(raw) -> int:
    if raw in (None, ""):
        return 50
    try:
        return int(str(raw))
    except ValueError:
        raise InvalidArgument("page_size должен быть целым числом") from None


def _codes(raw: str | None) -> set[str] | None:
    if not raw:
        return None
    return {item.strip() for item in raw.split(",") if item.strip()}


class Analyses:
    """Сценарии `…/analyses` и `…/findings`. Чтение книги — через `FasService`."""

    def __init__(self, service) -> None:
        self.service = service
        self.rules = load_rules()

    @property
    def store(self):
        return self.service.store

    def capabilities(self) -> list[dict]:
        return [rule.describe() for rule in self.rules.values()]

    async def _target(self, job_id: str, actor: Actor, build_key: str | None, *, wait_sec: float):
        from finance_analysis.application.service import Accepted, Freshness

        svc = self.service
        ensured = await svc.ensure(job_id, actor, wait_sec=min(wait_sec, svc.settings.load_sync_sec))
        if isinstance(ensured, Accepted):
            return ensured
        fresh = isinstance(ensured, Freshness)
        head = ensured.head if isinstance(ensured, Freshness) else ensured
        if head is None:
            raise NotFound("книга не загружена")
        build = head.build_key if build_key in (None, "") else check_build(str(build_key))
        try:
            manifest = await svc._manifest(job_id, build)
        except NotFound:
            raise NotFound("сборка не найдена") from None
        derived = None
        if build != head.build_key:
            derived = await self._derived_at(job_id, build, head.state_seq)
            if derived is None and head.derive_key:
                derived = await svc.derive_for_build(job_id, head, build)
        return Target(head=head, build=build, manifest=manifest, fresh=fresh, derived=derived)

    async def _derived_at(self, job_id: str, build: str, state_seq: int) -> str | None:
        async for item in self.store.list(f"books/{job_id}/{build}/derived/"):
            if not item.key.endswith("/_done.json"):
                continue
            done = json.loads(await self.store.get(item.key))
            if int(done.get("state_seq") or 0) == state_seq:
                return done.get("derive_key")
        return None

    async def _input(self, job_id: str, target: Target, needed: frozenset[str]) -> AuditInput:
        files = target.manifest.get("files") or {}

        async def rows(dataset: str) -> list[dict]:
            rel = next((item for item in files if str(item).endswith(f"/{dataset}.parquet")), None)
            if rel is None:
                return []
            raw = await self.store.get(f"books/{job_id}/{target.build}/{rel}")
            return await self.service.parquet.read(raw)

        dim_rows = await rows("dim_row")
        for row in dim_rows:
            raw = row.get("formula_exceptions_json")
            row["formula_exceptions"] = json.loads(raw) if raw else []
        periods = await rows("dim_period")
        bindings: list[dict] = []
        row_semantics: list[dict] = []
        try:
            pinned = _pinned(target)
            bindings = await self.service._dataset_rows(job_id, pinned, "bindings")
            semantics = await self.service._dataset_rows(job_id, pinned, "period_semantics")
            if "semantics" in needed:
                row_semantics = await self.service._dataset_rows(job_id, pinned, "row_semantics")
        except (NotFound, StopIteration):
            semantics = []
        phases = {(row["axis_id"], row["period_id"]): row.get("phase") for row in semantics if row.get("phase")}
        for period in periods:
            phase = phases.get((period["axis_id"], period["period_id"]))
            if phase:
                period["phase"] = phase
        return AuditInput(
            rows=dim_rows,
            periods=periods,
            facts=await rows("fact_observation"),
            links=await rows("graph_links") if "links" in needed else [],
            counters=dict(target.manifest.get("builder_counters") or {}),
            bindings=bindings,
            semantics=row_semantics,
            composition=await self.service.glossary.composition(target.head.versions.get("glossary")),
            profile=await self._profile(target.head),
            absent=await self._absent(job_id, target),
        )

    async def _absent(self, job_id: str, target: Target) -> frozenset[str]:
        """`concept.absent` журнала на закреплённом `state_seq` (ключ — книга и понятие, §5.10.5)."""

        events = await self.service.guard.read_all(job_id)
        return absent_in_journal([event for event in events if int(event["seq"]) <= target.head.state_seq])

    async def _profile(self, head: Head) -> dict:
        """Тело профиля книги: знак, маркер, варианты ADSCR и LLCR (§5.7)."""

        profile = head.versions.get("profile") or ""
        profile_id = profile.split("@", 1)[0] if "@" in profile else None
        return (await self.service.glossary.profile_body(profile_id) if profile_id else None) or {}

    async def _annotate(self, envelope: dict) -> None:
        """Текст сводки и находок пишется в результат один раз. GET его не пересчитывает."""

        summary = envelope.get("summary") or {}
        findings = (envelope.get("result_data") or {}).get("findings") or []
        items = [
            {
                "id": "summary",
                "code": summary.get("code") or "analysis",
                "params": summary.get("params") or {},
                "title": None,
            }
        ]
        for item in findings:
            items.append(
                {
                    "id": item.get("fingerprint") or item.get("code"),
                    "code": item.get("code") or "",
                    "params": item.get("params") or {},
                    "title": item.get("code"),
                }
            )
        texts = await narrate(getattr(self.service.models, "llm", None), items, effective(self.service.settings.llm_timeout_sec * 1000))
        summary["text"] = texts.get("summary")
        envelope["summary"] = summary
        for item in findings:
            item["explanation"] = texts.get(item.get("fingerprint") or item.get("code"))

    async def report(self, job_id: str, analysis_id: str, fmt: str) -> tuple[bytes, str]:
        result = await self.result(job_id, analysis_id)
        if fmt == "md":
            return render_markdown(result).encode(), "text/markdown; charset=utf-8"
        if fmt == "json":
            return render_json(result), "application/json"
        raise NotAcceptable("формат json или md", extra={"formats": ["json", "md"]})

    async def run(self, job_id: str, body: dict, actor: Actor, *, wait_sec: float):
        from finance_analysis.application.service import Accepted

        if "include" in body and body["include"] is not None:
            raise InvalidArgument("поле include не принимается")
        if "include" in body:
            body = {key: value for key, value in body.items() if key != "include"}
        body = _prepare_analysis_body(body)
        kind = body.get("type")
        render = body.get("render")
        if render not in (None, "json", "md"):
            raise NotAcceptable("render: json или md", extra={"formats": ["json", "md"]})
        if kind == "ratios":
            return await self._ratios(job_id, body, actor, wait_sec=wait_sec)
        if kind == "impact":
            return await self._impact(job_id, body, actor, wait_sec=wait_sec)
        if kind == "full":
            return await self._full(job_id, body, actor, wait_sec=wait_sec)
        if kind != "audit":
            raise InvalidArgument("type должен быть audit", extra={"supported": list(ANALYSIS_TYPES)})
        rules = select_rules(self.rules, body.get("rules"))
        scope = _scope(body)
        notes: list[dict] = []
        target = await self._target(job_id, actor, body.get("build_key"), wait_sec=wait_sec)
        if isinstance(target, Accepted):
            return target
        analysis_id = str(ULID())
        work = self.service.spawn(self._execute(job_id, target, analysis_id, rules, scope, notes, actor))
        if body.get("async") is True:
            return await self._defer(job_id, actor, analysis_id, work)
        budget = max(0.1, min(wait_sec, self.service.settings.sync_deadline_ms / 1000) * 0.8)
        try:
            return await asyncio.wait_for(asyncio.shield(work), timeout=budget)
        except TimeoutError:
            return await self._defer(job_id, actor, analysis_id, work)

    async def _impact(self, job_id: str, body: dict, actor: Actor, *, wait_sec: float):
        from finance_analysis.application.service import Accepted

        spec = _impact_target(body.get("target"))
        target = await self._target(job_id, actor, body.get("build_key"), wait_sec=wait_sec)
        if isinstance(target, Accepted):
            return target
        analysis_id = str(ULID())
        work = self.service.spawn(self._execute_impact(job_id, target, analysis_id, spec, body, actor))
        wide = False
        try:
            periods = await self.service._dataset_rows(job_id, target.head, "dim_period")
            wide = len(periods) > self.service.settings.sync_max_periods
        except (NotFound, StopIteration):
            wide = False
        if body.get("async") is True or wide:
            return await self._defer(job_id, actor, analysis_id, work, kind="impact")
        budget = max(0.1, min(wait_sec, self.service.settings.sync_deadline_ms / 1000) * 0.8)
        try:
            return await asyncio.wait_for(asyncio.shield(work), timeout=budget)
        except TimeoutError:
            return await self._defer(job_id, actor, analysis_id, work, kind="impact")

    async def _full(self, job_id: str, body: dict, actor: Actor, *, wait_sec: float):
        """Всегда 202. shortcut: тот же in-process spawn, что у audit, не отдельная задача Taskiq."""

        from finance_analysis.application.service import Accepted

        spec = _impact_target(body.get("target")) if body.get("target") else None
        metrics = _full_metrics(body)
        target = await self._target(job_id, actor, body.get("build_key"), wait_sec=wait_sec)
        if isinstance(target, Accepted):
            return target
        analysis_id = str(ULID())
        op = await self.service.create_op("analysis", job_id, actor, {"analysis_id": analysis_id, "type": "full"})
        self.service.spawn(self._execute_full(job_id, target, analysis_id, list(metrics), spec, body, actor, op["id"]))
        return Accepted(op)

    async def _ratios(self, job_id: str, body: dict, actor: Actor, *, wait_sec: float):
        from finance_analysis.application.service import Accepted

        metrics = _check_metrics(body.get("metrics"))
        target = await self._target(job_id, actor, body.get("build_key"), wait_sec=wait_sec)
        if isinstance(target, Accepted):
            return target
        analysis_id = str(ULID())
        work = self.service.spawn(self._execute_ratios(job_id, target, analysis_id, list(metrics), actor))
        wide = False
        try:
            periods = await self.service._dataset_rows(job_id, target.head, "dim_period")
            wide = len(periods) > self.service.settings.sync_max_periods
        except (NotFound, StopIteration):
            wide = False
        if body.get("async") is True or wide:
            return await self._defer(job_id, actor, analysis_id, work, kind="ratios")
        budget = max(0.1, min(wait_sec, self.service.settings.sync_deadline_ms / 1000) * 0.8)
        try:
            return await asyncio.wait_for(asyncio.shield(work), timeout=budget)
        except TimeoutError:
            return await self._defer(job_id, actor, analysis_id, work, kind="ratios")

    async def compute_metrics(self, job_id: str, target: Target, metrics: list[str]) -> dict:
        """Строки метрик на закреплённой сборке и состоянии; общий код `ratios` и `:compare`."""

        svc = self.service
        pinned = _pinned(target)
        bindings = await svc._dataset_rows(job_id, pinned, "bindings")
        facts = await svc._dataset_rows(job_id, pinned, "fact_observation")
        periods = await svc._dataset_rows(job_id, pinned, "dim_period")
        try:
            semantics = await svc._dataset_rows(job_id, pinned, "period_semantics")
        except (NotFound, StopIteration):
            semantics = []
        phase_of = {(row["axis_id"], row["period_id"]): row.get("phase") for row in semantics}
        explicit = any(phase_of.values())
        body = await self._profile(target.head)
        direction = body.get("adscr_direction") or "lookback"
        basis = body.get("llcr_basis") or "period_end"
        if direction not in DIRECTIONS or basis not in BASES:
            raise InvalidArgument(
                "профиль: adscr_direction или llcr_basis вне списка",
                extra={"directions": list(DIRECTIONS), "bases": list(BASES)},
            )
        common = {
            "facts": facts,
            "bindings": bindings,
            "periods": periods,
            "period_phase": phase_of,
            "explicit_phases": explicit,
            "sign_convention": body.get("sign_convention") or "outflow_negative",
            "marker_class": body.get("marker_class"),
            "absent": await self._absent(job_id, target),
        }
        computed = []
        needs = []
        warnings = []
        for metric in metrics:
            if metric in LOAN_LIFE:
                result = loan_life_ratio(metric, basis=basis, **common)
            elif metric in REDUCED:
                result = dscr_reductions(metric, **common)
            elif metric == "adscr":
                result = adscr(direction=direction, **common)
            else:
                result = coverage_ratio(metric=metric, **common)
            needs.extend(result["needs_input"])
            warnings.extend(result["warnings"])
            computed.extend({**row, "metric": metric} for row in result["rows"])
        return {
            "rows": computed,
            "needs_input": needs,
            "warnings": warnings,
            "bindings": bindings,
            "facts": facts,
            "periods": periods,
            "phase_of": phase_of,
            "profile": body,
            "absent": common["absent"],
        }

    async def _execute_ratios(self, job_id: str, target: Target, analysis_id: str, metrics: list[str], actor: Actor) -> dict:
        started = _now()
        head = target.head
        got = await self.compute_metrics(job_id, target, metrics)
        computed, needs, warnings = got["rows"], got["needs_input"], got["warnings"]
        text_rows, citations = _ratio_rows(got)
        attached = await self._metric_findings(
            job_id, target, metrics, got["bindings"], got["facts"], got["periods"], got["phase_of"], got["profile"], got["absent"]
        )
        envelope = {
            "analysis_id": analysis_id,
            "status": "succeeded",
            "builder_ref": target.manifest.get("builder_ref"),
            "versions": {**head.versions, "fas": FAS_VERSION, "state_seq": head.state_seq, "derive_key": target.derive_key},
            "build_key": target.build,
            "is_latest": target.is_latest,
            "summary": {"code": "ratios_completed", "params": {"rows": len(computed)}, "text": None},
            "result_data": {
                "findings": [item.as_dict(target.manifest.get("builder_ref")) for item in attached],
                "ratios": text_rows,
                "series": [],
                "expression": None,
                "impact": None,
            },
            "tables": [],
            "charts": [],
            "citations": citations,
            "needs_input": needs,
            "warnings": warnings,
        }
        await self._annotate(envelope)
        stored = _ratio_stored(job_id, target, analysis_id, head, computed)
        await self._save_tables(job_id, target, analysis_id, "ratios", {"ratios": stored}, envelope, actor, started)
        return envelope

    async def _execute_impact(self, job_id: str, target: Target, analysis_id: str, spec: dict, body: dict, actor: Actor) -> dict:
        started = _now()
        view, warnings = await self._impact_of(job_id, target, spec, body)
        head = target.head
        envelope = {
            "analysis_id": analysis_id,
            "status": "succeeded",
            "builder_ref": target.manifest.get("builder_ref"),
            "versions": {**head.versions, "fas": FAS_VERSION, "state_seq": head.state_seq, "derive_key": target.derive_key},
            "build_key": target.build,
            "is_latest": target.is_latest,
            "summary": {"code": "impact_completed", "params": {"drivers": len(view["drivers"])}, "text": None},
            "result_data": {"findings": [], "ratios": [], "series": [], "expression": None, "impact": view},
            "tables": [],
            "charts": [],
            "citations": [],
            "needs_input": [],
            "warnings": warnings,
        }
        await self._annotate(envelope)
        await self._save_tables(job_id, target, analysis_id, "impact", {}, envelope, actor, started)
        return envelope

    async def _impact_of(self, job_id: str, target: Target, spec: dict, body: dict) -> tuple[dict, list[dict]]:
        direction = body.get("direction") or "precedents"
        if direction not in {"precedents", "dependents"}:
            raise InvalidArgument("direction: precedents или dependents")
        depth = _trace_depth(body.get("depth"), {})
        data = await self._input(job_id, target, frozenset({"links"}))
        origins = _origins(data, spec)
        locations = [Location(cell, None, None, None) for cell in origins]
        trace = await self._trace(job_id, target, data, locations, direction=direction, depth=depth)
        try:
            marker = await self._last_audit(job_id, target)
            findings = list(marker["result"]["result_data"]["findings"])
        except NoAudit:
            findings = []
        origin = spec.get("cell_id") or spec.get("row_key") or spec.get("concept")
        view = impact_view(trace, data.link_cells, findings, str(origin), data.facts_by_cell)
        return view, list(view["warnings"])

    async def _execute_full(
        self,
        job_id: str,
        target: Target,
        analysis_id: str,
        metrics: list[str],
        spec: dict | None,
        body: dict,
        actor: Actor,
        op_id: str,
    ) -> None:
        try:
            if await self._cancelled(op_id):
                return
            started = _now()
            rules = select_rules(self.rules, body.get("rules"))
            scope = _scope(body)
            await self.service.progress_op(op_id, "loading")
            data = await self._input(job_id, target, requirements(rules) | {"links"})
            if await self._cancelled(op_id):
                return
            await self.service.progress_op(op_id, "semantics")
            await self.service.progress_op(op_id, "mapping")
            await self.service.progress_op(op_id, "evaluating")
            got = await self.compute_metrics(job_id, target, metrics)
            found = await anyio.to_thread.run_sync(lambda: run_rules(rules, data), limiter=self.service._cpu)
            bound: set[str] = set()
            if "concepts" in scope:
                bound = await self._bound_keys(job_id, target, target.derive_key, scope["concepts"])
            findings = [item for item in found if _in_scope(item, scope, data, bound)]
            warnings = list(got["warnings"])
            impact = None
            if spec:
                impact, extra = await self._impact_of(job_id, target, spec, body)
                warnings.extend(extra)
            await self.service.progress_op(op_id, "rendering")
            text_rows, citations = _ratio_rows(got)
            head = target.head
            envelope = {
                "analysis_id": analysis_id,
                "status": "succeeded",
                "builder_ref": target.manifest.get("builder_ref"),
                "versions": {
                    **head.versions,
                    "rules": {rule.code: rule.version for rule in rules},
                    "fas": FAS_VERSION,
                    "state_seq": head.state_seq,
                    "derive_key": target.derive_key,
                },
                "build_key": target.build,
                "is_latest": target.is_latest,
                "summary": {"code": "full_completed", "params": {"metrics": metrics, "findings": len(findings)}, "text": None},
                "result_data": {
                    "findings": [item.as_dict(target.manifest.get("builder_ref")) for item in findings],
                    "ratios": text_rows,
                    "series": [],
                    "expression": None,
                    "impact": impact,
                },
                "tables": [],
                "charts": [],
                "citations": citations,
                "needs_input": got["needs_input"],
                "warnings": warnings,
            }
            await self._annotate(envelope)
            if await self._cancelled(op_id):
                return
            stored = [_finding_row(job_id, target.build, head.state_seq, analysis_id, item) for item in findings]
            ratio_stored = _ratio_stored(job_id, target, analysis_id, head, got["rows"])
            tables = {}
            if stored:
                tables["findings"] = stored
            if ratio_stored:
                tables["ratios"] = ratio_stored
            await self._save_tables(job_id, target, analysis_id, "full", tables, envelope, actor, started)
            await self.service.finish_op(
                op_id,
                "succeeded",
                result={"analysis_id": analysis_id, "resource": f"/v1/books/{job_id}/analyses/{analysis_id}"},
            )
        except Exception as exc:  # noqa: BLE001 — ошибка полного отчёта закрывает операцию
            if await self._cancelled(op_id):
                return
            await self.service.finish_op(op_id, "failed", error={"code": getattr(exc, "code", "failed"), "detail": str(exc)})

    async def _cancelled(self, op_id: str) -> bool:
        current = await self.service.get_op(op_id)
        if current["status"] in {"succeeded", "failed", "cancelled"}:
            return True
        if not await self.service.support.cache_get(f"fas:op:{op_id}:cancel"):
            return False
        await self.service.finish_op(op_id, "cancelled")
        return True

    async def _metric_findings(
        self, job_id, target: Target, metrics, bindings, facts, periods, phase_of, profile, absent
    ) -> list[Finding]:
        """Находки, которые прикрепляются к результату метрики (§6.2): статус метрики они не меняют.

        `period_grain_mismatch` — к метрикам семейства DSCR; `missing_total_row` —
        если понятие, нужное запрошенной метрике, отмечено `concept.absent`.
        """

        wanted = set(metrics)
        rules = []
        if wanted & set(METRIC_INPUTS["debt_service"]):
            rules.append(PERIOD_GRAIN_MISMATCH)
        absent_needed = {concept for concept, users in METRIC_INPUTS.items() if wanted & set(users)}
        if absent_needed:
            rules.append(MISSING_TOTAL_ROW)
        if not rules:
            return []
        dim_rows = await self.service._dataset_rows(job_id, _pinned(target), "dim_row")
        staged = [{**period, "phase": phase_of.get((period["axis_id"], period["period_id"]))} for period in periods]
        data = AuditInput(
            rows=dim_rows,
            periods=staged,
            facts=facts,
            bindings=bindings,
            composition=await self.service.glossary.composition(target.head.versions.get("glossary")),
            profile=profile or {},
            absent=absent,
        )
        found = run_rules(rules, data)
        return [item for item in found if item.code != "missing_total_row" or item.params.get("concept") in absent_needed]

    async def _save_tables(self, job_id, target: Target, analysis_id, kind, tables, envelope, actor, started) -> None:
        svc = self.service
        head = target.head
        finished = _now()
        run_row = {
            "analysis_id": analysis_id,
            "model_id": job_id,
            "build_key": target.build,
            "state_seq": head.state_seq,
            "analysis_type": kind,
            "status": envelope["status"],
            "glossary_version": head.versions.get("glossary"),
            "taxonomy_version": head.versions.get("taxonomy"),
            "calibrator_version": head.versions.get("calibrator"),
            "rules_version": "{}",
            "metrics_version": kind,
            "profile_id": head.versions.get("profile"),
            "profile_version": head.versions.get("profile"),
            "derive_key": target.derive_key,
            "fas_version": FAS_VERSION,
            "created_at_utc": started,
            "finished_at_utc": finished,
        }
        files = {}
        for dataset, rows in {**tables, "run": [run_row]}.items():
            payload, count = await svc.parquet.write(dataset, rows, build_key=target.build)
            name = f"{dataset}.parquet"
            await self.store.put_if_absent(keys.result_key(job_id, target.build, analysis_id, name), payload)
            files[keys.result_rel(analysis_id, name)] = {
                "sha256": sha256_bytes(payload),
                "rows": count,
                "bytes": len(payload),
                "schema": await svc.parquet.schema_tag(dataset),
            }
        marker = {
            "analysis_id": analysis_id,
            "analysis_type": kind,
            "status": envelope["status"],
            "build_key": target.build,
            "state_seq": head.state_seq,
            "derive_key": target.derive_key,
            "created_at_utc": _stamp(started),
            "finished_at_utc": _stamp(finished),
            "files": files,
            "result": envelope,
        }
        await self.store.put_if_absent(keys.result_key(job_id, target.build, analysis_id, "result.json"), _dumps(marker))
        index = {
            "analysis_id": analysis_id,
            "analysis_type": kind,
            "status": envelope["status"],
            "build_key": target.build,
            "state_seq": head.state_seq,
            "derive_key": target.derive_key,
            "issued_at": _stamp(finished),
            "created_at_utc": _stamp(started),
            "finding_count": 0,
            "rules": [],
            "actor": {"user_id": actor.user_id, "client_id": actor.client_id},
            "revoked": False,
        }
        try:
            await self.store.put_if_absent(keys.report_index_key(job_id, analysis_id), _dumps(index))
        except AlreadyExists:
            pass

    async def _defer(self, job_id: str, actor: Actor, analysis_id: str, work: asyncio.Task, *, kind: str = "audit"):
        from finance_analysis.application.service import Accepted

        svc = self.service
        op = await svc.create_op("analysis", job_id, actor, {"analysis_id": analysis_id, "type": kind})

        async def _finish() -> None:
            try:
                await work
            except Exception as exc:  # noqa: BLE001 — любая ошибка прогона закрывает операцию
                await svc.finish_op(op["id"], "failed", error={"code": getattr(exc, "code", "failed"), "detail": str(exc)})
                return
            await svc.finish_op(
                op["id"],
                "succeeded",
                result={"analysis_id": analysis_id, "resource": f"/v1/books/{job_id}/analyses/{analysis_id}"},
            )

        svc.spawn(_finish())
        return Accepted(op)

    async def _execute(
        self,
        job_id: str,
        target: Target,
        analysis_id: str,
        rules: list,
        scope: dict,
        notes: list[dict],
        actor: Actor,
    ) -> dict:
        started = _now()
        needed = requirements(rules)
        data = await self._input(job_id, target, needed)
        found = await anyio.to_thread.run_sync(lambda: run_rules(rules, data), limiter=self.service._cpu)
        bound: set[str] = set()
        if "concepts" in scope:
            bound = await self._bound_keys(job_id, target, target.derive_key, scope["concepts"])
        findings = [item for item in found if _in_scope(item, scope, data, bound)]
        warnings = list(notes)
        if target.fresh:
            warnings.insert(0, {"code": "freshness_unknown", "params": {}})
        if COUNTER_RULES_INPUT in needed and not target.manifest.get("builder_counters"):
            skipped = sorted(rule.code for rule in rules if COUNTER_RULES_INPUT in rule.requires)
            warnings.append({"code": "builder_counters_missing", "params": {"rules": skipped}})
        envelope = self._envelope(job_id, target, analysis_id, rules, data, findings, warnings)
        await self._annotate(envelope)
        await self._save(job_id, target, analysis_id, rules, findings, envelope, actor, started)
        return envelope

    def _envelope(self, job_id, target: Target, analysis_id, rules, data, findings, warnings) -> dict:
        ref = target.manifest.get("builder_ref")
        severity = Counter(item.severity for item in findings)
        by_rule = Counter((item.code, item.severity) for item in findings)
        head = target.head
        return {
            "analysis_id": analysis_id,
            "status": "succeeded",
            "builder_ref": ref,
            "versions": {
                **head.versions,
                "latest_glossary": head.versions.get("glossary"),
                "rules": {rule.code: rule.version for rule in rules},
                "fas": FAS_VERSION,
                "state_seq": head.state_seq,
                "derive_key": target.derive_key,
            },
            "build_key": target.build,
            "is_latest": target.is_latest,
            "summary": {
                "code": "audit_completed",
                "params": {"findings": len(findings), "by_severity": dict(sorted(severity.items()))},
                "text": None,
            },
            "result_data": {
                "findings": [item.as_dict(ref) for item in findings],
                "ratios": [],
                "series": [],
                "expression": None,
                "impact": None,
            },
            "tables": [
                {
                    "id": "findings_by_rule",
                    "columns": ["code", "severity", "count"],
                    "rows": [[code, sev, count] for (code, sev), count in sorted(by_rule.items())],
                }
            ],
            "charts": [],
            "citations": _citations(data, findings),
            "needs_input": [],
            "warnings": warnings,
        }

    async def _save(self, job_id, target: Target, analysis_id, rules, findings, envelope, actor, started) -> None:
        svc = self.service
        head = target.head
        finished = _now()
        tables = {
            "findings": [_finding_row(job_id, target.build, head.state_seq, analysis_id, item) for item in findings],
            "run": [
                {
                    "analysis_id": analysis_id,
                    "model_id": job_id,
                    "build_key": target.build,
                    "state_seq": head.state_seq,
                    "analysis_type": "audit",
                    "status": envelope["status"],
                    "glossary_version": head.versions.get("glossary"),
                    "taxonomy_version": head.versions.get("taxonomy"),
                    "calibrator_version": head.versions.get("calibrator"),
                    "rules_version": json.dumps(envelope["versions"]["rules"], sort_keys=True),
                    "metrics_version": None,
                    "profile_id": head.versions.get("profile"),
                    "profile_version": head.versions.get("profile"),
                    "derive_key": target.derive_key,
                    "fas_version": FAS_VERSION,
                    "created_at_utc": started,
                    "finished_at_utc": finished,
                }
            ],
        }
        files = {}
        for dataset, rows in tables.items():
            payload, count = await svc.parquet.write(dataset, rows, build_key=target.build)
            name = f"{dataset}.parquet"
            await self.store.put_if_absent(keys.result_key(job_id, target.build, analysis_id, name), payload)
            files[keys.result_rel(analysis_id, name)] = {
                "sha256": sha256_bytes(payload),
                "rows": count,
                "bytes": len(payload),
                "schema": await svc.parquet.schema_tag(dataset),
            }
        marker = {
            "analysis_id": analysis_id,
            "analysis_type": "audit",
            "status": envelope["status"],
            "build_key": target.build,
            "state_seq": head.state_seq,
            "derive_key": target.derive_key,
            "created_at_utc": _stamp(started),
            "finished_at_utc": _stamp(finished),
            "files": files,
            "result": envelope,
        }
        await self.store.put_if_absent(keys.result_key(job_id, target.build, analysis_id, "result.json"), _dumps(marker))
        index = {
            "analysis_id": analysis_id,
            "analysis_type": "audit",
            "status": envelope["status"],
            "build_key": target.build,
            "state_seq": head.state_seq,
            "derive_key": target.derive_key,
            "issued_at": _stamp(finished),
            "created_at_utc": _stamp(started),
            "finding_count": len(findings),
            "rules": sorted(rule.code for rule in rules),
            "actor": {"user_id": actor.user_id, "client_id": actor.client_id},
            "revoked": False,
        }
        try:
            await self.store.put_if_absent(keys.report_index_key(job_id, analysis_id), _dumps(index))
        except AlreadyExists:
            pass

    async def _reports(self, job_id: str) -> list[dict]:
        found = []
        async for item in self.store.list(keys.report_index_prefix(job_id)):
            if item.key.endswith(".json"):
                found.append(json.loads(await self.store.get(item.key)))
        found.sort(key=lambda item: item.get("analysis_id") or "", reverse=True)
        return found

    async def history(
        self,
        job_id: str,
        *,
        kind: str | None = None,
        status: str | None = None,
        page_size: int = 50,
        page_token: str | None = None,
    ) -> dict:
        head, _token = await self.service._read_head(job_id)
        items = []
        for report in await self._reports(job_id):
            if kind and report.get("analysis_type") != kind:
                continue
            if status and report.get("status") != status:
                continue
            items.append(
                {
                    **report,
                    "current": bool(
                        head and report.get("build_key") == head.build_key and report.get("state_seq") == head.state_seq
                    ),
                }
            )
        page, token = _page(items, key="analysis_id", page_size=page_size, page_token=page_token)
        return {"items": page, "next_page_token": token}

    async def _marker(self, job_id: str, report: dict) -> dict:
        key = keys.result_key(job_id, report["build_key"], report["analysis_id"], "result.json")
        return json.loads(await self.store.get(key))

    async def result(self, job_id: str, analysis_id: str) -> dict:
        check_ulid(analysis_id)
        try:
            report = json.loads(await self.store.get(keys.report_index_key(job_id, analysis_id)))
            marker = await self._marker(job_id, report)
        except NotFound:
            raise NotFound("анализ не найден") from None
        head, _token = await self.service._read_head(job_id)
        result = dict(marker["result"])
        result["is_latest"] = bool(
            head and marker["build_key"] == head.build_key and marker["state_seq"] == head.state_seq
        )
        return result

    async def _last_audit(self, job_id: str, target: Target) -> dict:
        for report in await self._reports(job_id):
            if (
                report.get("analysis_type") == "audit"
                and report.get("status") == "succeeded"
                and report.get("build_key") == target.build
                and report.get("state_seq") == target.head.state_seq
            ):
                return await self._marker(job_id, report)
        raise NoAudit(
            "на этой сборке и состоянии аудита ещё не было",
            extra={
                "build_key": target.build,
                "state_seq": target.head.state_seq,
                "hint": {"method": "POST", "path": f"/v1/books/{job_id}/analyses", "body": {"type": "audit"}},
            },
        )

    async def findings(self, job_id: str, actor: Actor, query: dict, *, wait_sec: float):
        from finance_analysis.application.service import Accepted

        target = await self._target(job_id, actor, query.get("build_key"), wait_sec=wait_sec)
        if isinstance(target, Accepted):
            return target
        marker = await self._last_audit(job_id, target)
        items = list(marker["result"]["result_data"]["findings"])
        rules = _codes(query.get("rule"))
        severities = _codes(query.get("severity"))
        if rules is not None:
            items = [item for item in items if item["code"] in rules]
        if severities is not None:
            items = [item for item in items if item["severity"] in severities]
        if query.get("concept"):
            bound = await self._bound_keys(job_id, target, marker.get("derive_key"), {str(query["concept"])})
            items = [item for item in items if item.get("binding_key") in bound]
        page, token = _page(
            items,
            key="fingerprint",
            page_size=_page_size(query.get("page_size")),
            page_token=query.get("page_token"),
        )
        return {
            "items": page,
            "next_page_token": token,
            "analysis_id": marker["analysis_id"],
            "build_key": target.build,
            "state_seq": target.head.state_seq,
            "is_latest": target.is_latest,
            "warnings": [{"code": "freshness_unknown", "params": {}}] if target.fresh else [],
        }

    async def _bound_keys(self, job_id: str, target: Target, derive: str | None, concepts: set[str]) -> set[str]:
        """Привязки той сборки и того состояния, на которых шёл аудит."""

        if not derive:
            raise InvalidArgument(
                "фильтр по понятиям: у сборки нет производного состояния на этом state_seq",
                extra={"build_key": target.build, "state_seq": target.head.state_seq},
            )
        pinned = Head(build_key=target.build, state_seq=target.head.state_seq, derive_key=derive, versions={})
        bindings = await self.service._dataset_rows(job_id, pinned, "bindings")
        return {row["binding_key"] for row in bindings if row.get("effective_concept") in concepts}

    async def finding(self, job_id: str, print_: str, actor: Actor, query: dict, *, wait_sec: float):
        from finance_analysis.application.service import Accepted

        check_fingerprint(print_)
        target = await self._target(job_id, actor, query.get("build_key"), wait_sec=wait_sec)
        if isinstance(target, Accepted):
            return target
        marker = await self._last_audit(job_id, target)
        found = next(
            (item for item in marker["result"]["result_data"]["findings"] if item["fingerprint"] == print_),
            None,
        )
        if found is None:
            raise NotFound("находка не найдена в последнем аудите")
        data = await self._input(job_id, target, frozenset({"links"}))
        rule = self.rules.get(found["code"])
        locations = [Location(**item) for item in found["locations"]]
        direction = query.get("direction") or "precedents"
        if direction not in {"precedents", "dependents"}:
            raise InvalidArgument("direction: precedents или dependents")
        depth = _trace_depth(query.get("depth"), found)
        trace = await self._trace(job_id, target, data, locations, direction=direction, depth=depth)
        return {
            "finding": found,
            "analysis_id": marker["analysis_id"],
            "build_key": target.build,
            "state_seq": target.head.state_seq,
            "is_latest": target.is_latest,
            "rule": rule.describe() if rule else None,
            "explanation": {
                "title": rule.title if rule else found["code"],
                "basis": found.get("basis") or [],
                "params": found.get("params") or {},
                "text": found.get("explanation")
                if isinstance(found.get("explanation"), str)
                else template_text(found["code"], found.get("params"), rule.title if rule else None),
            },
            "citations": [item for item in (_citation(data, location) for location in locations) if item],
            "trace": trace,
        }

    async def _trace(self, job_id, target: Target, data: AuditInput, locations, *, direction: str, depth: int) -> dict:
        """Цепочка ячеек находки — trace builder (R5, §2.1), кэш Redis по `summary_etag`.

        Если builder не отвечает или публикация пересобирается, цепочка строится
        на один уровень по `graph_links` сборки и помечается `source: graph_links`.
        """

        origins = [item.cell_id for item in locations if item.cell_id][:TRACE_CELLS]
        etag = (target.manifest.get("builder_ref") or {}).get("summary_etag") or target.build
        items = []
        try:
            for origin in origins:
                found = await self._builder_trace(job_id, etag, origin, direction, depth)
                if found is None:
                    raise DependencyUnavailable("builder пересобирает публикацию")
                items.append(found)
        except (DependencyUnavailable, NotFound) as exc:
            return {
                "source": "graph_links",
                "direction": "precedents",
                "depth": 1,
                "items": [_chain(data, Location(origin, None, None, None)) for origin in origins],
                "warnings": [{"code": "trace_unavailable", "params": {"detail": str(exc)}}],
                "truncated": len(locations) > len(origins),
            }
        return {
            "source": "builder",
            "direction": direction,
            "depth": depth,
            "items": items,
            "warnings": [],
            "truncated": len(locations) > len(origins),
        }

    async def _builder_trace(self, job_id: str, etag: str, origin: str, direction: str, depth: int) -> dict | None:
        svc = self.service
        digest = sha256_bytes(f"{etag}|{origin}|{direction}|{depth}".encode())[:32]
        key = f"fas:trace:{job_id}:{digest}"
        cached = await svc.support.cache_get(key)
        if cached:
            return json.loads(cached)
        found = await svc.builder.trace(job_id, origin, direction=direction, depth=depth)
        if isinstance(found, ReportNotReady):
            return None
        await svc.support.cache_set(key, _dumps(found), svc.settings.etag_ttl)
        return found


_NULL_ABSENT = ("metrics", "rules", "render", "build_key", "scope")
_TARGET_KEYS = ("cell_id", "row_key", "concept")


def _prepare_analysis_body(body: dict) -> dict:
    """null у необязательных полей и объект target из пустых значений — как отсутствие ключа."""

    prepared = dict(body)
    for key in _NULL_ABSENT:
        if key in prepared and prepared[key] is None:
            del prepared[key]
    target = prepared.get("target")
    if isinstance(target, dict) and not any(target.get(name) for name in _TARGET_KEYS):
        del prepared["target"]
    return prepared


def _full_metrics(body: dict) -> list[str]:
    """Нет ключа — DSCR. Пустой список и null проверяет `_check_metrics`."""

    metrics = body.get("metrics") if "metrics" in body else ["dscr"]
    return _check_metrics(metrics)


def _check_metrics(metrics) -> list[str]:
    if not isinstance(metrics, list) or not metrics:
        raise InvalidArgument("нужен список metrics", extra={"supported": list(RATIO_METRICS)})
    unknown = [item for item in metrics if item not in RATIO_METRICS]
    if unknown:
        raise InvalidArgument("неизвестная метрика", extra={"supported": list(RATIO_METRICS), "metrics": unknown})
    return list(metrics)


def _impact_target(raw) -> dict:
    if isinstance(raw, str) and raw.strip():
        text = raw.strip()
        if "|" in text:
            return {"row_key": text}
        if "!" in text:
            return {"cell_id": text}
        return {"concept": text}
    if isinstance(raw, dict):
        keys = [name for name in ("cell_id", "row_key", "concept") if raw.get(name)]
        if len(keys) == 1:
            return {keys[0]: str(raw[keys[0]])}
    raise InvalidArgument("target: одно из cell_id, row_key, concept")


def _origins(data: AuditInput, spec: dict) -> list[str]:
    row_key = spec.get("row_key")
    if spec.get("cell_id"):
        cell = str(spec["cell_id"])
        if cell not in data.facts_by_cell and cell not in data.link_cells:
            raise NotFound("ячейка не найдена", extra={"cell_id": cell})
        return [cell]
    if spec.get("concept"):
        primary = _primaries(data.bindings).get(spec["concept"])
        if primary is None:
            raise NotFound("понятие не привязано", extra={"concept": spec["concept"]})
        row_key = primary["row_key"]
    cells: list[str] = []
    for fact in data.facts:
        cell = fact.get("cell_id")
        if fact.get("row_key") == row_key and cell and cell not in cells:
            cells.append(cell)
    if not cells:
        for cell, link in data.link_cells.items():
            if link.row_key == row_key and cell not in cells:
                cells.append(cell)
    if not cells:
        raise NotFound("строка не найдена", extra={"row_key": row_key})
    return cells[:TRACE_CELLS]


def _ratio_rows(got: dict) -> tuple[list[dict], list[dict]]:
    text_rows = []
    citations: dict[str, dict] = {}
    bound = {item["row_key"]: item for item in got["bindings"] if item.get("row_key")}
    for row in got["rows"]:
        value = row.get("value")
        cells = ratio_cells(row, got["facts"], got["bindings"], got["periods"], got["absent"])
        for fact in cells:
            citations.setdefault(fact["cell_id"], _fact_citation(fact, bound.get(fact["row_key"], {})))
        text_rows.append(
            {
                **row,
                "value": _decimal_text(value),
                "value_f": None if value is None else float(value),
                "cell_ids": sorted(fact["cell_id"] for fact in cells),
            }
        )
    return text_rows, [citations[cell] for cell in sorted(citations)]


def _ratio_stored(job_id: str, target: Target, analysis_id: str, head: Head, rows: list[dict]) -> list[dict]:
    stored = []
    for row in rows:
        value = row.get("value")
        stored.append(
            {
                "analysis_id": analysis_id,
                "model_id": job_id,
                "build_key": target.build,
                "state_seq": head.state_seq,
                "glossary_version": head.versions.get("glossary"),
                "metric": row["metric"],
                "axis_id": row["axis_id"],
                "period_id": row["period_id"],
                "period_key_base": row.get("period_key_base"),
                "period_marker": row.get("period_marker"),
                "value": value,
                "value_f": None if value is None else float(value),
                "status": row["status"],
                "reason": row.get("reason"),
                "variant": row.get("variant"),
                "inputs_json": json.dumps(
                    {"metric": row["metric"], **{name: row[name] for name in RATIO_EXTRAS if row.get(name) is not None}},
                    sort_keys=True,
                ),
            }
        )
    return stored


def _trace_depth(raw, finding: dict) -> int:
    if raw in (None, ""):
        # Цикл обходится целиком: глубина не меньше числа его ячеек.
        members = (finding.get("params") or {}).get("members")
        return min(TRACE_DEPTH_MAX, max(TRACE_DEPTH, int(members or 0) + 1))
    try:
        depth = int(str(raw))
    except ValueError:
        raise InvalidArgument("depth должен быть целым числом") from None
    if depth < 1 or depth > TRACE_DEPTH_MAX:
        raise InvalidArgument(f"depth должен быть от 1 до {TRACE_DEPTH_MAX}")
    return depth


def _chain(data: AuditInput, location: Location) -> dict:
    link = data.link_cells.get(location.cell_id or "")
    refs = list(link.refs) if link else []
    precedents = []
    for ref in refs[:32]:
        placed = data.placed(ref)
        cited = _citation(data, placed)
        precedents.append(cited or placed.as_dict())
    return {
        "cell_id": location.cell_id,
        "formula": link.formula if link else None,
        "formula_class": link.formula_class if link else None,
        "precedents": precedents,
        "truncated": len(refs) > 32,
    }
