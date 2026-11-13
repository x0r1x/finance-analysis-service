"""Составные коэффициенты среза 2: ковенантный DSCR, чистый долг и эскроу.

Арифметика только над привязанными строками. Чисел из профиля нет: оттуда
приходят состав числителя, знаменателя и окно.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from finance_analysis.domain.cover_metrics import (
    _missing,
    _ordered,
    _ratio,
    _window,
    grain_months,
)
from finance_analysis.domain.free_cash_flow import free_cash_flow
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
    confirm_paid_interest,
    coverage_ratio,
    interest_choice,
    recipe_block,
    unconfirmed_scale,
)
from finance_analysis.domain.model_type import Composed, Side
from finance_analysis.domain.period_basis import basis_of
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
    primaries = _primaries(bindings, absent)
    injected = confirm_paid_interest(primaries, bindings, absent)
    definition, fallback = _swap_interest(
        definition,
        primaries,
        order,
        row_fallbacks=row_fallbacks,
    )
    if injected is not None:
        bindings = [*bindings, injected]
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
    links: list[dict] | None = None,
    statement_sheets: frozenset[str] | None = None,
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
    if metric == "fcff":
        return free_cash_flow(
            facts=common["facts"],
            bindings=common["bindings"],
            periods=common["periods"],
            sign_convention=common.get("sign_convention") or "outflow_negative",
            absent=common.get("absent") or frozenset(),
            links=common.get("graph_links") if links is None else links,
            book=common.get("book_fcff") or [],
            statement_sheets=(
                statement_sheets
                if statement_sheets is not None
                else common.get("statement_sheets") or frozenset()
            ),
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
