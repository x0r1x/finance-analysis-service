"""Корпоративный FCFF. Произведение (1 − t) считает этот модуль, не YAML.

fcff = operating_cash_flow + shield − capex.
Щит есть только когда проценты уже вычтены из выбранной строки OCF:
величина уплаченных процентов × (1 − ставка этого периода).
Нет строки OCF — из прибыли и амортизации её не собирать. Ставку 20% не подставлять.
Сверка пишет fcff_book_mismatch только по цитатам аргумента book.
Разбор коэффициентов цитату не ищет. Ячейка книги входом не является.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, localcontext

from finance_analysis.domain.metrics import (
    HUMAN_SOURCES,
    MONEY,
    _close,
    _figure,
    _output_sheet,
    _primaries,
    _stated_digits,
    _sums,
    aligned_keys,
    confirm_paid_interest,
    unconfirmed_scale,
)
from finance_analysis.domain.model_type import sheet_name_key
from finance_analysis.domain.period_basis import basis_of, keys_for_basis

_EXCLUDED = (
    "Операционный поток не уменьшен на проценты. "
    "FCFF посчитан как OCF − capex, без добавки процентов после налога."
)
_NO_ANNUAL = "Годовой FCFF не посчитан. Число книги не вход калькулятора."
_DIFFERS = "Годовой FCFF не совпал с числом книги."
_ADD_BACK = frozenset({"interest", "interest_paid"})
_BOUND = frozenset({"bound", "bound_with_warning"})
_FINANCING_SECTION = (
    "финансовая деятельность",
    "финансовой деятельности",
    "financing",
)
_GUARDED = ("operating_cash_flow", "capex")


def free_cash_flow(
    *,
    facts: list[dict],
    bindings: list[dict],
    periods: list[dict],
    sign_convention: str = "outflow_negative",
    absent: frozenset[str] = frozenset(),
    links: list[dict] | None = None,
    book: list[dict] | None = None,
    statement_sheets: frozenset[str] = frozenset(),
) -> dict:
    primaries = _primaries(bindings, absent)
    clash = _ambiguous_primary(bindings, absent)
    if clash:
        return _finish(_ambiguous(clash), [], periods, book)
    ocf = primaries.get("operating_cash_flow")
    capex = primaries.get("capex")
    if ocf is None:
        return _finish(_missing("operating_cash_flow"), [], periods, book)
    if capex is None:
        return _finish(_missing("capex"), [], periods, book)
    confirm_paid_interest(primaries, bindings, absent)
    paid = primaries.get("interest_paid")
    accrued = primaries.get("interest")
    if (
        accrued is not None
        and paid is not None
        and accrued.get("row_key") == paid.get("row_key")
    ):
        accrued = None
    watched = [ocf, capex]
    if paid is not None:
        watched.append(paid)
    if unconfirmed_scale(facts, watched):
        rows = [
            _blank(period, "scale_unconfirmed")
            for period in _ocf_periods(facts, ocf, periods)
        ]
        return _finish(
            {
                "metric": "fcff",
                "rows": rows,
                "needs_input": [],
                "warnings": [],
                "status": "not_computed",
            },
            rows,
            periods,
            book,
        )
    statement = frozenset(sheet_name_key(name) for name in statement_sheets)
    basis = _basis(ocf, bindings, absent, facts, links or [], statement)
    rate_row = primaries.get("income_tax_rate")
    aligned = aligned_keys(periods)
    ocf_flow = _flow(facts, ocf, aligned, periods)
    capex_flow = _flow(facts, capex, aligned, periods)
    paid_flow = _flow(facts, paid, aligned, periods) if paid is not None else {}
    accrued_flow = _flow(facts, accrued, aligned, periods) if accrued is not None else {}
    ocf_axes = {
        fact.get("axis_id")
        for fact in facts
        if fact.get("row_key") == ocf.get("row_key")
    }
    table, rate_periods = (
        _rates(facts, rate_row, aligned, ocf_axes) if rate_row else ({}, [])
    )
    warnings: list[dict] = []
    seen: set[str] = set()
    rows: list[dict] = []
    for period in _ocf_periods(facts, ocf, periods):
        ocf_value = _at(ocf_flow, period, aligned)
        capex_value = _at(capex_flow, period, aligned)
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
                blocked = _candidate_block(
                    accrued_flow, paid_flow, accrued, paid, period, aligned
                )
                if blocked:
                    rows.append(_blank(period, blocked))
                    continue
            if paid is None:
                rows.append(_blank(period, "interest_paid_unconfirmed"))
                continue
            paid_value = _at(paid_flow, period, aligned)
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
    return _finish(
        {
            "metric": "fcff",
            "rows": rows,
            "needs_input": [],
            "warnings": warnings,
            "status": status,
        },
        rows,
        periods,
        book,
    )


def _basis(
    ocf: dict,
    bindings: list[dict],
    absent: frozenset[str],
    facts: list[dict],
    links: list[dict],
    statement: frozenset[str],
) -> str:
    rows = _interest_rows(bindings, absent)
    coded = [row for row in rows if _stated_digits(row) == "4123"]
    if _on_statement(ocf, statement) and _stated_digits(ocf) == "4100" and coded:
        return "interest_included"
    if rows and not coded and all(_financing(row) for row in rows):
        return "interest_excluded"
    if _formula_candidate(ocf, bindings, absent, facts, links):
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


def _on_statement(row: dict, statement: frozenset[str]) -> bool:
    if not statement:
        return False
    sheet = row.get("sheet")
    if not isinstance(sheet, str) or not sheet.strip():
        key = row.get("row_key")
        sheet = key.split("|", 1)[0] if isinstance(key, str) and "|" in key else ""
    return bool(sheet) and sheet_name_key(str(sheet)) in statement


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


def _formula_candidate(
    ocf: dict,
    bindings: list[dict],
    absent: frozenset[str],
    facts: list[dict],
    links: list[dict],
) -> bool:
    # shortcut: ссылка без привязанного предшественника базис не задаёт и не отменяет. Поднять, когда у каждой ссылки есть строка.
    concepts = _precedent_concepts(ocf, bindings, absent, facts, links)
    if concepts:
        return "net_income" in concepts and not concepts & _ADD_BACK
    return _named_in_formula(ocf)


def _precedent_concepts(
    ocf: dict,
    bindings: list[dict],
    absent: frozenset[str],
    facts: list[dict],
    links: list[dict],
) -> set[str]:
    row_key = ocf.get("row_key")
    if not isinstance(row_key, str) or not links:
        return set()
    cell_row: dict[str, str] = {}
    for link in links:
        cell = link.get("cell")
        key = link.get("row_key")
        if isinstance(cell, str) and cell and isinstance(key, str) and key:
            cell_row.setdefault(cell, key)
    for fact in facts:
        cell = fact.get("cell_id")
        key = fact.get("row_key")
        if isinstance(cell, str) and cell and isinstance(key, str) and key:
            cell_row.setdefault(cell, key)
    bound: dict[str, set[str]] = {}
    for row in bindings:
        if row.get("status") not in _BOUND:
            continue
        key = row.get("row_key")
        concept = row.get("effective_concept")
        if not isinstance(key, str) or not isinstance(concept, str) or not concept:
            continue
        if concept in absent and row.get("source") not in HUMAN_SOURCES:
            continue
        bound.setdefault(key, set()).add(concept)
    found: set[str] = set()
    for link in links:
        if link.get("row_key") != row_key:
            continue
        ref = link.get("ref_cell")
        if not isinstance(ref, str) or not ref:
            continue
        target = cell_row.get(ref)
        if not target or target == row_key:
            continue
        found |= bound.get(target, set())
    return found


def _named_in_formula(ocf: dict) -> bool:
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


def _candidate_block(accrued_flow, paid_flow, accrued, paid, period, aligned) -> str | None:
    if paid is None or accrued is None:
        return (
            "interest_paid_unconfirmed" if paid is None else "interest_accrual_cash_gap"
        )
    paid_value = _at(paid_flow, period, aligned)
    accrued_value = _at(accrued_flow, period, aligned)
    if (
        paid_value is None
        or accrued_value is None
        or not _close(abs(paid_value), abs(accrued_value))
    ):
        return "interest_accrual_cash_gap"
    return None


def _rates(
    facts: list[dict],
    binding: dict,
    aligned: dict,
    ocf_axes: set,
) -> tuple[dict, list[dict]]:
    by_key: dict = {}
    sources: list[dict] = []
    # Ключ шкалы — (timeline, index), не ось. Общую ставку даёт только факт вне оси OCF.
    rate_on_ocf = False
    for fact in facts:
        if fact.get("row_key") != binding.get("row_key"):
            continue
        number = _figure(fact)
        if number is None:
            continue
        if number < 0 or number > 1:
            number = None
        axis, pid = fact.get("axis_id"), fact.get("period_id")
        if axis in ocf_axes:
            rate_on_ocf = True
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
        not rate_on_ocf
        and usable
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


def _flow(facts: list[dict], binding: dict, aligned: dict, periods: list[dict]) -> dict:
    """Та же сумма, что у остальных денежных метрик: нарастающий итог уже за период.

    Строка `ltm` не складывается по кварталам: остаётся конец её окна.
    """

    series = _sums(facts, binding, aligned, periods)
    if basis_of(binding)[0] != "ltm":
        return series
    by_axis: dict[str, list] = {}
    ordered = sorted(periods, key=lambda item: item.get("period_index") or 0)
    for period in ordered:
        own = (period.get("axis_id"), period.get("period_id"))
        key = aligned.get(own, own)
        if key not in series:
            continue
        bucket = by_axis.setdefault(str(period.get("axis_id") or ""), [])
        if key not in bucket:
            bucket.append(key)
    kept: set = set()
    for keys in by_axis.values():
        kept.update(keys_for_basis(keys, binding))
    return {key: series[key] for key in kept}


def _at(series: dict, period: dict, aligned: dict) -> Decimal | None:
    wanted = aligned.get(
        (period["axis_id"], period["period_id"]),
        (period["axis_id"], period["period_id"]),
    )
    value = series.get(wanted)
    return value if isinstance(value, Decimal) else None


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


def _finish(result: dict, rows: list[dict], periods: list[dict], book) -> dict:
    notes = _book_mismatch(rows, periods, book or [])
    if notes:
        result["warnings"] = [*result["warnings"], *notes]
    return result


def _book_mismatch(rows: list[dict], periods: list[dict], book: list[dict]) -> list[dict]:
    """Год сверки — сумма кварталов calendar_year. Нет годового числа — так и пишем."""

    if not book:
        return []
    notes = []
    for item in book:
        if not isinstance(item, dict):
            continue
        book_value = _book_figure(item.get("value"))
        if book_value is None:
            continue
        year = _year(item.get("calendar_year"))
        fas = _fas_for_year(rows, periods, year) if year is not None else None
        if fas is not None and _close(fas, book_value):
            continue
        cell = item.get("cell_id") or item.get("cell")
        notes.append(
            {
                "code": "fcff_book_mismatch",
                "params": {
                    "cell": None if cell is None else str(cell),
                    "book": book_value,
                    "fas": fas,
                    "calendar_year": year,
                    "message": _NO_ANNUAL if fas is None else _DIFFERS,
                },
            }
        )
    return notes


def _fas_for_year(rows: list[dict], periods: list[dict], year: int) -> Decimal | None:
    """Одна ось и одно зерно. Нет периода этой оси — годового числа нет."""

    period_of = {
        (period.get("axis_id"), period.get("period_id")): period for period in periods
    }
    located: list[tuple[dict, dict]] = []
    for row in rows:
        period = period_of.get((row.get("axis_id"), row.get("period_id")))
        if period is None or _year(period.get("calendar_year")) != year:
            continue
        located.append((period, row))
    scopes = {(period.get("axis_id"), period.get("grain")) for period, _row in located}
    if len(scopes) != 1:
        return None
    axis_id, grain = next(iter(scopes))
    needed: set[tuple] = set()
    for period in periods:
        if period.get("axis_id") != axis_id or period.get("grain") != grain:
            continue
        if _year(period.get("calendar_year")) != year:
            continue
        needed.add((axis_id, period.get("period_id")))
    got = {(period.get("axis_id"), period.get("period_id")) for period, _row in located}
    if got != needed or not needed:
        return None
    values: list[Decimal] = []
    for _period, row in located:
        value = row.get("value")
        if row.get("status") != "computed" or not isinstance(value, Decimal):
            return None
        values.append(value)
    if len(values) != len(needed):
        return None
    return _money(sum(values, Decimal(0)))


def _year(value) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _book_figure(value) -> Decimal | None:
    if isinstance(value, bool) or value is None or isinstance(value, float):
        return None
    if isinstance(value, Decimal):
        number = value
    elif isinstance(value, (int, str)):
        try:
            number = Decimal(value)
        except InvalidOperation:
            return None
    else:
        return None
    return _money(number)


def _ambiguous_primary(bindings: list[dict], absent: frozenset[str]) -> str | None:
    """Имя OCF или capex, если основных строк больше одной."""

    counts = {name: 0 for name in _GUARDED}
    for row in bindings:
        concept = row.get("effective_concept")
        if concept not in counts:
            continue
        if not (row.get("is_primary") and row.get("status") in _BOUND):
            continue
        if concept in absent and row.get("source") not in HUMAN_SOURCES:
            continue
        counts[concept] += 1
    for name in _GUARDED:
        if counts[name] > 1:
            return name
    return None


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


def _ambiguous(subject: str) -> dict:
    return {
        "metric": "fcff",
        "rows": [],
        "needs_input": [{"kind": "concept", "reason": "ambiguous", "subject": subject}],
        "missing_inputs": [subject],
        "warnings": [],
        "status": "needs_input",
    }
