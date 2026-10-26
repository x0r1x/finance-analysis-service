"""DSCR и ICR (§5.7). Частное считает Decimal, не DuckDB."""

from __future__ import annotations

from decimal import Decimal, localcontext

MONEY = Decimal("0.000001")
RATIO = Decimal("0.0000000001")
_BOUND = frozenset({"bound", "bound_with_warning"})


def quantize_ratio(value: Decimal) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 38
        ctx.rounding = "ROUND_HALF_EVEN"
        return value.quantize(RATIO)


def coverage_ratio(
    *,
    metric: str,
    facts: list[dict],
    bindings: list[dict],
    periods: list[dict],
    period_phase: dict[tuple[str, str], str | None],
    explicit_phases: bool,
    sign_convention: str = "outflow_negative",
) -> dict:
    from finance_analysis.domain.coverage import is_coverage_test_period

    primaries = _primaries(bindings)
    if metric == "dscr":
        needed = ("cfads", "debt_service")
    elif metric == "icr":
        needed = ("interest",)
    else:
        return {"metric": metric, "rows": [], "needs_input": [], "warnings": [], "status": "missing_input"}
    missing = [name for name in needed if name not in primaries]
    warnings: list[dict] = []
    numerator_name = None
    if metric == "icr":
        if "ebitda" in primaries and "ebit" in primaries:
            numerator_name = "ebitda"
            warnings.append({"code": "icr_numerator", "params": {"concept": "ebitda"}})
        elif "ebitda" in primaries:
            numerator_name = "ebitda"
        elif "ebit" in primaries:
            numerator_name = "ebit"
        else:
            missing.append("ebitda")
    else:
        numerator_name = "cfads"
    watched = set(needed) | {"ebitda", "ebit"}
    ambiguous = [name for name, rows in _groups(bindings).items() if len(rows) > 1 and name in watched]
    if not ambiguous:
        ambiguous = [
            row.get("effective_concept")
            for row in bindings
            if row.get("status") == "ambiguous" and row.get("effective_concept") in watched
        ]
    if ambiguous:
        return {
            "metric": metric,
            "rows": [],
            "needs_input": [{"kind": "concept", "reason": "ambiguous", "subject": ambiguous[0]}],
            "warnings": warnings,
            "status": "needs_input",
        }
    absent = {
        row.get("effective_concept")
        for row in bindings
        if row.get("source") == "confirmed" and row.get("status") == "unknown"
    }
    if missing:
        subject = missing[0]
        reason = "absent_in_book" if subject in absent else "concept_unknown"
        return {
            "metric": metric,
            "rows": [],
            "needs_input": [{"kind": "concept", "reason": reason, "subject": subject}],
            "warnings": warnings,
            "status": "missing_input",
        }
    denominator_name = "debt_service" if metric == "dscr" else "interest"
    numerator = _sums(facts, primaries[numerator_name])
    denominator = _sums(facts, primaries[denominator_name])
    rows = []
    for period in periods:
        axis, period_id = period["axis_id"], period["period_id"]
        key = (axis, period_id)
        # shortcut: период без числителя или знаменателя пропускается, ноль вместо факта не подставляется
        if key not in denominator or key not in numerator:
            continue
        den = denominator[key]
        payment = _payment(den, sign_convention)
        phase = period_phase.get((axis, period.get("period_key_base") or period_id))
        marker = period.get("marker_class")
        # shortcut: любой маркер вне окна, пока профиль не выбирает actual или plan
        if marker:
            continue
        if metric == "dscr" and not is_coverage_test_period(
            debt_service_nonzero=payment != 0,
            phase=phase,
            explicit_phases=explicit_phases,
        ):
            continue
        if payment == 0:
            rows.append(_row(metric, period, None, "no_debt_service" if metric == "dscr" else "missing_input", "zero_denominator"))
            continue
        num = numerator[key]
        with localcontext() as ctx:
            ctx.prec = 38
            ctx.rounding = "ROUND_HALF_EVEN"
            value = quantize_ratio(num / payment)
        rows.append(_row(metric, period, value, "computed", None))
    return {"metric": metric, "rows": rows, "needs_input": [], "warnings": warnings, "status": "succeeded"}


def _primaries(bindings: list[dict]) -> dict[str, dict]:
    found = {}
    for row in bindings:
        if row.get("is_primary") and row.get("status") in _BOUND and row.get("effective_concept"):
            found[row["effective_concept"]] = row
    return found


def _groups(bindings: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for row in bindings:
        if row.get("is_primary") and row.get("effective_concept"):
            grouped.setdefault(row["effective_concept"], []).append(row)
    return grouped


def _sums(facts: list[dict], binding: dict) -> dict[tuple[str, str], Decimal]:
    totals: dict[tuple[str, str], Decimal] = {}
    row_key = binding["row_key"]
    for fact in facts:
        if fact.get("row_key") != row_key:
            continue
        number = fact.get("normalized_value")
        if number is None:
            number = fact.get("value_dec")
        if number is None:
            continue
        key = (fact["axis_id"], fact["period_id"])
        totals[key] = totals.get(key, Decimal(0)) + Decimal(number)
    return totals


def _payment(value: Decimal, convention: str) -> Decimal:
    if convention == "outflow_positive":
        return value
    return -value if value < 0 else value


def _row(metric, period, value, status, reason) -> dict:
    return {
        "metric": metric,
        "axis_id": period["axis_id"],
        "period_id": period["period_id"],
        "period_key_base": period.get("period_key_base"),
        "period_marker": period.get("period_marker"),
        "value": value,
        "status": status,
        "reason": reason,
    }
