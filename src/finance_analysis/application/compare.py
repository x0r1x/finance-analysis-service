"""Сравнение: две сборки, сценарии одной книги или две книги (§3.2, §6.4).

Сценарий — только сохранённые числа (`period_marker` или колонка params).
Две книги — два отдельных расчёта и diff. Общего SQL нет.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal, localcontext

import anyio

from finance_analysis.application.analyses import RATIO_METRICS, Target, _decimal_text
from finance_analysis.application.rule_engine import (
    requirements,
    run_rules,
    select_rules,
)
from finance_analysis.domain.audit import axis_ordinals
from finance_analysis.domain.errors import InvalidArgument
from finance_analysis.domain.ids import job_id as check_job
from finance_analysis.domain.metrics import RATIO, _primaries, aligned_keys

_BASE_FIELDS = {"build_key", "scenario"}
_OTHER_FIELDS = {"build_key", "scenario", "job_id"}
DEFAULT_METRICS = ("dscr",)
_SCENARIO_MISSING = "сценарий не найден в числах книги; неактивный кейс сравнивается как две сборки или две книги"


def _side(raw, name: str) -> dict:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise InvalidArgument(f"{name} должен быть объектом")
    allowed = _OTHER_FIELDS if name == "other" else _BASE_FIELDS
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise InvalidArgument(f"неизвестные поля {name}", extra={"fields": unknown})
    return raw


def match_periods(periods: list[dict], name: str) -> list[dict]:
    """Колонка кейса по заголовку, иначе маркер факт/план."""

    needle = str(name).casefold()
    exact = [row for row in periods if str(row.get("header_text") or "").casefold() == needle]
    if exact:
        return exact
    return [
        row
        for row in periods
        if needle in {str(row.get("period_marker") or "").casefold(), str(row.get("marker_class") or "").casefold()}
    ]


def _input_index(
    facts: list[dict],
    periods: list[dict],
    *,
    by_row: bool = False,
    skip: set[str] | None = None,
) -> dict[tuple, Decimal | None]:
    chosen = {(row["axis_id"], row["period_id"]): row for row in periods}
    found: dict[tuple, Decimal | None] = {}
    skipped = skip or set()
    for fact in facts:
        row_key = fact.get("row_key")
        if row_key in skipped:
            continue
        meta = chosen.get((fact.get("axis_id"), fact.get("period_id")))
        if meta is None:
            continue
        number = _number(fact.get("value_dec") if fact.get("value_dec") is not None else fact.get("value"))
        # case-1 и case-2 не делят календарный ключ, поэтому внутри блока кейсов ключ — строка.
        key = (row_key, None) if by_row else (row_key, meta.get("period_key_base") or fact.get("period_id"))
        if key not in found or found[key] is None:
            found[key] = number
    return found


def _scenario_inputs(facts: list[dict], rows: list[dict], left: list[dict], right: list[dict]) -> list[dict]:
    """Кейс с кейсом — по строке и без формул. Факт/план — по календарному периоду."""

    by_row = bool(left and right) and all(row.get("axis_kind") == "params" for row in left + right)
    skip = {row["row_key"] for row in rows if row.get("formula") or row.get("has_formula")} if by_row else set()
    return _input_deltas(
        _input_index(facts, left, by_row=by_row, skip=skip),
        _input_index(facts, right, by_row=by_row, skip=skip),
    )


def _input_deltas(left: dict[tuple, Decimal | None], right: dict[tuple, Decimal | None]) -> list[dict]:
    found = []
    for key in sorted(set(left) | set(right), key=lambda item: tuple(str(part) for part in item)):
        before, after = left.get(key), right.get(key)
        found.append(
            {
                "row_key": key[0],
                "period_key_base": key[1],
                "base": _decimal_text(before),
                "other": _decimal_text(after),
                **_delta(before, after),
            }
        )
    return found


@dataclass(frozen=True)
class _Places:
    ordinals: dict[str, tuple[str, int]]
    timelines: dict[str, str]
    aligned: dict[tuple[str, str], tuple]


def _axis_key(periods: list[dict]) -> _Places:
    ordinals = axis_ordinals(period["axis_id"] for period in periods)
    return _Places(
        ordinals={axis: (axis.rsplit("!", 1)[0], ordinal) for axis, ordinal in ordinals.items()},
        timelines={period["axis_id"]: period["timeline_id"] for period in periods if period.get("timeline_id")},
        aligned=aligned_keys(periods),
    )


def _period_key(axes: _Places, axis_id: str | None, period_id: str | None) -> tuple:
    """Устойчивый ключ периода между сборками: шкала, затем номер оси на листе."""

    place = axes.aligned.get((axis_id or "", period_id or ""))
    if place is not None:
        return (*place, period_id)
    if period_id is None and axis_id in axes.timelines:
        return (axes.timelines[axis_id], -1, None)
    return (*axes.ordinals.get(axis_id or "", (axis_id, -1)), period_id)


def _delta(base: Decimal | None, other: Decimal | None) -> dict:
    if base is None or other is None:
        return {"delta_abs": None, "delta_pct": None}
    with localcontext() as ctx:
        ctx.prec = 38
        ctx.rounding = "ROUND_HALF_EVEN"
        diff = other - base
        pct = None if base == 0 else (diff / abs(base)).quantize(RATIO)
    return {"delta_abs": _decimal_text(diff), "delta_pct": _decimal_text(pct)}


def _number(value) -> Decimal | None:
    return None if value is None else Decimal(str(value))


class Comparisons:
    """`…:compare` поверх `Analyses`: та же закреплённая сборка и тот же расчёт метрик."""

    def __init__(self, analyses) -> None:
        self.analyses = analyses
        self.service = analyses.service

    async def run(self, job_id: str, body: dict, actor, *, wait_sec: float):
        from finance_analysis.application.service import Accepted

        base_side = _side(body.get("base"), "base")
        other_side = _side(body.get("other"), "other")
        if base_side.get("scenario") or other_side.get("scenario"):
            if other_side.get("job_id"):
                raise InvalidArgument("scenario относится к одной книге")
            if not base_side.get("scenario") or not other_side.get("scenario"):
                raise InvalidArgument("для кейсов нужны base.scenario и other.scenario")
            return await self._run_scenarios(job_id, actor, base_side, other_side, body, wait_sec=wait_sec)
        if other_side.get("job_id"):
            return await self._run_books(job_id, actor, base_side, other_side, body, wait_sec=wait_sec)
        if not other_side.get("build_key"):
            raise InvalidArgument("нужен other.build_key, other.scenario или other.job_id")
        metrics = body.get("metrics", list(DEFAULT_METRICS))
        if not isinstance(metrics, list) or any(item not in RATIO_METRICS for item in metrics):
            raise InvalidArgument("неизвестная метрика", extra={"supported": list(RATIO_METRICS)})
        rules = None
        if body.get("rules") is not None:
            rules = select_rules(self.analyses.rules, body.get("rules"))
        base = await self.analyses._target(job_id, actor, base_side.get("build_key"), wait_sec=wait_sec)
        if isinstance(base, Accepted):
            return base
        other = await self.analyses._target(job_id, actor, other_side.get("build_key"), wait_sec=wait_sec)
        if isinstance(other, Accepted):
            return other
        if base.build == other.build:
            raise InvalidArgument("base и other — одна и та же сборка", extra={"build_key": base.build})
        work = self.service.spawn(self._compare(job_id, base, job_id, other, list(metrics), rules))
        if body.get("async") is True:
            return await self._defer(job_id, actor, work)
        budget = max(0.1, min(wait_sec, self.service.settings.sync_deadline_ms / 1000) * 0.8)
        try:
            return await asyncio.wait_for(asyncio.shield(work), timeout=budget)
        except TimeoutError:
            return await self._defer(job_id, actor, work)

    async def _defer(self, job_id: str, actor, work: asyncio.Task):
        from finance_analysis.application.service import Accepted

        svc = self.service
        op = await svc.create_op("compare", job_id, actor, {})

        async def _finish() -> None:
            try:
                result = await work
            except Exception as exc:  # noqa: BLE001 — любая ошибка сравнения закрывает операцию
                await svc.finish_op(op["id"], "failed", error={"code": getattr(exc, "code", "failed"), "detail": str(exc)})
                return
            await svc.finish_op(op["id"], "succeeded", result=result)

        svc.spawn(_finish())
        return Accepted(op)

    async def _run_scenarios(self, job_id, actor, base_side, other_side, body, *, wait_sec: float):
        from finance_analysis.application.service import Accepted

        build = base_side.get("build_key") or other_side.get("build_key")
        if base_side.get("build_key") and other_side.get("build_key") and base_side["build_key"] != other_side["build_key"]:
            raise InvalidArgument("сценарии сравниваются внутри одной сборки")
        target = await self.analyses._target(job_id, actor, build, wait_sec=wait_sec)
        if isinstance(target, Accepted):
            return target
        work = self.service.spawn(self._scenarios(job_id, target, base_side["scenario"], other_side["scenario"]))
        if body.get("async") is True:
            return await self._defer(job_id, actor, work)
        budget = max(0.1, min(wait_sec, self.service.settings.sync_deadline_ms / 1000) * 0.8)
        try:
            return await asyncio.wait_for(asyncio.shield(work), timeout=budget)
        except TimeoutError:
            return await self._defer(job_id, actor, work)

    async def _scenarios(self, job_id: str, target, left_name: str, right_name: str) -> dict:
        data = await self.analyses._input(job_id, target, frozenset())
        left_periods = match_periods(data.periods, left_name)
        right_periods = match_periods(data.periods, right_name)
        if not left_periods or not right_periods:
            missing = left_name if not left_periods else right_name
            raise InvalidArgument(_SCENARIO_MISSING, extra={"scenario": missing})
        pin = self._pin(target)
        return {
            "job_id": job_id,
            "base": {**pin, "scenario": left_name},
            "other": {**pin, "scenario": right_name},
            "metrics": [],
            "inputs": _scenario_inputs(data.facts, data.rows, left_periods, right_periods),
            "concepts": [],
            "structure": None,
            "findings": None,
            "needs_input": [],
            "warnings": [{"code": "scenario_inputs_only", "params": {}}],
        }

    async def _run_books(self, job_id, actor, base_side, other_side, body, *, wait_sec: float):
        from finance_analysis.application.service import Accepted

        right_job = check_job(str(other_side["job_id"]))
        metrics = body.get("metrics", list(DEFAULT_METRICS))
        if not isinstance(metrics, list) or any(item not in RATIO_METRICS for item in metrics):
            raise InvalidArgument("неизвестная метрика", extra={"supported": list(RATIO_METRICS)})
        rules = select_rules(self.analyses.rules, body.get("rules")) if body.get("rules") is not None else None
        base = await self.analyses._target(job_id, actor, base_side.get("build_key"), wait_sec=wait_sec)
        if isinstance(base, Accepted):
            return base
        other = await self.analyses._target(right_job, actor, other_side.get("build_key"), wait_sec=wait_sec)
        if isinstance(other, Accepted):
            return other
        if job_id == right_job and base.build == other.build:
            raise InvalidArgument("base и other — одна и та же сборка", extra={"build_key": base.build})
        work = self.service.spawn(self._compare(job_id, base, right_job, other, list(metrics), rules))
        if body.get("async") is True:
            return await self._defer(job_id, actor, work)
        budget = max(0.1, min(wait_sec, self.service.settings.sync_deadline_ms / 1000) * 0.8)
        try:
            return await asyncio.wait_for(asyncio.shield(work), timeout=budget)
        except TimeoutError:
            return await self._defer(job_id, actor, work)

    async def _compare(self, left_job: str, base: Target, right_job: str, other: Target, metrics: list[str], rules) -> dict:
        left = await self.analyses.compute_metrics(left_job, base, metrics)
        right = await self.analyses.compute_metrics(right_job, other, metrics)
        result = {
            "job_id": left_job,
            "base": self._pin(base),
            "other": self._pin(other),
            "metrics": self._metric_deltas(left, right),
            "concepts": self._concept_deltas(left, right),
            "structure": await self._structure(left_job, right_job, base, other, left, right),
            "findings": None,
            "needs_input": _unique(left["needs_input"] + right["needs_input"]),
            "warnings": _unique(left["warnings"] + right["warnings"]),
        }
        if right_job != left_job:
            result["other_job_id"] = right_job
        if rules is not None:
            result["findings"] = await self._finding_deltas(left_job, right_job, base, other, rules)
        return result

    @staticmethod
    def _pin(target: Target) -> dict:
        return {
            "build_key": target.build,
            "state_seq": target.head.state_seq,
            "derive_key": target.derive_key,
            "is_latest": target.is_latest,
            "builder_ref": target.manifest.get("builder_ref"),
        }

    @staticmethod
    def _metric_deltas(left: dict, right: dict) -> list[dict]:
        def keyed(side: dict) -> dict[tuple, dict]:
            axes = _axis_key(side["periods"])
            return {
                (row["metric"], row.get("variant"), *_period_key(axes, row.get("axis_id"), row.get("period_id"))): row
                for row in side["rows"]
            }

        mine, theirs = keyed(left), keyed(right)
        found = []
        for key in sorted(set(mine) | set(theirs), key=lambda item: tuple(str(part) for part in item)):
            before, after = mine.get(key), theirs.get(key)
            shown = after or before
            found.append(
                {
                    "metric": shown["metric"],
                    "variant": shown.get("variant"),
                    "axis_id": shown.get("axis_id"),
                    "period_id": shown.get("period_id"),
                    "base": None if before is None else _decimal_text(before.get("value")),
                    "other": None if after is None else _decimal_text(after.get("value")),
                    "base_status": None if before is None else before["status"],
                    "other_status": None if after is None else after["status"],
                    **_delta(
                        None if before is None else before.get("value"),
                        None if after is None else after.get("value"),
                    ),
                }
            )
        return found

    @staticmethod
    def _concept_deltas(left: dict, right: dict) -> list[dict]:
        def sums(side: dict) -> dict[tuple, Decimal]:
            axes = _axis_key(side["periods"])
            totals: dict[tuple, Decimal] = {}
            by_row: dict[str, list[dict]] = {}
            for fact in side["facts"]:
                by_row.setdefault(fact.get("row_key"), []).append(fact)
            for concept, binding in _primaries(side["bindings"]).items():
                for fact in by_row.get(binding["row_key"], ()):
                    raw = fact.get("normalized_value")
                    number = _number(raw if raw is not None else fact.get("value_dec"))
                    if number is None:
                        continue
                    key = (concept, *_period_key(axes, fact["axis_id"], fact["period_id"]))
                    totals[key] = totals.get(key, Decimal(0)) + number
            return totals

        mine, theirs = sums(left), sums(right)
        found = []
        for key in sorted(set(mine) | set(theirs), key=lambda item: tuple(str(part) for part in item)):
            before, after = mine.get(key), theirs.get(key)
            if before is not None and after is not None and before == after:
                continue
            found.append(
                {
                    "concept": key[0],
                    "period_id": key[-1],
                    "base": _decimal_text(before),
                    "other": _decimal_text(after),
                    **_delta(before, after),
                }
            )
        return found

    async def _structure(self, left_job: str, right_job: str, base: Target, other: Target, left: dict, right: dict) -> dict:
        from finance_analysis.application.analyses import _pinned

        svc = self.service
        rows_before = {row["binding_key"]: row for row in await svc._dataset_rows(left_job, _pinned(base), "dim_row")}
        rows_after = {row["binding_key"]: row for row in await svc._dataset_rows(right_job, _pinned(other), "dim_row")}

        def periods(side: dict) -> set[tuple]:
            axes = _axis_key(side["periods"])
            return {_period_key(axes, item["axis_id"], item["period_id"]) for item in side["periods"]}

        def primary(side: dict, rows: dict) -> dict[str, str]:
            by_row = {row["row_key"]: key for key, row in rows.items()}
            return {concept: by_row.get(binding["row_key"]) for concept, binding in _primaries(side["bindings"]).items()}

        before_periods, after_periods = periods(left), periods(right)
        before_bound, after_bound = primary(left, rows_before), primary(right, rows_after)
        return {
            "rows_added": sorted(set(rows_after) - set(rows_before)),
            "rows_removed": sorted(set(rows_before) - set(rows_after)),
            "periods_added": sorted(item[-1] for item in after_periods - before_periods),
            "periods_removed": sorted(item[-1] for item in before_periods - after_periods),
            "bindings_changed": [
                {"concept": concept, "base": before_bound.get(concept), "other": after_bound.get(concept)}
                for concept in sorted(set(before_bound) | set(after_bound))
                if before_bound.get(concept) != after_bound.get(concept)
            ],
        }

    async def _finding_deltas(self, left_job: str, right_job: str, base: Target, other: Target, rules) -> dict:
        needed = requirements(rules)
        found = {}
        jobs = {"base": left_job, "other": right_job}
        for name, target in (("base", base), ("other", other)):
            data = await self.analyses._input(jobs[name], target, needed)
            items = await anyio.to_thread.run_sync(lambda data=data: run_rules(rules, data), limiter=self.service._cpu)
            found[name] = {item.fingerprint: item for item in items}

        def brief(item) -> dict:
            return {"code": item.code, "fingerprint": item.fingerprint, "severity": item.severity, "binding_key": item.binding_key}

        return {
            "added": [brief(found["other"][key]) for key in sorted(set(found["other"]) - set(found["base"]))],
            "removed": [brief(found["base"][key]) for key in sorted(set(found["base"]) - set(found["other"]))],
            "unchanged": len(set(found["base"]) & set(found["other"])),
        }


def _unique(items: list[dict]) -> list[dict]:
    seen, found = set(), []
    for item in items:
        marker = repr(sorted(item.items()))
        if marker not in seen:
            seen.add(marker)
            found.append(item)
    return found
