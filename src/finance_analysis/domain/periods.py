"""Даты периодов и классы маркеров (§4.8)."""

from __future__ import annotations

import calendar
import re
from collections.abc import Mapping, Sequence
from datetime import date, timedelta

from finance_analysis.domain.dictionaries import marker_token_sets

_MARKER_ATTRS = {
    "MARKER_ACTUAL": "actual",
    "MARKER_PLAN": "plan",
    "MARKER_ESTIMATE": "estimate",
}

_YEAR = re.compile(r"^(\d{4})$")
_QUARTER = re.compile(r"^(\d{4})Q([1-4])$")
_HALF = re.compile(r"^(\d{4})H([12])$")
_MONTH = re.compile(r"^(\d{4})-(\d{2})$")
_DAY = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_ANCHOR = re.compile(r"^([YQMP])(\d+)$", re.IGNORECASE)


def __getattr__(name: str):
    """MARKER_* — тонкие обёртки над dictionaries.yaml (через catalog loader)."""

    klass = _MARKER_ATTRS.get(name)
    if klass is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return marker_token_sets().get(klass, frozenset())


def split_period_key(period_key: str) -> tuple[str, str | None]:
    if "@" not in period_key:
        return period_key, None
    base, marker = period_key.split("@", 1)
    marker = marker.strip()
    return base, marker or None


def marker_class(
    marker: str | None,
    markers: Mapping[str, Sequence[str]] | None = None,
) -> str | None:
    """Класс маркера по словарю markers из glossary catalog / dictionaries.yaml.

    Без ``markers=`` — только default ``dictionaries_file()``. Alt-каталог:
    передайте ``markers=package.markers`` из ``load_catalog(custom_path)``.
    """

    if not marker:
        return None
    token = marker.casefold().strip()
    tables = marker_token_sets(markers)
    for klass in ("actual", "plan", "estimate"):
        if token in tables.get(klass, frozenset()):
            return klass
    return "other"


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def resolve_period_dates(
    period_key_base: str,
    *,
    calendar_year: int | None,
    start_date: date | None,
    end_date: date | None,
    previous_end: date | None,
) -> tuple[date | None, date | None, str]:
    """Возвращает (start, end, date_source). Маркер на даты не влияет."""

    if start_date is not None and end_date is not None:
        return start_date, end_date, "builder"
    base = period_key_base
    matched = _YEAR.fullmatch(base)
    if matched:
        year = int(matched.group(1))
        return date(year, 1, 1), date(year, 12, 31), "key"
    matched = _QUARTER.fullmatch(base)
    if matched:
        year, quarter = int(matched.group(1)), int(matched.group(2))
        start_month = 3 * (quarter - 1) + 1
        return date(year, start_month, 1), _month_end(year, start_month + 2), "key"
    matched = _HALF.fullmatch(base)
    if matched:
        year, half = int(matched.group(1)), int(matched.group(2))
        if half == 1:
            return date(year, 1, 1), date(year, 6, 30), "key"
        return date(year, 7, 1), date(year, 12, 31), "key"
    matched = _MONTH.fullmatch(base)
    if matched:
        year, month = int(matched.group(1)), int(matched.group(2))
        if 1 <= month <= 12:
            return date(year, month, 1), _month_end(year, month), "key"
    matched = _DAY.fullmatch(base)
    if matched:
        year, month, day = (int(matched.group(i)) for i in (1, 2, 3))
        try:
            end = date(year, month, day)
        except ValueError:
            return None, None, "none"
        start = previous_end + timedelta(days=1) if previous_end else end
        return start, end, "key"
    matched = _ANCHOR.fullmatch(base)
    if matched and calendar_year:
        kind, number = matched.group(1).upper(), int(matched.group(2))
        year = calendar_year
        if kind == "Y":
            return date(year, 1, 1), date(year, 12, 31), "anchor"
        if kind == "Q" and 1 <= number <= 4:
            start_month = 3 * (number - 1) + 1
            return date(year, start_month, 1), _month_end(year, start_month + 2), "anchor"
        if kind == "M" and 1 <= number <= 12:
            return date(year, number, 1), _month_end(year, number), "anchor"
        if kind == "P":
            return date(year, 1, 1), date(year, 12, 31), "anchor"
    return None, None, "none"


_RANGE_RE = re.compile(
    r"^(?:(?P<sheet>[^!]+)!)?(?P<a>\$?[A-Z]{1,3})(?P<ar>\$?\d+):(?P<b>\$?[A-Z]{1,3})(?P<br>\$?\d+)$",
    re.IGNORECASE,
)
_CELL_RE = re.compile(
    r"^(?:(?P<sheet>[^!]+)!)?(?P<col>\$?[A-Z]{1,3})(?P<row>\$?\d+)$",
    re.IGNORECASE,
)
_COL_RANGE_RE = re.compile(
    r"^(?:(?P<sheet>[^!]+)!)?(?P<a>\$?[A-Z]{1,3}):(?P<b>\$?[A-Z]{1,3})$",
    re.IGNORECASE,
)


def _col_index(letters: str) -> int:
    n = 0
    for ch in letters.upper().lstrip("$"):
        n = n * 26 + (ord(ch) - 64)
    return n


MAX_RANGE_CELLS = 50_000


def _col_letters(number: int) -> str:
    letters = ""
    n = number
    while n:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def split_cell(cell: str) -> tuple[str, int, int] | None:
    """`Лист!AB12` → (лист, номер колонки, номер строки); иначе None."""

    sheet, _, address = cell.rpartition("!")
    matched = _CELL_RE.fullmatch(address)
    if not sheet or not matched:
        return None
    return sheet, _col_index(matched.group("col")), int(matched.group("row").lstrip("$"))


def expand_ref(
    ref: str,
    *,
    default_sheet: str | None,
    used_rows: int,
    used_cols: int,
) -> tuple[list[str], bool]:
    """Разворачивает ссылку A1 или диапазон. Полные колонки режутся used range."""

    text = ref.strip()
    truncated = False
    matched = _CELL_RE.fullmatch(text)
    if matched and ":" not in text:
        sheet = matched.group("sheet") or default_sheet or ""
        return [f"{sheet}!{matched.group('col').lstrip('$').upper()}{matched.group('row').lstrip('$')}"], False
    matched = _RANGE_RE.fullmatch(text)
    if matched:
        sheet = matched.group("sheet") or default_sheet or ""
        c1, r1 = _col_index(matched.group("a")), int(matched.group("ar").lstrip("$"))
        c2, r2 = _col_index(matched.group("b")), int(matched.group("br").lstrip("$"))
        c1, c2 = sorted((c1, c2))
        r1, r2 = sorted((r1, r2))
        last_row = max(used_rows, 1)
        last_col = max(used_cols, 1)
        if r2 > last_row:
            r2 = last_row
            truncated = True
        if c2 > last_col:
            c2 = last_col
            truncated = True
        if r1 > r2 or c1 > c2:
            return [], True
        width = c2 - c1 + 1
        room = max(MAX_RANGE_CELLS // width, 1)
        if r2 - r1 + 1 > room:
            r2 = r1 + room - 1
            truncated = True
        cells = [
            f"{sheet}!{_col_letters(c)}{r}"
            for r in range(r1, r2 + 1)
            for c in range(c1, c2 + 1)
        ]
        return cells, truncated
    matched = _COL_RANGE_RE.fullmatch(text)
    if matched:
        sheet = matched.group("sheet") or default_sheet or ""
        c1, c2 = sorted((_col_index(matched.group("a")), _col_index(matched.group("b"))))
        last_row = max(used_rows, 1)
        last_col = max(used_cols, c2)
        if c2 - c1 > 64:
            c2 = c1 + 64
            truncated = True
        if last_row > 500:
            last_row = 500
            truncated = True
        cells = [
            f"{sheet}!{_col_letters(c)}{r}"
            for r in range(1, last_row + 1)
            for c in range(c1, min(c2, last_col) + 1)
        ]
        return cells, truncated or True
    return [text], False
