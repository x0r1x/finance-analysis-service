"""NPV и IRR проекта по процитированному денежному потоку.

Степень — доля года от конца интервала приведения до конца интервала (ВК 477,
формула 2.2). Год без дат: номер интервала, у первого заполненного степень 0.
Короче года и без дат ряд не считается. Терминальная стоимость — одна
процитированная строка на последнем интервале. IRR ищет неотрицательный корень
после критерия Норстрёма по накопленному потоку.

Сверка ``fcf_identity`` не подменяет ряд. Вариант задаёт автор модели.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, localcontext

from finance_analysis.domain.metrics import MONEY, _payment, _primaries, quantize_ratio

_NPV_TOL = Decimal("0.01")
_IRR_TOL = Decimal("1e-9")
_RATE_ORDER = ("wacc", "discount_rate")
_ANNUAL = frozenset({"year", "model_year"})
_SUBYEAR = frozenset({"half", "half_year", "quarter", "month", "week", "day"})
_IDENTITY = frozenset({"vk477", "fcff_after_interest"})
_YEAR = Decimal(365)


def project_return(
    metric: str,
    *,
    facts: list[dict],
    bindings: list[dict],
    periods: list[dict],
    absent: frozenset[str] = frozenset(),
) -> dict:
    primaries = _primaries(bindings, absent)
    flow = primaries.get("project_fcf")
    if flow is None:
        return _missing(metric, "project_fcf")
    steps, problem = _steps(facts, flow, periods)
    if problem == "series_gap":
        return _warned(metric, "project_return_incomplete")
    if isinstance(problem, str) and problem.startswith("npv_"):
        return _warned(metric, problem)
    if steps is None:
        return _empty(metric, "missing_input")
    terminal, terminal_problem = _terminal(facts, primaries.get("terminal_value"), steps, periods)
    if terminal_problem == "missing":
        return _empty(metric, "missing_input")
    if terminal_problem:
        return _warned(metric, terminal_problem)
    flows = [step.flow for step in steps]
    if terminal is not None:
        flows[-1] = flows[-1] + terminal
    if metric == "npv":
        concept, rate = _rate(facts, primaries, steps, periods)
        if rate == "not_unique":
            return _warned(metric, "discount_rate_not_unique")
        if rate == "missing":
            return _empty(metric, "missing_input")
        if concept is None:
            return _missing(metric, "discount_rate")
        shown = _npv(steps, flows, rate).quantize(MONEY)
        inputs = ["project_fcf", concept]
    else:
        solved = _irr(steps, flows)
        if solved == "not_unique":
            return _warned(metric, "irr_not_unique")
        if solved == "undefined":
            return _warned(metric, "irr_undefined")
        if not isinstance(solved, Decimal):
            return _empty(metric, "not_computed")
        shown = quantize_ratio(solved)
        inputs = ["project_fcf"]
        rate = solved
    if terminal is not None:
        inputs.append("terminal_value")
    home = steps[-1].period
    warnings = _timing(metric, steps, rate)
    warnings.extend(_book(metric, shown, facts, primaries.get(metric)))
    return {
        "metric": metric,
        "rows": [
            {
                "metric": metric,
                "axis_id": home["axis_id"],
                "period_id": home["period_id"],
                "period_key_base": home.get("period_key_base"),
                "period_marker": home.get("period_marker"),
                "value": shown,
                "status": "computed",
                "reason": None,
                "inputs": inputs,
                "window": [step.period["period_id"] for step in steps],
            }
        ],
        "needs_input": [],
        "warnings": warnings,
        "status": "succeeded",
    }


def fcf_identity(
    variant: str | None,
    *,
    facts: list[dict],
    bindings: list[dict],
    periods: list[dict],
    absent: frozenset[str] = frozenset(),
    sign_convention: str = "outflow_negative",
) -> dict:
    """Сверка названного варианта. Без варианта предупреждения нет и ряд не строится."""

    metric = "fcf_identity"
    if variant not in _IDENTITY:
        return _empty(metric, "succeeded")
    primaries = _primaries(bindings, absent)
    flow = primaries.get("project_fcf")
    operating = primaries.get("ocf")
    spent = primaries.get("capex")
    if flow is None:
        return _missing(metric, "project_fcf")
    if operating is None:
        return _missing(metric, "ocf")
    if spent is None:
        return _missing(metric, "capex")
    steps, problem = _steps(facts, flow, periods, timed=False)
    if problem == "series_gap":
        return _warned(metric, "project_return_incomplete")
    if steps is None:
        return _empty(metric, "missing_input")
    shield = variant == "fcff_after_interest"
    tax = None
    interest = primaries.get("net_interest") if shield else None
    if shield:
        if interest is None:
            return _missing(metric, "net_interest")
        tax_row = primaries.get("tax_rate")
        if tax_row is None:
            return _missing(metric, "tax_rate")
        tax = _one_rate(facts, tax_row, periods)
        if tax == "not_unique":
            return _warned(metric, "tax_rate_not_unique")
        if not isinstance(tax, Decimal):
            return _empty(metric, "missing_input")
    warnings = []
    for step in steps:
        earned = _at(facts, operating["row_key"], step.period)
        capex = _at(facts, spent["row_key"], step.period)
        if earned is None:
            return _missing(metric, "ocf")
        if capex is None:
            return _missing(metric, "capex")
        built = earned - _payment(capex, sign_convention)
        cells = [_cell(facts, operating["row_key"], step.period), _cell(facts, spent["row_key"], step.period)]
        if shield and interest is not None and isinstance(tax, Decimal):
            paid = _at(facts, interest["row_key"], step.period)
            if paid is None:
                return _missing(metric, "net_interest")
            built += paid * (Decimal(1) - tax)
            cells.append(_cell(facts, interest["row_key"], step.period))
        if abs(built - step.flow) > _NPV_TOL:
            warnings.append(
                {
                    "code": "fcf_identity_mismatch",
                    "params": {
                        "metric": metric,
                        "period_id": step.period["period_id"],
                        "fas": str(built),
                        "model": str(step.flow),
                        "cells": [item for item in cells if item],
                    },
                }
            )
    return {"metric": metric, "rows": [], "needs_input": [], "warnings": warnings, "status": "succeeded"}


class _Step:
    def __init__(self, index: int, flow: Decimal, period: dict, exponent: Decimal, delta: Decimal) -> None:
        self.index = index
        self.flow = flow
        self.period = period
        self.exponent = exponent
        self.delta = delta


def _steps(
    facts: list[dict], binding: dict, periods: list[dict], *, timed: bool = True
) -> tuple[list[_Step] | None, str | None]:
    row = binding["row_key"]
    axes = {fact["axis_id"] for fact in facts if fact.get("row_key") == row}
    filled: dict[int, tuple[Decimal, dict]] = {}
    for period in periods:
        if period.get("axis_id") not in axes or period.get("period_index") is None:
            continue
        index = int(period["period_index"])
        value = _at(facts, row, period)
        if value is None:
            continue
        current = filled.get(index)
        filled[index] = (value if current is None else current[0] + value, period)
    if not filled:
        return None, "missing"
    low, high = min(filled), max(filled)
    if any(index not in filled for index in range(low, high + 1)):
        return None, "series_gap"
    ordered = [filled[index] for index in range(low, high + 1)]
    grains = {str(period.get("grain") or "") for _flow, period in ordered}
    if timed and len(grains) != 1:
        return None, "npv_grain_mixed"
    grain = next(iter(grains)) if grains else ""
    dated = [_as_date(period.get("period_end")) for _flow, period in ordered]
    if not timed:
        exponents = [Decimal(index - low) for index in range(low, high + 1)]
    elif any(item is None for item in dated) and any(item is not None for item in dated):
        return None, "npv_period_dates_incomplete"
    elif all(item is not None for item in dated):
        ends = [item for item in dated if item is not None]
        origin = ends[0]
        exponents = [Decimal((item - origin).days) / _YEAR for item in ends]
        if any(later < earlier for earlier, later in zip(exponents, exponents[1:])):
            return None, "npv_period_order"
    elif grain in _ANNUAL or grain == "":
        exponents = [Decimal(index - low) for index in range(low, high + 1)]
    elif grain in _SUBYEAR:
        return None, "npv_subyear_without_dates"
    else:
        return None, "npv_subyear_without_dates"
    steps = []
    for offset, index in enumerate(range(low, high + 1)):
        previous = exponents[offset - 1] if offset else exponents[0]
        delta = Decimal(0) if offset == 0 else exponents[offset] - previous
        steps.append(_Step(index, filled[index][0], filled[index][1], exponents[offset], delta))
    return steps, None


def _terminal(
    facts: list[dict], binding: dict | None, steps: list[_Step], periods: list[dict]
) -> tuple[Decimal | None, str | None]:
    if binding is None:
        return None, None
    indexes = _index_of(periods)
    found: list[tuple[int | None, Decimal]] = []
    for fact in facts:
        if fact.get("row_key") != binding["row_key"] or fact.get("normalized_value") is None:
            continue
        found.append((indexes.get((fact.get("axis_id"), fact.get("period_id"))), Decimal(str(fact["normalized_value"]))))
    if not found:
        return None, "missing"
    if len(found) != 1:
        return None, "terminal_value_not_unique"
    index, value = found[0]
    last = steps[-1]
    if index != last.index:
        return None, "terminal_value_not_on_horizon"
    return value, None


def _rate(
    facts: list[dict], primaries: dict, steps: list[_Step], periods: list[dict]
) -> tuple[str | None, Decimal | dict[int, Decimal] | str | None]:
    seen = False
    for concept in _RATE_ORDER:
        binding = primaries.get(concept)
        if binding is None:
            continue
        seen = True
        parsed = _rate_series(facts, binding, steps, periods)
        if parsed == "empty":
            continue
        return concept, parsed
    if not seen:
        return None, None
    return None, "missing"


def _rate_series(
    facts: list[dict], binding: dict, steps: list[_Step], periods: list[dict]
) -> Decimal | dict[int, Decimal] | str:
    indexes = _index_of(periods)
    by_index: dict[int, list[Decimal]] = {}
    loose: list[Decimal] = []
    for fact in facts:
        if fact.get("row_key") != binding["row_key"] or fact.get("normalized_value") is None:
            continue
        value = Decimal(str(fact["normalized_value"]))
        index = indexes.get((fact.get("axis_id"), fact.get("period_id")))
        if index is None:
            loose.append(value)
        else:
            by_index.setdefault(index, []).append(value)
    if not by_index and not loose:
        return "empty"
    flat = [*loose, *(item for values in by_index.values() for item in values)]
    if any(item <= -1 for item in flat):
        return "missing"
    for values in by_index.values():
        if _spread(values):
            return "not_unique"
    if _spread(loose):
        return "not_unique"
    chosen = {index: values[0] for index, values in by_index.items()}
    if loose and chosen and any(abs(item - loose[0]) > Decimal("1e-12") for item in chosen.values()):
        return "not_unique"
    if loose and not chosen:
        return loose[0]
    needed = [step.index for step in steps[1:]]
    if any(index not in chosen for index in needed):
        if chosen and not _spread([*chosen.values(), *loose]):
            return next(iter(chosen.values()))
        return "missing"
    series = {step.index: chosen[step.index] for step in steps[1:]}
    if steps and steps[0].index in chosen:
        series[steps[0].index] = chosen[steps[0].index]
    if not _spread(list(series.values())):
        return next(iter(series.values()))
    return {step.index: chosen[step.index] for step in steps[1:]}


def _one_rate(facts: list[dict], binding: dict, periods: list[dict]) -> Decimal | str | None:
    del periods
    found = [
        Decimal(str(fact["normalized_value"]))
        for fact in facts
        if fact.get("row_key") == binding["row_key"] and fact.get("normalized_value") is not None
    ]
    if not found:
        return None
    if any(item <= -1 for item in found) or _spread(found):
        return "not_unique" if _spread(found) else "missing"
    return found[0]


def _npv(steps: list[_Step], flows: list[Decimal], rate: Decimal | dict[int, Decimal]) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 38
        ctx.rounding = "ROUND_HALF_EVEN"
        total = Decimal(0)
        for step, flow, factor in zip(steps, flows, _factors(steps, rate)):
            del step
            total += flow * factor
        return total


def _factors(steps: list[_Step], rate: Decimal | dict[int, Decimal]) -> list[Decimal]:
    if isinstance(rate, Decimal):
        base = Decimal(1) + rate
        return [Decimal(1) / base**step.exponent for step in steps]
    factors = [Decimal(1)]
    product = Decimal(1)
    for step in steps[1:]:
        product *= (Decimal(1) + rate[step.index]) ** step.delta
        factors.append(Decimal(1) / product)
    return factors


def _irr(steps: list[_Step], flows: list[Decimal]) -> Decimal | str | None:
    if not _norstrom(flows):
        return "not_unique"

    def at(rate: Decimal) -> Decimal:
        return _npv(steps, flows, rate)

    low, high = Decimal(0), Decimal(20)
    left = at(low)
    if abs(left) <= Decimal("1e-18"):
        return Decimal(0)
    right = at(high)
    if left * right > 0:
        return "undefined"
    for _step in range(200):
        mid = (low + high) / 2
        value = at(mid)
        if abs(value) <= Decimal("1e-18") or high - low <= Decimal("1e-18"):
            return mid
        if left * value <= 0:
            high = mid
        else:
            low, left = mid, value
    return (low + high) / 2


def _norstrom(flows: list[Decimal]) -> bool:
    """Накопленный поток начинается с отрицательного числа и меняет знак один раз."""

    total = Decimal(0)
    sign = 0
    changes = 0
    started = False
    for flow in flows:
        total += flow
        if total == 0:
            continue
        current = 1 if total > 0 else -1
        if not started:
            if current > 0:
                return False
            started = True
            sign = current
            continue
        if current != sign:
            changes += 1
            sign = current
    return started and changes == 1


def _timing(metric: str, steps: list[_Step], rate: Decimal | dict[int, Decimal] | str | None) -> list[dict]:
    if not isinstance(rate, (Decimal, dict)):
        return []

    def at(step: _Step) -> Decimal:
        if isinstance(rate, dict):
            return rate.get(step.index, Decimal(0))
        return rate

    coarse = False
    for step in steps[1:]:
        if step.delta > 1 or (step.delta < 1 and at(step) * step.delta >= Decimal("0.1")):
            coarse = True
    if not coarse:
        return []
    return [{"code": "intra_step_timing", "params": {"metric": metric}}]


def _book(metric: str, shown: Decimal, facts: list[dict], binding: dict | None) -> list[dict]:
    if binding is None:
        return []
    tol = _NPV_TOL if metric == "npv" else _IRR_TOL
    cells = [
        Decimal(str(fact["normalized_value"]))
        for fact in facts
        if fact.get("row_key") == binding["row_key"] and fact.get("normalized_value") is not None
    ]
    if not cells or any(abs(shown - other) <= tol for other in cells):
        return []
    return [{"code": f"{metric}_book_mismatch", "params": {"metric": metric, "fas": str(shown), "model": str(cells[0])}}]


def _at(facts: list[dict], row: str, period: dict) -> Decimal | None:
    for fact in facts:
        if fact.get("row_key") != row or fact.get("axis_id") != period.get("axis_id") or fact.get("period_id") != period.get("period_id"):
            continue
        number = fact.get("normalized_value")
        if number is None:
            return None
        return Decimal(str(number))
    return None


def _cell(facts: list[dict], row: str, period: dict) -> str | None:
    for fact in facts:
        if fact.get("row_key") == row and fact.get("axis_id") == period.get("axis_id") and fact.get("period_id") == period.get("period_id"):
            return fact.get("cell_id")
    return None


def _index_of(periods: list[dict]) -> dict[tuple, int]:
    found = {}
    for period in periods:
        if period.get("period_index") is None:
            continue
        found[(period.get("axis_id"), period.get("period_id"))] = int(period["period_index"])
    return found


def _spread(values: list[Decimal]) -> bool:
    if len(values) < 2:
        return False
    return any(abs(item - values[0]) > Decimal("1e-12") for item in values)


def _as_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _missing(metric: str, subject: str) -> dict:
    return {
        "metric": metric,
        "rows": [],
        "needs_input": [{"kind": "concept", "reason": "concept_unknown", "subject": subject}],
        "warnings": [],
        "status": "missing_input",
    }


def _empty(metric: str, status: str) -> dict:
    return {"metric": metric, "rows": [], "needs_input": [], "warnings": [], "status": status}


def _warned(metric: str, code: str) -> dict:
    return {
        "metric": metric,
        "rows": [],
        "needs_input": [],
        "warnings": [{"code": code, "params": {"metric": metric}}],
        "status": "not_computed",
    }
