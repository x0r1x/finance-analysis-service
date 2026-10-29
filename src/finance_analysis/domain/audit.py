"""Находки аудита, отпечаток и вход правил (§6.1).

Модуль чистый: без I/O. Правила получают `AuditInput` со строками
проекции и счётчиками R1 и возвращают `Finding`.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import cached_property

from finance_analysis.domain.book import SEP
from finance_analysis.domain.periods import split_period_key

SEVERITIES = ("info", "low", "medium", "high", "critical")
# Наборы входов правила (`Rule.requires`): планировщик грузит только их.
ROWS = frozenset({"rows", "periods", "facts"})
ROWS_LINKS = ROWS | {"links"}
ROWS_COUNTERS = ROWS | {"counters"}
# Правила фазы 2: знак строки из `row_semantics` (§5.4).
ROWS_SEMANTICS = ROWS | {"semantics"}
ERROR_CLASSES = frozenset({"mechanical", "logic", "omission", "quantitative", "qualitative"})
LOCATIONS_MAX = 32

_AXIS = re.compile(r"^(?P<sheet>.*)!r(?P<row>\d+)$")


def severity_rank(severity: str) -> int:
    return SEVERITIES.index(severity)


def fingerprint(code: str, subject: str, period_key_base: str, marker: str, axis_ordinal: str) -> str:
    """sha1(code › binding_key › period_key_base › marker › axis_ordinal), §6.1."""

    material = SEP.join([code, subject, period_key_base, marker, axis_ordinal])
    return hashlib.sha1(material.encode("utf-8")).hexdigest()


def axis_ordinals(axis_ids: Iterable[str]) -> dict[str, int]:
    """Номер оси среди осей своего листа по строке шапки.

    `axis_id` = `Лист!rN` смещается при вставке строк выше шапки, а порядок
    осей на листе нет. Ось вне шаблона получает номер по алфавиту.
    """

    by_sheet: dict[str, list[tuple[int, str]]] = {}
    for axis_id in set(axis_ids):
        matched = _AXIS.fullmatch(axis_id)
        sheet, row = (matched.group("sheet"), int(matched.group("row"))) if matched else (axis_id, 0)
        by_sheet.setdefault(sheet, []).append((row, axis_id))
    ordinals = {}
    for items in by_sheet.values():
        for ordinal, (_row, axis_id) in enumerate(sorted(items)):
            ordinals[axis_id] = ordinal
    return ordinals


@dataclass(frozen=True)
class Location:
    cell_id: str | None
    row_key: str | None
    axis_id: str | None
    period_id: str | None

    def as_dict(self) -> dict:
        return {
            "cell_id": self.cell_id,
            "row_key": self.row_key,
            "axis_id": self.axis_id,
            "period_id": self.period_id,
        }


@dataclass(frozen=True)
class Finding:
    code: str
    version: str
    error_class: str
    severity: str
    params: dict
    locations: tuple[Location, ...]
    fingerprint: str
    binding_key: str | None
    truncated: bool
    basis: tuple[str, ...]

    def as_dict(self, builder_ref: dict | None = None) -> dict:
        return {
            "code": self.code,
            "version": self.version,
            "error_class": self.error_class,
            "severity": self.severity,
            "params": self.params,
            "locations": [item.as_dict() for item in self.locations],
            "fingerprint": self.fingerprint,
            "binding_key": self.binding_key,
            "truncated": self.truncated,
            "builder_ref": builder_ref,
            "basis": list(self.basis),
        }


@dataclass(frozen=True)
class LinkCell:
    cell: str
    formula: str | None
    formula_class: str | None
    row_key: str | None
    period_id: str | None
    refs: tuple[str, ...]


@dataclass
class AuditInput:
    """Строки проекции сборки и счётчики R1 из manifest."""

    rows: list[dict] = field(default_factory=list)
    periods: list[dict] = field(default_factory=list)
    facts: list[dict] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)
    counters: dict = field(default_factory=dict)
    # Пустой список: правила коэффициентов молчат, отпечаток аудита не плывёт.
    bindings: list[dict] = field(default_factory=list)
    # `row_semantics` закреплённого состояния: знак, природа строки (§5.4).
    semantics: list[dict] = field(default_factory=list)
    # Состав понятий таксономии (`composition`, §5.1): debt_service → interest, principal.
    composition: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # Параметры профиля, которые меняют только вариант расчёта (§5.7).
    profile: dict = field(default_factory=dict)
    # Понятия с записью `concept.absent` в журнале книги (§5.10.5).
    absent: frozenset[str] = frozenset()

    @cached_property
    def rows_by_key(self) -> dict[str, dict]:
        return {row["row_key"]: row for row in self.rows}

    @cached_property
    def facts_by_cell(self) -> dict[str, dict]:
        found: dict[str, dict] = {}
        for fact in self.facts:
            found.setdefault(fact["cell_id"], fact)
        return found

    @cached_property
    def facts_by_row(self) -> dict[str, list[dict]]:
        grouped: dict[str, list[dict]] = {}
        for fact in self.facts:
            grouped.setdefault(fact["row_key"], []).append(fact)
        return grouped

    @cached_property
    def link_cells(self) -> dict[str, LinkCell]:
        refs: dict[str, list[str]] = {}
        first: dict[str, dict] = {}
        for link in self.links:
            cell = link.get("cell")
            if not cell:
                continue
            first.setdefault(cell, link)
            if link.get("ref_cell"):
                refs.setdefault(cell, []).append(link["ref_cell"])
        return {
            cell: LinkCell(
                cell=cell,
                formula=link.get("formula"),
                formula_class=link.get("formula_class"),
                row_key=link.get("row_key"),
                period_id=link.get("period_id"),
                refs=tuple(refs.get(cell, ())),
            )
            for cell, link in first.items()
        }

    @cached_property
    def cycles(self) -> list[tuple[str, ...]]:
        """Сильно связные компоненты графа формул: ячейки циклов, по возрастанию."""

        edges = {cell: [ref for ref in link.refs if ref in self.link_cells] for cell, link in self.link_cells.items()}
        return strongly_connected(edges)

    @cached_property
    def ordinals(self) -> dict[str, int]:
        return axis_ordinals([period["axis_id"] for period in self.periods])

    @cached_property
    def period_keys(self) -> dict[tuple[str, str], tuple[str, str]]:
        keys = {}
        for period in self.periods:
            base = period.get("period_key_base")
            marker = period.get("period_marker")
            if base is None:
                base, marker = split_period_key(period["period_id"])
            keys[(period["axis_id"], period["period_id"])] = (base, marker or "")
        return keys

    def placed(self, cell: str) -> Location:
        """Ячейка → строка, ось и период. Ячейка вне серий — только `row_key` связи."""

        fact = self.facts_by_cell.get(cell)
        if fact is not None:
            return Location(cell, fact["row_key"], fact["axis_id"], fact["period_id"])
        link = self.link_cells.get(cell)
        row_key = link.row_key if link and link.row_key in self.rows_by_key else None
        return Location(cell, row_key, None, None)


@dataclass(frozen=True)
class Rule:
    code: str
    version: str
    error_class: str
    severity: str
    basis: tuple[str, ...]
    title: str
    requires: frozenset[str]
    phase: int = 1

    def describe(self) -> dict:
        return {
            "code": self.code,
            "version": self.version,
            "error_class": self.error_class,
            "severity": self.severity,
            "basis": list(self.basis),
            "title": self.title,
            "requires": sorted(self.requires),
            "phase": self.phase,
        }

    def check(self, data: AuditInput) -> list[Finding]:
        raise NotImplementedError

    def finding(
        self,
        data: AuditInput,
        *,
        locations: Iterable[Location] = (),
        row_key: str | None = None,
        axis_id: str | None = None,
        period_id: str | None = None,
        subject: str | None = None,
        params: dict | None = None,
        severity: str | None = None,
        truncated: bool = False,
    ) -> Finding:
        """Отпечаток строится из `binding_key` строки, периода и номера оси.

        Находка уровня книги берёт вместо `binding_key` пустую строку или
        `subject` (номер цикла, ячейка вне строк книги).
        """

        located = list(locations)
        row = data.rows_by_key.get(row_key or "")
        binding = row["binding_key"] if row else None
        base, marker = ("", "")
        if axis_id is not None and period_id is not None:
            base, marker = data.period_keys.get((axis_id, period_id), split_period_key(period_id))
            marker = marker or ""
        ordinal = "" if axis_id is None else str(data.ordinals.get(axis_id, ""))
        print_ = fingerprint(self.code, binding or subject or "", base, marker, ordinal)
        if not located and (row_key or axis_id):
            located = [Location(None, row_key, axis_id, period_id)]
        return Finding(
            code=self.code,
            version=self.version,
            error_class=self.error_class,
            severity=severity or self.severity,
            params=params or {},
            locations=tuple(located[:LOCATIONS_MAX]),
            fingerprint=print_,
            binding_key=binding,
            truncated=truncated or len(located) > LOCATIONS_MAX,
            basis=self.basis,
        )


def strongly_connected(edges: dict[str, list[str]]) -> list[tuple[str, ...]]:
    """Тарьян без рекурсии. Компонента — цикл, если в ней ≥ 2 ячеек или петля."""

    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    found: list[tuple[str, ...]] = []
    counter = 0
    for root in sorted(edges):
        if root in index:
            continue
        work = [(root, iter(edges.get(root, ())))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, children = work[-1]
            advanced = False
            for child in children:
                if child not in index:
                    index[child] = low[child] = counter
                    counter += 1
                    stack.append(child)
                    on_stack.add(child)
                    work.append((child, iter(edges.get(child, ()))))
                    advanced = True
                    break
                if child in on_stack:
                    low[node] = min(low[node], index[child])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                members = []
                while True:
                    item = stack.pop()
                    on_stack.discard(item)
                    members.append(item)
                    if item == node:
                        break
                if len(members) > 1 or node in edges.get(node, ()):
                    found.append(tuple(sorted(members)))
    return sorted(found, key=lambda item: (len(item), item))


def group_cells(locations: Iterable[Location]) -> dict[tuple, list[Location]]:
    """Ячейки по (строка, ось). Ячейка вне строк книги — своя группа."""

    grouped: dict[tuple, list[Location]] = {}
    for location in locations:
        if location.row_key is None:
            key: tuple = ("cell", location.cell_id)
        else:
            key = ("row", location.row_key, location.axis_id)
        grouped.setdefault(key, []).append(location)
    return grouped


def grouped_finding(rule: Rule, data: AuditInput, key: tuple, cells: list[Location], **kwargs) -> Finding:
    ordered = sorted(cells, key=lambda item: item.cell_id or "")
    if key[0] == "cell":
        return rule.finding(data, locations=ordered, subject=f"cell:{key[1]}", **kwargs)
    return rule.finding(data, locations=ordered, row_key=key[1], axis_id=key[2], **kwargs)
