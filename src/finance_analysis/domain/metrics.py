"""Коэффициенты покрытия (§5.7). Частное, окна и NPV считает Decimal, не DuckDB.

Периоды строк разных осей сопоставляются через `timeline_id` + `period_index`
(§5.7, инвариант основной строки): CFADS на листе CFS и обслуживание долга на
листе Debt одной шкалы — один период. Строка результата лежит на оси
знаменателя.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext

from finance_analysis.domain.mapping import marked_line_code
from finance_analysis.domain.model_type import sheet_name_key
from finance_analysis.domain.period_basis import basis_of, restate_series

MONEY = Decimal("0.000001")
RATIO = Decimal("0.0000000001")
# То же двенадцатимесячное окно, что у чистого долга к EBITDA. Привязка строки не меняется.
PARTIAL_DENOMINATOR = (
    "Окно знаменателя неполное: нет двенадцати месяцев подряд до конца периода числителя. "
    "Коэффициент не рассчитан."
)
SCALE_UNCONFIRMED = "Масштаб числителя и знаменателя не подтверждён. Коэффициент не рассчитан."
SCALE_ASSUMED = (
    "Масштаб одной стороны не подтверждён. Принято, что обе стороны выражены в единицах книги, "
    "и коэффициент рассчитан по числам на листе."
)
INTEREST_BASIS_FALLBACK = "В знаменателе взяты уплаченные проценты: строки начисленных процентов нет."
MIXED_BASIS = "Способ показа числителя и знаменателя различается. Коэффициент не рассчитан."
_BOUND = frozenset({"bound", "bound_with_warning"})
# Источники привязки от человека: только они отменяют `concept.absent` (§5.10.5).
HUMAN_SOURCES = frozenset({"confirmed", "profile"})


def quantize_ratio(value: Decimal) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 38
        ctx.rounding = "ROUND_HALF_EVEN"
        return value.quantize(RATIO)


def interest_choice(
    primaries: dict,
    order: tuple[str, ...] | list[str],
    *,
    row_fallbacks: dict | None = None,
) -> tuple[str | None, dict | None]:
    """Первое имя `interest_order`, у которого есть основная строка в primaries.

    Lookup — по id из порядка (concept или row_fallback id). Поля
    `binding_key` / `matching.rule` у fallback декларативны и сюда не входят.
    Предупреждение — когда выбраны уплаченные проценты, а строки начисления нет.
    """

    fallbacks = row_fallbacks or {}
    for name in order:
        if name not in primaries:
            continue
        canonical = None
        warn = False
        if name in fallbacks:
            canonical = getattr(fallbacks[name], "canonical", None)
            warn = canonical not in primaries
        elif name == "interest_paid":
            canonical = "interest"
            warn = "interest" not in primaries
        if warn:
            return name, {
                "code": "interest_basis_fallback",
                "params": {
                    "concept": name,
                    "canonical": canonical,
                    "fallback": name,
                    "message": INTEREST_BASIS_FALLBACK,
                },
            }
        return name, None
    return None, None


# shortcut: имена листов Outputs скопированы из sheet_roles.yaml. У привязки нет колонки листа: имя берётся из sheet, иначе из первого сегмента row_key. Поднять, когда привязка хранит лист.
_OUTPUT_SHEETS = frozenset({"outputs", "output", "итоги", "сводка"})
_PAID_INTEREST_CODE = "4123"


def confirm_paid_interest(
    primaries: dict, bindings: list[dict], absent: frozenset[str] = frozenset()
) -> dict | None:
    """Единственная строка interest с кодом 4123 занимает пустой ключ interest_paid.

    Основную interest не заменяет. Уже занятый interest_paid не переписывает.
    Ноль или несколько таких строк ничего не добавляют. Лист Outputs не доказательство.
    """

    if "interest_paid" in primaries:
        return None
    paid = [row for row in bindings if _paid_interest_row(row, absent)]
    if len(paid) != 1:
        return None
    injected = {**paid[0], "effective_concept": "interest_paid", "is_primary": True}
    primaries["interest_paid"] = injected
    return injected


def _paid_interest_row(row: dict, absent: frozenset[str]) -> bool:
    if row.get("effective_concept") != "interest" or row.get("status") not in _BOUND:
        return False
    if "interest" in absent and row.get("source") not in HUMAN_SOURCES:
        return False
    if _output_sheet(row):
        return False
    return _stated_digits(row) == _PAID_INTEREST_CODE


def _output_sheet(row: dict) -> bool:
    sheet = row.get("sheet")
    if not isinstance(sheet, str) or not sheet.strip():
        key = row.get("row_key")
        sheet = key.split("|", 1)[0] if isinstance(key, str) and "|" in key else ""
    return bool(sheet) and sheet_name_key(str(sheet)) in _OUTPUT_SHEETS


def _stated_digits(row: dict) -> str | None:
    raw = row.get("line_code")
    if not isinstance(raw, str) or not raw:
        evidence = row.get("evidence")
        if not isinstance(evidence, dict):
            packed = row.get("evidence_json")
            if isinstance(packed, str) and packed:
                try:
                    evidence = json.loads(packed)
                except json.JSONDecodeError:
                    evidence = None
        raw = evidence.get("line_code") if isinstance(evidence, dict) else None
    code = marked_line_code(raw)
    if code is None or not code.startswith("стр. "):
        return None
    digits = code.removeprefix("стр. ")
    return digits if digits.isdigit() else None


_EBITDA_DEFINITION = frozenset({"book", "ras", "ifrs", "gaap"})
_RAS_UNPUBLISHED = (
    "Коэффициент не посчитан: выбрана EBITDA (РСБУ), а она ещё не собрана. "
    "Нужны прибыль от продаж и амортизация за тот же период. "
    "Прочие доходы и расходы входят только после удаления курсовых разниц, резервов, "
    "продажи и переоценки имущества, штрафов и других статей не обычной работы. "
    "Строка EBITDA из модели сюда не подставляется."
)
_IFRS_UNPUBLISHED = (
    "Коэффициент не посчитан: выбрана EBITDA (МСФО), а она ещё не собрана. "
    "Нужны операционная прибыль и амортизация за тот же период. "
    "Продажу активов, переоценку, курсовые разницы и участие в других организациях убирают "
    "только если они внутри этой операционной прибыли и человек их отметил. "
    "Строка EBITDA из модели сюда не подставляется."
)


def ebitda_definition_error(value) -> str | None:
    """None — значение можно сохранить. Чисел и свободной формулы нет."""

    if isinstance(value, str) and value in _EBITDA_DEFINITION:
        return None
    return "ebitda_definition: book, ras, ifrs или gaap"


def ebitda_definition(profile: dict | None) -> str:
    """Пустая пометка равна book. Чужое значение не читается как книжная строка."""

    raw = (profile or {}).get("ebitda_definition")
    if raw in (None, ""):
        return "book"
    if isinstance(raw, str) and raw in _EBITDA_DEFINITION:
        return raw
    return "invalid"


def methodology_block(
    profile: dict | None,
    bindings: list[dict],
    *,
    metric: str,
    names: tuple[str, ...] | None = None,
) -> dict | None:
    """Книжная EBITDA остаётся у пометки book. Остальные пометки эту строку не подставляют.

    EBITDA по отчётности считает только профиль icr.bank. Для прочих коэффициентов
    методика расчёта не выпускается.
    """

    kind = ebitda_definition(profile)
    if kind == "book":
        return None
    if names is not None and "ebitda" not in names and "ebit" not in names:
        return None
    # Одна фраза на ICR, чистый долг к EBITDA и корпоративный DSCR. Найденные строки её не меняют.
    del bindings
    message = _methodology_message(kind)
    return {
        "metric": metric,
        "rows": [],
        "needs_input": [],
        "missing_inputs": [],
        "warnings": [{"code": "ebitda_methodology_unpublished", "params": {"message": message}}],
        "status": "not_computed",
        "message": message,
    }


_GAAP_UNPUBLISHED = (
    "Коэффициент не посчитан: выбрана отчётность GAAP, а отдельная методика расчёта EBITDA ещё не утверждена. "
    "Методика МСФО сюда не подставляется."
)


def _methodology_message(kind: str) -> str:
    if kind == "ras":
        return _RAS_UNPUBLISHED
    if kind == "ifrs":
        return _IFRS_UNPUBLISHED
    if kind == "gaap":
        return _GAAP_UNPUBLISHED
    return "Пометка определения: book, ras, ifrs или gaap."


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
    interest_order: dict | None = None,
    row_fallbacks: dict | None = None,
    profile: dict | None = None,
) -> dict:
    """`absent` — понятия с записью `concept.absent` в журнале книги (§5.10.5).

    Такое понятие не берётся из автоматической привязки, только из явного
    `concept.set` человека, который отменяет отметку.
    """

    from finance_analysis.domain.coverage import is_coverage_test_period

    if metric in {"icr", "icr_ebit"}:
        blocked = methodology_block(profile, bindings, metric=metric)
        if blocked:
            return blocked
    primaries = _primaries(bindings, absent)
    confirm_paid_interest(primaries, bindings, absent)
    order = interest_order or {}
    warnings: list[dict] = []
    fallback_parts: tuple[str, str] | None = None
    if metric == "dscr":
        if "debt_service" in primaries or not order.get("pf"):
            needed = ("cfads", "debt_service")
            denominator_name = "debt_service"
        else:
            chosen, warning = interest_choice(primaries, order["pf"], row_fallbacks=row_fallbacks)
            if "cfads" not in primaries:
                needed = ("cfads",)
                denominator_name = "debt_service"
            elif chosen is None:
                needed = ("cfads", "debt_service")
                denominator_name = "debt_service"
            elif "principal" not in primaries:
                needed = ("cfads", "principal")
                denominator_name = "principal"
            else:
                needed = ("cfads", chosen, "principal")
                denominator_name = chosen
                fallback_parts = (chosen, "principal")
                if warning:
                    warnings.append(warning)
    elif metric in {"icr", "icr_ebit"}:
        slot = "icr_ebit" if metric == "icr_ebit" else "icr"
        chosen, warning = interest_choice(
            primaries, order.get(slot, ("interest",)), row_fallbacks=row_fallbacks
        )
        needed = (chosen or "interest",)
        denominator_name = chosen or "interest"
        if warning:
            warnings.append(warning)
    else:
        return {"metric": metric, "rows": [], "needs_input": [], "warnings": [], "status": "missing_input"}
    missing = [name for name in needed if name not in primaries]
    numerator_name = None
    if metric == "icr_ebit":
        if "ebit" in primaries:
            numerator_name = "ebit"
        else:
            missing.append("ebit")
    elif metric == "icr":
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
            "missing_inputs": missing or [ambiguous[0]],
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
            "missing_inputs": list(missing),
            "warnings": warnings,
            "status": "missing_input",
        }
    numerator_basis = _flow_basis(primaries[numerator_name])
    denominator_basis = _flow_basis(primaries[denominator_name])
    named = {numerator_name: primaries[numerator_name], denominator_name: primaries[denominator_name]}
    if fallback_parts is not None:
        named["principal"] = primaries["principal"]
    if unconfirmed_scale(facts, list(named.values())):
        components, scales = _scale_bundle(facts, named)
        return _explained(
            metric,
            periods,
            "scale_unconfirmed",
            SCALE_UNCONFIRMED,
            warnings,
            home=_home_period(facts, primaries[numerator_name], periods),
            components=components,
            scales=scales,
        )
    if fallback_parts is not None and _flow_basis(primaries["principal"]) != denominator_basis:
        return _explained(metric, periods, "basis_mismatch", MIXED_BASIS, warnings)
    if numerator_basis != denominator_basis and not (numerator_basis == "ltm" and denominator_basis == "period"):
        message = MIXED_BASIS
        if metric in {"icr", "icr_ebit"}:
            message = _basis_message(numerator_name, primaries[numerator_name], primaries[denominator_name]) or MIXED_BASIS
        return _explained(metric, periods, "basis_mismatch", message, warnings)
    sheet = _assume_sheet_units(facts, list(named.values()), warnings)
    if numerator_basis == "ltm" and denominator_basis == "period":
        extra = []
        if fallback_parts is not None:
            extra.append(primaries["principal"])
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
            sheet=sheet,
            extra_denominators=extra,
        )
    aligned = aligned_keys(periods)
    numerator = _sums(facts, primaries[numerator_name], aligned, periods, sheet=sheet)
    if fallback_parts is None:
        denominator = _sums(facts, primaries[denominator_name], aligned, periods, sheet=sheet)
        home = _axes_of(facts, primaries[denominator_name])
    else:
        paid = _sums(facts, primaries[fallback_parts[0]], aligned, periods, sheet=sheet)
        repaid = _sums(facts, primaries["principal"], aligned, periods, sheet=sheet)
        # Платёж считается по каждой части отдельно и только потом складывается.
        # Сумма до знака уменьшает знаменатель, если у частей разные знаки.
        denominator = {
            key: _payment(paid[key], sign_convention) + _payment(repaid[key], sign_convention)
            for key in paid.keys() & repaid.keys()
        }
        home = _axes_of(facts, primaries[fallback_parts[0]]) | _axes_of(facts, primaries["principal"])
    if metric in {"icr", "icr_ebit"} and _numerator_misses_axis(numerator, denominator, periods, aligned, home):
        raw = _sums(facts, primaries[numerator_name], aligned, None, sheet=sheet)
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
        built = _row(metric, period, value, "computed", None)
        built["components"] = {
            numerator_name: _component_cells(facts, primaries[numerator_name], [period]),
            denominator_name: _component_cells(facts, primaries[denominator_name], [period]),
        }
        if fallback_parts is not None:
            built["components"]["principal"] = _component_cells(facts, primaries["principal"], [period])
        rows.append(built)
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
    sheet: bool = False,
    extra_denominators: list[dict] | None = None,
) -> dict:
    """Числитель `ltm` делится на сумму знаменателя за двенадцать месяцев до его конца.

    Дополнительные строки знаменателя, например основной долг рядом с процентами,
    входят в ту же сумму. Платёж берётся по каждой строке отдельно. Привязка строк
    не меняется. Неполное окно даёт `partial_window`. Окно то же, что у отношения
    чистого долга к EBITDA.
    """

    from finance_analysis.domain.cover_metrics import _window
    from finance_analysis.domain.coverage import is_coverage_test_period

    aligned = aligned_keys(periods)
    numerator = _sums(facts, numerator_binding, aligned, periods, sheet=sheet)
    denominator_bindings = [denominator_binding, *(extra_denominators or [])]
    denominators = [
        (binding, _sums(facts, binding, aligned, periods, sheet=sheet)) for binding in denominator_bindings
    ]
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
            for _binding, series in denominators:
                if dkey not in series:
                    complete = False
                    break
                total += _payment(series[dkey], sign_convention)
            if not complete:
                break
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
        numerator_name = _bound_name(numerator_binding, "cfads" if metric == "dscr" else "ebitda")
        row["components"] = {numerator_name: _component_cells(facts, numerator_binding, [period])}
        row["scale_factor"] = {numerator_name: _stored_scale(facts, numerator_binding)}
        for binding, _series in denominators:
            name = _bound_name(binding, "debt_service" if metric == "dscr" else "interest")
            row["components"][name] = _component_cells(facts, binding, window)
            row["scale_factor"][name] = _stored_scale(facts, binding)
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


def _explained(
    metric: str,
    periods: list[dict],
    status: str,
    message: str,
    warnings: list[dict],
    *,
    home: dict | None = None,
    components: dict | None = None,
    scales: dict | None = None,
) -> dict:
    """Один явный исход вместо пустого списка строк.

    Ось — ось числителя, если она известна. Ячейки и масштаб остаются в строке,
    чтобы отказ можно было сверить с книгой.
    """

    period = home if home is not None else (periods[0] if periods else None)
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
    if components is not None:
        row["components"] = components
    if scales is not None:
        row["scale_factor"] = scales
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


def _bound_name(binding: dict, default: str) -> str:
    """Имя понятия основной строки. Берётся `effective_concept`, а не сырое `concept`."""

    return str(binding.get("effective_concept") or binding.get("concept") or default)


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
    *,
    sheet: bool = False,
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
        number = _figure(fact, sheet=sheet)
        if number is None:
            continue
        own = (fact["axis_id"], fact["period_id"])
        key = aligned.get(own, own)
        totals[key] = totals.get(key, Decimal(0)) + Decimal(number)
    if periods is None:
        return totals
    return restate_series(totals, binding, periods, aligned)


def _component_cells(facts: list[dict], binding: dict, periods: list[dict]) -> list[str]:
    """Ячейки строки понятия за указанные периоды. Пустой список, если ячеек нет."""

    wanted = {(item.get("axis_id"), item.get("period_id")) for item in periods}
    found = []
    for fact in facts:
        if fact.get("row_key") != binding.get("row_key"):
            continue
        if (fact.get("axis_id"), fact.get("period_id")) not in wanted:
            continue
        cell = fact.get("cell_id")
        if cell and cell not in found:
            found.append(str(cell))
    return found


def unconfirmed_scale(facts: list[dict], bindings: list[dict]) -> bool:
    """Число строки спорит с её масштабом.

    Отсутствие масштаба у одной стороны отказом не является: тогда обе стороны
    берутся числами на листе.
    """

    return any(_scale_kind(facts, binding) == "unconfirmed" for binding in bindings)


def _assume_sheet_units(facts: list[dict], bindings: list[dict], warnings: list[dict]) -> bool:
    """Масштаб умножает коэффициент, только если он есть у каждой стороны.

    Иначе стороны считаются в единицах книги. Предупреждение одно на расчёт.
    """

    if _scale_policy(facts, bindings) != "sheet":
        return False
    warnings.append({"code": "scale_assumed", "params": {"message": SCALE_ASSUMED}})
    return True


def _scale_policy(facts: list[dict], bindings: list[dict]) -> str:
    known = sum(_stored_scale(facts, binding) is not None for binding in bindings)
    if known == 0 or known == len(bindings):
        return "plain" if known == 0 else "apply"
    return "sheet"


def _home_period(facts: list[dict], binding: dict, periods: list[dict]) -> dict | None:
    """Первый период оси числителя. Чужая ось в начале списка периодов не годится."""

    axes = {fact.get("axis_id") for fact in facts if fact.get("row_key") == binding.get("row_key")}
    for period in periods:
        if period.get("axis_id") in axes:
            return period
    return None


def _scale_bundle(facts: list[dict], named: dict[str, dict]) -> tuple[dict, dict]:
    components = {}
    scales = {}
    for name, binding in named.items():
        cells: list[str] = []
        for fact in facts:
            if fact.get("row_key") != binding.get("row_key"):
                continue
            cell = fact.get("cell_id")
            if cell and str(cell) not in cells:
                cells.append(str(cell))
        components[name] = cells
        scales[name] = _stored_scale(facts, binding)
    return components, scales


def _stored_scale(facts: list[dict], binding: dict):
    for fact in facts:
        if fact.get("row_key") != binding.get("row_key"):
            continue
        scale = fact.get("scale_factor")
        if scale not in (None, ""):
            return scale
    return None


def _scale_kind(facts: list[dict], binding: dict) -> str:
    kinds = {_one_scale(fact) for fact in facts if fact.get("row_key") == binding.get("row_key")}
    if not kinds:
        return "raw"
    if kinds == {"raw"} or kinds == {"base"}:
        return next(iter(kinds))
    return "unconfirmed"


def _one_scale(fact: dict) -> str:
    raw = _decimal(fact.get("value_dec"))
    if raw is None:
        raw = _decimal(fact.get("value"))
    norm = _decimal(fact.get("normalized_value"))
    scale = _scale(fact.get("scale_factor"))
    if scale is None:
        return "raw"
    if scale == 1:
        return "base"
    if raw is not None and norm is not None and _close(norm, raw * scale):
        return "base"
    if raw is not None and (norm is None or norm == raw):
        return "base"
    return "unconfirmed"


def _figure(fact: dict, *, sheet: bool = False) -> Decimal | None:
    """Величина ячейки.

    `sheet` берёт число на листе и не умножает его: так считается коэффициент,
    когда масштаб известен не у каждой стороны. Иначе заданный масштаб применяется,
    если нормализованное значение его ещё не учитывает.
    """

    raw = _decimal(fact.get("value_dec"))
    if raw is None:
        raw = _decimal(fact.get("value"))
    norm = _decimal(fact.get("normalized_value"))
    if sheet:
        return raw if raw is not None else norm
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
