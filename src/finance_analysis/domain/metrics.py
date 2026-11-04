"""Коэффициенты покрытия (§5.7). Частное, окна и NPV считает Decimal, не DuckDB.

Периоды строк разных осей сопоставляются через `timeline_id` + `period_index`
(§5.7, инвариант основной строки): CFADS на листе CFS и обслуживание долга на
листе Debt одной шкалы — один период. Строка результата лежит на оси
знаменателя.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation, localcontext

from finance_analysis.domain.period_basis import basis_of, restate_series

MONEY = Decimal("0.000001")
RATIO = Decimal("0.0000000001")
# То же двенадцатимесячное окно, что у чистого долга к EBITDA. Привязка строки не меняется.
PARTIAL_DENOMINATOR = (
    "Окно знаменателя неполное: нет двенадцати месяцев подряд до конца периода числителя. "
    "Коэффициент не рассчитан."
)
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
    numerator_basis = _flow_basis(primaries[numerator_name])
    denominator_basis = _flow_basis(primaries[denominator_name])
    if numerator_basis == "ltm" and denominator_basis == "period":
        return _ltm_numerator(
            metric,
            facts,
            primaries[numerator_name],
            primaries[denominator_name],
            periods,
            warnings,
            sign_convention,
            period_phase=period_phase,
            explicit_phases=explicit_phases,
            marker_class=marker_class,
        )
    if metric == "icr" and numerator_basis != denominator_basis:
        mismatch = _basis_message(numerator_name, primaries[numerator_name], primaries[denominator_name])
        if mismatch:
            return _explained(metric, periods, "basis_mismatch", mismatch, warnings)
    aligned = aligned_keys(periods)
    numerator = _sums(facts, primaries[numerator_name], aligned, periods)
    denominator = _sums(facts, primaries[denominator_name], aligned, periods)
    home = _axes_of(facts, primaries[denominator_name])
    if metric == "icr" and _numerator_misses_axis(numerator, denominator, periods, aligned, home):
        raw = _sums(facts, primaries[numerator_name], aligned, None)
        if not _numerator_misses_axis(raw, denominator, periods, aligned, home):
            message = (
                "Нарастающий итог числителя ICR не удалось перевести в значение за период. "
                "Коэффициент не рассчитан."
            )
        else:
            message = "Числитель ICR не содержит значений на оси процентов. Коэффициент не рассчитан."
        return _explained(metric, periods, "input_absent", message, warnings)
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


def _ltm_numerator(
    metric: str,
    facts: list[dict],
    numerator_binding: dict,
    denominator_binding: dict,
    periods: list[dict],
    warnings: list[dict],
    sign_convention: str,
    *,
    period_phase: dict,
    explicit_phases: bool,
    marker_class: str | None,
) -> dict:
    """Числитель `ltm` делится на сумму знаменателя за двенадцать месяцев до его конца.

    Привязка строк не меняется. Неполное окно даёт `partial_window`. Окно то же,
    что у отношения чистого долга к EBITDA.
    """

    from finance_analysis.domain.cover_metrics import _window
    from finance_analysis.domain.coverage import is_coverage_test_period

    aligned = aligned_keys(periods)
    numerator = _sums(facts, numerator_binding, aligned, periods)
    denominator = _sums(facts, denominator_binding, aligned, periods)
    numerator_axes = _axes_of(facts, numerator_binding)
    denominator_axes = _axes_of(facts, denominator_binding)
    ordered = _dated_periods([period for period in periods if period["axis_id"] in denominator_axes])
    rows = []
    computed = False
    for period in _dated_periods([period for period in periods if period["axis_id"] in numerator_axes]):
        marker = period.get("marker_class")
        if marker_class and marker and marker != marker_class:
            continue
        key = aligned.get((period["axis_id"], period["period_id"]), (period["axis_id"], period["period_id"]))
        if key not in numerator:
            continue
        window = _window(ordered, period, "lookback")
        if window is None:
            rows.append(_noted(metric, period, "partial_window", PARTIAL_DENOMINATOR))
            continue
        total = Decimal(0)
        complete = True
        for item in window:
            dkey = aligned.get((item["axis_id"], item["period_id"]), (item["axis_id"], item["period_id"]))
            if dkey not in denominator:
                complete = False
                break
            total += _payment(denominator[dkey], sign_convention)
        if not complete:
            rows.append(_noted(metric, period, "partial_window", PARTIAL_DENOMINATOR))
            continue
        phase = period_phase.get((period["axis_id"], period["period_id"]))
        if metric == "dscr" and not is_coverage_test_period(
            debt_service_nonzero=total != 0,
            phase=phase,
            explicit_phases=explicit_phases,
        ):
            continue
        if total == 0:
            status = "no_debt_service" if metric == "dscr" else "missing_input"
            rows.append(_row(metric, period, None, status, "zero_denominator"))
            continue
        with localcontext() as ctx:
            ctx.prec = 38
            ctx.rounding = "ROUND_HALF_EVEN"
            value = quantize_ratio(numerator[key] / total)
        row = _row(metric, period, value, "computed", None)
        row["window"] = [item["period_id"] for item in window]
        rows.append(row)
        computed = True
    if not rows:
        return _explained(metric, periods, "partial_window", PARTIAL_DENOMINATOR, warnings)
    status = "succeeded" if computed else "partial_window"
    result = {"metric": metric, "rows": rows, "needs_input": [], "warnings": warnings, "status": status}
    if not computed:
        result["message"] = PARTIAL_DENOMINATOR
    return result


def _noted(metric: str, period: dict, status: str, message: str) -> dict:
    row = _row(metric, period, None, status, status)
    row["message"] = message
    return row


def _dated_periods(periods: list[dict]) -> list[dict]:
    found = []
    for period in periods:
        start = _as_date(period.get("period_start"))
        end = _as_date(period.get("period_end"))
        found.append({**period, "period_start": start, "period_end": end})
    return sorted(found, key=lambda item: (item["period_end"] or date.min, int(item.get("period_index") or 0)))


def _as_date(value) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _explained(metric: str, periods: list[dict], status: str, message: str, warnings: list[dict]) -> dict:
    """Один явный исход вместо пустого списка строк."""

    period = periods[0] if periods else None
    if period is None:
        row = {
            "metric": metric,
            "axis_id": None,
            "period_id": None,
            "period_key_base": None,
            "period_marker": None,
            "value": None,
            "status": status,
            "reason": status,
            "message": message,
        }
    else:
        row = _row(metric, period, None, status, status)
        row["message"] = message
    return {"metric": metric, "rows": [row], "needs_input": [], "warnings": warnings, "status": status, "message": message}


def _basis_message(numerator_name: str, numerator: dict, denominator: dict) -> str | None:
    """Сообщение, если способ показа числителя нельзя делить на проценты за период."""

    left = _flow_basis(numerator)
    right = _flow_basis(denominator)
    if left == right:
        return None
    title = "EBITDA" if numerator_name == "ebitda" else "EBIT"
    return (
        f"Строка {title} имеет способ показа «{left}», а строка процентов — «{right}». "
        "ICR по этим строкам не рассчитан."
    )


def _flow_basis(binding: dict) -> str:
    basis, source = basis_of(binding)
    if basis == "ytd" and source in {"header", "formula"}:
        return "period"
    return basis


def _numerator_misses_axis(numerator: dict, denominator: dict, periods: list[dict], aligned: dict, home: set[str]) -> bool:
    """У процентов есть значения, но ни один период не содержит обе стороны."""

    seen_denominator = False
    for period in periods:
        if period["axis_id"] not in home:
            continue
        key = aligned.get((period["axis_id"], period["period_id"]), (period["axis_id"], period["period_id"]))
        if key not in denominator:
            continue
        seen_denominator = True
        if key in numerator:
            return False
    return seen_denominator


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
        number = _figure(fact)
        if number is None:
            continue
        own = (fact["axis_id"], fact["period_id"])
        key = aligned.get(own, own)
        totals[key] = totals.get(key, Decimal(0)) + Decimal(number)
    if periods is None:
        return totals
    return restate_series(totals, binding, periods, aligned)


def _figure(fact: dict) -> Decimal | None:
    """Величина ячейки в одной шкале со второй стороной коэффициента.

    Если `scale_factor` задан, а `normalized_value` всё ещё равен числу на листе,
    число умножается на масштаб. Уже приведённое значение не умножается второй раз.
    Без масштаба остаётся прежнее правило: нормализованное значение, иначе `value_dec`.
    """

    raw = _decimal(fact.get("value_dec"))
    if raw is None:
        raw = _decimal(fact.get("value"))
    norm = _decimal(fact.get("normalized_value"))
    scale = _scale(fact.get("scale_factor"))
    if scale is None or scale == 1:
        return norm if norm is not None else raw
    if raw is not None and norm is not None and _close(norm, raw * scale):
        return norm
    if raw is not None and (norm is None or norm == raw):
        return raw * scale
    return norm


def _decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _scale(value) -> Decimal | None:
    number = _decimal(value)
    if number is None or number == 0:
        return None
    return number


def _close(left: Decimal, right: Decimal) -> bool:
    return abs(left - right) <= max(abs(right) * Decimal("0.0001"), Decimal("0.01"))


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
