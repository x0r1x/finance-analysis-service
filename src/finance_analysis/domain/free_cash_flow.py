"""Корпоративный FCFF. Произведение (1 − t) считает этот модуль, не YAML.

fcff = operating_cash_flow + shield − capex.
Щит есть только когда проценты уже вычтены из выбранной строки OCF:
величина уплаченных процентов × (1 − ставка этого периода).
Нет строки OCF — из прибыли и амортизации её не собирать. Ставку 20% не подставлять.
"""

from __future__ import annotations

from decimal import Decimal, localcontext

from finance_analysis.domain.metrics import (
    HUMAN_SOURCES,
    MONEY,
    _close,
    _figure,
    _output_sheet,
    _primaries,
    _stated_digits,
    aligned_keys,
    confirm_paid_interest,
)

_EXCLUDED = (
    "Операционный поток не уменьшен на проценты. "
    "FCFF посчитан как OCF − capex, без добавки процентов после налога."
)
_BOUND = frozenset({"bound", "bound_with_warning"})
_FINANCING_SECTION = (
    "финансовая деятельность",
    "финансовой деятельности",
    "financing",
)


def free_cash_flow(
    *,
    facts: list[dict],
    bindings: list[dict],
    periods: list[dict],
    sign_convention: str = "outflow_negative",
    absent: frozenset[str] = frozenset(),
) -> dict:
    primaries = _primaries(bindings, absent)
    ocf = primaries.get("operating_cash_flow")
    capex = primaries.get("capex")
    if ocf is None:
        return _missing("operating_cash_flow")
    if capex is None:
        return _missing("capex")
    confirm_paid_interest(primaries, bindings, absent)
    paid = primaries.get("interest_paid")
    accrued = primaries.get("interest")
    if (
        accrued is not None
        and paid is not None
        and accrued.get("row_key") == paid.get("row_key")
    ):
        accrued = None
    basis = _basis(ocf, bindings, absent)
    rate_row = primaries.get("income_tax_rate")
    aligned = aligned_keys(periods)
    table, rate_periods = _rates(facts, rate_row, aligned) if rate_row else ({}, [])
    warnings: list[dict] = []
    seen: set[str] = set()
    rows: list[dict] = []
    for period in _ocf_periods(facts, ocf, periods):
        ocf_value = _at(facts, ocf, period, aligned)
        capex_value = _at(facts, capex, period, aligned)
        if ocf_value is None or capex_value is None:
            rows.append(
                _blank(
                    period,
                    "missing_capex" if ocf_value is not None else "missing_input",
                )
            )
            continue
        capex_mag, capex_bad = _outflow(capex_value, sign_convention)
        shield = Decimal(0)
        used_paid = False
        paid_bad = False
        if basis == "unknown":
            rows.append(_blank(period, "ocf_basis_unknown"))
            continue
        if basis != "interest_excluded":
            if basis == "candidate":
                blocked = _candidate_block(facts, accrued, paid, period, aligned)
                if blocked:
                    rows.append(_blank(period, blocked))
                    continue
            if paid is None:
                rows.append(_blank(period, "interest_paid_unconfirmed"))
                continue
            paid_value = _at(facts, paid, period, aligned)
            if paid_value is None:
                rows.append(_blank(period, "interest_paid_unconfirmed"))
                continue
            paid_mag, paid_bad = _outflow(paid_value, sign_convention)
            rate = _rate_for(table, aligned, period)
            if rate is None:
                rows.append(_blank(period, "missing_tax_rate"))
                continue
            shield = paid_mag * (Decimal(1) - rate)
            used_paid = True
        if basis == "interest_excluded":
            _once(
                warnings,
                seen,
                "fcff_interest_excluded",
                {"metric": "fcff", "message": _EXCLUDED},
            )
        if capex_bad:
            _once(
                warnings, seen, "sign_mismatch", {"concept": "capex", "metric": "fcff"}
            )
        if paid_bad:
            _once(
                warnings,
                seen,
                "sign_mismatch",
                {"concept": "interest_paid", "metric": "fcff"},
            )
        inputs = ["operating_cash_flow", "capex"]
        if used_paid:
            inputs.extend(("income_tax_rate", "interest_paid"))
        # shortcut: след каталога не знает interest_paid. Ячейки уплаченных процентов лежат в components. Поднять, когда след принимает привязку без concept_id.
        row = _blank(period, None)
        row["value"] = _money(ocf_value + shield - capex_mag)
        row["status"] = "computed"
        row["inputs"] = inputs
        row["components"] = _components(
            facts,
            period,
            aligned,
            ocf,
            capex,
            rate_row if used_paid else None,
            paid if used_paid else None,
            rate_periods if used_paid and "*" in table else None,
        )
        rows.append(row)
    status = (
        "succeeded"
        if any(item["status"] == "computed" for item in rows)
        else "not_computed"
    )
    return {
        "metric": "fcff",
        "rows": rows,
        "needs_input": [],
        "warnings": warnings,
        "status": status,
    }


def _basis(ocf: dict, bindings: list[dict], absent: frozenset[str]) -> str:
    rows = _interest_rows(bindings, absent)
    coded = [row for row in rows if _stated_digits(row) == "4123"]
    if _stated_digits(ocf) == "4100" and coded:
        return "interest_included"
    if rows and not coded and all(_financing(row) for row in rows):
        return "interest_excluded"
    if _formula_candidate(ocf):
        return "candidate"
    return "unknown"


def _interest_rows(bindings: list[dict], absent: frozenset[str]) -> list[dict]:
    found = []
    for row in bindings:
        if (
            row.get("effective_concept") != "interest"
            or row.get("status") not in _BOUND
        ):
            continue
        if "interest" in absent and row.get("source") not in HUMAN_SOURCES:
            continue
        if _output_sheet(row):
            continue
        found.append(row)
    return found


def _financing(row: dict) -> bool:
    text = _section(row).casefold()
    return any(phrase in text for phrase in _FINANCING_SECTION)


def _section(row: dict) -> str:
    # shortcut: раздел ОДДС — только родитель в label_path_text. Заголовок выше родителя не виден. Поднять, когда привязка хранит раздел отчёта.
    path = row.get("label_path_text")
    if not isinstance(path, str):
        return ""
    parts = [part.strip() for part in path.split(" › ") if part.strip()]
    return parts[-2] if len(parts) > 1 else ""


def _formula_candidate(ocf: dict) -> bool:
    # shortcut: базис по графу читает только текст formula на привязке OCF. Ссылки на ячейки без имени понятия базис не задают. Поднять, когда в расчёт приходят понятия предшественников.
    text = ocf.get("formula")
    if not isinstance(text, str) or not text.strip():
        return False
    folded = text.casefold()
    mentions_income = (
        "net_income" in folded
        or "чистая прибыль" in folded
        or "чистой прибыли" in folded
    )
    mentions_interest = "interest" in folded or "процент" in folded
    return mentions_income and not mentions_interest


def _candidate_block(facts, accrued, paid, period, aligned) -> str | None:
    if paid is None or accrued is None:
        return (
            "interest_paid_unconfirmed" if paid is None else "interest_accrual_cash_gap"
        )
    paid_value = _at(facts, paid, period, aligned)
    accrued_value = _at(facts, accrued, period, aligned)
    if (
        paid_value is None
        or accrued_value is None
        or not _close(abs(paid_value), abs(accrued_value))
    ):
        return "interest_accrual_cash_gap"
    return None


def _rates(facts: list[dict], binding: dict, aligned: dict) -> tuple[dict, list[dict]]:
    by_key: dict = {}
    sources: list[dict] = []
    for fact in facts:
        if fact.get("row_key") != binding.get("row_key"):
            continue
        number = _figure(fact)
        if number is None:
            continue
        if number < 0 or number > 1:
            number = None
        axis, pid = fact.get("axis_id"), fact.get("period_id")
        key = aligned.get((axis, pid), (axis, pid))
        previous = by_key.get(key, number)
        if key in by_key and (
            previous is None or number is None or not _close(previous, number)
        ):
            by_key[key] = None
        else:
            by_key[key] = number
        sources.append({"axis_id": axis, "period_id": pid})
    usable = [value for value in by_key.values() if value is not None]
    if (
        usable
        and len(usable) == len(by_key)
        and all(_close(item, usable[0]) for item in usable)
    ):
        return {"*": usable[0]}, sources
    return by_key, sources


def _rate_for(table: dict, aligned: dict, period: dict) -> Decimal | None:
    if not table:
        return None
    if "*" in table:
        return table["*"]
    key = aligned.get(
        (period["axis_id"], period["period_id"]),
        (period["axis_id"], period["period_id"]),
    )
    value = table.get(key)
    return value if isinstance(value, Decimal) else None


def _ocf_periods(facts: list[dict], binding: dict, periods: list[dict]) -> list[dict]:
    have = set()
    for fact in facts:
        if fact.get("row_key") == binding.get("row_key") and _figure(fact) is not None:
            have.add((fact.get("axis_id"), fact.get("period_id")))
    ordered = []
    seen = set()
    for period in periods:
        key = (period.get("axis_id"), period.get("period_id"))
        if key in have and key not in seen:
            ordered.append(period)
            seen.add(key)
    return ordered


def _at(
    facts: list[dict], binding: dict, period: dict, aligned: dict
) -> Decimal | None:
    wanted = aligned.get(
        (period["axis_id"], period["period_id"]),
        (period["axis_id"], period["period_id"]),
    )
    total = None
    for fact in facts:
        if fact.get("row_key") != binding.get("row_key"):
            continue
        key = aligned.get(
            (fact.get("axis_id"), fact.get("period_id")),
            (fact.get("axis_id"), fact.get("period_id")),
        )
        if key != wanted:
            continue
        number = _figure(fact)
        if number is None:
            continue
        total = number if total is None else total + number
    return total


def _cells(facts: list[dict], binding: dict, period: dict, aligned: dict) -> list[str]:
    wanted = aligned.get(
        (period["axis_id"], period["period_id"]),
        (period["axis_id"], period["period_id"]),
    )
    found = []
    for fact in facts:
        if fact.get("row_key") != binding.get("row_key"):
            continue
        key = aligned.get(
            (fact.get("axis_id"), fact.get("period_id")),
            (fact.get("axis_id"), fact.get("period_id")),
        )
        if key != wanted:
            continue
        cell = fact.get("cell_id")
        if cell and str(cell) not in found:
            found.append(str(cell))
    return found


def _components(facts, period, aligned, ocf, capex, rate_row, paid, rate_span) -> dict:
    named = {
        "operating_cash_flow": _cells(facts, ocf, period, aligned),
        "capex": _cells(facts, capex, period, aligned),
    }
    if rate_row is not None:
        span = rate_span or [period]
        cells: list[str] = []
        for item in span:
            for cell in _cells(facts, rate_row, item, aligned):
                if cell not in cells:
                    cells.append(cell)
        named["income_tax_rate"] = cells
    if paid is not None:
        named["interest_paid"] = _cells(facts, paid, period, aligned)
    return named


def _outflow(value: Decimal, convention: str) -> tuple[Decimal, bool]:
    expected_negative = convention != "outflow_positive"
    mismatch = value != 0 and (value < 0) != expected_negative
    return abs(value), mismatch


def _once(warnings: list[dict], seen: set[str], code: str, params: dict) -> None:
    key = code if code != "sign_mismatch" else f"{code}:{params.get('concept')}"
    if key in seen:
        return
    seen.add(key)
    warnings.append({"code": code, "params": params})


def _money(value: Decimal) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 38
        ctx.rounding = "ROUND_HALF_EVEN"
        return value.quantize(MONEY)


def _blank(period: dict, reason: str | None) -> dict:
    return {
        "metric": "fcff",
        "axis_id": period["axis_id"],
        "period_id": period["period_id"],
        "period_key_base": period.get("period_key_base"),
        "period_marker": period.get("period_marker"),
        "value": None,
        "status": "not_computed",
        "reason": reason,
    }


def _missing(subject: str) -> dict:
    return {
        "metric": "fcff",
        "rows": [],
        "needs_input": [
            {"kind": "concept", "reason": "concept_unknown", "subject": subject}
        ],
        "warnings": [],
        "status": "missing_input",
    }
