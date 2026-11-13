"""Составные коэффициенты среза 2: ковенантный DSCR, чистый долг и эскроу.

Арифметика только над привязанными строками. Чисел из профиля нет: оттуда
приходят состав числителя, знаменателя и окно.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from itertools import pairwise

from finance_analysis.domain.cash_flow import net_cash_flow
from finance_analysis.domain.cover_metrics import (
    _missing,
    _ordered,
    _ratio,
    _window,
    grain_months,
)
from finance_analysis.domain.metrics import (
    MIXED_BASIS,
    PARTIAL_DENOMINATOR,
    SCALE_UNCONFIRMED,
    _assume_sheet_units,
    _axes_of,
    _component_cells,
    _flow_basis,
    _payment,
    _primaries,
    _sums,
    aligned_keys,
    coverage_ratio,
    interest_choice,
    lease_interest_coverage,
    unconfirmed_scale,
)
from finance_analysis.domain.model_type import Composed, Side
from finance_analysis.domain.period_basis import basis_of
from finance_analysis.domain.returns import fcf_identity, project_return

DEFAULT_DEFINITION_TEXT = "определение по умолчанию, не из договора"
_WINDOWS = frozenset({"LTM", "period"})
_FIELDS = frozenset({"numerator", "denominator", "window", "basis_ref"})
_SIDE_FIELDS = frozenset({"plus", "minus"})
_CYCLE = frozenset({"dscr", "dscr_covenant"})
_MISMATCH = Decimal("0.005")
_CASH_OTHER = "other_financial_debt_service"
_CASH_CORE = ("ocf", "interest_paid", "capex", "principal")
_CAPITALIZED_INTEREST = re.compile(r"(?<!\d)4224(?!\d)")
CAPITALIZED_INTEREST = (
    "Проценты в стоимости инвестиционного актива, в надбавку к OCF не входят."
)
# shortcut: год i — календарный год по дате конца периода, другой финансовый год — когда в книге появится дата закрытия года
PARTIAL_YEAR = (
    "Год i неполный: нет непрерывных двенадцати месяцев до 31 декабря. Коэффициент не рассчитан."
)


def _number(value) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, dict):
        return any(_number(item) for item in value.values())
    if isinstance(value, list):
        return any(_number(item) for item in value)
    return False


def _terms(side: dict) -> list:
    return [*(side.get("plus") or []), *(side.get("minus") or [])]


def dscr_definition_error(value, *, concepts: frozenset[str], money: frozenset[str]) -> str | None:
    """None — структуру можно сохранить. Числа, чужие понятия и цикл отвергаются."""

    if not isinstance(value, dict) or set(value) - _FIELDS or _number(value):
        return "dscr_definition: только состав числителя и знаменателя, окно и basis_ref, без чисел"
    if value.get("window") not in _WINDOWS:
        return "dscr_definition: окно LTM или period"
    if "basis_ref" in value and not isinstance(value["basis_ref"], str):
        return "dscr_definition: basis_ref — строка"
    for name in ("numerator", "denominator"):
        problem = _side_error(value.get(name), concepts, money, name)
        if problem:
            return problem
    if not _terms(value["numerator"]):
        return "dscr_definition: числитель не пуст"
    if not _terms(value["denominator"]):
        return "dscr_definition: знаменатель не пуст"
    return None


def _side_error(side, concepts: frozenset[str], money: frozenset[str], name: str) -> str | None:
    if not isinstance(side, dict) or set(side) - _SIDE_FIELDS:
        return f"dscr_definition: {name} — plus и minus"
    terms = _terms(side)
    if any(not isinstance(item, str) for item in terms):
        return f"dscr_definition: {name} — id понятий"
    if any(item not in concepts for item in terms):
        return "dscr_definition: понятие вне каталога"
    if any(item in _CYCLE for item in terms):
        return "dscr_definition: цикл на dscr"
    if any(item not in money for item in terms):
        return "dscr_definition: слагаемые должны быть деньгами"
    return None


def _parse(value: dict) -> Composed:
    return Composed(_as_side(value["numerator"]), _as_side(value["denominator"]), str(value["window"]))


def _as_side(raw: dict) -> Side:
    return Side(tuple(raw.get("plus") or ()), tuple(raw.get("minus") or ()))


def resolve_covenant(
    profile: dict | None,
    profile_ref: str | None,
    default: Composed,
    *,
    concepts: frozenset[str],
    money: frozenset[str],
) -> tuple[Composed, str, dict | None, list[dict]]:
    raw = (profile or {}).get("dscr_definition")
    note = {"code": "dscr_default_definition", "params": {"text": DEFAULT_DEFINITION_TEXT}}
    if not raw:
        return default, "default", None, [note]
    problem = dscr_definition_error(raw, concepts=concepts, money=money)
    if problem:
        return default, "default", None, [note, {"code": "dscr_definition_invalid", "params": {"reason": problem}}]
    ref = {
        "profile_id": profile_ref.split("@", 1)[0] if profile_ref and "@" in profile_ref else profile_ref,
        "profile_version": profile_ref,
        "basis_ref": raw.get("basis_ref"),
    }
    return _parse(raw), "profile", ref, []


def covenant_dscr(
    *,
    facts: list[dict],
    bindings: list[dict],
    periods: list[dict],
    default: Composed,
    concepts: frozenset[str],
    money: frozenset[str],
    profile: dict | None = None,
    profile_ref: str | None = None,
    sign_convention: str = "outflow_negative",
    marker_class: str | None = None,
    absent: frozenset[str] = frozenset(),
    interest_order: dict | None = None,
    row_fallbacks: dict | None = None,
) -> dict:
    definition, source, ref, notes = resolve_covenant(
        profile, profile_ref, default, concepts=concepts, money=money
    )
    definition, fallback = _swap_interest(
        definition,
        _primaries(bindings, absent),
        (interest_order or {}).get("corporate_covenant", ()),
        row_fallbacks=row_fallbacks,
    )
    if fallback:
        notes = [*notes, fallback]
    result = composed_ratio(
        "dscr",
        definition,
        facts=facts,
        bindings=bindings,
        periods=periods,
        sign_convention=sign_convention,
        marker_class=marker_class,
        absent=absent,
    )
    if source == "default" and result["status"] == "succeeded":
        notes = [*notes, *_mismatch(result["rows"], facts, bindings, periods, absent)]
    return {**result, "warnings": [*notes, *result["warnings"]], "definition_source": source, "definition_ref": ref}


def composed_ratio(
    metric: str,
    formula: Composed,
    *,
    facts: list[dict],
    bindings: list[dict],
    periods: list[dict],
    sign_convention: str = "outflow_negative",
    marker_class: str | None = None,
    absent: frozenset[str] = frozenset(),
) -> dict:
    formula, unbound = _leverage_formula(metric, formula, bindings, absent)
    needed = (
        *formula.numerator.plus,
        *formula.numerator.minus,
        *formula.denominator.plus,
        *formula.denominator.minus,
    )
    needed = tuple(name for name in needed if name not in unbound)
    missing = _missing(metric, bindings, needed, absent)
    if missing:
        return missing
    primaries = _primaries(bindings, absent)
    inputs = list(dict.fromkeys(needed))
    if unconfirmed_scale(facts, [primaries[name] for name in inputs]):
        return _refused(metric, periods, "scale_unconfirmed", SCALE_UNCONFIRMED, inputs)
    flow = {_flow_basis(primaries[name]) for name in inputs}
    reconciled = formula.window == "LTM" or (formula.window == "period" and _rolls(primaries, formula))
    if len(flow) > 1 and not reconciled:
        return _refused(metric, periods, "basis_mismatch", MIXED_BASIS, inputs)
    warnings: list[dict] = []
    sheet = _assume_sheet_units(facts, [primaries[name] for name in inputs], warnings)
    aligned = aligned_keys(periods)
    series = {
        name: _sums(facts, primaries[name], aligned, periods, sheet=sheet) for name in dict.fromkeys(needed)
    }
    basis = {name: basis_of(primaries[name])[0] for name in series}
    roll = formula.window == "period" and _rolls(primaries, formula)
    window_name = "LTM" if roll else formula.window
    # Строка EBITDA со способом `ltm` уже покрывает двенадцать месяцев.
    # Четыре квартала такой строки не складываются и не требуют полного окна.
    leverage = metric in _LEVERAGE
    ebitda_ltm = leverage and basis.get("ebitda") == "ltm"
    span_name = "period" if ebitda_ltm else window_name
    home_name = formula.denominator.plus[0] if formula.denominator.plus else formula.denominator.minus[0]
    numerator_names = (*formula.numerator.plus, *formula.numerator.minus)
    rows = []
    negative_denominator = False
    for axis in sorted(_axes_of(facts, primaries[home_name])):
        ordered = _ordered(periods, axis)
        axis_keys = [aligned.get((axis, item["period_id"]), (axis, item["period_id"])) for item in ordered]
        on_axis = any(key in (series.get(name) or {}) for name in numerator_names for key in axis_keys)
        dated = any(
            _stock_choice(item, periods, aligned, series.get(name) or {})[0] is not None
            for name in numerator_names
            for item in ordered
        )
        debt_on_axis = not leverage or on_axis or dated
        for period in ordered:
            if unbound:
                rows.append(
                    _line(
                        metric,
                        period,
                        None,
                        "input_absent",
                        "input_absent",
                        list(dict.fromkeys((*inputs, *unbound))),
                        None,
                        message=_OFF_BALANCE_ABSENT,
                    )
                )
                continue
            marker = period.get("marker_class")
            if marker_class and marker and marker != marker_class:
                continue
            keys, window, problem = _span(span_name, ordered, period, aligned, axis)
            if problem and not debt_on_axis:
                rows.append(
                    _line(
                        metric,
                        period,
                        None,
                        "input_absent",
                        "input_absent",
                        inputs,
                        window,
                        message=_stock_absent_message(formula.numerator),
                    )
                )
                continue
            if problem:
                message = PARTIAL_DENOMINATOR if roll and problem == "partial_window" else None
                rows.append(_line(metric, period, None, "not_computed", problem, inputs, window, message=message))
                continue
            if leverage:
                numerator, stock_problem = _stock_numerator(
                    period, periods, aligned, series, formula.numerator
                )
                if stock_problem:
                    rows.append(
                        _line(
                            metric,
                            period,
                            None,
                            "not_computed",
                            stock_problem,
                            inputs,
                            window,
                            message=_AMBIGUOUS_STOCK,
                        )
                    )
                    continue
                denominator = _part(keys, series, "ebitda", sign_convention, False, basis)
                present = any(key in (series.get(name) or {}) for name in numerator_names for key in keys)
                if numerator is None and not present:
                    rows.append(
                        _line(
                            metric,
                            period,
                            None,
                            "input_absent",
                            "input_absent",
                            inputs,
                            window,
                            message=_stock_absent_message(formula.numerator),
                        )
                    )
                    continue
            else:
                numerator = _total(keys, series, formula.numerator, sign_convention, pay_plus=False, basis=basis)
                denominator = _total(keys, series, formula.denominator, sign_convention, pay_plus=True, basis=basis)
            if numerator is None or denominator is None:
                rows.append(_line(metric, period, None, "missing_input", "no_binding", inputs, window))
                continue
            if denominator == 0:
                status = "no_debt_service" if metric == "dscr" else "missing_input"
                rows.append(_line(metric, period, None, status, "zero_denominator", inputs, window))
                continue
            if leverage and denominator < 0:
                negative_denominator = True
            line = _line(metric, period, _ratio(numerator, denominator), "computed", None, inputs, window)
            if leverage:
                used = [period] if ebitda_ltm else [item for item in ordered if item["period_id"] in set(window or [])]
                line["components"] = {
                    name: _component_cells(facts, primaries[name], _same_end(periods, period))
                    for name in numerator_names
                }
                line["components"]["ebitda"] = _component_cells(facts, primaries["ebitda"], used or [period])
            rows.append(line)
    if negative_denominator:
        warnings.append({"code": "ebitda_non_positive", "params": {"message": _EBITDA_NON_POSITIVE}})
    if metric == "escrow_coverage":
        warnings.extend(_escrow_coverage_book(rows, facts, bindings, periods, absent, warnings))
    status = "succeeded"
    message = None
    stock_absent = leverage and any(row["status"] == "input_absent" for row in rows)
    if stock_absent and not any(row["status"] == "computed" for row in rows):
        status = "input_absent"
        message = next(
            (row.get("message") for row in rows if row.get("message")),
            _stock_absent_message(formula.numerator),
        )
    elif roll and rows and not any(row["status"] == "computed" for row in rows):
        if any(row.get("reason") == "partial_window" for row in rows):
            status = "partial_window"
            message = PARTIAL_DENOMINATOR
    elif any(row.get("reason") == "ambiguous_stock" for row in rows) and not any(row["status"] == "computed" for row in rows):
        status = "not_computed"
        message = _AMBIGUOUS_STOCK
    result = {"metric": metric, "rows": rows, "needs_input": [], "warnings": warnings, "status": status}
    if message:
        result["message"] = message
    return result


def _rolls(primaries: dict, formula: Composed) -> bool:
    """Числитель `ltm` и знаменатель за период: знаменатель собирается окном LTM.

    Привязка строк не меняется. Окно уже заданное как LTM здесь не подменяется.
    """

    numerator = [*formula.numerator.plus, *formula.numerator.minus]
    denominator = [*formula.denominator.plus, *formula.denominator.minus]
    if not numerator or not denominator:
        return False
    if any(_flow_basis(primaries[name]) != "ltm" for name in numerator):
        return False
    return all(_flow_basis(primaries[name]) == "period" for name in denominator)


def cash_covenant_dscr(
    *,
    facts: list[dict],
    bindings: list[dict],
    periods: list[dict],
    sign_convention: str = "outflow_negative",
    marker_class: str | None = None,
    absent: frozenset[str] = frozenset(),
) -> dict:
    """Кассовый DSCR года i. OCF со знаком, остальные входы — модули платежей.

    `debt_service` в знаменатель не входит. `concept.absent` на прочей
    финансовой задолженности убирает третье слагаемое и не подставляет ноль
    вместо ненайденной строки. Неполный календарный год не считается.
    """

    include_other = _CASH_OTHER not in absent
    needed = (*_CASH_CORE, *((_CASH_OTHER,) if include_other else ()))
    missing = _missing("dscr", bindings, needed, absent)
    if missing:
        note = _capitalized_interest(bindings)
        if note:
            missing["warnings"] = [*missing["warnings"], note]
        return missing
    primaries = _primaries(bindings, absent)
    inputs = list(needed)
    if unconfirmed_scale(facts, [primaries[name] for name in inputs]):
        return _refused("dscr", periods, "scale_unconfirmed", SCALE_UNCONFIRMED, inputs)
    if len({_flow_basis(primaries[name]) for name in inputs}) > 1:
        return _refused("dscr", periods, "basis_mismatch", MIXED_BASIS, inputs)
    warnings: list[dict] = []
    note = _capitalized_interest(bindings)
    if note:
        warnings.append(note)
    sheet = _assume_sheet_units(facts, [primaries[name] for name in inputs], warnings)
    aligned = aligned_keys(periods)
    series = {name: _sums(facts, primaries[name], aligned, periods, sheet=sheet) for name in inputs}
    rows = []
    for axis in sorted(_axes_of(facts, primaries["ocf"])):
        ordered = _ordered(periods, axis)
        for window, problem in _cash_spans(ordered):
            anchor = window[-1]
            marker = anchor.get("marker_class")
            if marker_class and marker and marker != marker_class:
                continue
            keys = [aligned.get((axis, item["period_id"]), (axis, item["period_id"])) for item in window]
            window_ids = [item["period_id"] for item in window]
            if problem:
                message = PARTIAL_YEAR if problem == "partial_window" else None
                rows.append(_line("dscr", anchor, None, "not_computed", problem, inputs, window_ids, message=message))
                continue
            numerator = _cash_numerator(keys, series, sign_convention)
            denominator = _cash_denominator(keys, series, sign_convention, include_other=include_other)
            if numerator is None or denominator is None:
                rows.append(_line("dscr", anchor, None, "missing_input", "no_binding", inputs, window_ids))
                continue
            if denominator == 0:
                rows.append(_line("dscr", anchor, None, "no_debt_service", "zero_denominator", inputs, window_ids))
                continue
            line = _line("dscr", anchor, _ratio(numerator, denominator), "computed", None, inputs, window_ids)
            line["components"] = {
                name: _component_cells(facts, primaries[name], window) for name in inputs
            }
            line["variant"] = "cash_covenant"
            rows.append(line)
    status = "succeeded"
    message = None
    if rows and not any(row["status"] == "computed" for row in rows):
        if any(row.get("reason") == "partial_window" for row in rows):
            status = "partial_window"
            message = PARTIAL_YEAR
        elif any(row.get("reason") in {"no_period_dates", "grain_unknown"} for row in rows):
            status = "not_computed"
    result = {"metric": "dscr", "rows": rows, "needs_input": [], "warnings": warnings, "status": status}
    if message:
        result["message"] = message
    return result


def _capitalized_interest(bindings: list[dict]) -> dict | None:
    for row in bindings:
        blob = " ".join(str(row.get(key) or "") for key in ("label", "label_path_text", "code"))
        if _CAPITALIZED_INTEREST.search(blob):
            return {"code": "capitalized_interest", "params": {"message": CAPITALIZED_INTEREST, "code": "4224"}}
    return None


def _cash_spans(ordered: list[dict]) -> list[tuple[list[dict], str | None]]:
    if not ordered:
        return []
    months = {grain_months(item.get("grain")) for item in ordered}
    if len(months) != 1 or None in months:
        return [(ordered[-1:], "grain_unknown")]
    span = next(iter(months))
    if span is not None and span >= 12:
        return [([item], None) for item in ordered]
    if any(item.get("period_start") is None or item.get("period_end") is None for item in ordered):
        return [(ordered[-1:], "no_period_dates")]
    groups: dict[int, list[dict]] = {}
    for item in ordered:
        groups.setdefault(item["period_end"].year, []).append(item)
    found = []
    for year in sorted(groups):
        items = sorted(groups[year], key=lambda item: (item["period_end"], int(item.get("period_index") or 0)))
        problem = None
        if items[0]["period_start"] != date(year, 1, 1) or items[-1]["period_end"] != date(year, 12, 31):
            problem = "partial_window"
        else:
            for before, after in pairwise(items):
                if before["period_end"] + timedelta(days=1) != after["period_start"]:
                    problem = "partial_window"
                    break
        found.append((items, problem))
    return found


def _cash_numerator(keys, series: dict, convention: str) -> Decimal | None:
    earned = _cash_signed(keys, series, "ocf")
    paid = _cash_paid(keys, series, "interest_paid", convention)
    spent = _cash_paid(keys, series, "capex", convention)
    if earned is None or paid is None or spent is None:
        return None
    return earned + paid - spent


def _cash_denominator(keys, series: dict, convention: str, *, include_other: bool) -> Decimal | None:
    principal = _cash_paid(keys, series, "principal", convention)
    paid = _cash_paid(keys, series, "interest_paid", convention)
    if principal is None or paid is None:
        return None
    total = principal + paid
    if not include_other:
        return total
    other = _cash_paid(keys, series, _CASH_OTHER, convention)
    if other is None:
        return None
    return total + other


def _cash_signed(keys, series: dict, name: str) -> Decimal | None:
    total = Decimal(0)
    values = series[name]
    for key in keys:
        if key not in values:
            return None
        total += values[key]
    return total


def _cash_paid(keys, series: dict, name: str, convention: str) -> Decimal | None:
    total = Decimal(0)
    values = series[name]
    for key in keys:
        if key not in values:
            return None
        total += _payment(values[key], convention)
    return total


def select_ratio(
    metric: str,
    variant: str | None,
    common: dict,
    *,
    profile: dict | None,
    profile_ref: str | None,
    composed: dict[str, Composed],
    concepts: frozenset[str],
    money: frozenset[str],
    interest_order: dict | None = None,
    row_fallbacks: dict | None = None,
) -> dict:
    """Вариант `corporate_covenant` считает определение из профиля или из каталога."""

    if metric in {"npv", "irr"}:
        return project_return(
            metric,
            facts=common["facts"],
            bindings=common["bindings"],
            periods=common["periods"],
            absent=common["absent"],
        )
    if metric == "fcf_identity":
        return fcf_identity(
            variant,
            facts=common["facts"],
            bindings=common["bindings"],
            periods=common["periods"],
            absent=common["absent"],
            sign_convention=common.get("sign_convention") or "outflow_negative",
        )
    if metric == "dscr" and variant == "cash_covenant":
        # Профиль dscr_definition этот вариант не переписывает: знак OCF и модуль процентов фиксированы.
        return cash_covenant_dscr(
            facts=common["facts"],
            bindings=common["bindings"],
            periods=common["periods"],
            sign_convention=common["sign_convention"],
            marker_class=common["marker_class"],
            absent=common["absent"],
        )
    if metric == "icr_lease":
        # Состав каталога не вычитает долг из платежа и не ловит двойной счёт.
        return lease_interest_coverage(
            facts=common["facts"],
            bindings=common["bindings"],
            periods=common["periods"],
            sign_convention=common["sign_convention"],
            marker_class=common["marker_class"],
            absent=common["absent"],
        )
    if metric == "dscr" and variant == "corporate_covenant":
        return covenant_dscr(
            facts=common["facts"],
            bindings=common["bindings"],
            periods=common["periods"],
            sign_convention=common["sign_convention"],
            marker_class=common["marker_class"],
            absent=common["absent"],
            profile=profile,
            profile_ref=profile_ref,
            default=composed["dscr.corporate_covenant"],
            concepts=concepts,
            money=money,
            interest_order=interest_order,
            row_fallbacks=row_fallbacks,
        )
    if metric == "ncf":
        return net_cash_flow(
            facts=common["facts"],
            bindings=common["bindings"],
            periods=common["periods"],
            sign_convention=common["sign_convention"],
            absent=common["absent"],
        )
    formula = composed.get(metric)
    if formula is not None:
        return composed_ratio(
            metric,
            formula,
            facts=common["facts"],
            bindings=common["bindings"],
            periods=common["periods"],
            sign_convention=common["sign_convention"],
            marker_class=common["marker_class"],
            absent=common["absent"],
        )
    return coverage_ratio(
        metric=metric, interest_order=interest_order, row_fallbacks=row_fallbacks, **common
    )


def _swap_interest(
    formula: Composed,
    primaries: dict,
    order: tuple[str, ...] | list[str],
    *,
    row_fallbacks: dict | None = None,
) -> tuple[Composed, dict | None]:
    """Подменяет начисленные проценты следующим именем порядка, если основной строки нет."""

    names = (
        *formula.numerator.plus,
        *formula.numerator.minus,
        *formula.denominator.plus,
        *formula.denominator.minus,
    )
    if "interest" not in names or not order:
        return formula, None
    chosen, warning = interest_choice(primaries, order, row_fallbacks=row_fallbacks)
    if chosen is None or chosen == "interest":
        return formula, None

    def replace(side: Side) -> Side:
        return Side(
            tuple(chosen if name == "interest" else name for name in side.plus),
            tuple(chosen if name == "interest" else name for name in side.minus),
        )

    return Composed(replace(formula.numerator), replace(formula.denominator), formula.window), warning


def _span(window: str, ordered: list[dict], period: dict, aligned: dict, axis: str):
    own = aligned.get((axis, period["period_id"]), (axis, period["period_id"]))
    if window == "period":
        return [own], [period["period_id"]], None
    months = grain_months(period.get("grain"))
    if months is not None and months >= 12:
        return [own], [period["period_id"]], None
    if months is None:
        return None, None, "grain_unknown"
    span = _window(ordered, period, "lookback")
    if span is None:
        return None, None, "partial_window"
    keys = [aligned.get((axis, item["period_id"]), (axis, item["period_id"])) for item in span]
    return keys, [item["period_id"] for item in span], None


_AMBIGUOUS_STOCK = (
    "На одну дату конца периода приходится несколько остатков одной зернистости. "
    "Остаток не выбран, коэффициент не рассчитан."
)


def _stock_choice(
    period: dict, periods: list[dict], aligned: dict, values: dict
) -> tuple[Decimal | None, str | None]:
    """Остаток на дату конца периода, без зависимости от порядка списка.

    Сначала берётся остаток той же оси. Если его нет, берётся единственный
    остаток той же зернистости. Несколько таких остатков не выбираются молча:
    метод возвращает причину `ambiguous_stock`. Ось без своей даты остаток не отдаёт.
    """

    axis = period["axis_id"]
    own = aligned.get((axis, period["period_id"]), (axis, period["period_id"]))
    if own in values:
        return values[own], None
    end = period.get("period_end")
    if end is None:
        return None, None
    seen: dict[tuple, dict] = {}
    for item in periods:
        if item.get("period_end") != end:
            continue
        key = aligned.get((item["axis_id"], item["period_id"]), (item["axis_id"], item["period_id"]))
        if key in values:
            seen[key] = item
    if not seen:
        return None, None
    same_axis = {key: item for key, item in seen.items() if item.get("axis_id") == axis}
    grain = period.get("grain")
    pool = same_axis or (
        {key: item for key, item in seen.items() if grain and item.get("grain") == grain} if grain else {}
    )
    if len(pool) == 1:
        return values[next(iter(pool))], None
    if len(pool) > 1:
        return None, "ambiguous_stock"
    return None, None


def _same_end(periods: list[dict], period: dict) -> list[dict]:
    """Периоды с той же датой конца, включая период оси коэффициента.

    Остаток на другой оси цитируется по этой дате. Период без даты остаётся один.
    """

    end = period.get("period_end")
    found = []
    seen = set()
    for item in periods:
        own = (item.get("axis_id"), item.get("period_id"))
        if own in seen:
            continue
        if own == (period.get("axis_id"), period.get("period_id")) or (end is not None and item.get("period_end") == end):
            seen.add(own)
            found.append(item)
    return found or [period]


def _total(keys, series: dict, side: Side, convention: str, *, pay_plus: bool, basis: dict | None = None) -> Decimal | None:
    total = Decimal(0)
    for name in side.plus:
        part = _part(keys, series, name, convention, pay_plus, basis)
        if part is None:
            return None
        total += part
    for name in side.minus:
        part = _part(keys, series, name, convention, True, basis)
        if part is None:
            return None
        total -= part
    return total


def _part(keys, series: dict, name: str, convention: str, pay: bool, basis: dict | None = None) -> Decimal | None:
    """Складывает окно. Строка `ltm` берётся как есть на конец окна и не суммируется."""

    chosen = keys[-1:] if basis and basis.get(name) == "ltm" and keys else keys
    total = Decimal(0)
    for key in chosen:
        if key not in series[name]:
            return None
        value = series[name][key]
        total += _payment(value, convention) if pay else value
    return total


_NET_DEBT_ABSENT = (
    "Чистый долг не содержит значений на оси, по которой считается отношение к EBITDA. "
    "Коэффициент не рассчитан."
)

_LEVERAGE = frozenset({"net_debt_ebitda", "total_debt_ebitda", "debt_off_balance_ebitda"})

_OFF_BALANCE_ABSENT = (
    "Забалансовые обязательства не привязаны. "
    "Показатель долговой нагрузки с их учётом не рассчитан."
)

_EBITDA_NON_POSITIVE = "EBITDA за окно не положительна. Отношение долга к EBITDA сохранено со знаком."

_STOCK_ABSENT = (
    "Остаток долга не содержит значений на оси, по которой считается отношение к EBITDA. "
    "Коэффициент не рассчитан."
)


def _leverage_formula(
    metric: str, formula: Composed, bindings: list[dict], absent: frozenset[str]
) -> tuple[Composed, frozenset[str]]:
    """Числитель запаса — остаток. Неполная пара долг и деньги не заменяется нулём.

    Нет строки забаланса при привязанном долге: этот показатель не считается,
    остальные метрики вызова не касаются.
    """

    primaries = _primaries(bindings, absent)
    if metric == "debt_off_balance_ebitda" and "total_debt" in primaries and "off_balance_obligations" not in primaries:
        return formula, frozenset({"off_balance_obligations"})
    if metric == "net_debt_ebitda" and not ("total_debt" in primaries and "cash" in primaries) and "net_debt" in primaries:
        return Composed(Side(("net_debt",), ()), formula.denominator, formula.window), frozenset()
    return formula, frozenset()


def _stock_absent_message(side: Side) -> str:
    if side.plus == ("net_debt",) and not side.minus:
        return _NET_DEBT_ABSENT
    return _STOCK_ABSENT


def _stock_numerator(
    period: dict, periods: list[dict], aligned: dict, series: dict, side: Side
) -> tuple[Decimal | None, str | None]:
    """Сумма остатков на одну дату. Пропуск слагаемого нулём не становится."""

    total = Decimal(0)
    for name, sign in (*((item, 1) for item in side.plus), *((item, -1) for item in side.minus)):
        value, problem = _stock_choice(period, periods, aligned, series.get(name) or {})
        if problem:
            return None, problem
        if value is None:
            return None, None
        total += sign * value
    return total, None


def _refused(metric: str, periods: list[dict], status: str, message: str, inputs: list[str]) -> dict:
    """Явный статус вместо числа, когда основания или масштаб нельзя свести."""

    period = periods[0] if periods else None
    if period is None:
        row = {
            "metric": metric,
            "axis_id": None,
            "period_id": None,
            "value": None,
            "status": status,
            "reason": status,
            "message": message,
            "inputs": inputs,
        }
    else:
        row = _line(metric, period, None, status, status, inputs, None, message=message)
    return {"metric": metric, "rows": [row], "needs_input": [], "warnings": [], "status": status, "message": message}


def _line(metric, period, value, status, reason, inputs, window, message: str | None = None) -> dict:
    row = {
        "metric": metric,
        "axis_id": period["axis_id"],
        "period_id": period["period_id"],
        "period_key_base": period.get("period_key_base"),
        "period_marker": period.get("period_marker"),
        "value": value,
        "status": status,
        "reason": reason,
        "inputs": inputs,
        "window": window,
    }
    if message:
        row["message"] = message
    return row


def _mismatch(rows, facts, bindings, periods, absent) -> list[dict]:
    primaries = _primaries(bindings, absent)
    book = primaries.get("dscr_covenant")
    if book is None:
        return []
    aligned = aligned_keys(periods)
    cached = _sums(facts, book, aligned, periods)
    for row in rows:
        if row.get("value") is None:
            continue
        key = aligned.get((row["axis_id"], row["period_id"]), (row["axis_id"], row["period_id"]))
        other = cached.get(key)
        if other is None or abs(Decimal(row["value"]) - other) <= _MISMATCH:
            continue
        return [
            {
                "code": "covenant_definition_mismatch",
                "params": {
                    "metric": "dscr",
                    "period_id": row["period_id"],
                    "fas": str(row["value"]),
                    "model": str(other),
                },
            }
        ]
    return []


# Пустое и ошибочное значение ячейки не является числом покрытия и не читается как ноль.
_NOT_A_NUMBER = frozenset({"empty", "not_applicable", "error", "missing"})


def _escrow_coverage_book(rows, facts, bindings, periods, absent, warnings) -> list[dict]:
    """Сверяет покрытие эскроу со строкой книги. Допуск — 0,005.

    Ячейка ищется по ключу шкалы суммы: `timeline_id` и `period_index`.
    Строка книги не суммируется, пустая ячейка с нормализованным нулём остаётся
    пустой. На одном ключе берётся ячейка оси результата; если её нет и чужая
    ячейка ровно одна, берётся она. Пустая ячейка совпадает с нулевым
    знаменателем и вторым предупреждением не становится. Число 0 в книге — уже
    расхождение. Ставка из покрытия этого месяца не считается.
    """

    book = _primaries(bindings, absent).get("escrow_coverage")
    if book is None:
        return []
    aligned = aligned_keys(periods)
    grouped: dict[tuple, list[dict]] = {}
    for fact in facts:
        if fact.get("row_key") != book.get("row_key"):
            continue
        own = (fact.get("axis_id"), fact.get("period_id"))
        grouped.setdefault(aligned.get(own, own), []).append(fact)
    noted = _zero_denominator_periods(warnings)
    extra = []
    for row in rows:
        period = row.get("period_id")
        own = (row.get("axis_id"), period)
        chosen = _aligned_coverage(grouped.get(aligned.get(own, own), []), row.get("axis_id"))
        state, number = _coverage_state(chosen)
        if state == "blank" and (row.get("reason") == "zero_denominator" or period in noted):
            continue
        if state != "number":
            if state == "blank" and row.get("value") is not None:
                extra.append(_coverage_warning(row, row.get("value"), None))
            continue
        fas = row.get("value")
        if fas is None:
            extra.append(_coverage_warning(row, None, number))
            continue
        if abs(Decimal(fas) - number) <= _MISMATCH:
            continue
        extra.append(_coverage_warning(row, fas, number))
    return extra


def _aligned_coverage(facts: list[dict], axis) -> dict | None:
    """Ячейка оси результата. Нет её — ровно одна чужая ячейка того же ключа."""

    home = [fact for fact in facts if fact.get("axis_id") == axis]
    if len(home) == 1:
        return home[0]
    if home or len(facts) != 1:
        return None
    return facts[0]


def _zero_denominator_periods(warnings) -> set:
    found = set()
    for item in warnings:
        params = item.get("params") if isinstance(item.get("params"), dict) else {}
        if item.get("code") != "zero_denominator" and params.get("reason") != "zero_denominator":
            continue
        period = params.get("period_id", item.get("period_id"))
        if period is not None:
            found.add(period)
    return found


def _coverage_state(fact) -> tuple[str, Decimal | None]:
    """`blank` — пустая ячейка, в том числе если рядом лежит нормализованный ноль."""

    if not isinstance(fact, dict):
        return "absent", None
    if fact.get("value_status") in _NOT_A_NUMBER:
        return "blank", None
    if "value_dec" in fact:
        number = _as_decimal(fact.get("value_dec"))
        return ("blank", None) if number is None else ("number", number)
    number = _as_decimal(fact.get("normalized_value"))
    return ("blank", None) if number is None else ("number", number)


def _as_decimal(value) -> Decimal | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _coverage_warning(row, fas, model) -> dict:
    return {
        "code": "escrow_coverage_book_mismatch",
        "params": {
            "metric": "escrow_coverage",
            "period_id": row.get("period_id"),
            "fas": None if fas is None else format(Decimal(fas), "f"),
            "model": None if model is None else format(Decimal(model), "f"),
            "message": "Покрытие эскроу расходится со строкой книги.",
        },
    }
