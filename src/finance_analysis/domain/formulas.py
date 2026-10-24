"""Разбор текста формулы A1 для правил фазы 1 (§6.1).

Полного парсера Excel здесь нет. Токенизатор отделяет строки, ссылки,
имена и функции от числовых литералов. Этого хватает для литералов,
функций и глубины вложенных `IF`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

_TOKEN = re.compile(
    r"""
    (?P<string>"(?:[^"]|"")*")
  | (?P<sheet>'(?:[^']|'')+'!|\[[^\]]*\][^!]*!|[A-Za-z_][A-Za-z0-9_.]*!)
  | (?P<cols>\$?[A-Za-z]{1,3}:\$?[A-Za-z]{1,3}(?![A-Za-z0-9_(]))
  | (?P<rows>\$?\d+:\$?\d+)
  | (?P<function>[A-Za-z_][A-Za-z0-9_.]*(?=\())
  | (?P<cell>\$?[A-Za-z]{1,3}\$?\d+(?![A-Za-z0-9_(.]))
  | (?P<name>[A-Za-z_\\][A-Za-z0-9_.\\]*)
  | (?P<number>(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?%?)
  | (?P<open>\()
  | (?P<close>\))
    """,
    re.VERBOSE,
)

# Универсальные константы не считаются литералами (FAST 3.04-01, ICAEW).
UNIVERSAL = frozenset(
    Decimal(value)
    for value in ("0", "1", "2", "4", "7", "12", "24", "52", "100", "360", "365", "366", "1000", "1000000")
)


@dataclass(frozen=True)
class FormulaFacts:
    literals: tuple[str, ...]
    functions: frozenset[str]
    operands: int
    if_depth: int
    chars: int


def _literal(text: str) -> Decimal | None:
    percent = text.endswith("%")
    raw = text[:-1] if percent else text
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    return value / 100 if percent else value


def _canonical(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def analyze(formula: str | None) -> FormulaFacts:
    text = (formula or "").lstrip("=")
    literals: list[str] = []
    functions: set[str] = set()
    operands = 0
    stack: list[str] = []
    depth = 0
    pending: str | None = None
    for match in _TOKEN.finditer(text):
        kind = match.lastgroup
        token = match.group()
        if kind == "function":
            pending = token.upper()
            functions.add(pending)
            continue
        if kind == "open":
            stack.append(pending or "")
            pending = None
            depth = max(depth, sum(1 for item in stack if item == "IF"))
            continue
        pending = None
        if kind == "close":
            if stack:
                stack.pop()
        elif kind in {"cell", "cols", "rows", "name"}:
            operands += 1
        elif kind == "number":
            value = _literal(token)
            if value is not None:
                operands += 1
                if value not in UNIVERSAL:
                    literals.append(_canonical(value))
    return FormulaFacts(
        literals=tuple(literals),
        functions=frozenset(functions),
        operands=operands,
        if_depth=depth,
        chars=len(text),
    )


_STRING = re.compile(r'"(?:[^"]|"")*"')
_COMPARISON = re.compile(r"<>|<=|>=|<|>|=")


def top_level_comparison(formula: str | None) -> bool:
    """Формула целиком — сравнение (`=A1-B1<0.01`): результат TRUE/FALSE.

    Сравнение внутри функции (`=IF(A1<>0,1,0)`) не считается.
    """

    text = _STRING.sub('""', (formula or "").lstrip("="))
    depth = 0
    outer = []
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif depth == 0:
            outer.append(char)
    return bool(_COMPARISON.search("".join(outer)))
