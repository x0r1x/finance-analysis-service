"""Составные коэффициенты среза 2: ковенантный DSCR, чистый долг и эскроу.

Арифметика только над привязанными строками. Чисел из профиля нет: оттуда
приходят состав числителя, знаменателя и окно.
"""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation

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
    recipe_block,
    unconfirmed_scale,
)
from finance_analysis.domain.model_type import Composed, Side
from finance_analysis.domain.period_basis import _as_date, basis_of
from finance_analysis.domain.returns import project_return

DEFAULT_DEFINITION_TEXT = "определение по умолчанию, не из договора"
_WINDOWS = frozenset({"LTM", "period"})
_FIELDS = frozenset({"numerator", "denominator", "window", "basis_ref", "variant"})
_VARIANT_FIELDS = frozenset({"variant", "basis_ref"})
_SIDE_FIELDS = frozenset({"plus", "minus"})
_CYCLE = frozenset({"dscr", "dscr_covenant"})
_MISMATCH = Decimal("0.005")


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


def dscr_definition_error(
    value,
    *,
    concepts: frozenset[str],
    money: frozenset[str],
    variants: frozenset[str] | None = None,
) -> str | None:
    """None — структуру можно сохранить. Числа, чужие понятия и цикл отвергаются."""

    if not isinstance(value, dict) or set(value) - _FIELDS or _number(value):
        return "dscr_definition: только состав числителя и знаменателя, окно и basis_ref, без чисел"
    if "variant" in value:
        return _variant_error(value, variants or frozenset())
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


def _variant_error(value: dict, variants: frozenset[str]) -> str | None:
    name = value.get("variant")
    if not isinstance(name, str) or not name:
        return "dscr_definition: variant — имя варианта"
    if set(value) - _VARIANT_FIELDS:
        return "dscr_definition: либо имя варианта, либо состав"
    if name not in variants:
        return "dscr_definition: неизвестный вариант"
    if "basis_ref" in value and not isinstance(value["basis_ref"], str):
        return "dscr_definition: basis_ref — строка"
    return None


def _named_variant(profile: dict | None) -> str | None:
    raw = (profile or {}).get("dscr_definition")
    if not isinstance(raw, dict) or "numerator" in raw or "denominator" in raw:
        return None
    name = raw.get("variant")
    if not isinstance(name, str) or not name:
        return None
    return name


def _variant_ids(composed: dict[str, Composed] | None) -> frozenset[str]:
    return frozenset(key.removeprefix("dscr.") for key in (composed or {}) if key.startswith("dscr."))


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
    composed: dict[str, Composed] | None = None,
) -> tuple[Composed, str, dict | None, list[dict]]:
    raw = (profile or {}).get("dscr_definition")
    note = {"code": "dscr_default_definition", "params": {"text": DEFAULT_DEFINITION_TEXT}}
    if not raw:
        return default, "default", None, [note]
    known = _variant_ids(composed)
    problem = dscr_definition_error(raw, concepts=concepts, money=money, variants=known)
    if problem:
        return default, "default", None, [note, {"code": "dscr_definition_invalid", "params": {"reason": problem}}]
    ref = {
        "profile_id": profile_ref.split("@", 1)[0] if profile_ref and "@" in profile_ref else profile_ref,
        "profile_version": profile_ref,
        "basis_ref": raw.get("basis_ref"),
    }
    named = _named_variant(profile)
    if named:
        return composed[f"dscr.{named}"], "profile", ref, []
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
    composed: dict[str, Composed] | None = None,
) -> dict:
    definition, source, ref, notes = resolve_covenant(
        profile, profile_ref, default, concepts=concepts, money=money, composed=composed
    )
    order_name = _named_variant(profile) if source == "profile" else None
    orders = interest_order or {}
    order = orders.get(order_name or "corporate_covenant", ())
    if not order:
        order = orders.get("corporate_covenant", ())
    definition, fallback = _swap_interest(
        definition,
        _primaries(bindings, absent),
        order,
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
        profile=profile,
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
    profile: dict | None = None,
) -> dict:
    blocked = recipe_block(
        profile,
        bindings,
        metric=metric,
        names=(
            *formula.numerator.plus,
            *formula.numerator.minus,
            *formula.denominator.plus,
            *formula.denominator.minus,
        ),
    )
    if blocked:
        return blocked
    needed = (
        *formula.numerator.plus,
        *formula.numerator.minus,
        *formula.denominator.plus,
        *formula.denominator.minus,
    )
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
    ebitda_ltm = metric == "net_debt_ebitda" and basis.get("ebitda") == "ltm"
    span_name = "period" if ebitda_ltm else window_name
    home_name = formula.denominator.plus[0] if formula.denominator.plus else formula.denominator.minus[0]
    stock = series.get("net_debt") or {}
    rows = []
    for axis in sorted(_axes_of(facts, primaries[home_name])):
        ordered = _ordered(periods, axis)
        axis_keys = [aligned.get((axis, item["period_id"]), (axis, item["period_id"])) for item in ordered]
        dated = any(_stock_choice(item, periods, aligned, stock)[0] is not None for item in ordered)
        debt_on_axis = metric != "net_debt_ebitda" or any(key in stock for key in axis_keys) or dated
        for period in ordered:
            marker = period.get("marker_class")
            if marker_class and marker and marker != marker_class:
                continue
            keys, window, problem = _span(span_name, ordered, period, aligned, axis)
            if problem and not debt_on_axis:
                rows.append(
                    _line(metric, period, None, "input_absent", "input_absent", inputs, window, message=_NET_DEBT_ABSENT)
                )
                continue
            if problem:
                message = PARTIAL_DENOMINATOR if roll and problem == "partial_window" else None
                rows.append(_line(metric, period, None, "not_computed", problem, inputs, window, message=message))
                continue
            if metric == "net_debt_ebitda":
                numerator, stock_problem = _stock_choice(period, periods, aligned, stock)
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
                if numerator is None and not any(key in series["net_debt"] for key in keys):
                    rows.append(
                        _line(
                            metric,
                            period,
                            None,
                            "input_absent",
                            "input_absent",
                            inputs,
                            window,
                            message=_NET_DEBT_ABSENT,
                        )
                    )
                    continue
            else:
                shared = frozenset(formula.numerator.plus) & frozenset(formula.denominator.plus)
                numerator = _total(
                    keys, series, formula.numerator, sign_convention, pay_plus=False, basis=basis, pay_names=shared
                )
                denominator = _total(keys, series, formula.denominator, sign_convention, pay_plus=True, basis=basis)
            if numerator is None or denominator is None:
                rows.append(_line(metric, period, None, "missing_input", "no_binding", inputs, window))
                continue
            if denominator == 0:
                status = "no_debt_service" if metric == "dscr" else "missing_input"
                rows.append(_line(metric, period, None, status, "zero_denominator", inputs, window))
                continue
            line = _line(metric, period, _ratio(numerator, denominator), "computed", None, inputs, window)
            if metric == "net_debt_ebitda":
                used = [period] if ebitda_ltm else [item for item in ordered if item["period_id"] in set(window or [])]
                line["components"] = {
                    "net_debt": _component_cells(facts, primaries["net_debt"], _same_end(periods, period)),
                    "ebitda": _component_cells(facts, primaries["ebitda"], used or [period]),
                }
            rows.append(line)
    if metric == "escrow_coverage":
        warnings.extend(_escrow_coverage_book(rows, facts, bindings, periods, absent, warnings))
    status = "succeeded"
    message = None
    absent = metric == "net_debt_ebitda" and any(row["status"] == "input_absent" for row in rows)
    if absent and not any(row["status"] == "computed" for row in rows):
        status = "input_absent"
        message = _NET_DEBT_ABSENT
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


_LEASE_MODES = frozenset({"in_interest", "add_interest", "nominal"})
_DENOMINATOR_FIELDS = ("source", "binding", "period", "standard", "method")
_DENOMINATOR_METHODS = frozenset({"interest_expense", "capitalised", "interest_paid"})
_QUARTER_LABEL = "за квартал, справочно"


def icr_definition_error(value) -> str | None:
    """None — профиль можно сохранить. Чисел и чужих полей нет."""

    if not isinstance(value, dict) or _number(value):
        return "icr_definition: variant и lease_mode, без чисел"
    if set(value) - {"variant", "lease_mode", "denominator", "finance_costs_confirmed"}:
        return "icr_definition: только variant, lease_mode, denominator и finance_costs_confirmed"
    if "variant" in value and value.get("variant") != "bank":
        return "icr_definition: variant bank"
    mode = value.get("lease_mode")
    if mode is not None and mode not in _LEASE_MODES:
        return "icr_definition: lease_mode in_interest, add_interest или nominal"
    if "finance_costs_confirmed" in value and not isinstance(value.get("finance_costs_confirmed"), bool):
        return "icr_definition: finance_costs_confirmed — да или нет"
    if "denominator" in value:
        return _denominator_error(value.get("denominator"))
    return None


def _denominator_error(value) -> str | None:
    if not isinstance(value, dict) or set(value) != set(_DENOMINATOR_FIELDS):
        return "icr_definition: denominator — source, binding, period, standard, method"
    for key in ("source", "binding", "period", "standard"):
        item = value.get(key)
        if not isinstance(item, str) or not item.strip():
            return "icr_definition: denominator — непустые source, binding, period, standard"
    if value.get("method") not in _DENOMINATOR_METHODS:
        return "icr_definition: method interest_expense, capitalised или interest_paid"
    return None


def bank_requested(variant: str | None, profile: dict | None) -> bool:
    """Внутренний профиль icr.bank. Сам по себе он не считается."""

    raw = (profile or {}).get("icr_definition")
    if isinstance(raw, dict) and raw.get("variant") == "bank":
        return True
    return variant == "bank"


def _icr_mode(profile: dict | None) -> str | None:
    raw = (profile or {}).get("icr_definition")
    if not isinstance(raw, dict):
        return None
    mode = raw.get("lease_mode")
    return mode if isinstance(mode, str) else None


def _ask(metric: str, subject: str, reason: str) -> dict:
    return {
        "metric": metric,
        "rows": [],
        "needs_input": [{"kind": "concept", "reason": reason, "subject": subject}],
        "warnings": [],
        "status": "needs_input",
        "missing_inputs": [subject],
    }


def _sign_name(value: Decimal) -> str:
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "zero"


_FISCAL_REASONS = frozenset({"fiscal_calendar_unknown", "fiscal_calendar_mismatch"})


def _quarter_of(period: dict, year_end_month: int) -> int | None:
    """Квартал финансового года: 4-й кончается в месяц закрытия, не в декабре."""

    end = _as_date(period.get("period_end"))
    if end is None:
        return None
    return {0: 4, 3: 1, 6: 2, 9: 3}.get((end.month - year_end_month) % 12)


def _fiscal_year_of(period: dict, month: int, day: int) -> int | None:
    """Год, в котором финансовый год заканчивается."""

    end = _as_date(period.get("period_end"))
    if end is None:
        return None
    if (end.month, end.day) <= (month, day):
        return end.year
    return end.year + 1


def _same_slot(ordered: list[dict], year: int, quarter: int, month: int, day: int) -> dict | None:
    for item in ordered:
        if _fiscal_year_of(item, month, day) == year and _quarter_of(item, month) == quarter:
            return item
    return None


def _aligned_key(period: dict, aligned: dict):
    own = (period.get("axis_id"), period.get("period_id"))
    return aligned.get(own, own)


def _ytd_ltm(series: dict, period: dict, ordered: list[dict], aligned: dict):
    """LTM = YTD + прошлый финансовый год − YTD того же квартала прошлого года.

    Полный год (4-й квартал финансового года или зерно от 12 месяцев) уже равен LTM.
    Нет конца года — причина fiscal_calendar_unknown или fiscal_calendar_mismatch.
    """

    current = series.get(_aligned_key(period, aligned))
    if current is None:
        return None, "needs_input"
    calendar = _fiscal_calendar(ordered)
    if isinstance(calendar, str):
        return None, calendar
    month, day = calendar
    months = grain_months(period.get("grain"))
    if months is not None and months >= 12:
        return current, None
    year = _fiscal_year_of(period, month, day)
    quarter = _quarter_of(period, month)
    if year is None or quarter is None:
        return None, "fiscal_calendar_mismatch"
    if quarter == 4:
        return current, None
    prior_end = _same_slot(ordered, year - 1, 4, month, day)
    prior_same = _same_slot(ordered, year - 1, quarter, month, day)
    if prior_end is None or prior_same is None:
        return None, "needs_input"
    problem = _ytd_comparable(period, prior_same, prior_end, month)
    if problem:
        return None, problem
    full_year = series.get(_aligned_key(prior_end, aligned))
    prior = series.get(_aligned_key(prior_same, aligned))
    if full_year is None or prior is None:
        return None, "needs_input"
    return current + full_year - prior, None


def _span_days(period: dict) -> int | None:
    start = _as_date(period.get("period_start"))
    end = _as_date(period.get("period_end"))
    if start is None or end is None or end < start:
        return None
    return (end - start).days


def _fiscal_quarter_month(year_end_month: int, quarter: int) -> int:
    month = (year_end_month + 3 * (quarter - 4)) % 12
    return 12 if month == 0 else month


def _dated_quarter(period: dict):
    months = grain_months(period.get("grain"))
    if months != 3:
        return None
    start = _as_date(period.get("period_start"))
    end = _as_date(period.get("period_end"))
    if start is None or end is None or end < start:
        return None
    return start, end


def _fiscal_calendar(ordered: list[dict]) -> tuple[int, int] | str:
    """(месяц, день) конца финансового года либо причина, почему его нет.

    Годовой период задаёт конец, если такие концы совпадают. Иначе конец — закрытие
    четырёх смежных кварталов от самого раннего period_start на оси. Первый квартал
    оси при этом читается как Q1: серия с середины года без годового периода от Q1
    не отличается.
    """

    annuals = []
    quarters = []
    for item in ordered:
        end = _as_date(item.get("period_end"))
        months = grain_months(item.get("grain"))
        if end is None or months is None:
            continue
        if months >= 12:
            annuals.append((end.month, end.day))
        elif _dated_quarter(item) is not None:
            quarters.append(item)
    annual_end = None
    if annuals:
        if len(set(annuals)) != 1:
            return "fiscal_calendar_mismatch"
        annual_end = annuals[0]
    quarter_end = _quarter_year_end(quarters)
    if isinstance(quarter_end, str):
        return quarter_end
    if annual_end is not None and quarter_end is not None and annual_end != quarter_end:
        return "fiscal_calendar_mismatch"
    found = annual_end or quarter_end
    if found is None:
        return "fiscal_calendar_unknown"
    if not _quarters_on_grid(quarters, found[0]):
        return "fiscal_calendar_mismatch"
    return found


def _quarter_year_end(quarters: list[dict]) -> tuple[int, int] | str | None:
    dated = []
    for item in quarters:
        pair = _dated_quarter(item)
        if pair is None:
            return "fiscal_calendar_mismatch"
        dated.append(pair)
    if len(dated) < 4:
        return None
    dated.sort(key=lambda row: row[1])
    anchor = min(start for start, _end in dated)
    anchor_key = (anchor.month, anchor.day)
    closings = []
    for index in range(len(dated) - 3):
        block = dated[index : index + 4]
        if not _contiguous(block):
            continue
        if (block[0][0].month, block[0][0].day) != anchor_key:
            continue
        rolled = block[-1][1] + timedelta(days=1)
        if (rolled.month, rolled.day) != anchor_key:
            continue
        closings.append((block[-1][1].month, block[-1][1].day))
    if not closings:
        return None
    if len(set(closings)) != 1:
        return "fiscal_calendar_mismatch"
    return closings[0]


def _contiguous(block: list[tuple]) -> bool:
    for index in range(len(block) - 1):
        if block[index][1] + timedelta(days=1) != block[index + 1][0]:
            return False
    return True


def _quarters_on_grid(quarters: list[dict], year_end_month: int) -> bool:
    for item in quarters:
        if _quarter_of(item, year_end_month) is None:
            return False
    return True


def _ytd_comparable(current: dict, prior_same: dict, prior_end: dict, year_end_month: int) -> str | None:
    """None — кварталы одного финансового года сравнимы. Иначе причина needs_input.

    Консолидация и учётная база в метаданных периода не лежат: их проверяет договор
    вызова, не эта функция.
    """

    if grain_months(current.get("grain")) != grain_months(prior_same.get("grain")):
        return "needs_input"
    if grain_months(prior_end.get("grain")) != grain_months(current.get("grain")):
        return "needs_input"
    current_len = _span_days(current)
    prior_len = _span_days(prior_same)
    if current_len is None or prior_len is None or current_len != prior_len or _span_days(prior_end) is None:
        return "needs_input"
    current_end = _as_date(current.get("period_end"))
    prior_end_date = _as_date(prior_same.get("period_end"))
    year_end = _as_date(prior_end.get("period_end"))
    quarter = _quarter_of(current, year_end_month)
    if current_end is None or prior_end_date is None or year_end is None or quarter is None:
        return "fiscal_calendar_mismatch"
    if (current_end.month, current_end.day) != (prior_end_date.month, prior_end_date.day):
        return "needs_input"
    if year_end.month != year_end_month:
        return "fiscal_calendar_mismatch"
    if _fiscal_quarter_month(year_end_month, quarter) != current_end.month:
        return "fiscal_calendar_mismatch"
    return None


def _ytd_step(series: dict, period: dict, ordered: list[dict], aligned: dict):
    """Приращение нарастающего итога за один финансовый квартал. На 4 не умножается."""

    current = series.get(_aligned_key(period, aligned))
    calendar = _fiscal_calendar(ordered)
    if current is None or isinstance(calendar, str):
        return None
    month, day = calendar
    quarter = _quarter_of(period, month)
    year = _fiscal_year_of(period, month, day)
    if quarter is None or year is None:
        return None
    if quarter == 1:
        return current
    previous = _same_slot(ordered, year, quarter - 1, month, day)
    if previous is None:
        return None
    prior = series.get(_aligned_key(previous, aligned))
    if prior is None:
        return None
    return current - prior


def _evidence_of(row: dict) -> dict:
    evidence = row.get("evidence")
    if isinstance(evidence, dict):
        return evidence
    raw = row.get("evidence_json")
    if isinstance(raw, str) and raw:
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError:
            loaded = {}
        if isinstance(loaded, dict):
            return loaded
    return {}


def _lease_scope(row: dict) -> str:
    scope = _evidence_of(row).get("lease_scope")
    return scope.strip() if isinstance(scope, str) else ""


def _finance_confirmed(profile: dict | None) -> bool:
    raw = (profile or {}).get("icr_definition")
    return isinstance(raw, dict) and raw.get("finance_costs_confirmed") is True


def _denominator(profile: dict | None) -> dict | None:
    raw = (profile or {}).get("icr_definition")
    if not isinstance(raw, dict):
        return None
    item = raw.get("denominator")
    return item if isinstance(item, dict) else None


def _require_interest_expense(profile, primaries, periods, binding_name: str) -> dict | None:
    """Режим in_interest без состава знаменателя число не выпускает.

    Процентный расход, капитализированные затраты и уплаченные проценты — три разных
    знаменателя. Полный лизинговый платёж сюда не подставляется.
    """

    evidence = _denominator(profile)
    if evidence is None or _denominator_error(evidence):
        return _ask("icr", "denominator_evidence", "missing")
    method = evidence.get("method")
    if method == "capitalised":
        return _ask("icr", "capitalised", "capitalised")
    if method == "interest_paid":
        return _ask("icr", "interest_paid", "interest_paid")
    if method != "interest_expense":
        return _ask("icr", "denominator_method", "missing")
    if evidence.get("binding") != binding_name or binding_name not in primaries:
        return _ask("icr", "denominator_evidence", "binding")
    period = str(evidence.get("period") or "").strip()
    known = {item.get("period_id") for item in periods}
    if period != "each" and period not in known:
        return _ask("icr", "denominator_evidence", "period")
    return None


def _unconfirmed_proxy() -> dict:
    warning = {"code": "finance_cost_proxy", "params": {"concept": "finance_costs"}}
    return {
        "metric": "icr",
        "rows": [],
        "needs_input": [],
        "warnings": [warning],
        "status": "not_computed",
        "message": "состав финансовых расходов не подтверждён",
    }


def _bank_formula(primaries: dict, mode: str, profile: dict | None) -> tuple[Composed | None, list[dict], dict | None]:
    """Знаменатель по режиму аренды. EBIT в формулу не входит. Подписи строки не вычитаются."""

    warnings: list[dict] = []
    if "interest" in primaries:
        plus = ["interest"]
    elif "finance_costs" in primaries:
        if not _finance_confirmed(profile):
            return None, [], _unconfirmed_proxy()
        plus = ["finance_costs"]
        warnings.append({"code": "finance_cost_proxy", "params": {"concept": "finance_costs"}})
        minus: list[str] = []
        if mode == "in_interest" and "lease_interest" in primaries:
            warnings.append({"code": "lease_interest_double_count", "params": {"concept": "lease_interest"}})
        if mode == "add_interest":
            extra_plus, extra_minus, problem = _lease_terms(primaries)
            if problem:
                return None, [], problem
            plus = [*plus, *extra_plus]
            minus = extra_minus
        return (
            Composed(Side(("ebitda",), ()), Side(tuple(plus), tuple(minus)), "LTM"),
            warnings,
            None,
        )
    else:
        return None, [], _ask("icr", "interest", "concept_unknown")
    minus = []
    if mode == "in_interest" and "lease_interest" in primaries:
        warnings.append({"code": "lease_interest_double_count", "params": {"concept": "lease_interest"}})
    if mode == "add_interest":
        extra_plus, extra_minus, problem = _lease_terms(primaries)
        if problem:
            return None, [], problem
        plus = [*plus, *extra_plus]
        minus = extra_minus
    return Composed(Side(("ebitda",), ()), Side(tuple(plus), tuple(minus)), "LTM"), warnings, None


def _lease_terms(primaries: dict) -> tuple[list[str], list[str], dict | None]:
    if "lease_interest" in primaries:
        return ["lease_interest"], [], None
    payments = primaries.get("lease_payments")
    principal = primaries.get("lease_principal")
    if payments is not None and principal is not None:
        scope = _lease_scope(payments)
        if not scope or scope != _lease_scope(principal):
            return [], [], _ask("icr", "lease_scope", "scope_mismatch")
        return ["lease_payments"], ["lease_principal"], None
    return [], [], _ask("icr", "lease_interest", "concept_unknown")


def bank_icr(
    *,
    facts: list[dict],
    bindings: list[dict],
    periods: list[dict],
    profile: dict | None = None,
    sign_convention: str = "outflow_negative",
    marker_class: str | None = None,
    absent: frozenset[str] = frozenset(),
) -> dict:
    """Внутренний профиль icr.bank. Не ICR по 6960-У и не ковенант договора.

    EBIT не подставляется. Окно LTM, квартал — только справочная строка.
    """

    blocked = recipe_block(profile, bindings, metric="icr", names=("ebitda",))
    if blocked:
        return blocked
    mode = _icr_mode(profile)
    if mode == "nominal":
        return _ask("icr", "lease_mode", "nominal")
    if mode not in _LEASE_MODES:
        return _ask("icr", "lease_mode", "missing")
    primaries = _primaries(bindings, absent)
    if "ebitda" not in primaries:
        return _ask("icr", "ebitda", "concept_unknown")
    formula, warnings, problem = _bank_formula(primaries, mode, profile)
    if problem:
        return problem
    assert formula is not None
    if mode == "in_interest":
        blocked_mode = _require_interest_expense(profile, primaries, periods, formula.denominator.plus[0])
        if blocked_mode:
            return blocked_mode
    names = [
        *formula.numerator.plus,
        *formula.numerator.minus,
        *formula.denominator.plus,
        *formula.denominator.minus,
    ]
    bases = {basis_of(primaries[name])[0] for name in names}
    if len(bases) != 1:
        return _ask("icr", "period_basis", "basis_mismatch")
    basis = bases.pop()
    if basis == "unknown":
        return _ask("icr", "period_basis", "basis_mismatch")
    aligned = aligned_keys(periods)
    raw = basis in {"ytd", "ltm"}
    series = {
        name: _sums(facts, primaries[name], aligned, None if raw else periods)
        for name in dict.fromkeys(names)
    }
    home_name = formula.denominator.plus[0]
    attested = None
    if mode == "in_interest":
        attested = str((_denominator(profile) or {}).get("period") or "").strip()
        if attested == "each":
            attested = None
    rows = []
    for axis in sorted(_axes_of(facts, primaries[home_name])):
        ordered = _ordered(periods, axis)
        for period in ordered:
            marker = period.get("marker_class")
            if marker_class and marker and marker != marker_class:
                continue
            if attested is not None and period.get("period_id") != attested:
                rows.append(
                    _line(
                        "icr",
                        period,
                        None,
                        "needs_input",
                        "denominator_period",
                        names,
                        "LTM",
                        variant="bank",
                    )
                )
                continue
            number, den, reason = _bank_pair(formula, series, period, ordered, aligned, basis, sign_convention)
            if reason == "partial_window" and basis != "ytd":
                rows.append(
                    _line("icr", period, None, "not_computed", "partial_window", names, "LTM", variant="bank")
                )
                continue
            if number is None or den is None:
                published = reason if reason in _FISCAL_REASONS else "needs_input"
                rows.append(_line("icr", period, None, "needs_input", published, names, "LTM", variant="bank"))
                continue
            if den == 0:
                rows.append(
                    _line(
                        "icr",
                        period,
                        None,
                        "missing_input",
                        "no_interest",
                        names,
                        "LTM",
                        variant="bank",
                        ebitda_sign=_sign_name(number),
                    )
                )
                continue
            if den < 0:
                rows.append(
                    _line(
                        "icr",
                        period,
                        None,
                        "not_computed",
                        "invalid_denominator",
                        names,
                        "LTM",
                        variant="bank",
                    )
                )
                continue
            value = _ratio(number, den)
            row = _line("icr", period, value, "computed", None, names, "LTM", variant="bank")
            if number <= 0:
                warnings.append(
                    {
                        "code": "negative_numerator",
                        "params": {"period_id": period["period_id"], "ebitda_sign": _sign_name(number)},
                    }
                )
            rows.append(row)
            step = _bank_pair(formula, series, period, ordered, aligned, basis, sign_convention, quarter=True)
            if (
                grain_months(period.get("grain")) == 3
                and basis != "ltm"
                and step[0] is not None
                and step[1] not in (None, 0)
                and step[1] > 0
            ):
                rows.append(
                    _line(
                        "icr",
                        period,
                        _ratio(step[0], step[1]),
                        "computed",
                        None,
                        names,
                        "period",
                        variant="quarter_reference",
                        message=_QUARTER_LABEL,
                    )
                )
    ltm = [row for row in rows if row.get("variant") == "bank"]
    status = "succeeded"
    if ltm and not any(row["status"] == "computed" for row in ltm):
        if any(row["status"] == "needs_input" for row in ltm):
            status = "needs_input"
        elif any(row.get("reason") == "no_interest" for row in ltm):
            status = "missing_input"
        elif any(row.get("reason") == "invalid_denominator" for row in ltm):
            status = "not_computed"
        elif any(row.get("reason") == "partial_window" for row in ltm):
            status = "partial_window"
    return {"metric": "icr", "rows": rows, "needs_input": [], "warnings": warnings, "status": status}


def _bank_pair(formula, series, period, ordered, aligned, basis, sign, *, quarter: bool = False):
    parts = {}
    names = (*formula.numerator.plus, *formula.numerator.minus, *formula.denominator.plus, *formula.denominator.minus)
    for name in dict.fromkeys(names):
        value, problem = _concept_amount(name, series, period, ordered, aligned, basis, quarter)
        if value is None:
            if problem in _FISCAL_REASONS:
                return None, None, problem
            return None, None, "partial_window" if basis != "ytd" and not quarter else "needs_input"
        parts[name] = value
    number = Decimal(0)
    for name in formula.numerator.plus:
        number += parts[name]
    for name in formula.numerator.minus:
        number -= parts[name]
    den = Decimal(0)
    for name in formula.denominator.plus:
        den += _payment(parts[name], sign)
    for name in formula.denominator.minus:
        den -= _payment(parts[name], sign)
    return number, den, None


def _concept_amount(name, series, period, ordered, aligned, basis, quarter: bool):
    column = series[name]
    if basis == "ytd":
        if quarter:
            return _ytd_step(column, period, ordered, aligned), None
        return _ytd_ltm(column, period, ordered, aligned)
    if basis == "ltm" or quarter:
        return column.get(_aligned_key(period, aligned)), None
    keys, _window, problem = _span("LTM", ordered, period, aligned, period["axis_id"])
    if problem or not keys:
        return None, None
    total = Decimal(0)
    for key in keys:
        if key not in column:
            return None, None
        total += column[key]
    return total, None


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
    """Именованный вариант профиля считает свою формулу на любом типе книги.

    Без имени корпоративный тип остаётся на `corporate_covenant`, остальные — на своей формуле.
    """

    if metric in {"npv", "irr"}:
        return project_return(
            metric,
            facts=common["facts"],
            bindings=common["bindings"],
            periods=common["periods"],
            absent=common["absent"],
        )
    named = _named_variant(profile)
    if metric == "dscr" and (variant == "corporate_covenant" or (named and f"dscr.{named}" in composed)):
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
            composed=composed,
        )
    if metric == "icr" and bank_requested(variant, profile):
        return bank_icr(
            facts=common["facts"],
            bindings=common["bindings"],
            periods=common["periods"],
            profile=profile,
            sign_convention=common["sign_convention"],
            marker_class=common["marker_class"],
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
            profile=profile,
        )
    return coverage_ratio(
        metric=metric,
        interest_order=interest_order,
        row_fallbacks=row_fallbacks,
        profile=profile,
        **common,
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


def _total(
    keys,
    series: dict,
    side: Side,
    convention: str,
    *,
    pay_plus: bool,
    basis: dict | None = None,
    pay_names: frozenset[str] = frozenset(),
) -> Decimal | None:
    total = Decimal(0)
    for name in side.plus:
        part = _part(keys, series, name, convention, pay_plus or name in pay_names, basis)
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


def _line(metric, period, value, status, reason, inputs, window, message: str | None = None, **extra) -> dict:
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
    row.update(extra)
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
