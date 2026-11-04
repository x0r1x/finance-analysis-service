"""Роль reference: строка только повторяет другую строку.

Формула из одной ссылки, та же ссылка со множителем масштаба и
вставленная копия значений — не новый факт. Модуль находит строку-источник
и не меняет статус привязки.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal

from finance_analysis.domain.model_type import sheet_name_key

# Относительный допуск 0,01 % и пол абсолютной единицы 1e-6.
# Ряд из одних нулей сюда не попадает: его снимает отдельное правило.
# Множитель ссылки — только 1, тысяча или миллион.
_RELATIVE = Decimal("0.0001")
_ABSOLUTE = Decimal("0.000001")
_UNIT_SCALE = frozenset({Decimal(1), Decimal(1000), Decimal(1_000_000)})
_UNIT_FACTORS = (Decimal(1000), Decimal(1_000_000))
_NUMBER = r"(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?"
_SHEET = r"(?:'(?:[^']|'')+'|[^\s'!][^'!]*)"
_A1 = re.compile(
    rf"^=?\s*(?:(?P<sheet>{_SHEET})!)?"
    rf"\$?(?P<col>[A-Za-z]{{1,3}})\$?(?P<row>\d+)"
    rf"(?:\s*(?P<op>[*/])\s*(?P<num>{_NUMBER}))?\s*$"
)
_R1C1 = re.compile(
    rf"^=?\s*(?:(?P<sheet>{_SHEET})!)?"
    rf"R(?:\[(?P<rrel>-?\d+)\]|(?P<rabs>\d+))"
    rf"C(?:\[(?P<crel>-?\d+)\]|(?P<cabs>\d+))?"
    rf"(?:\s*(?P<op>[*/])\s*(?P<num>{_NUMBER}))?\s*$",
    re.IGNORECASE,
)
_CELL = re.compile(
    rf"^(?:(?P<sheet>{_SHEET})!)?\$?(?P<col>[A-Za-z]{{1,3}})\$?(?P<row>\d+)$"
)


def formula_reference(
    formula: str | None,
    *,
    default_sheet: str,
    origin_row: int | None = None,
) -> tuple[str, int] | None:
    """Возвращает лист и номер строки, если формула только повторяет одну ячейку.

    `formula` — текст формулы A1 или R1C1. `default_sheet` — лист самой
    строки, если в формуле лист не назван. `origin_row` — номер строки
    формулы; он нужен для относительной ссылки R1C1. Допускается умножение
    или деление только на 1, 1000 или 1 000 000. Множитель 1,1 или 10 даёт
    `None`. Сумма, функция и ссылка на две ячейки тоже дают `None`.
    """

    text = str(formula or "").strip()
    if not text:
        return None
    matched = _A1.fullmatch(text)
    if matched:
        row_number = int(matched.group("row"))
    else:
        matched = _R1C1.fullmatch(text)
        if matched is None:
            return None
        if matched.group("rabs"):
            row_number = int(matched.group("rabs"))
        elif origin_row is None or matched.group("rrel") is None:
            return None
        else:
            row_number = int(origin_row) + int(matched.group("rrel"))
    if row_number < 1 or not _scale_ok(matched.group("op"), matched.group("num")):
        return None
    return _sheet_name(matched.group("sheet"), default_sheet), row_number


def link_target(
    row: dict,
    links: list[dict] | None,
    cells: dict[tuple[str, int], str],
) -> str | None:
    """Возвращает `row_key` источника, если вся строка — одна ссылка.

    `row` — строка книги. `links` — связи графа этой строки: у каждой
    ячейки своя формула и список ссылок. `cells` сопоставляет лист и номер
    строки с `row_key`. Если хотя бы одна ячейка не является ссылкой на ту
    же строку, метод возвращает `None`. Ссылка на саму строку тоже
    возвращает `None`.
    """

    if _has_exceptions(row):
        return None
    own = str(row.get("row_key") or "")
    grouped = list(links or [])
    if grouped:
        found: set[str] = set()
        for link in grouped:
            target = _one_link(link, row, cells)
            if target is None or target == own:
                return None
            found.add(target)
        if len(found) == 1:
            return next(iter(found))
        return None
    formula = row.get("formula")
    if not formula:
        return None
    parsed = formula_reference(
        str(formula),
        default_sheet=str(row.get("sheet") or ""),
        origin_row=_origin_row(row),
    )
    if parsed is None:
        return None
    target = cells.get((sheet_name_key(parsed[0]), parsed[1]))
    if not target or target == own:
        return None
    return target


def values_match(source: dict, copy: dict) -> bool:
    """Совпадают ли значения копии с источником на всех её периодах.

    `source` и `copy` — словари период → число. Пустое пересечение периодов
    не является совпадением. Периоды копии должны быть подмножеством периодов
    источника: более длинный ряд не считается копией. Хотя бы одно общее
    значение должно быть ненулевым. Числа совпадают, если разница не больше
    0,01 % большего модуля и не меньше абсолютного пола 1e-6. Если прямой ряд
    не совпал, допускается один множитель 1000 или 1 000 000 в любую сторону.
    Нуль обязан остаться нулём.
    """

    overlap = set(source) & set(copy)
    if not overlap or not set(copy) <= set(source):
        return False
    pairs = [(_decimal(source[key]), _decimal(copy[key])) for key in copy]
    if not any(left != 0 or right != 0 for left, right in pairs):
        return False
    if all(_close(left, right) for left, right in pairs):
        return True
    for factor in _UNIT_FACTORS:
        if all(_unit_scaled(left, right, factor) for left, right in pairs):
            return True
    return False


def blank_series(series: dict | None) -> bool:
    """Нет ни одного числа, или каждое число равно нулю.

    `series` — значения строки по периодам. Пустой словарь тоже пустая
    строка. Ненулевое значение делает строку обычным кандидатом.
    """

    if not series:
        return True
    return all(_decimal(value) == 0 for value in series.values())


def _one_link(link: dict, row: dict, cells: dict[tuple[str, int], str]) -> str | None:
    origin = _cell_row(str(link.get("cell") or ""))
    default_sheet = origin[0] if origin else str(row.get("sheet") or "")
    origin_row = origin[1] if origin else _origin_row(row)
    parsed = formula_reference(
        str(link.get("formula") or ""),
        default_sheet=default_sheet,
        origin_row=origin_row,
    )
    if parsed is None:
        refs = [str(item) for item in (link.get("refs") or []) if item]
        if len(refs) != 1:
            return None
        parsed = _cell_address(refs[0], default_sheet)
        if parsed is None:
            return None
    return cells.get((sheet_name_key(parsed[0]), parsed[1]))


def _cell_address(text: str, default_sheet: str) -> tuple[str, int] | None:
    matched = _CELL.fullmatch(text.strip())
    if matched is None:
        return None
    return _sheet_name(matched.group("sheet"), default_sheet), int(matched.group("row"))


def _cell_row(cell: str) -> tuple[str, int] | None:
    if "!" not in cell:
        return None
    return _cell_address(cell, "")


def _origin_row(row: dict) -> int | None:
    number = row.get("row_num")
    if isinstance(number, bool) or not isinstance(number, int):
        return None
    return number


def _sheet_name(raw: str | None, default_sheet: str) -> str:
    if not raw:
        return default_sheet
    text = raw.strip()
    if len(text) >= 2 and text[0] == "'" and text[-1] == "'":
        text = text[1:-1].replace("''", "'")
    return text


def _scale_ok(op: str | None, number: str | None) -> bool:
    if op is None and number is None:
        return True
    if op not in {"*", "/"} or number is None:
        return False
    try:
        value = Decimal(number)
    except ArithmeticError:
        return False
    return value in _UNIT_SCALE


def _unit_scaled(source: Decimal, copied: Decimal, factor: Decimal) -> bool:
    if source == 0 or copied == 0:
        return source == 0 and copied == 0
    return _close(source * factor, copied) or _close(source, copied * factor)


def _close(left: Decimal, right: Decimal) -> bool:
    diff = abs(left - right)
    span = max(abs(left), abs(right), Decimal(1))
    return diff <= max(_ABSOLUTE, _RELATIVE * span)


def _decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _has_exceptions(row: dict) -> bool:
    raw = row.get("formula_exceptions_json")
    if raw in (None, "", "[]"):
        return False
    if isinstance(raw, list):
        return bool(raw)
    try:
        found = json.loads(str(raw))
    except json.JSONDecodeError:
        return True
    return bool(found)
