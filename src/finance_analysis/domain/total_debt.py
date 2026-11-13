"""Долг на дату: заемные средства плюс обязательство по аренде.

Частное не считается. Знак потока на запас не вешается. Разбор 76.07 — гипотеза.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal

from finance_analysis.domain.metrics import _figure

_STANDARDS = frozenset({"ras", "ifrs", "gaap"})
_METHODOLOGY = {
    "ras": "Долг (РСБУ: ФСБУ 4/2023, ФСБУ 25/2018)",
    "ifrs": "Долг (МСФО: IFRS 16)",
    "gaap": "Долг (US GAAP: ASC 842)",
}
_FORM_CODES = frozenset({"1400", "1410", "1500", "1510", "1520", "510", "610"})
_BOUND = frozenset({"bound", "bound_with_warning"})
# Гипотеза 1С требует все четыре субсчёта. Отсутствующий не заменяется нулём: .2 и .9 тоже обязательны.
_REQUIRED_SUBACCOUNTS = ("1", "2", "5", "9")
_DASH = frozenset({"-", "—", "–", "−"})


def debt_standard_error(value) -> str | None:
    if isinstance(value, str) and value in _STANDARDS:
        return None
    return "debt_standard: ras, ifrs или gaap"


def debt_standard(profile: dict | None) -> str:
    """Пустой профиль считает РСБУ. Язык подписи стандарт не выбирает."""

    raw = (profile or {}).get("debt_standard")
    if raw in (None, ""):
        return "ras"
    if isinstance(raw, str) and raw in _STANDARDS:
        return raw
    return "invalid"


def operating_lease_flag_error(value) -> str | None:
    if isinstance(value, bool):
        return None
    return "include_operating_lease_liability: true или false"


def include_operating_lease(profile: dict | None) -> bool | None:
    """По умолчанию операционная аренда входит в долг US GAAP. Ветки РСБУ и МСФО флаг не читают."""

    if profile is None or "include_operating_lease_liability" not in profile:
        return True
    raw = profile.get("include_operating_lease_liability")
    if isinstance(raw, bool):
        return raw
    return None


def total_debt_result(
    *,
    facts: list[dict],
    bindings: list[dict],
    periods: list[dict],
    profile: dict | None = None,
    marker_class: str | None = None,
) -> dict:
    standard = debt_standard(profile)
    flag = include_operating_lease(profile)
    if standard == "invalid" or flag is None:
        return _blocked("debt_standard: ras, ifrs или gaap; include_operating_lease_liability: true или false")
    rows = []
    for period in periods:
        marker = period.get("marker_class")
        if marker_class and marker and marker != marker_class:
            continue
        rows.append(_one_period(period, periods, facts, bindings, standard, flag))
    if not rows:
        return {"metric": "total_debt", "rows": [], "needs_input": [], "warnings": [], "status": "missing_input"}
    if any(row["status"] == "computed" for row in rows):
        status = "succeeded"
    elif any(row["status"] == "not_computed" for row in rows):
        status = "not_computed"
    else:
        status = "missing_input"
    result = {"metric": "total_debt", "rows": rows, "needs_input": [], "warnings": [], "status": status}
    if status != "succeeded":
        result["message"] = rows[0].get("message")
    return result


def _blocked(message: str) -> dict:
    return {
        "metric": "total_debt",
        "rows": [],
        "needs_input": [],
        "warnings": [],
        "status": "not_computed",
        "message": message,
    }


def _one_period(period: dict, periods: list[dict], facts: list[dict], bindings: list[dict], standard: str, flag: bool) -> dict:
    form = _form_seen(bindings)
    missing: list[str] = []
    inferred: list[str] = []
    anomaly = False
    components: list[dict] = []
    total = Decimal(0)
    conflict = False

    borrowings, borrow_missing, borrow_inferred, borrow_conflict, borrow_anomaly, borrow_parts = _borrowings(
        period, periods, facts, bindings
    )
    missing.extend(borrow_missing)
    inferred.extend(borrow_inferred)
    anomaly = anomaly or borrow_anomaly
    conflict = conflict or borrow_conflict
    components.extend(borrow_parts)
    if borrowings is not None:
        total += borrowings

    lease, lease_missing, lease_anomaly, lease_part = _lease(period, periods, facts, bindings, standard, flag)
    missing.extend(lease_missing)
    anomaly = anomaly or lease_anomaly
    if lease_part.get("conflict"):
        conflict = True
    if lease is not None:
        total += lease
    if lease_part.get("parts"):
        components.extend(lease_part["parts"])
    elif lease_part:
        components.append(
            {key: value for key, value in lease_part.items() if key not in {"conflict", "missing_subaccounts"}}
        )

    engaged = form or any(item.get("value") is not None for item in components) or inferred
    if lease_part.get("missing_subaccounts"):
        return _row(period, None, "not_computed", "missing_subaccount", missing, standard, flag, components, inferred, anomaly, lease_part)
    if _mixed_units(components):
        return _row(period, None, "not_computed", "unit_unknown", missing, standard, flag, components, inferred, anomaly, lease_part)
    if conflict:
        return _row(period, None, "not_computed", "source_conflict", missing, standard, flag, components, inferred, anomaly, lease_part)
    if missing and engaged:
        return _row(period, None, "not_computed", "missing_component", missing, standard, flag, components, inferred, anomaly, lease_part)
    if missing:
        return _row(period, None, "missing_input", "no_binding", missing, standard, flag, components, inferred, anomaly, lease_part)
    return _row(period, total, "computed", None, missing, standard, flag, components, inferred, anomaly, lease_part)


def _row(period, value, status, reason, missing, standard, flag, components, inferred, anomaly, lease_part) -> dict:
    item = {
        "metric": "total_debt",
        "period_id": period.get("period_id"),
        "axis_id": period.get("axis_id"),
        "value": value,
        "status": status,
        "reason": reason,
        "missing_inputs": missing,
        "inputs": ["borrowings_lt", "borrowings_st", "lease_liability"],
        "methodology": _METHODOLOGY[standard],
        "standard": standard,
        "components": components,
        "inferred_zero": inferred,
        "sign_anomaly": anomaly,
        "lease_source": lease_part.get("source"),
        "lease_measurement": lease_part.get("measurement"),
    }
    if standard == "gaap":
        item["include_operating_lease_liability"] = flag
    if status != "computed":
        item["message"] = _message(status, reason, missing)
    return item


def _message(status: str, reason: str | None, missing: list[str]) -> str:
    if reason == "source_conflict":
        return "На одну дату квартал и год дают разные числа. Долг не выпущен."
    if reason == "missing_subaccount":
        return "Нет субсчетов гипотезы 1С: " + ", ".join(missing) + ". Отсутствие в книге не считается нулём."
    if missing:
        return "Не хватает компонента: " + ", ".join(missing)
    return status


def _borrowings(period, periods, facts, bindings):
    long_rows = _bound(bindings, "borrowings_lt")
    short_rows = _bound(bindings, "borrowings_st")
    total_rows = _bound(bindings, "borrowings_total")
    parts = []
    missing = []
    inferred = []
    conflict = False
    anomaly = False
    amount = Decimal(0)
    found_line = False
    for concept, rows in (("borrowings_lt", long_rows), ("borrowings_st", short_rows)):
        value, problem, flagged, cells = _stock(period, periods, facts, rows)
        if problem == "conflict":
            conflict = True
        if flagged:
            anomaly = True
        if value is None and not rows:
            zero = _inferred_zero(period, periods, facts, bindings, concept)
            if zero is not None:
                inferred.append(concept)
                parts.append({"role": concept, "value": "0", "source": "inferred_zero", "cells": [], "scaled": False})
                found_line = True
                continue
            missing.append(concept)
            continue
        if value is None:
            missing.append(concept)
            continue
        amount += value
        found_line = True
        parts.append({"role": concept, "value": _text(value), "source": _code(rows), "cells": cells, "scaled": _scaled(rows)})
    if not found_line and total_rows and "borrowings_lt" in missing and "borrowings_st" in missing:
        value, problem, flagged, cells = _stock(period, periods, facts, total_rows)
        if problem == "conflict":
            conflict = True
        anomaly = anomaly or flagged
        if value is not None:
            missing = [name for name in missing if name not in {"borrowings_lt", "borrowings_st"}]
            amount += value
            parts.append({"role": "borrowings_total", "value": _text(value), "source": "total", "cells": cells, "granularity": "total", "scaled": _scaled(total_rows)})
    return amount if not missing else None, missing, inferred, conflict, anomaly, parts


def _inferred_zero(period, periods, facts, bindings, concept: str):
    total_concept = "section_lt_total" if concept == "borrowings_lt" else "section_st_total"
    marker = "долгосрочные обязательства" if concept == "borrowings_lt" else "краткосрочные обязательства"
    totals = _bound(bindings, total_concept)
    if not totals:
        return None
    total, problem, _flag, _cells = _stock(period, periods, facts, totals)
    if total is None or problem:
        return None
    others = Decimal(0)
    seen = False
    for row in bindings:
        if row.get("row_key") in {item.get("row_key") for item in totals}:
            continue
        blob = _label(row)
        if marker not in blob and "раздел iv" not in blob and "раздел v" not in blob:
            continue
        if concept == "borrowings_lt" and "долгосроч" not in blob and "раздел iv" not in blob:
            continue
        if concept == "borrowings_st" and "краткосроч" not in blob and "раздел v" not in blob:
            continue
        value, problem, _flag, _cells = _stock(period, periods, facts, [row])
        if value is None or problem:
            return None
        others += value
        seen = True
    if seen and others == total:
        return Decimal(0)
    return None


def _lease(period, periods, facts, bindings, standard: str, flag: bool):
    if standard == "gaap":
        return _gaap_lease(period, periods, facts, bindings, flag)
    rows = _bound(bindings, "lease_liability")
    if not rows:
        if _confirmed_zero(bindings):
            part = {"role": "lease_liability", "value": "0", "source": "confirmed_zero", "measurement": None, "cells": [], "scaled": False}
            return Decimal(0), [], False, part
        return None, ["lease_liability"], False, {}
    value, measurement, source, anomaly, conflict, cells, missing_subs = _lease_amount(period, periods, facts, rows)
    if missing_subs:
        return None, missing_subs, anomaly, {
            "role": "lease_liability",
            "value": None,
            "source": source,
            "measurement": measurement,
            "cells": cells,
            "scaled": False,
            "missing_subaccounts": missing_subs,
        }
    if conflict:
        return None, [], anomaly, {"role": "lease_liability", "value": None, "source": source, "conflict": True, "cells": cells}
    if value is None:
        return None, ["lease_liability"], anomaly, {}
    part = {
        "role": "lease_liability",
        "value": _text(value),
        "source": source,
        "measurement": measurement,
        "cells": cells,
        "scaled": _scaled(rows),
    }
    return value, [], anomaly, part


def _gaap_lease(period, periods, facts, bindings, flag: bool):
    finance_rows = _bound(bindings, "finance_lease_liability")
    operating_rows = _bound(bindings, "operating_lease_liability")
    finance, fin_problem, fin_flag, fin_cells = _stock(period, periods, facts, finance_rows)
    operating, op_problem, op_flag, op_cells = _stock(period, periods, facts, operating_rows)
    missing = []
    if finance is None:
        missing.append("finance_lease_liability")
    # Выключенная операционная аренда остаётся в разборе и не меняет статус, конфликт и знак.
    if flag and op_problem != "conflict" and operating is None:
        missing.append("operating_lease_liability")
    conflict = fin_problem == "conflict" or (flag and op_problem == "conflict")
    anomaly = fin_flag or (flag and op_flag)
    amount = None
    if not missing and not conflict and finance is not None:
        amount = finance
        if flag and operating is not None:
            amount += operating
    extra = []
    if finance is not None:
        extra.append(
            {
                "role": "finance_lease_liability",
                "value": _text(finance),
                "source": "asc_842",
                "cells": fin_cells,
                "scaled": _scaled(finance_rows),
            }
        )
    if operating_rows:
        extra.append(
            {
                "role": "operating_lease_liability",
                "value": None if operating is None else _text(operating),
                "source": "asc_842",
                "cells": op_cells,
                "included": flag,
                "scaled": _scaled(operating_rows),
            }
        )
    part = {
        "role": "lease_gaap",
        "value": None if amount is None else _text(amount),
        "source": "asc_842",
        "measurement": None,
        "cells": [*fin_cells, *op_cells] if flag else fin_cells,
        "conflict": conflict,
        "parts": extra,
    }
    return amount, missing, anomaly, part


def _lease_amount(period, periods, facts, rows):
    grouped = {"1": [], "2": [], "5": [], "9": [], "part": [], "total": []}
    for row in rows:
        grouped[_lease_kind(row)].append(row)
    anomaly = False

    def take(bucket: str):
        nonlocal anomaly
        values = []
        cells = []
        flagged = False
        for row in grouped[bucket]:
            value, problem, flag, row_cells = _stock(period, periods, facts, [row])
            if problem == "conflict":
                return None, True, row_cells, True
            if flag:
                flagged = True
            if value is not None:
                values.append(value)
                cells.extend(row_cells)
        if not values:
            return None, flagged, cells, False
        return sum(values, Decimal(0)), flagged, cells, False

    if any(grouped[key] for key in _REQUIRED_SUBACCOUNTS):
        # shortcut: дебет 76.07.5 и 76.07.9 вычитается по модулю, живую книгу сверяет E1.
        # Все четыре субсчёта обязательны. Нет строки или нет числа — не ноль.
        pieces = {}
        cells = []
        conflict = False
        missing = []
        for key in _REQUIRED_SUBACCOUNTS:
            code = f"76.07.{key}"
            if not grouped[key]:
                missing.append(code)
                continue
            value, flagged, row_cells, row_conflict = take(key)
            anomaly = anomaly or flagged
            cells.extend(row_cells)
            if row_conflict:
                conflict = True
                continue
            if value is None and _dash_zero(grouped[key], period, periods, facts):
                value = Decimal(0)
            if value is None:
                missing.append(code)
                continue
            pieces[key] = value
        if missing:
            return None, "pv_hypothesis", "76", anomaly, False, cells, missing
        if conflict:
            return None, "pv_hypothesis", "76", anomaly, True, cells, []
        amount = pieces["1"] + pieces["2"] - abs(pieces["5"]) - abs(pieces["9"])
        return amount, "pv_hypothesis", "76", anomaly, False, cells, []
    if grouped["total"] and grouped["part"]:
        value, flagged, cells, row_conflict = take("total")
        return value, "as_reported", _lease_source(rows), anomaly or flagged, row_conflict, cells, []
    bucket = "part" if grouped["part"] else "total"
    value, flagged, cells, row_conflict = take(bucket)
    return value, "as_reported", _lease_source(rows), anomaly or flagged, row_conflict, cells, []


def _dash_zero(rows: list[dict], period: dict, periods: list[dict], facts: list[dict]) -> bool:
    """Прочерк в существующей ячейке — подтверждённый ноль, не пропуск строки."""

    end = period.get("period_end")
    for row in rows:
        for fact in facts:
            if fact.get("row_key") != row.get("row_key"):
                continue
            if not _same_date(fact, period, periods, end):
                continue
            if _figure(fact) is not None:
                continue
            if str(fact.get("display") or "").strip() in _DASH:
                return True
    return False


def _lease_kind(row: dict) -> str:
    text = _label(row)
    for key, pattern in (("1", r"76\s*\.\s*07\s*\.\s*1"), ("2", r"76\s*\.\s*07\s*\.\s*2"), ("5", r"76\s*\.\s*07\s*\.\s*5"), ("9", r"76\s*\.\s*07\s*\.\s*9")):
        if re.search(pattern, text):
            return key
    if "долгосроч" in text or "краткосроч" in text:
        return "part"
    return "total"


def _lease_source(rows: list[dict]) -> str:
    text = " ".join(_label(row) for row in rows)
    if "76" in text:
        return "76"
    if "8.1" in text or "наличие и движение обязательств" in text:
        return "note_8_1"
    return "balance_line"


def _confirmed_zero(bindings: list[dict]) -> bool:
    text = " ".join(_label(row) for row in bindings)
    note = "4.2" in text and "пользован" in text and "отсутств" in text
    exempt = "пункт 11" in text or "упрощен" in text
    return note and exempt


def _stock(period, periods, facts, rows):
    """Одно число на дату. Одинаковые значения схлопываются, разные — конфликт."""

    if not rows:
        return None, None, False, []
    end = period.get("period_end")
    found: list[tuple[Decimal, bool, str]] = []
    for row in rows:
        scale = _unit_scale(row)
        for fact in facts:
            if fact.get("row_key") != row.get("row_key"):
                continue
            if not _same_date(fact, period, periods, end):
                continue
            number = _figure(fact)
            if number is None:
                continue
            display = str(fact.get("display") or "")
            anomaly = number < 0 or display.strip().startswith(("(", "-"))
            if scale is None and _any_unit(rows):
                return None, "unit", False, []
            if scale is not None:
                number = number * scale
            cell = str(fact.get("cell_id") or "")
            found.append((number, anomaly, cell))
    if not found:
        if _any_unit(rows) and any(_unit_scale(row) is None for row in rows):
            return None, "unit", False, []
        return None, None, False, []
    amounts = {item[0] for item in found}
    if len(amounts) > 1:
        return None, "conflict", any(item[1] for item in found), [item[2] for item in found if item[2]]
    return found[0][0], None, any(item[1] for item in found), [item[2] for item in found if item[2]]


def _same_date(fact: dict, period: dict, periods: list[dict], end) -> bool:
    own = fact.get("axis_id") == period.get("axis_id") and fact.get("period_id") == period.get("period_id")
    if end is None:
        return own
    for item in periods:
        if item.get("axis_id") == fact.get("axis_id") and item.get("period_id") == fact.get("period_id"):
            return item.get("period_end") == end
    return own


def _mixed_units(components: list[dict]) -> bool:
    flags = [
        part["scaled"]
        for part in components
        if "scaled" in part and part.get("included", True) is not False and part.get("source") not in {"inferred_zero", "confirmed_zero"}
    ]
    return bool(flags) and any(flags) and not all(flags)


def _scaled(rows: list[dict]) -> bool:
    return bool(rows) and all(_unit_scale(row) is not None for row in rows)


def _any_unit(rows: list[dict]) -> bool:
    return any(_unit_scale(row) is not None for row in rows)


def _unit_scale(row: dict) -> Decimal | None:
    raw = row.get("unit")
    if not isinstance(raw, str) or raw in {"", "money"}:
        return None
    text = raw.casefold().replace("ё", "е").replace(" ", "")
    if "млн" in text or text == "385":
        return Decimal(1_000_000)
    if "тыс" in text or text == "384":
        return Decimal(1000)
    if "руб" in text:
        return Decimal(1)
    return None


def _bound(bindings: list[dict], concept: str) -> list[dict]:
    return [
        row
        for row in bindings
        if row.get("effective_concept") == concept and row.get("status") in _BOUND
    ]


def _label(row: dict) -> str:
    return " ".join(
        str(row.get(key) or "") for key in ("label", "label_path_text", "parent_label")
    ).casefold().replace("ё", "е")


def _code(rows: list[dict]) -> str | None:
    for row in rows:
        evidence = _evidence(row)
        code = evidence.get("line_code")
        if code:
            return str(code)
    return None


def _evidence(row: dict) -> dict:
    raw = row.get("evidence")
    if isinstance(raw, dict):
        return raw
    text = row.get("evidence_json")
    if isinstance(text, str) and text:
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return loaded if isinstance(loaded, dict) else {}
    return {}


def _form_seen(bindings: list[dict]) -> bool:
    for row in bindings:
        code = _evidence(row).get("line_code")
        if code in _FORM_CODES:
            return True
        text = _label(row)
        if any(needle in text for needle in ("0710001", "долгосрочные обязательства", "краткосрочные обязательства", "раздел iv", "раздел v")):
            return True
    return False


def _text(value: Decimal) -> str:
    return format(value, "f")
