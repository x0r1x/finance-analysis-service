"""Составные коэффициенты среза 2: ковенантный DSCR, чистый долг и эскроу.

Арифметика только над привязанными строками. Чисел из профиля нет: оттуда
приходят состав числителя, знаменателя и окно.
"""

from __future__ import annotations

from decimal import Decimal

from finance_analysis.domain.cover_metrics import (
    _missing,
    _ordered,
    _ratio,
    _window,
    grain_months,
)
from finance_analysis.domain.metrics import (
    _axes_of,
    _payment,
    _primaries,
    _sums,
    aligned_keys,
    coverage_ratio,
)
from finance_analysis.domain.model_type import Composed, Side
from finance_analysis.domain.period_basis import basis_of
from finance_analysis.domain.returns import project_return

DEFAULT_DEFINITION_TEXT = "определение по умолчанию, не из договора"
_WINDOWS = frozenset({"LTM", "period"})
_FIELDS = frozenset({"numerator", "denominator", "window", "basis_ref"})
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
) -> dict:
    definition, source, ref, notes = resolve_covenant(
        profile, profile_ref, default, concepts=concepts, money=money
    )
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
    aligned = aligned_keys(periods)
    series = {name: _sums(facts, primaries[name], aligned, periods) for name in dict.fromkeys(needed)}
    basis = {name: basis_of(primaries[name])[0] for name in series}
    home_name = formula.denominator.plus[0] if formula.denominator.plus else formula.denominator.minus[0]
    inputs = list(dict.fromkeys(needed))
    rows = []
    for axis in sorted(_axes_of(facts, primaries[home_name])):
        ordered = _ordered(periods, axis)
        axis_keys = [aligned.get((axis, item["period_id"]), (axis, item["period_id"])) for item in ordered]
        debt_on_axis = metric != "net_debt_ebitda" or any(key in series["net_debt"] for key in axis_keys)
        for period in ordered:
            marker = period.get("marker_class")
            if marker_class and marker and marker != marker_class:
                continue
            keys, window, problem = _span(formula.window, ordered, period, aligned, axis)
            if problem and not debt_on_axis:
                rows.append(
                    _line(metric, period, None, "input_absent", "input_absent", inputs, window, message=_NET_DEBT_ABSENT)
                )
                continue
            if problem:
                rows.append(_line(metric, period, None, "not_computed", problem, inputs, window))
                continue
            if metric == "net_debt_ebitda":
                numerator = _ending(keys, series, "net_debt")
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
                numerator = _total(keys, series, formula.numerator, sign_convention, pay_plus=False, basis=basis)
                denominator = _total(keys, series, formula.denominator, sign_convention, pay_plus=True, basis=basis)
            if numerator is None or denominator is None:
                rows.append(_line(metric, period, None, "missing_input", "no_binding", inputs, window))
                continue
            if denominator == 0:
                status = "no_debt_service" if metric == "dscr" else "missing_input"
                rows.append(_line(metric, period, None, status, "zero_denominator", inputs, window))
                continue
            rows.append(_line(metric, period, _ratio(numerator, denominator), "computed", None, inputs, window))
    status = "succeeded"
    message = None
    absent = metric == "net_debt_ebitda" and any(row["status"] == "input_absent" for row in rows)
    if absent and not any(row["status"] == "computed" for row in rows):
        status = "input_absent"
        message = _NET_DEBT_ABSENT
    result = {"metric": metric, "rows": rows, "needs_input": [], "warnings": [], "status": status}
    if message:
        result["message"] = message
    return result


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
    return coverage_ratio(metric=metric, **common)


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


def _ending(keys, series: dict, name: str) -> Decimal | None:
    if not keys or keys[-1] not in series[name]:
        return None
    return series[name][keys[-1]]


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
