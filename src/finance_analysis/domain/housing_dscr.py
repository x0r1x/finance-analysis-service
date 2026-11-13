"""DSCR жилищного строительства: ряд интервалов по сальдо ОДДС и старшему долгу.

Пустая ячейка не становится нулём. Явный ноль остаётся нулём. Вариант pf этот модуль не считает.
"""

from __future__ import annotations

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
METHODOLOGY = (
    "DSCR интервала жилищного строительства: сальдо денежных потоков от текущих операций "
    "плюс сальдо от инвестиционных операций плюс поступления по финансовой деятельности, "
    "делённые на погашение основного долга и уплаченные проценты по несубординированным кредитам и займам. "
    "Пустая ячейка не заменяется нулём."
)


def interest_addback_error(value) -> str | None:
    if value is True or value is False:
        return None
    return "interest_addback: true или false"


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
    if flag is None:
        return {
            "metric": "dscr",
            "variant": "housing",
            "rows": [],
            "needs_input": [],
            "warnings": [],
            "status": "not_computed",
            "message": "interest_addback: true или false",
            "definition_source": "housing",
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
        "definition_source": "housing",
    }


def _period_row(period, facts, bindings, aligned, convention, absent, addback: bool):
    own = (period.get("axis_id"), period.get("period_id"))
    key = aligned.get(own, own)
    missing: list[str] = []
    components: dict = {}
    cells: list[str] = []
    notes: list[str] = []
    numerator = Decimal(0)
    for concept in _NUMERATOR:
        amount, found, hole = _concept_amount(
            _bound(bindings, concept, absent), facts, key, aligned, payment=False, convention=convention
        )
        if hole or amount is None:
            missing.append(concept)
            continue
        numerator += amount
        components[concept] = format(amount, "f")
        cells.extend(found)
        if concept == "financing_inflows":
            notes.append("financing_inflows_included")
    if addback:
        extra, extra_cells = _cash_interest(bindings, facts, key, aligned, convention, absent)
        if extra is not None and "cfo_statement" not in missing and "cfi_statement" not in missing:
            numerator += extra
            components["interest_addback"] = format(extra, "f")
            cells.extend(extra_cells)
    if _cash_interest_rows(bindings):
        notes.append("interest_inside_numerator")
    denominator, denom_missing, blocked, denom_cells = _denominator(
        bindings, facts, key, aligned, convention, absent
    )
    missing.extend(denom_missing)
    cells.extend(denom_cells)
    if _draw_and_repay(bindings, facts, key, aligned, absent, denominator):
        notes.append("same_interval_draw_and_repay")
    if _escrow_outside(bindings, facts, key, aligned, absent, components.get("cfo_statement")):
        notes.append("escrow_outside_cfads")
    numerator_ready = not any(concept in missing for concept in _NUMERATOR)
    if missing:
        status, reason, value = "not_computed", "missing_component", None
    elif blocked or denominator is None:
        status, reason, value = "not_computed", "seniority_unknown", None
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
        "methodology": METHODOLOGY,
        "standard": "ОДДС",
        "components": components,
        "inputs": [*_NUMERATOR, "senior_principal", "senior_interest_paid"],
        "warnings": notes,
    }
    return row, [{"code": code, "params": {"period_id": period.get("period_id")}} for code in notes]


def _denominator(bindings, facts, key, aligned, convention, absent):
    debt = [row for concept in _DEBT for row in _bound(bindings, concept, absent)]
    senior = [row for row in debt if _seniority(row) == "senior" and _role(row)]
    parts = [row for row in senior if _role(row) in {"principal", "interest"}]
    totals = [row for row in senior if _role(row) == "total"]
    if parts:
        principal_rows = [row for row in parts if _role(row) == "principal"]
        interest_rows = [row for row in parts if _role(row) == "interest"]
        missing = []
        cells: list[str] = []
        principal, principal_cells, principal_hole = _sum_rows(principal_rows, facts, key, aligned, True, convention)
        interest, interest_cells, interest_hole = _sum_rows(interest_rows, facts, key, aligned, True, convention)
        cells.extend(principal_cells)
        cells.extend(interest_cells)
        if not principal_rows or principal_hole or principal is None:
            missing.append("senior_principal")
        if not interest_rows or interest_hole or interest is None:
            if _capitalized(debt):
                interest = Decimal(0)
            else:
                missing.append("senior_interest_paid")
        if missing:
            return None, missing, False, cells
        return principal + interest, [], False, cells
    if totals:
        amount, cells, hole = _sum_rows(totals, facts, key, aligned, True, convention)
        if hole or amount is None:
            return None, ["senior_principal", "senior_interest_paid"], False, cells
        return amount, [], False, cells
    if debt:
        return None, [], True, []
    return None, ["senior_principal", "senior_interest_paid"], False, []


def _capitalized(rows: list[dict]) -> bool:
    return any("капитализ" in _text(row) and _seniority(row) == "senior" for row in rows)


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
    if not rows:
        return None, []
    total = Decimal(0)
    cells = []
    any_number = False
    for row in rows:
        amount, found, hole = _amount(facts, row, key, aligned)
        if hole or amount is None:
            continue
        any_number = True
        total += _payment(amount, convention)
        cells.extend(found)
    if not any_number:
        return None, cells
    return total, cells


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
