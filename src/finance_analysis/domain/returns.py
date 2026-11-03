"""NPV и IRR проекта по процитированному денежному потоку.

Степень дисконта — `period_index`. Одинаковый сдвиг всех индексов не меняет
корень IRR, поэтому шкала с нуля и с единицы сходится с IRR Excel. Пропущенный
год нулём не заполняется.
"""

from __future__ import annotations

from decimal import Decimal, localcontext

from finance_analysis.domain.metrics import MONEY, _primaries, quantize_ratio

_NPV_TOL = Decimal("0.01")
_IRR_TOL = Decimal("1e-9")


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
    points, problem = _points(facts, flow, periods)
    if problem == "series_gap":
        return _warned(metric, "project_return_incomplete")
    if points is None:
        return _empty(metric, "missing_input")
    rate = None
    if metric == "npv":
        rate_row = primaries.get("discount_rate")
        if rate_row is None:
            return _missing(metric, "discount_rate")
        rate = _unique(facts, rate_row)
        if rate == "not_unique":
            return _warned(metric, "discount_rate_not_unique")
        if rate is None:
            return _empty(metric, "missing_input")
        shown = _npv(points, rate).quantize(MONEY)
    else:
        solved = _irr(points)
        if solved is None:
            return _empty(metric, "not_computed")
        shown = quantize_ratio(solved)
    home = points[-1][2]
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
                "inputs": ["project_fcf", "discount_rate"] if metric == "npv" else ["project_fcf"],
                "window": [period["period_id"] for _index, _flow, period in points],
            }
        ],
        "needs_input": [],
        "warnings": _book(metric, shown, facts, primaries.get(metric)),
        "status": "succeeded",
    }


def _points(
    facts: list[dict], binding: dict, periods: list[dict]
) -> tuple[list[tuple[int, Decimal, dict]] | None, str | None]:
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
    return [(index, filled[index][0], filled[index][1]) for index in range(low, high + 1)], None


def _at(facts: list[dict], row: str, period: dict) -> Decimal | None:
    for fact in facts:
        if fact.get("row_key") != row or fact.get("axis_id") != period["axis_id"] or fact.get("period_id") != period["period_id"]:
            continue
        number = fact.get("normalized_value")
        if number is None:
            return None
        return Decimal(str(number))
    return None


def _unique(facts: list[dict], binding: dict) -> Decimal | None | str:
    found = [
        Decimal(str(fact["normalized_value"]))
        for fact in facts
        if fact.get("row_key") == binding["row_key"] and fact.get("normalized_value") is not None
    ]
    if not found or found[0] <= -1:
        return None
    if any(abs(item - found[0]) > Decimal("1e-12") for item in found):
        return "not_unique"
    return found[0]


def _npv(points: list[tuple[int, Decimal, dict]], rate: Decimal) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 38
        ctx.rounding = "ROUND_HALF_EVEN"
        base = Decimal(1) + rate
        return sum((flow / base**index for index, flow, _period in points), Decimal(0))


def _irr(points: list[tuple[int, Decimal, dict]]) -> Decimal | None:
    # shortcut: ищется один корень на (−0.9, 20); второй корень при нескольких переменах знака не ищется
    signs = {1 if flow > 0 else -1 for _index, flow, _period in points if flow != 0}
    if len(signs) < 2:
        return None
    low, high = Decimal("-0.9"), Decimal(5)
    left = _npv(points, low)
    if left * _npv(points, high) > 0:
        high = Decimal(20)
        if left * _npv(points, high) > 0:
            return None
    for _step in range(200):
        mid = (low + high) / 2
        value = _npv(points, mid)
        if abs(value) <= Decimal("1e-18") or high - low <= Decimal("1e-18"):
            return mid
        if left * value <= 0:
            high = mid
        else:
            low, left = mid, value
    return (low + high) / 2


def _book(metric: str, shown: Decimal, facts: list[dict], binding: dict | None) -> list[dict]:
    if binding is None:
        return []
    tol = _NPV_TOL if metric == "npv" else _IRR_TOL
    for fact in facts:
        if fact.get("row_key") != binding["row_key"] or fact.get("normalized_value") is None:
            continue
        other = Decimal(str(fact["normalized_value"]))
        if abs(shown - other) > tol:
            return [{"code": f"{metric}_book_mismatch", "params": {"metric": metric, "fas": str(shown), "model": str(other)}}]
    return []


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
