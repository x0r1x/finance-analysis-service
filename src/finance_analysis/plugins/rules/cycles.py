"""Правила по циклам и итеративным вычислениям (§6.1)."""

from __future__ import annotations

from dataclasses import dataclass

from finance_analysis.domain.audit import (
    ROWS_COUNTERS,
    ROWS_LINKS,
    AuditInput,
    Finding,
    Rule,
)


def _located(data: AuditInput, cycles: list[dict]) -> dict[str, tuple[str, ...]]:
    """Цикл R1 `{id, class, members}` → ячейки компоненты графа того же размера.

    В `/summary` у цикла только число ячеек. Сами ячейки FAS находит в
    `graph_links`; одинаковые по размеру циклы сопоставляются по порядку.
    Полная цепочка — trace builder в `…/findings/{fingerprint}`.
    """

    free = list(data.cycles)
    found: dict[str, tuple[str, ...]] = {}
    for cycle in cycles:
        size = cycle.get("members")
        match = next((members for members in free if len(members) == size), None)
        if match is not None:
            free.remove(match)
            found[str(cycle.get("id"))] = match
    return found


@dataclass(frozen=True)
class UnexpectedCycle(Rule):
    def check(self, data: AuditInput) -> list[Finding]:
        cycles = list(data.counters.get("cycles") or ())
        members = _located(data, cycles)
        findings = []
        for cycle in cycles:
            if cycle.get("class") != "unexpected":
                continue
            cells = members.get(str(cycle.get("id")), ())
            findings.append(
                self.finding(
                    data,
                    locations=[data.placed(cell) for cell in cells],
                    subject=f"cycle:{cycle.get('id')}",
                    params={"cycle_id": cycle.get("id"), "members": cycle.get("members"), "located": bool(cells)},
                )
            )
        return findings


@dataclass(frozen=True)
class IterativeCalcEnabled(Rule):
    def check(self, data: AuditInput) -> list[Finding]:
        if data.counters.get("iterate") is True:
            return [self.finding(data, params={"iterate": True})]
        return []


@dataclass(frozen=True)
class IterativeCycleWithoutIterate(Rule):
    def check(self, data: AuditInput) -> list[Finding]:
        cycles = data.counters.get("cycles") or ()
        if cycles and data.counters.get("iterate") is False:
            return [self.finding(data, params={"cycles": len(cycles), "iterate": False})]
        return []


UNEXPECTED_CYCLE = UnexpectedCycle(
    "unexpected_cycle", "1", "logic", "high", ("ICAEW avoid circular references",),
    "Непредусмотренная циклическая ссылка", ROWS_LINKS | ROWS_COUNTERS,
)
ITERATIVE_CALC_ENABLED = IterativeCalcEnabled(
    "iterative_calc_enabled", "1", "qualitative", "medium", ("ICAEW iterative calculation",),
    "Включены итеративные вычисления", ROWS_COUNTERS,
)
ITERATIVE_CYCLE_WITHOUT_ITERATE = IterativeCycleWithoutIterate(
    "iterative_cycle_without_iterate", "1", "mechanical", "high", (),
    "Цикл при выключенных итеративных вычислениях", ROWS_COUNTERS,
)
