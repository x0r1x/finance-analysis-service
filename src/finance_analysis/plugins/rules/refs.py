"""Правила по ссылкам (§6.1): висячие, неразрешённые, внешние."""

from __future__ import annotations

from dataclasses import dataclass

from finance_analysis.domain.audit import (
    ROWS_COUNTERS,
    ROWS_LINKS,
    AuditInput,
    Finding,
    Rule,
    group_cells,
    grouped_finding,
)

REFS_SHOWN = 10


@dataclass(frozen=True)
class CounterRule(Rule):
    """Счётчик R1 `{count, ids}` → одна находка книги, `ids` — места.

    `dangling_classes` builder — ссылки на действительно пустые ячейки
    (`empty_ref`, `empty_range_member`, вне `dangling.count`). Это не ошибка,
    поэтому классы идут только в `params` находки по `dangling.count`.
    """

    counter: str = ""

    def extra(self, data: AuditInput) -> dict:
        if self.counter == "dangling" and isinstance(data.counters.get("dangling_classes"), dict):
            return {"dangling_classes": data.counters["dangling_classes"]}
        return {}

    def counted(self, data: AuditInput) -> tuple[int, list[str]]:
        counter = data.counters.get(self.counter)
        if not isinstance(counter, dict):
            return 0, []
        return int(counter.get("count") or 0), [str(item) for item in counter.get("ids") or []]

    def check(self, data: AuditInput) -> list[Finding]:
        count, ids = self.counted(data)
        if count <= 0:
            return []
        return [
            self.finding(
                data,
                locations=[data.placed(cell) for cell in ids],
                params={"count": count, **self.extra(data)},
                truncated=count > len(ids),
            )
        ]


@dataclass(frozen=True)
class ExternalRef(CounterRule):
    """Ссылки на внешнюю книгу: `graph.json links[].refs` вида `[книга]Лист!A1` и счётчик R1 `external`.

    Ячейки со ссылками из графа дают находки по строке и оси. Если счётчик R1
    больше числа таких ячеек, остаток — одна находка книги с `truncated`.
    """

    def check(self, data: AuditInput) -> list[Finding]:
        refs: dict[str, list[str]] = {}
        for cell, link in data.link_cells.items():
            outside = [ref for ref in link.refs if ref.startswith("[") or "]" in ref.split("!", 1)[0]]
            if outside:
                refs[cell] = outside
        findings = []
        for key, cells in group_cells(data.placed(cell) for cell in refs).items():
            found = sorted({ref for item in cells for ref in refs[item.cell_id or ""]})
            params = {"refs": found[:REFS_SHOWN], "distinct": len(found), "cells": len(cells)}
            findings.append(grouped_finding(self, data, key, cells, params=params))
        count, ids = self.counted(data)
        if count > len(refs):
            unlocated = [cell for cell in ids if cell not in refs]
            findings.append(
                self.finding(
                    data,
                    locations=[data.placed(cell) for cell in unlocated],
                    params={"count": count, "located": len(refs), "unlocated": count - len(refs)},
                    truncated=True,
                )
            )
        return findings


DANGLING_REF = CounterRule(
    "dangling_ref", "1", "mechanical", "high", (), "Ссылка на пустую или удалённую ячейку", ROWS_COUNTERS,
    counter="dangling",
)
UNRESOLVED_REF = CounterRule(
    "unresolved_ref", "1", "mechanical", "high", (), "Ссылка не разрешена", ROWS_COUNTERS, counter="unresolved",
)
EXTERNAL_REF = ExternalRef(
    "external_ref", "1", "qualitative", "medium", ("FAST 1.03-02", "FAST 1.03-04"),
    "Ссылка на внешнюю книгу", ROWS_LINKS | ROWS_COUNTERS, counter="external",
)
