"""Один шаблон формулы на ряд периода.

Сравнение идёт по R1C1 за один проход: второй проход принял бы уже
написанный R1C1 за новый адрес A1, и абсолютный диапазон разъехался бы
по столбцам. Блок кварталов одного года на годовой колонке схлопывается
в один токен, иначе годовая сумма кварталов выглядит новой формулой
каждый год.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from finance_analysis.domain.audit import AuditInput

_YEAR = re.compile(r"(?:19|20)\d{2}")
# Слева — граница токена. Иначе Revenue2025 даёт адрес e2025. MS-XLSX: name и A1-cell — разные продукции.
_REF = re.compile(
    r"(?<![A-Za-zА-Яа-яЁё0-9_])"
    r"(?:(?P<sheet>'(?:[^']|'')+'|[A-Za-zА-Яа-яЁё_][\w. ]*)!)?"
    r"(?P<abscol>\$)?(?P<col>[A-Za-z]{1,3})(?P<absrow>\$)?(?P<row>\d+)"
    r"(?::(?P<abscol2>\$)?(?P<col2>[A-Za-z]{1,3})(?P<absrow2>\$)?(?P<row2>\d+))?"
    r"(?![A-Za-z0-9_(])"
)
_STRING = re.compile(r'"(?:[^"]|"")*"')
_ADDR = re.compile(r"^(?:(?P<sheet>'[^']+'|[^!]+)!)?\$?(?P<col>[A-Za-z]{1,3})\$?(?P<row>\d+)$")
_ZERO = re.compile(r"0+(?:\.0+)?%?")


def column_number(letters: str) -> int:
    number = 0
    for char in letters.upper():
        number = number * 26 + ord(char) - 64
    return number


def parse_cell(address: str) -> tuple[str, int, int] | None:
    match = _ADDR.fullmatch(address.strip())
    if not match:
        return None
    sheet = match.group("sheet") or ""
    if sheet.startswith("'") and sheet.endswith("'"):
        sheet = sheet[1:-1].replace("''", "'")
    return sheet, column_number(match.group("col")), int(match.group("row"))


def _sheet_name(raw: str | None, host: str) -> str:
    if not raw:
        return host
    if raw.startswith("'"):
        return raw[1:-1].replace("''", "'")
    return raw


def _piece(col: int, row: int, abs_col: bool, abs_row: bool, host_col: int, host_row: int) -> str:
    column = f"C{col}" if abs_col else ("C" if col == host_col else f"C[{col - host_col}]")
    line = f"R{row}" if abs_row else ("R" if row == host_row else f"R[{row - host_row}]")
    return line + column


def normalize(
    formula: str | None,
    *,
    host_sheet: str,
    host_col: int,
    host_row: int,
    year_at,
    host_year: int | None,
) -> str:
    """R1C1 относительно ячейки-хозяина. Годовой блок кварталов — токен."""

    text = (formula or "").lstrip("=")
    blanks = _STRING.sub(lambda match: " " * len(match.group(0)), text)
    parts: list[str] = []
    last = 0
    for match in _REF.finditer(blanks):
        parts.append(text[last : match.start()])
        sheet = _sheet_name(match.group("sheet"), host_sheet)
        prefix = "" if sheet == host_sheet else (match.group("sheet") or "")
        left_col = column_number(match.group("col"))
        left_row = int(match.group("row"))
        if match.group("col2"):
            right_col = column_number(match.group("col2"))
            right_row = int(match.group("row2"))
            token = _year_token(sheet, left_col, right_col, left_row, right_row, year_at, host_year)
            if token:
                parts.append(token)
            else:
                left = _piece(left_col, left_row, bool(match.group("abscol")), bool(match.group("absrow")), host_col, host_row)
                right = _piece(right_col, right_row, bool(match.group("abscol2")), bool(match.group("absrow2")), host_col, host_row)
                parts.append(f"{prefix}{left}:{right}")
        else:
            parts.append(prefix + _piece(left_col, left_row, bool(match.group("abscol")), bool(match.group("absrow")), host_col, host_row))
        last = match.end()
    parts.append(text[last:])
    return "".join(parts)


def _year_token(sheet: str, left: int, right: int, row_a: int, row_b: int, year_at, host_year: int | None) -> str | None:
    if host_year is None or row_a != row_b or left == right:
        return None
    years = [year_at(sheet, col) for col in range(min(left, right), max(left, right) + 1)]
    if any(year is None for year in years):
        return None
    if all(year == host_year for year in years):
        return "«год»"
    if all(year == host_year - 1 for year in years):
        return "«прошлый год»"
    return None


def series_kind(pairs: list[tuple[int, str]]) -> str:
    """uniform, opening (только первая ячейка), segment (два сплошных), break."""

    if len(pairs) < 2:
        return "uniform"
    patterns = [pattern for _col, pattern in sorted(pairs)]
    if len(set(patterns)) == 1:
        return "uniform"
    if len(set(patterns[1:])) == 1 and patterns[0] != patterns[1]:
        return "opening"
    runs: list[str] = []
    for pattern in patterns:
        if not runs or runs[-1] != pattern:
            runs.append(pattern)
    if len(runs) != len(set(runs)):
        return "break"
    return "segment" if len(runs) == 2 else "break"


def additive_terms(formula: str | None) -> list[str]:
    """Слагаемые по обе стороны деления, на каждом уровне скобок."""

    text = (formula or "").lstrip("=")

    def split(chunk: str, ops: str) -> list[tuple[str, str]]:
        parts: list[tuple[str, str]] = []
        depth = 0
        buf: list[str] = []
        sign = "+"
        for char in chunk:
            if char == "(":
                depth += 1
            elif char == ")" and depth:
                depth -= 1
            if char in ops and depth == 0:
                parts.append((sign, "".join(buf).strip()))
                buf = []
                sign = char
            else:
                buf.append(char)
        if buf:
            parts.append((sign, "".join(buf).strip()))
        return parts

    def walk(chunk: str) -> list[str]:
        found: list[str] = []
        for _sign, side in split(chunk, "/"):
            for sign, term in split(side, "+-"):
                if not term or sign not in "+-":
                    continue
                if term.startswith("(") and term.endswith(")"):
                    found.extend(walk(term[1:-1]))
                else:
                    found.append(term)
        return found

    return walk(text)


_FN = re.compile(r"[A-Za-zА-Яа-яЁё_][\w.]*")
_NUM = re.compile(r"(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?%?")
# Знаки формулы. Двоеточие — оператор диапазона, не «где-то в тексте есть двоеточие».
_OP = frozenset("(),:;+-*/^=<>&%")


def _scan(body: str) -> list[tuple] | None:
    """Токены слагаемого. None — остался неразобранный кусок.

    Диапазон — один операнд (или две ссылки через «:»), как у openpyxl OPERAND/RANGE
    и formulas.tokens.operand.Range. IF и прочие функции сюда не входят.
    """

    tokens: list[tuple] = []
    index = 0
    while index < len(body):
        if body[index].isspace():
            index += 1
            continue
        if body[index] == '"':
            end = index + 1
            while end < len(body):
                if body[end] == '"':
                    if end + 1 < len(body) and body[end + 1] == '"':
                        end += 2
                        continue
                    end += 1
                    break
                end += 1
            else:
                return None
            tokens.append(("str", body[index:end]))
            index = end
            continue
        name = _FN.match(body, index)
        if name and name.end() < len(body) and body[name.end()] == "(":
            tokens.append(("fn", name.group(0).upper()))
            index = name.end()
            continue
        ref = _REF.match(body, index)
        if ref:
            tokens.append(("ref", ref))
            index = ref.end()
            continue
        number = _NUM.match(body, index)
        if number:
            tokens.append(("num", number.group(0)))
            index = number.end()
            continue
        if body[index] in _OP:
            tokens.append(("op", body[index]))
            index += 1
            continue
        return None
    return tokens


def _box(tokens: list[tuple]) -> tuple | None:
    """('cell', ref) или ('box', start, end). Иная форма — None."""

    if len(tokens) == 1 and tokens[0][0] == "num":
        return ("num", tokens[0][1])
    if len(tokens) == 1 and tokens[0][0] == "ref":
        ref = tokens[0][1]
        return ("box", ref, ref) if ref.group("col2") else ("cell", ref)
    if _is_span(tokens):
        return ("box", tokens[0][1], tokens[2][1])
    if (
        len(tokens) == 4
        and tokens[0] == ("fn", "SUM")
        and tokens[1] == ("op", "(")
        and tokens[2][0] == "ref"
        and tokens[2][1].group("col2")
        and tokens[3] == ("op", ")")
    ):
        return ("box", tokens[2][1], tokens[2][1])
    if len(tokens) == 6 and tokens[0] == ("fn", "SUM") and tokens[1] == ("op", "(") and tokens[5] == ("op", ")") and _is_span(tokens[2:5]):
        return ("box", tokens[2][1], tokens[4][1])
    return None


def _is_span(tokens: list[tuple]) -> bool:
    return (
        len(tokens) == 3
        and tokens[0][0] == "ref"
        and not tokens[0][1].group("col2")
        and tokens[1] == ("op", ":")
        and tokens[2][0] == "ref"
        and not tokens[2][1].group("col2")
    )


def _corner(ref, which: str) -> tuple[int, int]:
    if which == "end" and ref.group("col2"):
        return column_number(ref.group("col2")), int(ref.group("row2"))
    return column_number(ref.group("col")), int(ref.group("row"))


def term_total(term: str, host_sheet: str, value_at) -> object | None:
    """Сумма кэша слагаемого. None — форма неизвестна или кэш неполон, это не ноль.

    Ноль только у константы 0, прямой ссылки на 0 и диапазона, где известна каждая ячейка.
    Пустая ячейка известна. Ячейки нет в facts_by_cell — диапазон не суммируется частично.
    """

    from decimal import Decimal

    tokens = _scan(term.strip())
    if tokens is None:
        return None
    shape = _box(tokens)
    if shape is None:
        return None
    if shape[0] == "num":
        return Decimal(0) if _ZERO.fullmatch(shape[1]) else None
    if shape[0] == "cell":
        ref = shape[1]
        return value_at(_sheet_name(ref.group("sheet"), host_sheet), int(ref.group("row")), column_number(ref.group("col")), False)
    start, end = shape[1], shape[2]
    sheet = _sheet_name(start.group("sheet"), host_sheet)
    other = _sheet_name(end.group("sheet"), host_sheet) if end.group("sheet") else sheet
    if other != sheet:
        return None
    left, right = _corner(start, "start"), _corner(end, "end")
    total = Decimal(0)
    for col in range(min(left[0], right[0]), max(left[0], right[0]) + 1):
        for row in range(min(left[1], right[1]), max(left[1], right[1]) + 1):
            number = value_at(sheet, row, col, True)
            if number is None:
                return None
            total += number
    return total


@dataclass(frozen=True)
class RowShape:
    row_key: str
    axis_id: str | None
    kind: str
    patterns: tuple[tuple[str, tuple[str, ...]], ...]
    cross: tuple[str, ...]
    prior: tuple[str, ...]
    zeros: tuple[tuple[str, str], ...]


def row_shapes(data: AuditInput) -> tuple[RowShape, ...]:
    cached = getattr(data, "_formula_shapes", None)
    if cached is not None:
        return cached
    built = tuple(_shapes(data))
    data._formula_shapes = built  # shortcut: повтор правил на том же входе не пересчитывает R1C1
    return built


def _shapes(data: AuditInput) -> list[RowShape]:
    years = _column_years(data.periods)
    period_year = _period_years(data.periods)
    numbers, blanks = _caches(data)

    def value_at(name, line, column, blank_zero=False):
        key = (name, line, column)
        if key in numbers:
            return numbers[key]
        if blank_zero and key in blanks:
            from decimal import Decimal

            return Decimal(0)
        return None

    grouped: dict[tuple[str, str | None], list] = {}
    for link in data.link_cells.values():
        if not link.row_key or not link.formula:
            continue
        fact = data.facts_by_cell.get(link.cell)
        # Вне факта оси это шапка. Итог на другой оси — свой RowShape, не шаблон периода.
        if fact is None:
            continue
        grouped.setdefault((link.row_key, fact.get("axis_id")), []).append(link)
    shapes: list[RowShape] = []
    for (row_key, axis_id), links in grouped.items():
        pairs: list[tuple[int, str]] = []
        by_pattern: dict[str, list[str]] = {}
        order: list[str] = []
        cross: list[str] = []
        prior: list[str] = []
        zeros: list[tuple[str, str]] = []
        for link in links:
            parsed = parse_cell(link.cell)
            if parsed is None:
                continue
            sheet, col, row = parsed
            if not sheet:
                sheet = _sheet_of(data, row_key)
            fact = data.facts_by_cell.get(link.cell)
            host_year = _host_year(link.period_id, fact, period_year)
            pattern = normalize(
                link.formula,
                host_sheet=sheet,
                host_col=col,
                host_row=row,
                year_at=lambda name, column, years=years: years.get((name, column)),
                host_year=host_year,
            )
            pairs.append((col, pattern))
            if pattern not in by_pattern:
                order.append(pattern)
                by_pattern[pattern] = []
            by_pattern[pattern].append(link.cell)
            if link.formula_class == "cross_period":
                cross.append(link.cell)
            elif link.formula_class == "rollforward":
                prior.append(link.cell)
            for term in additive_terms(link.formula):
                total = term_total(term, sheet, value_at)
                if total == 0:
                    zeros.append((link.cell, term[:80]))
                    break
        kind = series_kind(pairs)
        patterns = tuple((chr(ord("A") + index), tuple(by_pattern[pattern])) for index, pattern in enumerate(order))
        shapes.append(
            RowShape(
                row_key=row_key,
                axis_id=axis_id,
                kind=kind,
                patterns=patterns,
                cross=tuple(cross),
                prior=tuple(prior),
                zeros=tuple(zeros),
            )
        )
    return shapes


def _column_years(periods: list[dict]) -> dict[tuple[str, int], int]:
    found: dict[tuple[str, int], int] = {}
    for period in periods:
        sheet = _axis_sheet(period.get("axis_id") or "")
        col = period.get("col")
        year = _year_of_period(period)
        if sheet and isinstance(col, int) and year is not None and (sheet, col) not in found:
            found[(sheet, col)] = year
    return found


def _period_years(periods: list[dict]) -> dict[tuple[str, str], int]:
    found: dict[tuple[str, str], int] = {}
    for period in periods:
        year = _year_of_period(period)
        axis = period.get("axis_id")
        period_id = period.get("period_id")
        if axis and period_id and year is not None:
            found[(axis, period_id)] = year
    return found


def _year_of_period(period: dict) -> int | None:
    year = period.get("calendar_year")
    if isinstance(year, int):
        return year
    match = _YEAR.search(str(period.get("header_text") or period.get("period_key_base") or period.get("period_id") or ""))
    return int(match.group(0)) if match else None


def _host_year(period_id: str | None, fact: dict | None, period_year: dict[tuple[str, str], int]) -> int | None:
    match = _YEAR.search(str(period_id or ""))
    if match:
        return int(match.group(0))
    if fact is None:
        return None
    return period_year.get((fact.get("axis_id"), fact.get("period_id")))


def _caches(data: AuditInput) -> tuple[dict[tuple[str, int, int], object], set[tuple[str, int, int]]]:
    """Числа кэша и пустые ячейки. Ключа нет — ячейка неизвестна, не ноль."""

    from decimal import Decimal, InvalidOperation

    numbers: dict[tuple[str, int, int], object] = {}
    blanks: set[tuple[str, int, int]] = set()
    for cell, fact in data.facts_by_cell.items():
        parsed = parse_cell(cell)
        if parsed is None:
            continue
        sheet, col, row = parsed
        if not sheet:
            sheet = _sheet_of(data, fact.get("row_key") or "")
        if not sheet:
            continue
        status = fact.get("value_status")
        if status == "empty":
            blanks.add((sheet, row, col))
            continue
        if status not in {"cached", "zero_explicit"}:
            continue
        number = fact.get("value_dec")
        if number is None and fact.get("value_raw") not in (None, ""):
            try:
                number = Decimal(str(fact["value_raw"]))
            except InvalidOperation:
                number = None
        if number is not None:
            numbers[(sheet, row, col)] = number
    return numbers, blanks


def _axis_sheet(axis_id: str) -> str:
    return axis_id.split("!r", 1)[0] if "!r" in axis_id else axis_id


def _sheet_of(data: AuditInput, row_key: str) -> str:
    row = data.rows_by_key.get(row_key) or {}
    return str(row.get("sheet") or "")
