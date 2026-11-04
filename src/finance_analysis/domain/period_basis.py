"""Способ показа периода у fact-строки (§5.5.2).

У строки, которая не `ytd` и не `ltm`, способ показа — `period`.
`ytd` ставится по заголовку или по формуле этой же строки, которая
прибавляет предыдущую ячейку и сбрасывается в начале года. Явный заголовок
сильнее формулы: формула его не отменяет. Форма ряда основанием не служит.
`unknown` здесь не ставится: это обычный исход для строки без признака,
и каскад считает его сильнее `ytd`.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from decimal import Decimal

from finance_analysis.domain.glossary import label_features, label_scan

_YTD = ("нарастающим итогом", "накопленным итогом", "с начала года")
_LTM = ("last 12 months", "за 12 месяцев")
_LTM_WORD = re.compile(r"(?<!\w)ltm(?!\w)")
_GRAIN_MONTHS = {"year": 12, "model_year": 12, "half": 6, "half_year": 6, "quarter": 3, "month": 1}


def classify_period_basis(
    row: dict,
    *,
    calendar: dict | None,
    links: list[dict] | None,
    series: dict | None,
    facts: list[dict] | None = None,
) -> tuple[str, str]:
    """Возвращает способ показа и источник: `label`, `header`, `formula` или `default`.

    `row` — fact-строка. `calendar` сопоставляет `(axis_id, period_id)` с зерном,
    датами и текстом заголовка колонки.     `links` — рёбра графа формул. `series` — значения строки, чтобы заголовок
    колонки читался только там, где есть число. `facts` добавляет в карту
    ячейку введённого числа: у неё есть `cell_id`, но нет формулы.
    """

    label = str(row.get("label") or "")
    if _label_ltm(label):
        return "ltm", "label"
    row_header = _row_header(row)
    columns = _column_headers(series, calendar)
    # Заголовок листа, раздела или согласованных колонок сильнее любой формулы.
    if _phrase_ytd(row_header) or _columns_agree(columns, _phrase_ytd):
        return "ytd", "header"
    if _phrase_ltm(row_header) or _columns_agree(columns, _phrase_ltm):
        return "ltm", "header"
    if _label_forces_period(label):
        return "period", "default"
    if _ltm_formula(row, links, calendar, series, facts):
        return "ltm", "formula"
    if _ytd_formula(row, links, calendar, series, facts):
        return "ytd", "formula"
    return "period", "default"


def basis_of(binding: dict) -> tuple[str, str]:
    """Читает способ показа из `evidence` или из `evidence_json` привязки."""

    evidence = binding.get("evidence")
    if not isinstance(evidence, dict):
        raw = binding.get("evidence_json")
        if isinstance(raw, str) and raw:
            try:
                loaded = json.loads(raw)
            except json.JSONDecodeError:
                loaded = {}
            evidence = loaded if isinstance(loaded, dict) else {}
        else:
            evidence = {}
    return str(evidence.get("period_basis") or "period"), str(evidence.get("period_basis_source") or "")


def restate_series(totals: dict[tuple, Decimal], binding: dict, periods: list[dict], aligned: dict) -> dict[tuple, Decimal]:
    """Переводит нарастающий итог в значение за период.

    Вычитание делается только если способ показа поставлен по заголовку или
    по формуле этой же строки. В начале года ряд не вычитается из прошлого
    года: формула в этот момент сбрасывается. Если предыдущий период того же
    года пуст, текущий период из ряда убирается, а не вычитается из более
    раннего значения. Строка `ltm` и строка `period` возвращаются как есть.
    Ряд без такого источника не пересчитывается.
    """

    basis, source = basis_of(binding)
    if basis != "ytd" or source not in {"header", "formula"}:
        return totals
    result = dict(totals)
    by_axis: dict[str, list[dict]] = {}
    for period in periods:
        by_axis.setdefault(str(period.get("axis_id") or ""), []).append(period)
    for items in by_axis.values():
        ordered = sorted(items, key=lambda item: item.get("period_index") or 0)
        previous_year = None
        previous_raw = None
        previous_present = False
        for period in ordered:
            own = (period.get("axis_id"), period.get("period_id"))
            key = aligned.get(own, own)
            year = _year_of(period)
            present = key in totals
            same_year = year is not None and year == previous_year
            if present and same_year and previous_present and previous_raw is not None:
                result[key] = totals[key] - previous_raw
            elif present and same_year and not previous_present:
                result.pop(key, None)
            if year is not None:
                previous_year = year
            if present:
                previous_raw = totals[key]
                previous_present = True
            else:
                previous_raw = None
                previous_present = False
    return result


def keys_for_basis(keys: list, binding: dict) -> list:
    """Оставляет конец окна у строки `ltm`, чтобы четыре квартала не складывались."""

    if keys and basis_of(binding)[0] == "ltm":
        return [keys[-1]]
    return list(keys)


def grain_span(grain: str | None) -> int | None:
    """Длина одного периода в месяцах. Неизвестный grain длину не имеет."""

    return _GRAIN_MONTHS.get(str(grain or "").lower())


def covered_months(series: dict, calendar: dict | None) -> tuple[str | None, int]:
    """Возвращает зерно строки и число покрытых месяцев.

    Зерно одно на все периоды, где у строки есть значение. Смешанное зерно
    или отсутствие дат дают пустое зерно: такие строки шаг покрытия не сравнивает.
    Месяц считается по `period_start` и `period_end`, включая оба конца.
    """

    if not calendar:
        return None, 0
    grains: set[str] = set()
    months: set[tuple[int, int]] = set()
    for key in series:
        meta = calendar.get(key)
        if not meta:
            continue
        grain = str(meta.get("grain") or "").lower()
        if grain:
            grains.add(grain)
        start = _as_date(meta.get("period_start"))
        end = _as_date(meta.get("period_end"))
        if start is None or end is None or end < start:
            continue
        months |= _month_span(start, end)
    if len(grains) != 1 or not months:
        return None, 0
    return next(iter(grains)), len(months)


def _label_forces_period(label: str) -> bool:
    """Хвост «за квартал» или «за период» оставляет `period`. Формула его не отменяет."""

    feature = label_features(label).period
    if not feature or _phrase_ltm(feature):
        return False
    folded = label_scan(feature)
    tails = {label_scan(item) for item in ("за кв.", "за кв", "за квартал", "за период", "за год")}
    return folded in tails


def _label_ltm(label: str) -> bool:
    feature = label_features(label).period
    if feature and _phrase_ltm(feature):
        return True
    return _phrase_ltm(label)


def _phrase_ltm(text: str) -> bool:
    folded = label_scan(text)
    if any(phrase in folded for phrase in _LTM):
        return True
    return _LTM_WORD.search(folded) is not None


def _phrase_ytd(text: str) -> bool:
    folded = label_scan(text)
    return any(phrase in folded for phrase in _YTD)


def _row_header(row: dict) -> str:
    """Заголовок листа и раздела. Колонка сюда не входит: она относится только к себе."""

    parts = [row.get("sheet"), row.get("parent_label")]
    parts.extend(_path(row))
    return " ".join(str(part) for part in parts if part)


def _column_headers(series: dict | None, calendar: dict | None) -> list[str]:
    headers = []
    for key in series or {}:
        meta = (calendar or {}).get(key) or {}
        headers.append(str(meta.get("header_text") or ""))
    return headers


def _columns_agree(headers: list[str], phrase) -> bool:
    """Способ показа колонки ставится строке, только если все числовые колонки совпали."""

    if not headers or any(not text for text in headers):
        return False
    return all(phrase(text) for text in headers)


def _path(row: dict) -> list[str]:
    path = row.get("label_path")
    if isinstance(path, list):
        return [str(item) for item in path]
    raw = row.get("label_path_json")
    if not isinstance(raw, str) or not raw:
        return []
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(loaded, list):
        return [str(item) for item in loaded]
    return []


def _ltm_formula(
    row: dict,
    links: list[dict] | None,
    calendar: dict | None,
    series: dict | None,
    facts: list[dict] | None = None,
) -> bool:
    """Скользящая сумма последних четырёх кварталов или двенадцати месяцев.

    Полное окно требуется с той колонки, где уже есть четыре квартала или
    двенадцать месяцев. Более ранние колонки могут складывать более короткий
    префикс той же строки или одной строки-источника. Хотя бы одно полное окно
    переходит через границу года и не сбрасывается в январе.
    """

    if not links or not calendar:
        return False
    grain, keys = _period_keys(series, calendar)
    width = {"quarter": 4, "month": 12}.get(grain or "")
    if not width or not keys:
        return False
    located = _located(links, facts)
    by_period = _formulas_by_period(links, str(row.get("row_key") or ""))
    crossed = False
    for axis, period_id in keys:
        order = _axis_order(calendar, axis)
        ids = [item[1] for item in order]
        if str(period_id) not in ids:
            return False
        index = ids.index(str(period_id))
        if index + 1 < width:
            expected = ids[: index + 1]
        else:
            expected = ids[index + 1 - width : index + 1]
        formulas = by_period.get(str(period_id)) or []
        if not any(_matches_window(formula, located, expected) for formula in formulas):
            return False
        if len(expected) < width:
            continue
        years = {_year_of(meta) for _index, pid, meta in order if pid in expected}
        years.discard(None)
        if len(years) >= 2:
            crossed = True
    return crossed


def _ytd_formula(
    row: dict,
    links: list[dict] | None,
    calendar: dict | None,
    series: dict | None,
    facts: list[dict] | None = None,
) -> bool:
    """Нарастающий итог по формуле этой строки или одной строки-источника.

    Либо каждый период после первого в году прибавляет предыдущую ячейку, либо
    формула складывает периоды с начала этого года и в следующем году начинается
    заново. Одной такой ячейки мало. Копирование предыдущей ячейки без сложения —
    перенос остатка или штопор, а не нарастающий итог.
    """

    if not links or not calendar:
        return False
    grain, keys = _period_keys(series, calendar)
    if not grain or not keys:
        return False
    row_key = str(row.get("row_key") or "")
    located = _located(links, facts)
    by_period = _formulas_by_period(links, row_key)
    if _copies_previous(by_period, row_key, located, calendar):
        return False
    if _running_add(by_period, row_key, located, calendar, keys):
        return True
    return _prefix_sum(by_period, located, calendar, keys)


def _running_add(by_period, row_key: str, located: dict, calendar: dict, keys: set[tuple]) -> bool:
    """Каждый период после первого в году прибавляет предыдущую ячейку этой строки."""

    wanted = {(str(axis), str(period_id)) for axis, period_id in keys}
    by_axis: dict[str, list[tuple[int, str, dict]]] = {}
    for (axis, period_id), meta in calendar.items():
        if (str(axis), str(period_id)) not in wanted:
            continue
        by_axis.setdefault(str(axis), []).append((int(meta.get("period_index") or 0), str(period_id), meta))
    qualified = False
    for items in by_axis.values():
        items.sort()
        order = [period_id for _index, period_id, _meta in items]
        previous = {period_id: order[index - 1] for index, period_id in enumerate(order) if index}
        years: dict[object, list[str]] = {}
        for _index, period_id, meta in items:
            year = _year_of(meta)
            if year is None:
                continue
            years.setdefault(year, []).append(period_id)
        for period_ids in years.values():
            if len(period_ids) < 2:
                continue
            flags = [
                _adds_previous(by_period.get(period_id) or [], row_key, previous.get(period_id), located)
                for period_id in period_ids
            ]
            if flags[0] or not all(flags[1:]):
                return False
            qualified = True
    return qualified


def _prefix_sum(by_period: dict, located: dict, calendar: dict, keys: set[tuple]) -> bool:
    """Сумма с начала года по одной строке. Следующий год эту сумму не продолжает."""

    by_axis: dict[str, list[str]] = {}
    for axis, period_id in keys:
        by_axis.setdefault(str(axis), []).append(str(period_id))
    qualified = False
    for axis, period_ids in by_axis.items():
        order = _axis_order(calendar, axis)
        years: dict[object, list[str]] = {}
        for period_id in period_ids:
            meta = next((meta for _index, pid, meta in order if pid == period_id), None)
            year = _year_of(meta) if meta else None
            if year is None:
                return False
            years.setdefault(year, []).append(period_id)
        for year, ids in years.items():
            year_ids = [pid for _index, pid, meta in order if _year_of(meta) == year]
            grew = False
            for period_id in ids:
                if period_id not in year_ids:
                    return False
                prefix = year_ids[: year_ids.index(period_id) + 1]
                formulas = by_period.get(period_id) or []
                matched = any(_matches_window(formula, located, prefix) for formula in formulas)
                if len(prefix) < 2:
                    continue
                if not matched:
                    return False
                grew = True
            if grew:
                qualified = True
            elif len(ids) >= 2:
                return False
    return qualified


def _matches_window(formula: dict, located: dict, expected: list[str]) -> bool:
    """Ссылки формулы — ровно эти периоды одной строки, без посторонних ячеек."""

    if not _sums_formula(formula):
        return False
    rows: set[str] = set()
    periods: list[str] = []
    for ref in formula["refs"]:
        target = located.get(ref)
        if target is None:
            return False
        rows.add(str(target[0]))
        periods.append(str(target[1]))
    if len(rows) != 1:
        return False
    return sorted(periods) == sorted(expected)


def _axis_order(calendar: dict, axis: str) -> list[tuple[int, str, dict]]:
    items = []
    for (found, period_id), meta in calendar.items():
        if str(found) != str(axis):
            continue
        items.append((int(meta.get("period_index") or 0), str(period_id), meta))
    items.sort()
    return items


def _adds_previous(formulas: list[dict], row_key: str, prior: str | None, located: dict) -> bool:
    """Формула прибавляет предыдущую ячейку. Голая ссылка на неё сложением не считается."""

    if not prior:
        return False
    for formula in formulas:
        if not _sums_formula(formula):
            continue
        if any(located.get(ref) == (row_key, prior) for ref in formula["refs"]):
            return True
    return False


def _copies_previous(by_period: dict, row_key: str, located: dict, calendar: dict) -> bool:
    """Копирование предыдущей ячейки без сложения — остаток или штопор."""

    by_axis: dict[str, list[str]] = {}
    ranked = sorted(calendar.items(), key=lambda item: (str(item[0][0]), int(item[1].get("period_index") or 0)))
    for (axis, period_id), _meta in ranked:
        by_axis.setdefault(str(axis), []).append(str(period_id))
    previous: dict[str, str] = {}
    for period_ids in by_axis.values():
        for index, period_id in enumerate(period_ids):
            if index:
                previous[period_id] = period_ids[index - 1]
    for period_id, formulas in by_period.items():
        prior = previous.get(str(period_id))
        if not prior:
            continue
        for formula in formulas:
            if _sums_formula(formula):
                continue
            if any(located.get(ref) == (row_key, prior) for ref in formula["refs"]):
                return True
    return False


def _period_keys(series: dict | None, calendar: dict | None) -> tuple[str | None, set[tuple]]:
    """Зерно и ключи колонок, в которых у строки есть число. Смешанное зерно пусто."""

    if not series or not calendar:
        return None, set()
    grouped: dict[str, set[tuple]] = {}
    for key in series:
        meta = calendar.get(key) or {}
        grain = str(meta.get("grain") or "").lower()
        if not grain:
            return None, set()
        grouped.setdefault(grain, set()).add(key)
    if len(grouped) != 1:
        return None, set()
    grain, keys = next(iter(grouped.items()))
    return grain, keys


def _formulas_by_period(links: list[dict], row_key: str) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for formula in _formulas(links, row_key).values():
        grouped.setdefault(str(formula.get("period_id") or ""), []).append(formula)
    return grouped


def _formulas(links: list[dict], row_key: str) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for link in links:
        if str(link.get("row_key") or "") != row_key:
            continue
        cell = str(link.get("cell") or "")
        item = found.setdefault(
            cell,
            {
                "formula": link.get("formula"),
                "formula_class": link.get("formula_class"),
                "period_id": link.get("period_id"),
                "refs": set(),
            },
        )
        if link.get("ref_cell"):
            item["refs"].add(str(link["ref_cell"]))
    return found


def _located(links: list[dict] | None, facts: list[dict] | None = None) -> dict[str, tuple[str, str]]:
    """Ячейка → строка и период. Введённое число берётся из факта, формула — из связи."""

    found: dict[str, tuple[str, str]] = {}
    for fact in facts or []:
        cell = fact.get("cell_id")
        row_key = fact.get("row_key")
        period_id = fact.get("period_id")
        if cell and row_key and period_id:
            found[str(cell)] = (str(row_key), str(period_id))
    for link in links or []:
        cell = link.get("cell")
        row_key = link.get("row_key")
        period_id = link.get("period_id")
        if cell and row_key and period_id:
            found[str(cell)] = (str(row_key), str(period_id))
    return found


def _sums_formula(formula: dict) -> bool:
    text = str(formula.get("formula") or "").casefold()
    kind = str(formula.get("formula_class") or "").casefold()
    return "sum" in kind or "sum" in text or "+" in text


def _year_of(period: dict) -> int | None:
    year = period.get("calendar_year")
    if isinstance(year, int):
        return year
    start = _as_date(period.get("period_start"))
    if start is not None:
        return start.year
    return None


def _as_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _month_span(start: date, end: date) -> set[tuple[int, int]]:
    months: set[tuple[int, int]] = set()
    year, month = start.year, start.month
    last = (end.year, end.month)
    while (year, month) <= last:
        months.add((year, month))
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return months
