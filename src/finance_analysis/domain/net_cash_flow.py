"""Чистый денежный поток на интервале: CFO + CFI + CFF.

Сумма уже подписанных чисел. Модуль не берётся. YAML сумму не исполняет.
Нет строки раздела — у интервала нет значения. Прочерк или пустая ячейка
помеченного итога 4100/4200/4300 на листе формы читается как ноль.
Строка 4400 — цитата аргумента book, не вход. Допуск сверки — одна единица
масштаба листа в тех единицах, в которых опубликована сумма.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, localcontext

from finance_analysis.domain.metrics import (
    _BOUND,
    HUMAN_SOURCES,
    MONEY,
    _figure,
    _one_scale,
    _primaries,
    _scale,
    _stated_digits,
    _stored_scale,
    _sums,
    aligned_keys,
    unconfirmed_scale,
)
from finance_analysis.domain.model_type import sheet_name_key
from finance_analysis.domain.period_basis import basis_of, keys_for_basis

DASH_NOTE = "прочерк на цитируемой строке формы"
_SECTIONS = (
    ("operating_cash_flow", "4100"),
    ("investing_cash_flow", "4200"),
    ("financing_cash_flow", "4300"),
)
_DASH_TEXT = frozenset({"", "-", "—", "–", "−"})


def net_cash_flow(
    *,
    facts: list[dict],
    bindings: list[dict],
    periods: list[dict],
    absent: frozenset[str] = frozenset(),
    book: list[dict] | None = None,
    statement_sheets: frozenset[str] = frozenset(),
) -> dict:
    statement = frozenset(sheet_name_key(name) for name in statement_sheets)
    clash = _ambiguous(bindings, absent)
    if clash:
        return _needs(clash)
    primaries = _primaries(bindings, absent)
    chosen: dict[str, dict] = {}
    for name, code in _SECTIONS:
        row = primaries.get(name)
        if row is None or not _accept(row, code, statement):
            return _missing(name)
        chosen[name] = row
    watched = list(chosen.values())
    if _scale_blocked(facts, watched):
        rows = [_blank(period, "scale_unconfirmed") for period in periods]
        return _with_book(
            {
                "metric": "ncf",
                "rows": rows,
                "needs_input": [],
                "warnings": [],
                "status": "not_computed",
            },
            rows,
            facts,
            watched,
            book,
        )
    aligned = aligned_keys(periods)
    series = {
        name: _flow(facts, row, aligned, periods) for name, row in chosen.items()
    }
    warnings: list[dict] = []
    seen: set[str] = set()
    rows = []
    for period in _periods_of(series, periods, aligned):
        parts: list[Decimal] = []
        dashed: list[str] = []
        hole = False
        for name, code in _SECTIONS:
            value = _at(series[name], period, aligned)
            if value is not None:
                parts.append(value)
                continue
            if _dash_period(facts, chosen[name], period, code, statement):
                parts.append(Decimal(0))
                dashed.append(name)
                continue
            hole = True
            break
        if hole:
            rows.append(_blank(period, "missing_input"))
            continue
        for name in dashed:
            _once(
                warnings,
                seen,
                "ncf_dashed_line",
                {"concept": name, "metric": "ncf", "message": DASH_NOTE},
            )
        row = _blank(period, None)
        row["value"] = _money(sum(parts, Decimal(0)))
        row["status"] = "computed"
        row["inputs"] = [name for name, _code in _SECTIONS]
        rows.append(row)
    status = (
        "succeeded"
        if any(item["status"] == "computed" for item in rows)
        else "not_computed"
    )
    return _with_book(
        {
            "metric": "ncf",
            "rows": rows,
            "needs_input": [],
            "warnings": warnings,
            "status": status,
        },
        rows,
        facts,
        watched,
        book,
    )


def dashed_lines(
    bindings: list[dict],
    facts: list[dict],
    statement_sheets: frozenset[str],
    absent: frozenset[str] = frozenset(),
) -> list[dict]:
    """Итоги разделов, у которых на форме есть прочерк. Для следа, не для суммы."""

    statement = frozenset(sheet_name_key(name) for name in statement_sheets)
    primaries = _primaries(bindings, absent)
    found = []
    for name, code in _SECTIONS:
        row = primaries.get(name)
        if row is None or not _accept(row, code, statement):
            continue
        if _stated_digits(row) != code or not _on_statement(row, statement):
            continue
        cells = tuple(
            str(fact["cell_id"])
            for fact in facts
            if fact.get("row_key") == row.get("row_key")
            and fact.get("cell_id")
            and _blank_fact(fact)
        )
        if not cells:
            continue
        found.append(
            {
                "concept": name,
                "binding_key": str(row.get("binding_key") or ""),
                "row_key": str(row.get("row_key") or ""),
                "cell_ids": cells,
            }
        )
    return found


def _accept(row: dict, code: str, statement: frozenset[str]) -> bool:
    digits = _stated_digits(row)
    if digits is None:
        return True
    return digits == code and _on_statement(row, statement)


def _on_statement(row: dict, statement: frozenset[str]) -> bool:
    if not statement:
        return False
    sheet = row.get("sheet")
    if not isinstance(sheet, str) or not sheet.strip():
        key = row.get("row_key")
        sheet = key.split("|", 1)[0] if isinstance(key, str) and "|" in key else ""
    return bool(sheet) and sheet_name_key(str(sheet)) in statement


def _dash_period(
    facts: list[dict],
    row: dict,
    period: dict,
    code: str,
    statement: frozenset[str],
) -> bool:
    if _stated_digits(row) != code or not _on_statement(row, statement):
        return False
    matched = [
        fact
        for fact in facts
        if fact.get("row_key") == row.get("row_key")
        and fact.get("axis_id") == period.get("axis_id")
        and fact.get("period_id") == period.get("period_id")
    ]
    if not matched:
        return True
    return all(_blank_fact(fact) for fact in matched)


def _blank_fact(fact: dict) -> bool:
    if _figure(fact) is not None:
        return False
    raw = fact.get("value")
    if raw is None:
        raw = fact.get("value_dec")
    if raw is None:
        return True
    return isinstance(raw, str) and raw.strip() in _DASH_TEXT


def _scale_blocked(facts: list[dict], bindings: list[dict]) -> bool:
    """Спор масштаба. Число листа без сырого значения спором не является."""

    if not unconfirmed_scale(facts, bindings):
        return False
    for binding in bindings:
        for fact in facts:
            if fact.get("row_key") != binding.get("row_key"):
                continue
            if _one_scale(fact) != "unconfirmed":
                continue
            raw = fact.get("value_dec")
            if raw is None:
                raw = fact.get("value")
            if raw in (None, ""):
                continue
            return True
    return False


def _flow(facts: list[dict], binding: dict, aligned: dict, periods: list[dict]) -> dict:
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


def _periods_of(series: dict[str, dict], periods: list[dict], aligned: dict) -> list[dict]:
    have: set = set()
    for values in series.values():
        have.update(values)
    ordered = []
    seen = set()
    for period in periods:
        key = aligned.get(
            (period.get("axis_id"), period.get("period_id")),
            (period.get("axis_id"), period.get("period_id")),
        )
        if key in have and key not in seen:
            ordered.append(period)
            seen.add(key)
    return ordered


def _at(series: dict, period: dict, aligned: dict) -> Decimal | None:
    key = aligned.get(
        (period.get("axis_id"), period.get("period_id")),
        (period.get("axis_id"), period.get("period_id")),
    )
    value = series.get(key)
    return value if isinstance(value, Decimal) else None


def _ambiguous(bindings: list[dict], absent: frozenset[str]) -> str | None:
    names = {name for name, _code in _SECTIONS}
    counts = {name: 0 for name in names}
    for row in bindings:
        concept = row.get("effective_concept")
        if concept not in counts:
            continue
        if not (row.get("is_primary") and row.get("status") in _BOUND):
            continue
        if concept in absent and row.get("source") not in HUMAN_SOURCES:
            continue
        counts[concept] += 1
    for name, _code in _SECTIONS:
        if counts[name] > 1:
            return name
    return None


def _sheet_unit(facts: list[dict], bindings: list[dict]) -> Decimal:
    """Одна единица листа в единицах опубликованной суммы.

    74 и 75 на листе в тысячах расходятся на единицу: это округление строк.
    Множитель масштаба становится допуском, только если сумма уже умножена на него.
    """

    multiplied: Decimal | None = None
    for binding in bindings:
        scale = _scale(_stored_scale(facts, binding))
        if scale is None or scale == 1:
            continue
        for fact in facts:
            if fact.get("row_key") != binding.get("row_key"):
                continue
            raw = fact.get("value_dec")
            if raw is None:
                raw = fact.get("value")
            try:
                raw_number = None if raw in (None, "") else Decimal(str(raw))
            except (InvalidOperation, ValueError):
                raw_number = None
            published = _figure(fact)
            if raw_number is None or published is None:
                continue
            if published == raw_number * scale and published != raw_number:
                multiplied = abs(scale)
    return multiplied if multiplied is not None else Decimal(1)


def _with_book(result, rows, facts, bindings, book) -> dict:
    notes = _book_mismatch(rows, facts, bindings, book or [])
    if notes:
        result["warnings"] = [*result["warnings"], *notes]
    return result


def _book_mismatch(rows, facts, bindings, book: list[dict]) -> list[dict]:
    # shortcut: одна цитата сверяется с суммой интервалов вызова, не с кварталом длинной оси. Поднять, когда сверка идёт по каждому периоду.
    computed = [
        row["value"]
        for row in rows
        if row.get("status") == "computed" and isinstance(row.get("value"), Decimal)
    ]
    fas = _money(sum(computed, Decimal(0))) if computed else None
    unit = _sheet_unit(facts, bindings)
    notes = []
    for item in book:
        if not isinstance(item, dict):
            continue
        book_value = _book_figure(item.get("value"))
        if book_value is None:
            continue
        if fas is not None and abs(fas - book_value) <= unit:
            continue
        cell = item.get("cell_id") or item.get("cell")
        notes.append(
            {
                "code": "ncf_book_mismatch",
                "params": {
                    "cell": None if cell is None else str(cell),
                    "book": book_value,
                    "fas": fas,
                    "message": "Сальдо книги разошлось с суммой трёх потоков.",
                },
            }
        )
    return notes


def _book_figure(value) -> Decimal | None:
    if isinstance(value, bool) or value is None or isinstance(value, float):
        return None
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return _money(number)


def _money(value: Decimal) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 38
        ctx.rounding = "ROUND_HALF_EVEN"
        return value.quantize(MONEY)


def _missing(subject: str) -> dict:
    return {
        "metric": "ncf",
        "rows": [],
        "needs_input": [{"kind": "concept", "reason": "concept_unknown", "subject": subject}],
        "warnings": [],
        "status": "missing_input",
    }


def _needs(subject: str) -> dict:
    return {
        "metric": "ncf",
        "rows": [],
        "needs_input": [{"kind": "concept", "reason": "ambiguous", "subject": subject}],
        "warnings": [],
        "status": "needs_input",
    }


def _blank(period: dict, reason: str | None) -> dict:
    return {
        "metric": "ncf",
        "axis_id": period.get("axis_id"),
        "period_id": period.get("period_id"),
        "period_key_base": period.get("period_key_base"),
        "period_marker": period.get("period_marker"),
        "value": None,
        "status": "not_computed",
        "reason": reason,
    }


def _once(warnings: list[dict], seen: set[str], code: str, params: dict) -> None:
    key = f"{code}:{params.get('concept')}"
    if key in seen:
        return
    seen.add(key)
    warnings.append({"code": code, "params": params})
