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
    sha256_bytes,
)
from finance_analysis.domain.errors import (
    AlreadyExists,
    InvalidArgument,
    NoAudit,
    NotFound,
)
from finance_analysis.domain.ids import build_key as check_build
from finance_analysis.domain.ids import fingerprint as check_fingerprint
from finance_analysis.domain.ids import ulid as check_ulid

# Типы из §3.2 и фаза, в которой они появляются (§12).
LATER_TYPES = {"ratios": 2, "impact": 4, "full": 4}
SCOPE_KEYS = frozenset({"sheets", "row_keys", "axis_id"})
COUNTER_RULES_INPUT = "counters"


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


def _scope(body: dict) -> tuple[dict, list[dict]]:
    raw = body.get("scope") or {}
    if not isinstance(raw, dict):
        raise InvalidArgument("scope должен быть объектом")
    ignored = sorted(set(raw) - SCOPE_KEYS)
    scope = {key: raw[key] for key in SCOPE_KEYS if raw.get(key)}
    for key in ("sheets", "row_keys"):
        if key in scope and not (isinstance(scope[key], list) and all(isinstance(item, str) for item in scope[key])):
            raise InvalidArgument(f"scope.{key} должен быть списком строк")
    if "axis_id" in scope and not isinstance(scope["axis_id"], str):
        raise InvalidArgument("scope.axis_id должен быть строкой")
    warnings = [{"code": "scope_ignored", "params": {"fields": ignored}}] if ignored else []
    return scope, warnings


def _in_scope(finding: Finding, scope: dict) -> bool:
    if not scope:
        return True
    located = [item for item in finding.locations if item.row_key or item.cell_id]
    if not located:
        # Находка уровня книги (циклы, счётчики R1) от среза не зависит.
        return True
    for location in located:
        sheet = (location.cell_id or "").split("!", 1)[0] if location.cell_id else None
        if not sheet and location.row_key:
            sheet = location.row_key.split("|", 1)[0]
        if scope.get("sheets") and sheet not in scope["sheets"]:
            continue
        if scope.get("row_keys") and location.row_key not in scope["row_keys"]:
            continue
        if scope.get("axis_id") and location.axis_id != scope["axis_id"]:
            continue
        return True
    return False


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
        return AuditInput(
            rows=dim_rows,
            periods=await rows("dim_period"),
            facts=await rows("fact_observation"),
            links=await rows("graph_links") if "links" in needed else [],
            counters=dict(target.manifest.get("builder_counters") or {}),
        )

    async def run(self, job_id: str, body: dict, actor: Actor, *, wait_sec: float):
        from finance_analysis.application.service import Accepted

        kind = body.get("type")
        if kind in LATER_TYPES:
            raise InvalidArgument(
                f"type={kind} появится в фазе {LATER_TYPES[kind]}",
                extra={"supported": ["audit"]},
            )
        if kind != "audit":
            raise InvalidArgument("type должен быть audit", extra={"supported": ["audit"]})
        if body.get("render") not in (None, "json"):
            raise InvalidArgument("render=md появится вместе с отчётами (фаза 4)", extra={"supported": ["json"]})
        rules = select_rules(self.rules, body.get("rules"))
        scope, notes = _scope(body)
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

    async def _defer(self, job_id: str, actor: Actor, analysis_id: str, work: asyncio.Task):
        from finance_analysis.application.service import Accepted

        svc = self.service
        op = await svc.create_op("analysis", job_id, actor, {"analysis_id": analysis_id, "type": "audit"})

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
        findings = [item for item in found if _in_scope(item, scope)]
        warnings = list(notes)
        if target.fresh:
            warnings.insert(0, {"code": "freshness_unknown", "params": {}})
        if COUNTER_RULES_INPUT in needed and not target.manifest.get("builder_counters"):
            skipped = sorted(rule.code for rule in rules if COUNTER_RULES_INPUT in rule.requires)
            warnings.append({"code": "builder_counters_missing", "params": {"rules": skipped}})
        envelope = self._envelope(job_id, target, analysis_id, rules, data, findings, warnings)
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
            bound = await self._bound_keys(job_id, target, marker.get("derive_key"), str(query["concept"]))
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

    async def _bound_keys(self, job_id: str, target: Target, derive: str | None, concept: str) -> set[str]:
        """Привязки той сборки и того состояния, на которых шёл аудит."""

        if not derive:
            raise InvalidArgument(
                "фильтр concept: у сборки нет производного состояния на этом state_seq",
                extra={"build_key": target.build, "state_seq": target.head.state_seq},
            )
        pinned = Head(build_key=target.build, state_seq=target.head.state_seq, derive_key=derive, versions={})
        bindings = await self.service._dataset_rows(job_id, pinned, "bindings")
        return {row["binding_key"] for row in bindings if row.get("effective_concept") == concept}

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
            },
            "citations": [item for item in (_citation(data, location) for location in locations) if item],
            "chain": [_chain(data, location) for location in locations if location.cell_id],
            # Глубокая цепочка — trace builder (R5), в фазе 1 не запрашивается.
            "trace": {"source": "graph_links", "depth": 1, "builder_trace": None},
        }


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
