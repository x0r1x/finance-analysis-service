"""Арифметика над именами ячеек (§6.3). Только целые литералы."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from finance_analysis.domain.errors import InvalidArgument


@dataclass(frozen=True)
class Num:
    value: Decimal


@dataclass(frozen=True)
class Name:
    ident: str


@dataclass(frozen=True)
class Unary:
    op: str
    expr: object


@dataclass(frozen=True)
class Bin:
    op: str
    left: object
    right: object


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.i = 0

    def parse(self):
        node = self._expr()
        self._skip()
        if self.i != len(self.text):
            raise InvalidArgument("выражение разобрано не до конца")
        return node

    def _skip(self) -> None:
        while self.i < len(self.text) and self.text[self.i].isspace():
            self.i += 1

    def _expr(self):
        node = self._term()
        while True:
            self._skip()
            if self.i < len(self.text) and self.text[self.i] in "+-":
                op = self.text[self.i]
                self.i += 1
                node = Bin(op, node, self._term())
            else:
                break
        return node

    def _term(self):
        node = self._factor()
        while True:
            self._skip()
            if self.i < len(self.text) and self.text[self.i] in "*/":
                op = self.text[self.i]
                self.i += 1
                node = Bin(op, node, self._factor())
            else:
                break
        return node

    def _factor(self):
        self._skip()
        if self.i >= len(self.text):
            raise InvalidArgument("неожиданный конец выражения")
        ch = self.text[self.i]
        if ch == "-":
            self.i += 1
            return Unary("-", self._factor())
        if ch == "(":
            self.i += 1
            node = self._expr()
            self._skip()
            if self.i >= len(self.text) or self.text[self.i] != ")":
                raise InvalidArgument("нет закрывающей скобки")
            self.i += 1
            return node
        if ch.isalpha() or ch == "_":
            start = self.i
            self.i += 1
            while self.i < len(self.text) and (self.text[self.i].isalnum() or self.text[self.i] == "_"):
                self.i += 1
            return Name(self.text[start : self.i])
        if ch.isdigit():
            start = self.i
            while self.i < len(self.text) and self.text[self.i].isdigit():
                self.i += 1
            return Num(Decimal(self.text[start : self.i]))
        raise InvalidArgument(f"недопустимый символ {ch!r}")


def parse_expression(text: str):
    if not isinstance(text, str) or not text.strip():
        raise InvalidArgument("пустое выражение")
    return _Parser(text).parse()


def names_of(node) -> list[str]:
    found: list[str] = []

    def walk(item) -> None:
        if isinstance(item, Name):
            found.append(item.ident)
        elif isinstance(item, Unary):
            walk(item.expr)
        elif isinstance(item, Bin):
            walk(item.left)
            walk(item.right)

    walk(node)
    return found


def literals_of(node) -> list[str]:
    found: list[str] = []

    def walk(item) -> None:
        if isinstance(item, Num):
            found.append(str(item.value))
        elif isinstance(item, Unary):
            walk(item.expr)
        elif isinstance(item, Bin):
            walk(item.left)
            walk(item.right)

    walk(node)
    return found


def evaluate(node, bindings: dict[str, Decimal]) -> Decimal:
    if isinstance(node, Num):
        return node.value
    if isinstance(node, Name):
        if node.ident not in bindings:
            raise InvalidArgument(f"имя {node.ident} не связано")
        return bindings[node.ident]
    if isinstance(node, Unary):
        return -evaluate(node.expr, bindings)
    if isinstance(node, Bin):
        left = evaluate(node.left, bindings)
        right = evaluate(node.right, bindings)
        if node.op == "+":
            return left + right
        if node.op == "-":
            return left - right
        if node.op == "*":
            return left * right
        if node.op == "/":
            if right == 0:
                raise InvalidArgument("деление на ноль")
            return left / right
    raise InvalidArgument("неизвестная конструкция выражения")
