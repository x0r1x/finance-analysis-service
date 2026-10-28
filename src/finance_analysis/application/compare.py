"""Сравнение двух сборок книги: `POST /v1/books/{job_id}:compare` (§3.2, §6.4).

Фаза 3 — только две сборки одной книги (`other.build_key`). Кейсы внутри
книги и вторая книга (`other.scenario`, `other.job_id`) — фаза 4.

Обе стороны считаются на текущем состоянии подтверждений: оно хранится по
`binding_key` (§4.5), поэтому разница — только в данных сборок. Строки и
периоды сопоставляются по устойчивым ключам: строка — `binding_key`,
период — номер оси на листе (как в отпечатке находки, §6.1) и `period_id`.
"""

from __future__ import annotations

import asyncio
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
from finance_analysis.domain.metrics import RATIO, _primaries

# Варианты `other`, которые появятся в фазе 4 (§12).
LATER_SIDES = {"scenario": 4, "job_id": 4}
DEFAULT_METRICS = ("dscr",)


def _side(raw, name: str) -> dict:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise InvalidArgument(f"{name} должен быть объектом")
    later = sorted(set(raw) & set(LATER_SIDES))
    if later:
        raise InvalidArgument(
            f"{name}.{later[0]} появится в фазе {LATER_SIDES[later[0]]}",
            extra={"supported": ["build_key"]},
        )
    unknown = sorted(set(raw) - {"build_key"})
    if unknown:
        raise InvalidArgument(f"неизвестные поля {name}", extra={"fields": unknown})
    return raw


def _axis_key(periods: list[dict]) -> dict[str, tuple[str, int]]:
    ordinals = axis_ordinals(period["axis_id"] for period in periods)
    return {axis: (axis.rsplit("!", 1)[0], ordinal) for axis, ordinal in ordinals.items()}


def _period_key(axes: dict, axis_id: str | None, period_id: str | None) -> tuple:
    return (*axes.get(axis_id or "", (axis_id, -1)), period_id)


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
        if not other_side.get("build_key"):
            raise InvalidArgument("нужен other.build_key: в фазе 3 сравниваются две сборки книги")
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
        work = self.service.spawn(self._compare(job_id, base, other, list(metrics), rules))
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

    async def _compare(self, job_id: str, base: Target, other: Target, metrics: list[str], rules) -> dict:
        left = await self.analyses.compute_metrics(job_id, base, metrics)
        right = await self.analyses.compute_metrics(job_id, other, metrics)
        result = {
            "job_id": job_id,
            "base": self._pin(base),
            "other": self._pin(other),
            "metrics": self._metric_deltas(left, right),
            "concepts": self._concept_deltas(left, right),
            "structure": await self._structure(job_id, base, other, left, right),
            "findings": None,
            "needs_input": _unique(left["needs_input"] + right["needs_input"]),
            "warnings": _unique(left["warnings"] + right["warnings"]),
        }
        if rules is not None:
            result["findings"] = await self._finding_deltas(job_id, base, other, rules)
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
            for concept, binding in _primaries(side["bindings"]).items():
                for fact in side["facts"]:
                    if fact.get("row_key") != binding["row_key"]:
                        continue
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

    async def _structure(self, job_id: str, base: Target, other: Target, left: dict, right: dict) -> dict:
        from finance_analysis.application.analyses import _pinned

        svc = self.service
        rows_before = {row["binding_key"]: row for row in await svc._dataset_rows(job_id, _pinned(base), "dim_row")}
        rows_after = {row["binding_key"]: row for row in await svc._dataset_rows(job_id, _pinned(other), "dim_row")}

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

    async def _finding_deltas(self, job_id: str, base: Target, other: Target, rules) -> dict:
        needed = requirements(rules)
        found = {}
        for name, target in (("base", base), ("other", other)):
            data = await self.analyses._input(job_id, target, needed)
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
