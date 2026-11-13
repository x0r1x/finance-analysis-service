"""DSCR жилищного строительства: ряд интервалов по сальдо ОДДС и старшему долгу.

Пустая ячейка не становится нулём. Явный ноль остаётся нулём. Вариант pf этот модуль не считает.
"""

from __future__ import annotations

import re
from decimal import Decimal, localcontext

from finance_analysis.domain.mapping import debt_seniority, marked_line_code
from finance_analysis.domain.metrics import (
    _BOUND,
    HUMAN_SOURCES,
    _figure,
    _payment,
    aligned_keys,
    quantize_ratio,
)

_NUMERATOR = ("cfo_statement", "cfi_statement", "financing_inflows")
_DEBT = frozenset({"senior_principal", "senior_interest_paid", "principal", "interest", "debt_service"})
_CASH_INTEREST = frozenset({"4123", "4224"})
_STATED = frozenset({"senior_principal", "senior_interest_paid"})
_JUNIOR_MARKS = ("субордин", "акционер", "участник", "учредител", "shareholder", "subordinated")
_TRANCHE = re.compile(r"(?:транш|tranche)\s*([0-9a-zа-я]+)")
COMPOSITION = (
    "cfo_statement + cfi_statement + financing_inflows / senior_principal + senior_interest_paid"
)
SERVICE_NOTE = " Реализация сервиса опубликованного определения, не воспроизведение закрытой модели банка."
DEFINITION_ID = "dscr.housing@service-v1"
METHODOLOGY = (
    "Вариант housing, не универсальный DSCR. "
    "DSCR интервала жилищного строительства: сальдо денежных потоков от текущих операций "
    "(cfo_statement) плюс сальдо от инвестиционных операций (cfi_statement) плюс поступления "
    "по финансовой деятельности (financing_inflows), делённые на погашение основного долга "
    "(senior_principal) и уплаченные проценты по несубординированным кредитам и займам "
    "(senior_interest_paid). Пустая ячейка не заменяется нулём."
    + SERVICE_NOTE
)


def interest_addback_error(value) -> str | None:
    if value is True or value is False:
        return None
    return "interest_addback: true или false"


def profile_flag_error(name: str, value) -> str | None:
    if value is True or value is False:
        return None
    return f"{name}: true или false"


def _named_flag(profile: dict | None, name: str) -> bool | None:
    """Выключен, когда поля нет. Чужое значение не читается как ложь."""

    if profile is None or name not in profile or profile.get(name) is None:
        return False
    raw = profile.get(name)
    if raw is True or raw is False:
        return raw
    return None


def interest_addback(profile: dict | None) -> bool | None:
    """Выключен, когда поля нет. Чужое значение не читается как ложь."""

    if profile is None or "interest_addback" not in profile or profile.get("interest_addback") is None:
        return False
    raw = profile.get("interest_addback")
    if raw is True or raw is False:
        return raw
    return None


def housing_dscr(
    *,
    facts: list[dict],
    bindings: list[dict],
    periods: list[dict],
    sign_convention: str = "outflow_negative",
    absent: frozenset[str] = frozenset(),
    profile: dict | None = None,
) -> dict:
    flag = interest_addback(profile)
    fees = _named_flag(profile, "include_senior_fees")
    swaps = _named_flag(profile, "include_senior_swaps")
    broken = None
    if flag is None:
        broken = "interest_addback: true или false"
    elif fees is None:
        broken = "include_senior_fees: true или false"
    elif swaps is None:
        broken = "include_senior_swaps: true или false"
    if broken:
        return {
            "metric": "dscr",
            "variant": "housing",
            "rows": [],
            "needs_input": [],
            "warnings": [],
            "status": "not_computed",
            "message": broken,
            "definition": DEFINITION_ID,
            "definition_source": "housing",
            "methodology": METHODOLOGY,
            "composition": COMPOSITION,
            "standard": "ОДДС",
        }
    aligned = aligned_keys(periods)
    rows = []
    warnings = []
    for period in periods:
        row, notes = _period_row(
            period,
            facts,
            bindings,
            aligned,
            sign_convention,
            absent,
            flag,
            fees is True,
            swaps is True,
        )
        rows.append(row)
        warnings.extend(notes)
    if any(row["status"] == "computed" for row in rows):
        status = "succeeded"
    elif rows:
        status = "not_computed"
    else:
        status = "missing_input"
    return {
        "metric": "dscr",
        "variant": "housing",
        "rows": rows,
        "needs_input": [],
        "warnings": warnings,
        "status": status,
        "definition": DEFINITION_ID,
        "definition_source": "housing",
        "methodology": METHODOLOGY,
        "composition": COMPOSITION,
    }


def collect_interval(period, facts, bindings, aligned, convention, absent) -> dict:
    """Потоки ОДДС и старшие обязательства интервала. Без возврата процентов, комиссий и свопов."""

    own = (period.get("axis_id"), period.get("period_id"))
    key = aligned.get(own, own)
    flows: dict[str, Decimal] = {}
    missing: list[str] = []
    cells: list[str] = []
    notes: list[str] = []
    for concept in _NUMERATOR:
        amount, found, hole = _concept_amount(
            _bound(bindings, concept, absent), facts, key, aligned, payment=False, convention=convention
        )
        if hole or amount is None:
            missing.append(concept)
            continue
        flows[concept] = amount
        cells.extend(found)
        if concept == "financing_inflows":
            notes.append("financing_inflows_included")
    split: dict = {}
    denominator, denom_missing, denom_reason, denom_cells = _denominator(
        bindings, facts, key, aligned, convention, absent, split
    )
    missing.extend(denom_missing)
    cells.extend(denom_cells)
    return {
        "flows": flows,
        "missing": missing,
        "principal": split.get("senior_principal"),
        "interest": split.get("senior_interest_paid"),
        "denominator": denominator,
        "denom_reason": denom_reason,
        "cells": cells,
        "notes": notes,
    }


def _period_row(period, facts, bindings, aligned, convention, absent, addback: bool, fees: bool = False, swaps: bool = False):
    own = (period.get("axis_id"), period.get("period_id"))
    key = aligned.get(own, own)
    collected = collect_interval(period, facts, bindings, aligned, convention, absent)
    missing = list(collected["missing"])
    components = {name: format(amount, "f") for name, amount in collected["flows"].items()}
    cells = list(collected["cells"])
    notes = list(collected["notes"])
    numerator = sum(collected["flows"].values(), Decimal(0))
    addback_reason = None
    if addback:
        extra, extra_cells, addback_reason = _cash_interest(bindings, facts, key, aligned, convention, absent)
        if (
            addback_reason is None
            and extra is not None
            and "cfo_statement" not in missing
            and "cfi_statement" not in missing
        ):
            numerator += extra
            components["interest_addback"] = format(extra, "f")
            cells.extend(extra_cells)
    if _cash_interest_rows(bindings):
        notes.append("interest_inside_numerator")
    if addback_reason:
        notes.append(addback_reason)
    denominator = collected["denominator"]
    denom_reason = collected["denom_reason"]
    for concept, enabled in (("senior_fees", fees), ("senior_swaps", swaps)):
        if not enabled:
            continue
        extra, problem, extra_cells = _attributed_cash(
            bindings, facts, key, aligned, convention, absent, concept
        )
        cells.extend(extra_cells)
        if problem == "missing":
            missing.append(concept)
        elif problem:
            denom_reason = denom_reason or problem
        elif extra is not None and denominator is not None:
            denominator += extra
            components[concept] = format(extra, "f")
    if _draw_and_repay(bindings, facts, key, aligned, absent, denominator):
        notes.append("same_interval_draw_and_repay")
    if _escrow_outside(bindings, facts, key, aligned, absent, components.get("cfo_statement")):
        notes.append("escrow_outside_cfads")
    numerator_ready = not any(concept in missing for concept in _NUMERATOR)
    if missing:
        status, reason, value = "not_computed", "missing_component", None
    elif addback_reason:
        status, reason, value = "not_computed", addback_reason, None
    elif denom_reason or denominator is None:
        status, reason, value = "not_computed", denom_reason or "seniority_unknown", None
    elif denominator == 0:
        status, reason, value = "no_debt_service", "zero_denominator", None
    else:
        with localcontext() as ctx:
            ctx.prec = 38
            ctx.rounding = "ROUND_HALF_EVEN"
            value = quantize_ratio(numerator / denominator)
        status, reason = "computed", None
    if denominator is not None:
        components["denominator"] = format(denominator, "f")
    if collected["principal"] is not None:
        components["senior_principal"] = format(collected["principal"], "f")
    if collected["interest"] is not None:
        components["senior_interest_paid"] = format(collected["interest"], "f")
    den_names = ["senior_principal", "senior_interest_paid"]
    if fees:
        den_names.append("senior_fees")
    if swaps:
        den_names.append("senior_swaps")
    composition = COMPOSITION
    if fees or swaps:
        composition = "cfo_statement + cfi_statement + financing_inflows / " + " + ".join(den_names)
    components["cells"] = cells
    _compare_book(
        notes,
        numerator if numerator_ready else None,
        value,
        bindings,
        facts,
        key,
        aligned,
        absent,
    )
    row = {
        "metric": "dscr",
        "variant": "housing",
        "period_id": period.get("period_id"),
        "axis_id": period.get("axis_id"),
        "value": value,
        "status": status,
        "reason": reason,
        "missing": missing,
        "definition": DEFINITION_ID,
        "methodology": METHODOLOGY,
        "composition": composition,
        "standard": "ОДДС",
        "components": components,
        "inputs": [*_NUMERATOR, "senior_principal", "senior_interest_paid"],
        "warnings": notes,
    }
    return row, [{"code": code, "params": {"period_id": period.get("period_id")}} for code in notes]


def _denominator(bindings, facts, key, aligned, convention, absent, split=None):
    debt = [row for concept in _DEBT for row in _bound(bindings, concept, absent)]
    caps = [row for row in debt if _is_cap(row) and _seniority(row) == "senior" and not _mixed(row)]
    senior = [
        row
        for row in debt
        if _seniority(row) == "senior" and _role(row) and not _is_cap(row) and not _mixed(row)
    ]
    mixed = [row for row in debt if _mixed(row) and _role(row) and not _is_cap(row)]
    parts = [row for row in senior if _role(row) in {"principal", "interest"}]
    totals = [row for row in senior if _role(row) == "total"]
    if parts:
        principal_rows = [row for row in parts if _role(row) == "principal"]
        interest_rows = [row for row in parts if _role(row) == "interest"]
        missing = []
        cells: list[str] = []
        principal, principal_cells, principal_hole = _sum_rows(principal_rows, facts, key, aligned, True, convention)
        cells.extend(principal_cells)
        if not principal_rows or principal_hole or principal is None:
            missing.append("senior_principal")
            principal = None
        interest, interest_cells, interest_missing = _resolve_interest(
            principal_rows, interest_rows, caps, facts, key, aligned, convention
        )
        cells.extend(interest_cells)
        if interest_missing:
            if not interest_rows and mixed and "senior_principal" not in missing:
                return None, [], "seniority_unsplit", cells
            missing.append("senior_interest_paid")
        if missing or principal is None or interest is None:
            return None, missing or ["senior_interest_paid"], None, cells
        if split is not None:
            split["senior_principal"] = principal
            split["senior_interest_paid"] = interest
        return principal + interest, [], None, cells
    if mixed and not totals:
        return None, [], "seniority_unsplit", []
    if totals:
        amount, cells, hole = _sum_rows(totals, facts, key, aligned, True, convention)
        if hole or amount is None:
            return None, ["senior_principal", "senior_interest_paid"], None, cells
        return amount, [], None, cells
    if debt:
        return None, [], "seniority_unknown", []
    return None, ["senior_principal", "senior_interest_paid"], None, []


def _resolve_interest(principal_rows, interest_rows, caps, facts, key, aligned, convention):
    """Ноль процентов подтверждается только у своего транша и только в этом периоде."""

    if not principal_rows:
        if not interest_rows:
            return None, [], True
        amount, cells, hole = _sum_rows(interest_rows, facts, key, aligned, True, convention)
        return amount, cells, hole or amount is None

    def capped(principal) -> bool:
        for cap in caps:
            if not _same_tranche(cap, principal, principal_rows):
                continue
            amount, _cells, hole = _amount(facts, cap, key, aligned)
            if not hole and amount is not None:
                return True
        return False

    total = Decimal(0)
    cells: list[str] = []
    unresolved = False
    specific_any = False
    shared = [row for row in interest_rows if _token(row) is None]
    for principal in principal_rows:
        token = _token(principal)
        specific = [row for row in interest_rows if token is not None and _token(row) == token]
        if specific:
            specific_any = True
            amount, row_cells, hole = _sum_rows(specific, facts, key, aligned, True, convention)
            if not hole and amount is not None:
                total += amount
                cells.extend(row_cells)
                continue
            if capped(principal):
                continue
            unresolved = True
            continue
        if capped(principal):
            continue
        if not shared:
            unresolved = True

    def is_dependent(principal) -> bool:
        token = _token(principal)
        own = token is not None and any(_token(row) == token for row in interest_rows)
        return not own and not capped(principal)

    dependents = [principal for principal in principal_rows if is_dependent(principal)]
    if shared and (dependents or not specific_any):
        amount, row_cells, hole = _sum_rows(shared, facts, key, aligned, True, convention)
        if dependents and (hole or amount is None):
            unresolved = True
        elif not hole and amount is not None:
            total += amount
            cells.extend(row_cells)
    if unresolved:
        return None, cells, True
    return total, cells, False


def _same_tranche(row, principal, principals) -> bool:
    row_token = _token(row)
    principal_token = _token(principal)
    if row_token is not None and principal_token is not None:
        return row_token == principal_token
    # Строка без имени транша подтверждает ноль только единственному кредиту.
    return row_token is None and len(principals) == 1


def _token(row: dict) -> str | None:
    found = _TRANCHE.search(_text(row))
    return found.group(1) if found else None


def _is_cap(row: dict) -> bool:
    return "капитализ" in _text(row)


def _mixed(row: dict) -> bool:
    """Старший и младший долг в одной строке. «Несубординированный» само по себе не смесь."""

    text = _text(row)
    if not any(mark in text for mark in ("несубордин", "старш", "senior")):
        return False
    stripped = text.replace("несубординированн", " ").replace("несубордин", " ")
    return any(mark in stripped for mark in _JUNIOR_MARKS)


def _seniority(row: dict) -> str:
    found = debt_seniority(row)
    if found != "unknown":
        return found
    if row.get("effective_concept") in _STATED:
        return "senior"
    return "unknown"


def _role(row: dict) -> str | None:
    concept = row.get("effective_concept")
    code = _code(row)
    if concept == "senior_principal" or code == "4323":
        return "principal"
    if concept == "senior_interest_paid" or (concept == "interest" and code in _CASH_INTEREST):
        return "interest"
    if concept == "principal":
        return "principal"
    if concept == "debt_service":
        return "total"
    if code in _CASH_INTEREST:
        return "interest"
    return None


def _concept_amount(rows, facts, key, aligned, *, payment: bool, convention: str):
    totals = [row for row in rows if (row.get("evidence") or {}).get("flow_role") == "total"]
    return _sum_rows(totals or rows, facts, key, aligned, payment, convention)


def _sum_rows(rows, facts, key, aligned, payment: bool, convention: str):
    if not rows:
        return None, [], True
    total = Decimal(0)
    cells: list[str] = []
    for row in rows:
        amount, found, hole = _amount(facts, row, key, aligned)
        if hole or amount is None:
            return None, cells, True
        total += _payment(amount, convention) if payment else amount
        cells.extend(found)
    return total, cells, False


def _amount(facts, row, key, aligned):
    total = Decimal(0)
    cells = []
    seen = False
    for fact in facts:
        if fact.get("row_key") != row.get("row_key"):
            continue
        own = (fact.get("axis_id"), fact.get("period_id"))
        if aligned.get(own, own) != key:
            continue
        number = _figure(fact)
        if number is None:
            continue
        seen = True
        total += number
        cell = fact.get("cell_id")
        if cell:
            cells.append(cell)
    if not seen:
        return None, cells, True
    return total, cells, False


def _bound(bindings, concept, absent) -> list[dict]:
    found = []
    for row in bindings:
        if row.get("effective_concept") != concept or not row.get("is_primary"):
            continue
        if row.get("status") not in _BOUND:
            continue
        if concept in absent and row.get("source") not in HUMAN_SOURCES:
            continue
        found.append(row)
    return found


def _code(row: dict) -> str | None:
    evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
    raw = evidence.get("line_code") or row.get("line_code")
    code = marked_line_code(raw)
    if not code:
        return None
    if code.startswith("стр. "):
        digits = code.removeprefix("стр. ")
        return digits if digits.isdigit() else None
    return code if code.isdigit() else None


def _text(row: dict) -> str:
    evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
    parts = [
        str(row.get("label") or ""),
        str(row.get("label_path_text") or ""),
        str(evidence.get("line_code") or ""),
    ]
    path = row.get("label_path")
    if isinstance(path, (list, tuple)):
        parts.extend(str(item) for item in path)
    return " ".join(parts).casefold().replace("ё", "е")


def _cash_interest_rows(bindings) -> list[dict]:
    return [row for row in bindings if _code(row) in _CASH_INTEREST and row.get("status", "bound") in _BOUND]


def _cash_interest(bindings, facts, key, aligned, convention, absent):
    """Вернуть только основную строку с подтверждённым старшим процентом.

    Смешанная или безымянная строка 4123/4224 целиком не прибавляется. Если разбивки нет,
    причина `interest_addback_unattributed`: число с таким флагом не выпускается.
    """

    rows = []
    seen = set()
    for row in _cash_interest_rows(bindings):
        identity = row.get("row_key")
        if identity in seen:
            continue
        if row.get("effective_concept") in absent and row.get("source") not in HUMAN_SOURCES:
            continue
        seen.add(identity)
        rows.append(row)
    clean = []
    blocked = False
    for row in rows:
        if _senior_cash(row):
            clean.append(row)
            continue
        if _seniority(row) == "subordinated" and not _mixed(row):
            continue
        blocked = True
    if blocked and not clean:
        return None, [], "interest_addback_unattributed"
    if not clean:
        return None, [], None
    amount, cells, hole = _sum_rows(clean, facts, key, aligned, True, convention)
    if hole or amount is None:
        return None, cells, "interest_addback_unattributed"
    return amount, cells, None


def _senior_cash(row: dict) -> bool:
    return bool(row.get("is_primary")) and _seniority(row) == "senior" and not _mixed(row) and not _is_cap(row)


def _attributed_cash(bindings, facts, key, aligned, convention, absent, concept):
    """Старшая кассовая сумма. Младшая строка не доказывает, что старшей суммы нет."""

    rows = _bound(bindings, concept, absent)
    if any(_mixed(row) for row in rows):
        return None, "seniority_unsplit", []
    senior = [row for row in rows if _seniority(row) == "senior"]
    if not senior:
        return None, "missing", []
    amount, cells, hole = _sum_rows(senior, facts, key, aligned, True, convention)
    if hole or amount is None:
        return None, "missing", cells
    return amount, None, cells


def _draw_and_repay(bindings, facts, key, aligned, absent, denominator) -> bool:
    if denominator is None or denominator == 0:
        return False
    principal = Decimal(0)
    for row in _bound(bindings, "senior_principal", absent) + _bound(bindings, "principal", absent):
        if _seniority(row) != "senior" or _role(row) != "principal":
            continue
        amount, _cells, hole = _amount(facts, row, key, aligned)
        if hole or amount is None:
            continue
        principal += _payment(amount, "outflow_negative")
    if principal == 0:
        return False
    for row in _bound(bindings, "financing_inflows", absent):
        if not _draw(row):
            continue
        amount, _cells, hole = _amount(facts, row, key, aligned)
        if amount is not None and not hole and amount != 0:
            return True
    return False


def _draw(row: dict) -> bool:
    if _code(row) == "4311":
        return True
    text = _text(row)
    return any(token in text for token in ("кредит", "займ", "заем", "loan", "draw"))


def _escrow_outside(bindings, facts, key, aligned, absent, cfo) -> bool:
    if cfo is None or Decimal(cfo) != 0:
        return False
    for row in _bound(bindings, "escrow_disclosure", absent):
        amount, _cells, hole = _amount(facts, row, key, aligned)
        if amount is not None and not hole and amount != 0:
            return True
    return False


def _compare_book(notes, numerator, ratio, bindings, facts, key, aligned, absent) -> None:
    """Строка книги сверяется и не подменяет расчёт. Нет строки — нет предупреждения."""

    if numerator is not None:
        book = _one_amount(bindings, "cfads", facts, key, aligned, absent)
        if book is not None and abs(book - numerator) > Decimal("0.005"):
            notes.append("housing_book_mismatch")
    if ratio is not None and "housing_book_mismatch" not in notes:
        book = _one_amount(bindings, "dscr", facts, key, aligned, absent)
        if book is not None and abs(quantize_ratio(book) - ratio) > Decimal("0.005"):
            notes.append("housing_book_mismatch")


def _one_amount(bindings, concept, facts, key, aligned, absent):
    rows = _bound(bindings, concept, absent)
    if not rows:
        return None
    amount, _cells, hole = _amount(facts, rows[0], key, aligned)
    if hole or amount is None:
        return None
    return amount
