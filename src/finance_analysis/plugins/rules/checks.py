"""Правила по проверочным строкам (§6.1)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from finance_analysis.domain.audit import ROWS, AuditInput, Finding, Location, Rule

_VALUED = frozenset({"cached", "zero_explicit"})


@dataclass(frozen=True)
class CheckFailure(Rule):
    """Сбой проверки — ненулевое значение в `check_row` (§6.1).

    Строка `check_row` без формулы (допуск, заголовок) — не проверка.
    """

    def check(self, data: AuditInput) -> list[Finding]:
        findings = []
        for row in data.rows:
            if not row.get("check_row") or not row.get("has_formula"):
                continue
            by_axis: dict[str, list[Location]] = {}
            for fact in data.facts_by_row.get(row["row_key"], ()):
                value = fact.get("value_dec")
                if fact["value_status"] not in _VALUED or value is None or Decimal(value) == 0:
                    continue
                by_axis.setdefault(fact["axis_id"], []).append(
                    Location(fact["cell_id"], row["row_key"], fact["axis_id"], fact["period_id"])
                )
            for axis_id, cells in by_axis.items():
                findings.append(
                    self.finding(
                        data,
                        locations=sorted(cells, key=lambda item: item.cell_id or ""),
                        row_key=row["row_key"],
                        axis_id=axis_id,
                        params={"nonzero_cells": len(cells), "label": row.get("label")},
                    )
                )
        return findings


@dataclass(frozen=True)
class NoMasterCheck(Rule):
    def check(self, data: AuditInput) -> list[Finding]:
        if any(row.get("check_row") for row in data.rows):
            return []
        return [self.finding(data, params={"check_rows": 0})]


CHECK_FAILURE = CheckFailure(
    "check_failure", "1", "quantitative", "critical", ("ICAEW include checks",),
    "Проверка книги не сходится", ROWS,
)
NO_MASTER_CHECK = NoMasterCheck(
    "no_master_check", "1", "qualitative", "info", ("ICAEW master check", "FAST 2.03-05"),
    "В книге нет проверочных строк", ROWS,
)
