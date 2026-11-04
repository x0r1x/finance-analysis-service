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
# Знак формулы не входит в имя листа: иначе `=Notes!C10` читается как лист `=Notes`.
_SHEET = r"(?:'(?:[^']|'')+'|[^'\s!=+()*/,]+)"
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
_SUM = re.compile(r"\bSUM\s*\(", re.IGNORECASE)
_RANGE = re.compile(
    rf"(?:(?P<sheet>{_SHEET})!)?"
    rf"\$?(?P<c1>[A-Za-z]{{1,3}})\$?(?P<r1>\d+)\s*:\s*"
    rf"\$?(?P<c2>[A-Za-z]{{1,3}})\$?(?P<r2>\d+)"
)
_CELL_FIND = re.compile(
    rf"(?:(?P<sheet>{_SHEET})!)?\$?(?P<col>[A-Za-z]{{1,3}})\$?(?P<row>\d+)"
)


def formula_reference(
    formula: str | None,
    *,
    default_sheet: str,
    origin_row: int | None = None,
    origin_column: str | None = None,
) -> tuple[str, int] | None:
    """Возвращает лист и номер строки, если формула повторяет одну ячейку того же столбца.

    `formula` — текст формулы A1 или R1C1. `default_sheet` — лист самой
    строки, если в формуле лист не назван. `origin_row` — номер строки
    формулы; он нужен для относительной ссылки R1C1. `origin_column` —
    столбец ячейки формулы. Ссылка на другой столбец той же строки — это
    лаг, а не копия, и метод возвращает `None`. Допускается умножение или
    деление только на 1, 1000 или 1 000 000. Множитель 1,1 или 10 даёт
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
    if not _same_column(matched, origin_column):
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


def referenced_row(cell: str, *, default_sheet: str) -> tuple[str, int] | None:
    """Лист и номер строки по адресу ячейки.

    `cell` — адрес вроде `C10` или `Debt!C10`. `default_sheet` подставляется,
    если лист в адресе не назван. Неадрес возвращает `None`.
    """

    parsed = _cell_address(cell, default_sheet)
    if parsed is None:
        return None
    return parsed[0], parsed[1]


def summed_row_refs(formula: str | None, *, default_sheet: str) -> tuple[tuple[str, int], ...] | None:
    """Строки, которые формула складывает в итог.

    `formula` — текст формулы. `default_sheet` — лист строки, если в ссылке
    лист не назван. Сумма — это `SUM` или знак «+». Одна ссылка, произведение
    и множитель вроде 1,1 суммой не являются: метод возвращает `None`.
    Диапазон `C10:C12` раскрывается в строки 10, 11 и 12. Имя листа
    заканчивается перед знаком формулы, поэтому `=Notes!C10` указывает на
    лист `Notes`. Повтор одной строки в ответе не дублируется.
    """

    text = _strip_lookups(str(formula or "").strip())
    if not text or not (_SUM.search(text) or "+" in text):
        return None
    found: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    spans: list[tuple[int, int]] = []

    def add(sheet: str, number: int) -> None:
        item = (sheet, number)
        if number >= 1 and item not in seen:
            seen.add(item)
            found.append(item)

    for match in _RANGE.finditer(text):
        sheet = _sheet_name(match.group("sheet"), default_sheet)
        start, end = int(match.group("r1")), int(match.group("r2"))
        lo, hi = (start, end) if start <= end else (end, start)
        for number in range(lo, hi + 1):
            add(sheet, number)
        spans.append(match.span())
    for match in _CELL_FIND.finditer(text):
        if any(start <= match.start() < end for start, end in spans):
            continue
        add(_sheet_name(match.group("sheet"), default_sheet), int(match.group("row")))
    # Одна строка на нескольких периодах — свёртка во времени, а не сумма частей.
    if len(found) < 2:
        return None
    return tuple(found)


_LOOKUP = re.compile(r"(?i)\b(?:LEFT|RIGHT|MID|LEN|ЛЕВСИМВ|ПРАВСИМВ|ДЛСТР)\s*\(")


def _strip_lookups(text: str) -> str:
    """Убирает LEFT/LEN: ячейка номера квартала не является слагаемым."""

    while True:
        match = _LOOKUP.search(text)
        if match is None:
            return text
        end = _close_paren(text, match.end() - 1)
        if end is None:
            return text[: match.start()] + text[match.end() :]
        text = text[: match.start()] + text[end:]


def _close_paren(text: str, open_index: int) -> int | None:
    depth = 0
    for index in range(open_index, len(text)):
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                return index + 1
    return None


def values_match(source: dict, copy: dict) -> bool:
    """Совпадают ли значения копии с источником на всех её периодах.

    `source` и `copy` — словари период → число. Пустое пересечение периодов
    не является совпадением. Периоды копии должны быть подмножеством периодов
    источника: более длинный ряд не считается копией. Хотя бы одно общее
    значение должно быть ненулевым. Числа совпадают, если разница не больше
    0,01 % большего из двух модулей и не меньше абсолютного пола 1e-6. Для
    чисел меньше единицы пол не раздувается до 0,0001. Если прямой ряд
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
    formula = str(link.get("formula") or "")
    origin_column = _column_of(str(link.get("cell") or ""))
    if formula:
        parsed = formula_reference(
            formula,
            default_sheet=default_sheet,
            origin_row=origin_row,
            origin_column=origin_column,
        )
        if parsed is None:
            return None
        return cells.get((sheet_name_key(parsed[0]), parsed[1]))
    refs = [str(item) for item in (link.get("refs") or []) if item]
    if len(refs) != 1:
        return None
    parsed = _cell_address(refs[0], default_sheet)
    if parsed is None or not _columns_equal(parsed[2], origin_column):
        return None
    return cells.get((sheet_name_key(parsed[0]), parsed[1]))


def _cell_address(text: str, default_sheet: str) -> tuple[str, int, str] | None:
    matched = _CELL.fullmatch(text.strip())
    if matched is None:
        return None
    return _sheet_name(matched.group("sheet"), default_sheet), int(matched.group("row")), matched.group("col")


def _cell_row(cell: str) -> tuple[str, int] | None:
    if "!" not in cell:
        return None
    parsed = _cell_address(cell, "")
    if parsed is None:
        return None
    return parsed[0], parsed[1]


def _column_of(cell: str) -> str | None:
    parsed = _cell_address(cell, "")
    if parsed is None:
        return None
    return parsed[2]


def _same_column(matched: re.Match[str], origin_column: str | None) -> bool:
    if "col" in matched.re.groupindex:
        return _columns_equal(matched.group("col"), origin_column)
    relative = matched.group("crel")
    if relative is not None:
        return int(relative) == 0
    absolute = matched.group("cabs")
    if absolute is None:
        return True
    if not origin_column:
        return False
    return _column_number(origin_column) == int(absolute)


def _columns_equal(referenced: str | None, origin: str | None) -> bool:
    if not origin or not referenced:
        return True
    return referenced.casefold() == origin.casefold()


def _column_number(letters: str) -> int:
    number = 0
    for char in letters.upper():
        number = number * 26 + (ord(char) - ord("A") + 1)
    return number


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
    span = max(abs(left), abs(right))
    if span == 0:
        return True
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
