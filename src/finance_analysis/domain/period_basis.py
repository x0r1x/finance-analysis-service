"""Способ показа периода у fact-строки (§5.5.2).

У строки, которая не `ytd` и не `ltm`, способ показа — `period`.
`ytd` ставится только по заголовку или по формуле этой же строки, которая
прибавляет предыдущую ячейку и сбрасывается в начале года. Форма ряда
основанием не служит. `unknown` здесь не ставится: это обычный исход для
строки без признака, и каскад считает его сильнее `ytd`.
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
    if _phrase_ltm(row_header) or _columns_agree(columns, _phrase_ltm):
        return "ltm", "header"
    if _ltm_formula(row, links, calendar, series, facts):
        return "ltm", "formula"
    if _phrase_ytd(row_header) or _columns_agree(columns, _phrase_ytd):
        return "ytd", "header"
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
    """Сумма четырёх кварталов ставит `ltm`, только если так устроена каждая колонка периода.

    Одна итоговая колонка года, которая складывает четыре квартала, строку не
    переводит. Колонки другого зерна в этот счёт не входят.
    """

    if not links or not calendar:
        return False
    grain, keys = _period_keys(series, calendar)
    if grain != "quarter" or not keys:
        return False
    located = _located(links, facts)
    by_period = _formulas_by_period(links, str(row.get("row_key") or ""))
    for key in keys:
        formulas = by_period.get(str(key[1])) or []
        if not any(_four_quarter_formula(formula, located, calendar) for formula in formulas):
            return False
    return True


def _four_quarter_formula(formula: dict, located: dict, calendar: dict) -> bool:
    if not _sums_formula(formula):
        return False
    metas = []
    for ref in formula["refs"]:
        target = located.get(ref)
        if target is None:
            continue
        meta = _meta_for(calendar, target[1])
        if meta is not None:
            metas.append(meta)
    return _four_quarters(metas)


def _four_quarters(metas: list[dict]) -> bool:
    spans: dict[tuple[date, date], None] = {}
    for meta in metas:
        if str(meta.get("grain") or "").lower() != "quarter":
            return False
        start = _as_date(meta.get("period_start"))
        end = _as_date(meta.get("period_end"))
        if start is None or end is None:
            return False
        spans[(start, end)] = None
    if len(spans) != 4:
        return False
    ordered = sorted(spans)
    months: set[tuple[int, int]] = set()
    for start, end in ordered:
        months |= _month_span(start, end)
    whole = _month_span(ordered[0][0], ordered[-1][1])
    return len(months) == 12 and months == whole


def _ytd_formula(
    row: dict,
    links: list[dict] | None,
    calendar: dict | None,
    series: dict | None,
    facts: list[dict] | None = None,
) -> bool:
    """Нарастающий итог по формуле: каждый период после первого в году прибавляет предыдущую ячейку.

    Одной такой ячейки мало. Копирование предыдущей ячейки без сложения — перенос
    остатка или штопор, а не нарастающий итог. Такая строка остаётся `period`,
    пока нарастающий итог не назван заголовком.
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


def _meta_for(calendar: dict, period_id: str) -> dict | None:
    for (_axis, key), meta in calendar.items():
        if str(key) == period_id:
            return meta
    return None


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
