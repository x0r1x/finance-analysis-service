"""Номинальный LLCR, ставка эскроу и сводки housing. NPV LLCR и pf этот модуль не считает.

Пустая ячейка не становится нулём. Исключённая или неразнесённая сумма не меняет число.
Каждая строка подписана своим составом и не называется универсальным DSCR.
"""

from __future__ import annotations

from decimal import Decimal, localcontext

from finance_analysis.domain.cover_metrics import (
    WINDOW_MONTHS,
    _ordered,
    _window,
    grain_months,
)
from finance_analysis.domain.housing_dscr import (
    COMPOSITION,
    _amount,
    _bound,
    housing_dscr,
)
from finance_analysis.domain.metrics import aligned_keys, quantize_ratio

_FAMILY = frozenset({"adscr", "dscr_min", "dscr_avg"})
_NOMINAL = frozenset({"cbr590", "domrf"})
_CASH = ("cfo_statement", "cfi_statement", "financing_inflows", "interest_addback")
_CBR = (
    "Вариант llcr.cbr590, не универсальный DSCR и не NPV LLCR. "
    "Номинальная сумма проектного потока (cfo_statement + cfi_statement + financing_inflows) "
    "плюс иные деньги guaranteed_funds один раз, делённая на номинальную сумму "
    "senior_principal и senior_interest_paid за весь срок. Дисконта нет. "
    "Пустая ячейка не заменяется нулём. Комиссии и свопы в эту дробь не входят."
)
_DOMRF = (
    "Вариант llcr.domrf, не универсальный DSCR и не NPV LLCR. "
    "Числитель — та же сумма проектного потока сервиса, не неопубликованная расшифровка ДОМ.РФ. "
    "Знаменатель — credit_limit плюс сумма senior_interest_paid. "
    "Погашение тела и debt_outstanding лимит не подменяют. Дисконта нет."
)
_RATE = (
    "Ставка escrow_blended_rate: покрытая часть выбранного долга умножается на специальную ставку "
    "или на ступень профиля, непокрытая — на базовую, частное делится на выбранный долг. "
    "Шкала 2019 года в код не зашита. Это не коэффициент покрытия долга."
)
_SUMMARY = (
    "Сводка варианта housing, не универсальный DSCR. "
    "Считается по уже посчитанным интервалам housing. "
    "Интервал без числа блокирует сводку. Интервал без обслуживания долга в минимум и среднее не входит."
)


def profile_variant(profile: dict | None, key: str):
    raw = (profile or {}).get(key)
    if isinstance(raw, dict):
        return raw.get("variant")
    return None


def use_housing_cover(metric: str, metric_variant, dscr_variant, profile: dict | None) -> bool:
    """pf и NPV LLCR остаются, пока вариант или профиль явно не просят другой состав."""

    if metric in _FAMILY:
        named = profile_variant(profile, "dscr_definition")
        return metric_variant == "housing" or dscr_variant == "housing" or named == "housing"
    if metric == "llcr":
        named = profile_variant(profile, "llcr_definition")
        if named:
            return True
        return metric_variant in _NOMINAL
    return metric == "escrow_blended_rate"


def llcr_definition_error(value) -> str | None:
    if isinstance(value, dict) and value.get("variant") in _NOMINAL and set(value) <= {"variant"}:
        return None
    return "llcr_definition.variant: cbr590 или domrf"


def scale_error(value) -> str | None:
    if not isinstance(value, dict):
        return "escrow_rate_scale: объект"
    if set(value) - {"base_rate", "special_rate", "rungs"}:
        return "escrow_rate_scale: лишнее поле"
    for key in ("base_rate", "special_rate"):
        if _decimal(value.get(key)) is None:
            return f"escrow_rate_scale.{key}: доля, не процент"
    rungs = value.get("rungs") or []
    if not isinstance(rungs, list):
        return "escrow_rate_scale.rungs: список"
    for rung in rungs:
        if not isinstance(rung, dict) or set(rung) - {"coverage", "rate"}:
            return "escrow_rate_scale.rungs: coverage и rate"
        if _decimal(rung.get("coverage")) is None or _decimal(rung.get("rate")) is None:
            return "escrow_rate_scale.rungs: доля"
    return None


def dispatch_cover(
    metric: str,
    *,
    metric_variant,
    dscr_variant,
    profile,
    basis: str,
    direction: str,
    common: dict,
):
    if not use_housing_cover(metric, metric_variant, dscr_variant, profile):
        return None
    return housing_cover(
        metric,
        facts=common["facts"],
        bindings=common["bindings"],
        periods=common["periods"],
        sign_convention=common["sign_convention"],
        absent=common["absent"],
        profile=profile,
        variant=metric_variant,
        direction=direction,
        basis=basis,
    )


def housing_cover(
    metric: str,
    *,
    facts: list[dict],
    bindings: list[dict],
    periods: list[dict],
    sign_convention: str = "outflow_negative",
    absent: frozenset[str] = frozenset(),
    profile: dict | None = None,
    variant: str | None = None,
    direction: str = "lookback",
    basis: str = "period_end",
) -> dict:
    if metric == "escrow_blended_rate":
        return _rate(facts, bindings, periods, sign_convention, absent, profile)
    if metric == "llcr":
        return _llcr(facts, bindings, periods, sign_convention, absent, profile, variant)
    return _family(metric, facts, bindings, periods, sign_convention, absent, profile, direction, basis)


def _llcr(facts, bindings, periods, convention, absent, profile, variant):
    choice = profile_variant(profile, "llcr_definition") or variant or "cbr590"
    if choice not in _NOMINAL:
        return _envelope("llcr", [], "not_computed", message="llcr_definition.variant: cbr590 или domrf")
    series = housing_dscr(
        facts=facts, bindings=bindings, periods=periods, sign_convention=convention, absent=absent, profile=profile
    )
    if series.get("message"):
        return _envelope("llcr", [], "not_computed", message=series["message"], variant=choice)
    rows = []
    for axis in _axes(series["rows"], periods):
        members = [row for row in series["rows"] if row.get("axis_id") == axis]
        rows.append(_life_row(choice, axis, members, facts, bindings, periods, convention, absent, profile))
    return _envelope("llcr", rows, _status(rows), variant=choice, warnings=series.get("warnings") or [])


def _life_row(choice, axis, members, facts, bindings, periods, convention, absent, profile):
    text = _CBR if choice == "cbr590" else _DOMRF
    composition = (
        "cfo_statement + cfi_statement + financing_inflows + guaranteed_funds / "
        "senior_principal + senior_interest_paid"
        if choice == "cbr590"
        else "cfo_statement + cfi_statement + financing_inflows / credit_limit + senior_interest_paid"
    )
    blocked = [row for row in members if row["status"] == "not_computed"]
    if blocked or not members:
        missing = sorted({name for row in blocked for name in row.get("missing") or []})
        return _metric_row(
            "llcr", axis, None, "not_computed", "missing_component", choice, text, composition, missing=missing
        )
    cash = _sum(_cash_of, members)
    if choice == "cbr590":
        debt = _sum(_obligations, members)
        if debt is None:
            return _metric_row(
                "llcr",
                axis,
                None,
                "not_computed",
                "missing_component",
                choice,
                text,
                composition,
                missing=["senior_principal", "senior_interest_paid"],
            )
        extra, problem = _once(facts, bindings, periods, axis, "guaranteed_funds", convention, absent)
        if problem and _none_confirmed(profile) is not True:
            return _metric_row(
                "llcr",
                axis,
                None,
                "not_computed",
                "missing_component",
                choice,
                text,
                composition,
                missing=["guaranteed_funds"],
            )
        extra = extra or Decimal(0)
        numerator = cash + extra
        parts = {"project_cash": format(cash, "f"), "guaranteed_funds": format(extra, "f"), "denominator": format(debt, "f")}
        return _ratio_row("llcr", axis, numerator, debt, choice, text, composition, parts)
    interest = _sum(_interest_of, members)
    if interest is None:
        return _metric_row(
            "llcr",
            axis,
            None,
            "not_computed",
            "missing_component",
            choice,
            text,
            composition,
            missing=["senior_interest_paid"],
        )
    limit, problem = _once(facts, bindings, periods, axis, "credit_limit", convention, absent)
    if problem or limit is None:
        return _metric_row(
            "llcr", axis, None, "not_computed", "missing_component", choice, text, composition, missing=["credit_limit"]
        )
    parts = {"project_cash": format(cash, "f"), "credit_limit": format(limit, "f"), "senior_interest_paid": format(interest, "f")}
    return _ratio_row("llcr", axis, cash, limit + interest, choice, text, composition, parts)


def _family(metric, facts, bindings, periods, convention, absent, profile, direction, basis):
    del basis
    series = housing_dscr(
        facts=facts, bindings=bindings, periods=periods, sign_convention=convention, absent=absent, profile=profile
    )
    if series.get("message"):
        return _envelope(metric, [], "not_computed", message=series["message"], variant="housing")
    rows = []
    for axis in _axes(series["rows"], periods):
        members = [row for row in series["rows"] if row.get("axis_id") == axis]
        ordered = _ordered(periods, axis)
        if metric == "adscr":
            rows.extend(_adscr(axis, members, ordered, direction))
        elif metric == "dscr_avg":
            rows.extend(_average(axis, members))
        else:
            rows.append(_minimum(axis, members))
    return _envelope(metric, rows, _status(rows), variant="housing", warnings=series.get("warnings") or [])


def _minimum(axis, members):
    blocked = [row for row in members if row["status"] == "not_computed"]
    if blocked:
        missing = sorted({name for row in blocked for name in row.get("missing") or []})
        return _metric_row("dscr_min", axis, None, "not_computed", "missing_component", "housing", _SUMMARY, COMPOSITION, missing=missing)
    usable = [row for row in members if row["status"] == "computed" and row.get("value") is not None]
    excluded = [row["period_id"] for row in members if row["status"] == "no_debt_service"]
    if not usable:
        return _metric_row(
            "dscr_min",
            axis,
            None,
            "not_computed",
            "no_computed_intervals",
            "housing",
            _SUMMARY,
            COMPOSITION,
            excluded=excluded,
        )
    lowest = min(usable, key=lambda row: row["value"])
    return _metric_row(
        "dscr_min",
        axis,
        lowest["value"],
        "computed",
        None,
        "housing",
        _SUMMARY,
        lowest.get("composition") or COMPOSITION,
        excluded=excluded,
        over=[row["period_id"] for row in usable],
    )


def _average(axis, members):
    blocked = [row for row in members if row["status"] == "not_computed"]
    excluded = [row["period_id"] for row in members if row["status"] == "no_debt_service"]
    usable = [row for row in members if row["status"] == "computed" and row.get("value") is not None]
    if blocked or not usable:
        missing = sorted({name for row in blocked for name in row.get("missing") or []})
        reason = "missing_component" if blocked else "no_computed_intervals"
        return [
            _metric_row(
                "dscr_avg",
                axis,
                None,
                "not_computed",
                reason,
                "housing",
                _SUMMARY,
                COMPOSITION,
                missing=missing,
                excluded=excluded,
                reduction=name,
            )
            for name in ("mean_of_ratios", "ratio_of_sums")
        ]
    with localcontext() as ctx:
        ctx.prec = 38
        ctx.rounding = "ROUND_HALF_EVEN"
        mean = quantize_ratio(sum((row["value"] for row in usable), Decimal(0)) / len(usable))
    numerator = _sum(_cash_of, usable)
    denominator = _sum(_service, usable)
    ratio = None if denominator in (None, 0) else _divide(numerator, denominator)
    composition = usable[0].get("composition") or COMPOSITION
    return [
        _metric_row(
            "dscr_avg", axis, mean, "computed", None, "housing", _SUMMARY, composition, excluded=excluded, reduction="mean_of_ratios"
        ),
        _metric_row(
            "dscr_avg",
            axis,
            ratio,
            "computed" if ratio is not None else "not_computed",
            None if ratio is not None else "zero_denominator",
            "housing",
            _SUMMARY,
            composition,
            excluded=excluded,
            reduction="ratio_of_sums",
        ),
    ]


def _adscr(axis, members, ordered, direction):
    by_period = {row["period_id"]: row for row in members}
    months = grain_months(ordered[0].get("grain") if ordered else None)
    if months is None or months >= WINDOW_MONTHS:
        return [
            _metric_row(
                "adscr", axis, None, "not_computed", "adscr_not_applicable", "housing", _SUMMARY, COMPOSITION, period=ordered[0] if ordered else None
            )
        ]
    rows = []
    for period in ordered:
        window = _window(ordered, period, direction) if period.get("period_start") is not None else None
        if window is None:
            rows.append(
                _metric_row(
                    "adscr", axis, None, "not_computed", "partial_window", "housing", _SUMMARY, COMPOSITION, period=period
                )
            )
            continue
        chosen = [by_period[item["period_id"]] for item in window if item["period_id"] in by_period]
        if len(chosen) != len(window) or any(row["status"] == "not_computed" for row in chosen):
            missing = sorted({name for row in chosen if row["status"] == "not_computed" for name in row.get("missing") or []})
            rows.append(
                _metric_row(
                    "adscr",
                    axis,
                    None,
                    "not_computed",
                    "missing_component",
                    "housing",
                    _SUMMARY,
                    COMPOSITION,
                    period=period,
                    missing=missing,
                )
            )
            continue
        numerator = _sum(_cash_of, chosen)
        denominator = _sum(_service, chosen)
        rows.append(_ratio_row("adscr", axis, numerator, denominator, "housing", _SUMMARY, chosen[0].get("composition") or COMPOSITION, period=period))
    return rows


def _rate(facts, bindings, periods, convention, absent, profile):
    scale = (profile or {}).get("escrow_rate_scale")
    problem = None if scale is None else scale_error(scale)
    rows = []
    aligned = aligned_keys(periods)
    for period in periods:
        if scale is None:
            rows.append(_metric_row("escrow_blended_rate", period.get("axis_id"), None, "not_computed", "rate_scale_unconfigured", "escrow_rate_scale", _RATE, _RATE_COMPOSITION, period=period))
            continue
        if problem:
            rows.append(_metric_row("escrow_blended_rate", period.get("axis_id"), None, "not_computed", "rate_scale_unconfigured", "escrow_rate_scale", _RATE, _RATE_COMPOSITION, period=period))
            continue
        rows.append(_blend(facts, bindings, period, aligned, convention, absent, scale))
    return _envelope("escrow_blended_rate", rows, _status(rows), variant="escrow_rate_scale")


_RATE_COMPOSITION = "(covered × special_or_rung + uncovered × base_rate) / debt_outstanding"


def _blend(facts, bindings, period, aligned, convention, absent, scale):
    drawn, drawn_missing = _at(facts, bindings, period, aligned, "debt_outstanding", convention, absent)
    escrow, escrow_missing = _at(facts, bindings, period, aligned, "escrow_balance", convention, absent)
    missing = [name for name, flag in (("debt_outstanding", drawn_missing), ("escrow_balance", escrow_missing)) if flag]
    if missing or drawn is None or escrow is None:
        return _metric_row(
            "escrow_blended_rate",
            period.get("axis_id"),
            None,
            "not_computed",
            "missing_component",
            "escrow_rate_scale",
            _RATE,
            _RATE_COMPOSITION,
            period=period,
            missing=missing or ["debt_outstanding", "escrow_balance"],
        )
    if drawn == 0:
        return _metric_row(
            "escrow_blended_rate",
            period.get("axis_id"),
            None,
            "no_debt_service",
            "zero_denominator",
            "escrow_rate_scale",
            _RATE,
            _RATE_COMPOSITION,
            period=period,
        )
    if drawn < 0 or escrow < 0:
        return _metric_row(
            "escrow_blended_rate",
            period.get("axis_id"),
            None,
            "not_computed",
            "negative_balance",
            "escrow_rate_scale",
            _RATE,
            _RATE_COMPOSITION,
            period=period,
        )
    coverage = escrow / drawn
    special = _decimal(scale["special_rate"])
    for rung in sorted(scale.get("rungs") or [], key=lambda item: _decimal(item["coverage"])):
        if coverage >= _decimal(rung["coverage"]):
            special = _decimal(rung["rate"])
    covered = min(escrow, drawn)
    uncovered = drawn - covered
    base = _decimal(scale["base_rate"])
    value = _divide(covered * special + uncovered * base, drawn)
    book, book_missing = _at(facts, bindings, period, aligned, "effective_rate", convention, absent)
    warnings = []
    if not book_missing and book is not None and quantize_ratio(book) != value:
        warnings.append("escrow_rate_book_mismatch")
    return _metric_row(
        "escrow_blended_rate",
        period.get("axis_id"),
        value,
        "computed",
        None,
        "escrow_rate_scale",
        _RATE,
        _RATE_COMPOSITION,
        period=period,
        warnings=warnings,
        components={
            "covered": format(covered, "f"),
            "uncovered": format(uncovered, "f"),
            "base_rate": format(base, "f"),
            "special_rate": format(special, "f"),
        },
    )


def _once(facts, bindings, periods, axis, concept, convention, absent):
    ordered = _ordered(periods, axis)
    if not ordered:
        return None, "missing"
    return _at(facts, bindings, ordered[-1], aligned_keys(periods), concept, convention, absent)


def _at(facts, bindings, period, aligned, concept, convention, absent):
    rows = _bound(bindings, concept, absent)
    if not rows:
        return None, True
    own = (period.get("axis_id"), period.get("period_id"))
    key = aligned.get(own, own)
    amount, _cells, hole = _sum_plain(rows, facts, key, aligned)
    if hole or amount is None:
        return None, True
    del convention
    return amount, False


def _sum_plain(rows, facts, key, aligned):
    total = Decimal(0)
    cells = []
    for row in rows:
        amount, found, hole = _amount(facts, row, key, aligned)
        if hole or amount is None:
            return None, cells, True
        total += amount
        cells.extend(found)
    return total, cells, False


def _cash_of(row) -> Decimal | None:
    if row["status"] not in {"computed", "no_debt_service"}:
        return None
    total = Decimal(0)
    seen = False
    for name in _CASH:
        if name in row["components"]:
            total += Decimal(row["components"][name])
            seen = True
    return total if seen else None


def _service(row) -> Decimal | None:
    raw = row["components"].get("denominator")
    if raw is None or row["status"] not in {"computed", "no_debt_service"}:
        return None
    return Decimal(raw)


def _obligations(row) -> Decimal | None:
    parts = row["components"]
    if "senior_principal" not in parts or "senior_interest_paid" not in parts:
        return None
    if row["status"] not in {"computed", "no_debt_service"}:
        return None
    return Decimal(parts["senior_principal"]) + Decimal(parts["senior_interest_paid"])


def _interest_of(row) -> Decimal | None:
    raw = row["components"].get("senior_interest_paid")
    if raw is None or row["status"] not in {"computed", "no_debt_service"}:
        return None
    return Decimal(raw)


def _sum(reader, rows):
    total = Decimal(0)
    for row in rows:
        amount = reader(row)
        if amount is None:
            return None
        total += amount
    return total


def _none_confirmed(profile) -> bool | None:
    if profile is None or "guaranteed_funds_none" not in profile or profile.get("guaranteed_funds_none") is None:
        return False
    raw = profile.get("guaranteed_funds_none")
    if raw is True or raw is False:
        return raw
    return None


def _divide(numerator, denominator):
    if denominator == 0:
        return None
    with localcontext() as ctx:
        ctx.prec = 38
        ctx.rounding = "ROUND_HALF_EVEN"
        return quantize_ratio(numerator / denominator)


def _ratio_row(metric, axis, numerator, denominator, variant, methodology, composition, components=None, period=None):
    if numerator is None or denominator is None:
        return _metric_row(metric, axis, None, "not_computed", "missing_component", variant, methodology, composition, period=period)
    if denominator == 0:
        return _metric_row(
            metric, axis, None, "no_debt_service", "zero_denominator", variant, methodology, composition, period=period, components=components
        )
    return _metric_row(
        metric,
        axis,
        _divide(numerator, denominator),
        "computed",
        None,
        variant,
        methodology,
        composition,
        period=period,
        components=components,
    )


def _metric_row(
    metric,
    axis,
    value,
    status,
    reason,
    variant,
    methodology,
    composition,
    *,
    period=None,
    missing=None,
    excluded=None,
    over=None,
    reduction=None,
    warnings=None,
    components=None,
):
    row = {
        "metric": metric,
        "variant": variant,
        "axis_id": axis,
        "period_id": None if period is None else period.get("period_id"),
        "value": value,
        "status": status,
        "reason": reason,
        "missing": list(missing or []),
        "methodology": methodology,
        "composition": composition,
        "standard": "ОДДС",
        "components": components or {},
        "warnings": list(warnings or []),
    }
    if excluded is not None:
        row["excluded_periods"] = excluded
    if over is not None:
        row["over"] = over
    if reduction is not None:
        row["reduction"] = reduction
    return row


def _envelope(metric, rows, status, *, variant=None, warnings=None, message=None):
    body = {
        "metric": metric,
        "rows": rows,
        "needs_input": [],
        "warnings": list(warnings or []),
        "status": status,
        "definition_source": variant or metric,
    }
    if variant:
        body["variant"] = variant
    if message:
        body["message"] = message
    return body


def _status(rows) -> str:
    if any(row["status"] == "computed" for row in rows):
        return "succeeded"
    if rows:
        return "not_computed"
    return "missing_input"


def _axes(rows, periods):
    found = []
    for source in (rows, periods):
        for item in source:
            axis = item.get("axis_id")
            if axis not in found:
                found.append(axis)
    return found


def _decimal(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = Decimal(str(value))
    except (ArithmeticError, ValueError):
        return None
    if not number.is_finite():
        return None
    return number
