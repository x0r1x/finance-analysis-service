"""Коэффициенты покрытия (§5.7). Частное, окна и NPV считает Decimal, не DuckDB.

Периоды строк разных осей сопоставляются через `timeline_id` + `period_index`
(§5.7, инвариант основной строки): CFADS на листе CFS и обслуживание долга на
листе Debt одной шкалы — один период. Строка результата лежит на оси
знаменателя.
"""

from __future__ import annotations

from decimal import Decimal, localcontext

from finance_analysis.domain.period_basis import restate_series

MONEY = Decimal("0.000001")
RATIO = Decimal("0.0000000001")
_BOUND = frozenset({"bound", "bound_with_warning"})
# Источники привязки от человека: только они отменяют `concept.absent` (§5.10.5).
HUMAN_SOURCES = frozenset({"confirmed", "profile"})


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
    marker_class: str | None = None,
    absent: frozenset[str] = frozenset(),
) -> dict:
    """`absent` — понятия с записью `concept.absent` в журнале книги (§5.10.5).

    Такое понятие не берётся из автоматической привязки, только из явного
    `concept.set` человека, который отменяет отметку.
    """

    from finance_analysis.domain.coverage import is_coverage_test_period

    primaries = _primaries(bindings, absent)
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
    if missing:
        subject = missing[0]
        reason = "absent_in_book" if subject in absent_concepts(bindings, absent) else "concept_unknown"
        return {
            "metric": metric,
            "rows": [],
            "needs_input": [{"kind": "concept", "reason": reason, "subject": subject}],
            "warnings": warnings,
            "status": "missing_input",
        }
    denominator_name = "debt_service" if metric == "dscr" else "interest"
    aligned = aligned_keys(periods)
    numerator = _sums(facts, primaries[numerator_name], aligned, periods)
    denominator = _sums(facts, primaries[denominator_name], aligned, periods)
    home = _axes_of(facts, primaries[denominator_name])
    rows = []
    for period in periods:
        axis, period_id = period["axis_id"], period["period_id"]
        if axis not in home:
            continue
        key = aligned.get((axis, period_id), (axis, period_id))
        # shortcut: период без числителя или знаменателя пропускается, ноль вместо факта не подставляется
        if key not in denominator or key not in numerator:
            continue
        den = denominator[key]
        payment = _payment(den, sign_convention)
        phase = period_phase.get((axis, period_id))
        if phase is None:
            phase = period_phase.get((axis, period.get("period_key_base") or period_id))
        marker = period.get("marker_class")
        if marker_class and marker and marker != marker_class:
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


def _primaries(bindings: list[dict], absent: frozenset[str] = frozenset()) -> dict[str, dict]:
    found = {}
    for row in bindings:
        concept = row.get("effective_concept")
        if not (row.get("is_primary") and row.get("status") in _BOUND and concept):
            continue
        if concept in absent and row.get("source") not in HUMAN_SOURCES:
            continue
        found[concept] = row
    return found


def absent_concepts(bindings: list[dict], absent: frozenset[str] = frozenset()) -> set[str]:
    """`concept.absent` из журнала и строки, которые человек снял с отсутствующего понятия."""

    marked = {
        row.get("effective_concept")
        for row in bindings
        if row.get("source") == "confirmed" and row.get("status") == "unknown" and row.get("effective_concept")
    }
    restored = {concept for concept, row in _primaries(bindings).items() if row.get("source") in HUMAN_SOURCES}
    return (marked | set(absent)) - restored


def _groups(bindings: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for row in bindings:
        if row.get("is_primary") and row.get("effective_concept"):
            grouped.setdefault(row["effective_concept"], []).append(row)
    return grouped


def aligned_keys(periods: list[dict]) -> dict[tuple[str, str], tuple]:
    """(axis_id, period_id) → ключ шкалы: (`timeline_id`, `period_index`), иначе свой."""

    found = {}
    for period in periods:
        timeline = period.get("timeline_id")
        index = period.get("period_index")
        if timeline and index is not None:
            found[(period["axis_id"], period["period_id"])] = (timeline, int(index))
    return found


def _axes_of(facts: list[dict], binding: dict) -> set[str]:
    return {fact["axis_id"] for fact in facts if fact.get("row_key") == binding["row_key"]}


def _sums(
    facts: list[dict],
    binding: dict,
    aligned: dict | None = None,
    periods: list[dict] | None = None,
) -> dict[tuple, Decimal]:
    """Сумма строки по ключу шкалы. Нарастающий итог переводится в значение за период.

    Перевод делается только когда у привязки есть календарь и способ показа
    поставлен по заголовку или по формуле. Строка `ltm` здесь не складывается
    и не выбрасывается: окно само берёт её конец.
    """

    totals: dict[tuple, Decimal] = {}
    row_key = binding["row_key"]
    aligned = aligned or {}
    for fact in facts:
        if fact.get("row_key") != row_key:
            continue
        number = fact.get("normalized_value")
        if number is None:
            number = fact.get("value_dec")
        if number is None:
            continue
        own = (fact["axis_id"], fact["period_id"])
        key = aligned.get(own, own)
        totals[key] = totals.get(key, Decimal(0)) + Decimal(number)
    if periods is None:
        return totals
    return restate_series(totals, binding, periods, aligned)


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
