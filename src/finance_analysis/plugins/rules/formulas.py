"""Правила по формулам (§6.1): константы, литералы, шаблон строки, кэш, функции.

Правилам не нужны понятия, поэтому они выполняются на любой книге (§5.10.5).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal

from finance_analysis.domain.audit import (
    ROWS,
    ROWS_COUNTERS,
    ROWS_LINKS,
    AuditInput,
    Finding,
    Location,
    Rule,
    default_finding_kind,
    group_cells,
    grouped_finding,
)
from finance_analysis.domain.formulas import FormulaFacts, analyze

_VALUED = frozenset({"cached", "zero_explicit"})
LONG_FORMULA_CHARS = 120
LONG_FORMULA_OPERANDS = 12
LITERALS_SHOWN = 10


@dataclass(frozen=True)
class FormulaRule(Rule):
    """Правило по тексту формулы: одна находка на строку и ось."""

    def match(self, facts: FormulaFacts) -> dict | None:
        raise NotImplementedError

    def check(self, data: AuditInput) -> list[Finding]:
        matched: dict[str, dict] = {}
        for cell, link in data.link_cells.items():
            found = self.match(analyze(link.formula))
            if found is not None:
                matched[cell] = found
        findings = []
        for key, cells in group_cells(data.placed(cell) for cell in matched).items():
            merged = self.merge([matched[item.cell_id] for item in cells if item.cell_id])
            findings.append(grouped_finding(self, data, key, cells, params=merged))
        return findings

    def merge(self, matches: list[dict]) -> dict:
        return {"cells": len(matches)}


@dataclass(frozen=True)
class HardcodedFormula(Rule):
    """Константа в строке формул (§6.1, входы `formula_class` и `formula_exceptions`).

    Строка формул — строка, у ячеек которой на этой оси есть `formula_class`
    (класс формулы из `graph.json`). Константа — ячейка этой строки со значением
    и без формулы. Ячейки из `formula_exceptions` — формулы с другим шаблоном,
    это `formula_inconsistent_in_row`, а не константа.
    """

    def check(self, data: AuditInput) -> list[Finding]:
        findings = []
        links = data.link_cells
        for row in data.rows:
            exceptions = set(row.get("formula_exceptions") or ())
            by_axis: dict[str, list[dict]] = {}
            for fact in data.facts_by_row.get(row["row_key"], ()):
                by_axis.setdefault(fact["axis_id"], []).append(fact)
            for axis_id, facts in by_axis.items():
                classes = Counter(
                    links[fact["cell_id"]].formula_class
                    for fact in facts
                    if fact["cell_id"] in links and links[fact["cell_id"]].formula_class
                )
                if not classes:
                    continue
                for fact in facts:
                    cell = fact["cell_id"]
                    if fact["value_status"] not in _VALUED or cell in links or cell in exceptions:
                        continue
                    findings.append(
                        self.finding(
                            data,
                            locations=[Location(cell, row["row_key"], axis_id, fact["period_id"])],
                            row_key=row["row_key"],
                            axis_id=axis_id,
                            period_id=fact["period_id"],
                            params={
                                "row_formula": row.get("formula"),
                                "formula_class": classes.most_common(1)[0][0],
                                "value": fact.get("value_raw"),
                            },
                        )
                    )
        return findings


@dataclass(frozen=True)
class LiteralInFormula(FormulaRule):
    def match(self, facts: FormulaFacts) -> dict | None:
        if not facts.literals:
            return None
        return {"literals": facts.literals}

    def check(self, data: AuditInput) -> list[Finding]:
        findings = []
        for finding in super().check(data):
            if finding.params.get("varies"):
                severity = "medium"
                kind = self.finding_kind or default_finding_kind(finding.error_class, severity)
                finding = Finding(**{**finding.__dict__, "severity": severity, "finding_kind": kind})
            findings.append(finding)
        return findings

    def merge(self, matches: list[dict]) -> dict:
        shapes = {tuple(item["literals"]) for item in matches}
        values = sorted({value for item in matches for value in item["literals"]}, key=Decimal)
        return {
            "literals": values[:LITERALS_SHOWN],
            "distinct": len(values),
            "cells": len(matches),
            "varies": len(shapes) > 1,
        }


@dataclass(frozen=True)
class FormulaInconsistent(Rule):
    """Ячейки строки с шаблоном формулы, отличным от основного (`formula_exceptions`)."""

    def check(self, data: AuditInput) -> list[Finding]:
        findings = []
        for row in data.rows:
            exceptions = row.get("formula_exceptions") or ()
            if not exceptions:
                continue
            by_axis: dict[str | None, list[Location]] = {}
            for location in (data.placed(cell) for cell in exceptions):
                by_axis.setdefault(location.axis_id, []).append(location)
            for axis_id, cells in by_axis.items():
                findings.append(
                    self.finding(
                        data,
                        locations=sorted(cells, key=lambda item: item.cell_id or ""),
                        row_key=row["row_key"],
                        axis_id=axis_id,
                        params={"row_formula": row.get("formula"), "cells": len(cells)},
                        truncated=bool(row.get("formula_exceptions_truncated")),
                    )
                )
        return findings


@dataclass(frozen=True)
class MissingCachedValue(Rule):
    """Формула без значения в кэше: `value_status = empty` у ячейки с формулой."""

    def check(self, data: AuditInput) -> list[Finding]:
        findings = []
        for fact in data.facts:
            if fact["value_status"] != "empty" or fact["cell_id"] not in data.link_cells:
                continue
            findings.append(
                self.finding(
                    data,
                    locations=[Location(fact["cell_id"], fact["row_key"], fact["axis_id"], fact["period_id"])],
                    row_key=fact["row_key"],
                    axis_id=fact["axis_id"],
                    period_id=fact["period_id"],
                    params={},
                )
            )
        counted = data.counters.get("missing_cached_values")
        if isinstance(counted, int) and counted > len(findings):
            # Остаток счётчика R1 вне серий проекции — одна находка книги.
            findings.append(
                self.finding(
                    data,
                    params={"count": counted, "located": len(findings), "unlocated": counted - len(findings)},
                    truncated=True,
                )
            )
        return findings


@dataclass(frozen=True)
class FunctionRule(FormulaRule):
    names: frozenset[str] = frozenset()

    def match(self, facts: FormulaFacts) -> dict | None:
        used = sorted(facts.functions & self.names)
        return {"functions": used} if used else None

    def merge(self, matches: list[dict]) -> dict:
        return {"functions": sorted({name for item in matches for name in item["functions"]}), "cells": len(matches)}


@dataclass(frozen=True)
class NestedIf(FormulaRule):
    def match(self, facts: FormulaFacts) -> dict | None:
        return {"depth": facts.if_depth} if facts.if_depth >= 2 else None

    def merge(self, matches: list[dict]) -> dict:
        return {"depth": max(item["depth"] for item in matches), "cells": len(matches)}


@dataclass(frozen=True)
class LongFormula(FormulaRule):
    def match(self, facts: FormulaFacts) -> dict | None:
        if facts.chars > LONG_FORMULA_CHARS or facts.operands > LONG_FORMULA_OPERANDS:
            return {"chars": facts.chars, "operands": facts.operands}
        return None

    def merge(self, matches: list[dict]) -> dict:
        return {
            "chars": max(item["chars"] for item in matches),
            "operands": max(item["operands"] for item in matches),
            "limit_chars": LONG_FORMULA_CHARS,
            "limit_operands": LONG_FORMULA_OPERANDS,
            "cells": len(matches),
        }


HARDCODED_FORMULA = HardcodedFormula(
    "hardcoded_formula", "1", "logic", "high", ("FAST 3.02-01", "ICAEW consistent formulas"),
    "Константа в строке формул", ROWS_LINKS,
)
LITERAL_IN_FORMULA = LiteralInFormula(
    "literal_in_formula", "1", "qualitative", "low", ("FAST 3.04-01", "ICAEW avoid hardcoding"),
    "Числовой литерал в формуле", ROWS_LINKS,
)
FORMULA_INCONSISTENT_IN_ROW = FormulaInconsistent(
    "formula_inconsistent_in_row", "1", "logic", "high", ("FAST 3.02-01", "FAST 3.02-02", "ICAEW"),
    "Формула строки отличается в отдельных ячейках", ROWS,
)
MISSING_CACHED_VALUE = MissingCachedValue(
    "missing_cached_value", "1", "omission", "medium", (), "Формула без значения в кэше",
    ROWS_LINKS | ROWS_COUNTERS,
)
OFFSET_INDIRECT_USED = FunctionRule(
    "offset_indirect_used", "1", "qualitative", "low", ("FAST 4.01-03",),
    "OFFSET или INDIRECT в формуле", ROWS_LINKS, finding_kind="methodology",
    names=frozenset({"OFFSET", "INDIRECT"}),
)
EXCEL_NPV_USED = FunctionRule(
    "excel_npv_used", "1", "logic", "medium", ("FAST 4.01-02", "Mazars XNPV"),
    "Функция NPV вместо XNPV", ROWS_LINKS, names=frozenset({"NPV"}),
)
NESTED_IF = NestedIf(
    "nested_if", "1", "qualitative", "low", ("FAST 3.03-07",), "Вложенные IF", ROWS_LINKS,
    finding_kind="methodology",
)
LONG_FORMULA = LongFormula(
    "long_formula", "1", "qualitative", "info", ("FAST 3.03-01", "ICAEW minimise complexity"),
    "Длинная формула", ROWS_LINKS, finding_kind="methodology",
)
