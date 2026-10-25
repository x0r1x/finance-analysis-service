"""Правила аудита фазы 1 (§6.1): формулы, ссылки, циклы, проверки.

Правилам не нужны понятия, поэтому они выполняются на любой книге
(§5.10.5). Входы — проекция сборки и счётчики R1 `/summary`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from finance_analysis.domain.audit import AuditInput, Finding, Location, Rule
from finance_analysis.domain.formulas import FormulaFacts, analyze, top_level_comparison

PROJECTION = frozenset({"rows", "periods", "facts"})
GRAPH = PROJECTION | {"links"}
SUMMARY = PROJECTION | {"counters"}

_VALUED = frozenset({"cached", "zero_explicit"})
LONG_FORMULA_CHARS = 120
LONG_FORMULA_OPERANDS = 12
LITERALS_SHOWN = 10


def _group(data: AuditInput, locations: Iterable[Location]) -> dict[tuple, list[Location]]:
    """Ячейки по (строка, ось). Ячейка вне строк книги — своя группа."""

    grouped: dict[tuple, list[Location]] = {}
    for location in locations:
        if location.row_key is None:
            key: tuple = ("cell", location.cell_id)
        else:
            key = ("row", location.row_key, location.axis_id)
        grouped.setdefault(key, []).append(location)
    return grouped


def _grouped_finding(rule: Rule, data: AuditInput, key: tuple, cells: list[Location], **kwargs) -> Finding:
    ordered = sorted(cells, key=lambda item: item.cell_id or "")
    if key[0] == "cell":
        return rule.finding(data, locations=ordered, subject=f"cell:{key[1]}", **kwargs)
    return rule.finding(data, locations=ordered, row_key=key[1], axis_id=key[2], **kwargs)


def _ids_finding(rule: Rule, data: AuditInput, name: str, extra: dict | None = None) -> list[Finding]:
    counter = data.counters.get(name)
    if not isinstance(counter, dict):
        return []
    count = int(counter.get("count") or 0)
    if count <= 0:
        return []
    ids = [str(item) for item in counter.get("ids") or []]
    params = {"count": count, **(extra or {})}
    return [
        rule.finding(
            data,
            locations=[data.placed(cell) for cell in ids],
            params=params,
            truncated=count > len(ids),
        )
    ]


@dataclass(frozen=True)
class _TextRule(Rule):
    """Правило по тексту формулы: одна находка на строку и ось."""

    def hit(self, facts: FormulaFacts) -> dict | None:
        raise NotImplementedError

    def check(self, data: AuditInput) -> list[Finding]:
        hits: dict[str, dict] = {}
        for cell, link in data.link_cells.items():
            found = self.hit(analyze(link.formula))
            if found is not None:
                hits[cell] = found
        findings = []
        for key, cells in _group(data, (data.placed(cell) for cell in hits)).items():
            merged = self.merge([hits[item.cell_id] for item in cells if item.cell_id])
            findings.append(_grouped_finding(self, data, key, cells, params=merged))
        return findings

    def merge(self, hits: list[dict]) -> dict:
        return {"cells": len(hits)}


@dataclass(frozen=True)
class HardcodedFormula(Rule):
    """Константа среди формул строки: у ячейки есть значение, но нет формулы."""

    def check(self, data: AuditInput) -> list[Finding]:
        findings = []
        formulas = data.link_cells
        for row in data.rows:
            if not row.get("has_formula"):
                continue
            by_axis: dict[str, list[dict]] = {}
            for fact in data.facts_by_row.get(row["row_key"], ()):
                by_axis.setdefault(fact["axis_id"], []).append(fact)
            for axis_id, facts in by_axis.items():
                constants = [
                    fact for fact in facts if fact["value_status"] in _VALUED and fact["cell_id"] not in formulas
                ]
                # Формула без кэша остаётся формулой: в знаменателе все ячейки с формулой.
                with_formula = sum(1 for fact in facts if fact["cell_id"] in formulas)
                # Строка формул — формулы хотя бы в половине ячеек с формулой или значением.
                if not constants or len(constants) > with_formula:
                    continue
                for fact in constants:
                    findings.append(
                        self.finding(
                            data,
                            locations=[Location(fact["cell_id"], row["row_key"], axis_id, fact["period_id"])],
                            row_key=row["row_key"],
                            axis_id=axis_id,
                            period_id=fact["period_id"],
                            params={"row_formula": row.get("formula"), "value": fact.get("value_raw")},
                        )
                    )
        return findings


@dataclass(frozen=True)
class LiteralInFormula(_TextRule):
    def hit(self, facts: FormulaFacts) -> dict | None:
        if not facts.literals:
            return None
        return {"literals": facts.literals}

    def check(self, data: AuditInput) -> list[Finding]:
        findings = []
        for finding in super().check(data):
            if finding.params.get("varies"):
                finding = Finding(**{**finding.__dict__, "severity": "medium"})
            findings.append(finding)
        return findings

    def merge(self, hits: list[dict]) -> dict:
        shapes = {tuple(hit["literals"]) for hit in hits}
        values = sorted({value for hit in hits for value in hit["literals"]}, key=Decimal)
        return {
            "literals": values[:LITERALS_SHOWN],
            "distinct": len(values),
            "cells": len(hits),
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
            located = [data.placed(cell) for cell in exceptions]
            by_axis: dict[str | None, list[Location]] = {}
            for location in located:
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
class CountedRefs(Rule):
    """Ссылки из счётчиков R1 `{count, ids}`: одна находка на книгу.

    `dangling_classes` builder — ссылки на действительно пустые ячейки
    (`empty_ref`, `empty_range_member`, вне `dangling.count`). Это не ошибка,
    поэтому классы идут только в `params` находки по `dangling.count`.
    """

    counter: str = ""

    def check(self, data: AuditInput) -> list[Finding]:
        extra = {}
        if self.counter == "dangling" and isinstance(data.counters.get("dangling_classes"), dict):
            extra["dangling_classes"] = data.counters["dangling_classes"]
        return _ids_finding(self, data, self.counter, extra)


@dataclass(frozen=True)
class UnexpectedCycle(Rule):
    def check(self, data: AuditInput) -> list[Finding]:
        findings = []
        for cycle in data.counters.get("cycles") or ():
            if cycle.get("class") != "unexpected":
                continue
            findings.append(
                self.finding(
                    data,
                    subject=f"cycle:{cycle.get('id')}",
                    params={"cycle_id": cycle.get("id"), "members": cycle.get("members")},
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


def _check_failed(value, *, boolean: bool) -> bool:
    if boolean:
        return value == 0
    return value != 0


@dataclass(frozen=True)
class CheckFailure(Rule):
    """Проверка не сходится.

    Две записи проверок: флаг ошибки (`=IF(A1<>0,1,0)`, сбой — не ноль) и
    сравнение (`=A1-B1<0.01`, TRUE = сошлось, сбой — FALSE = 0). Строка без
    формулы (допуск, заголовок) — не проверка.
    """

    def check(self, data: AuditInput) -> list[Finding]:
        findings = []
        for row in data.rows:
            if not row.get("check_row") or not row.get("has_formula"):
                continue
            boolean = top_level_comparison(row.get("formula"))
            by_axis: dict[str, list[Location]] = {}
            for fact in data.facts_by_row.get(row["row_key"], ()):
                value = fact.get("value_dec")
                if fact["value_status"] not in _VALUED or value is None:
                    continue
                if _check_failed(Decimal(value), boolean=boolean):
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
                        params={
                            "failed_cells": len(cells),
                            "label": row.get("label"),
                            "convention": "comparison" if boolean else "error_flag",
                        },
                    )
                )
        return findings


@dataclass(frozen=True)
class NoMasterCheck(Rule):
    def check(self, data: AuditInput) -> list[Finding]:
        if any(row.get("check_row") for row in data.rows):
            return []
        return [self.finding(data, params={"check_rows": 0})]


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
class FunctionUsed(_TextRule):
    names: frozenset[str] = frozenset()

    def hit(self, facts: FormulaFacts) -> dict | None:
        used = sorted(facts.functions & self.names)
        return {"functions": used} if used else None

    def merge(self, hits: list[dict]) -> dict:
        return {"functions": sorted({name for hit in hits for name in hit["functions"]}), "cells": len(hits)}


@dataclass(frozen=True)
class NestedIf(_TextRule):
    def hit(self, facts: FormulaFacts) -> dict | None:
        return {"depth": facts.if_depth} if facts.if_depth >= 2 else None

    def merge(self, hits: list[dict]) -> dict:
        return {"depth": max(hit["depth"] for hit in hits), "cells": len(hits)}


@dataclass(frozen=True)
class LongFormula(_TextRule):
    def hit(self, facts: FormulaFacts) -> dict | None:
        if facts.chars > LONG_FORMULA_CHARS or facts.operands > LONG_FORMULA_OPERANDS:
            return {"chars": facts.chars, "operands": facts.operands}
        return None

    def merge(self, hits: list[dict]) -> dict:
        return {
            "chars": max(hit["chars"] for hit in hits),
            "operands": max(hit["operands"] for hit in hits),
            "limit_chars": LONG_FORMULA_CHARS,
            "limit_operands": LONG_FORMULA_OPERANDS,
            "cells": len(hits),
        }


RULES: tuple[Rule, ...] = (
    HardcodedFormula(
        "hardcoded_formula", "1", "logic", "high", ("FAST 3.02-01", "ICAEW consistent formulas"),
        "Константа в строке формул", GRAPH,
    ),
    LiteralInFormula(
        "literal_in_formula", "1", "qualitative", "low", ("FAST 3.04-01", "ICAEW avoid hardcoding"),
        "Числовой литерал в формуле", GRAPH,
    ),
    FormulaInconsistent(
        "formula_inconsistent_in_row", "1", "logic", "high", ("FAST 3.02-01", "FAST 3.02-02", "ICAEW"),
        "Формула строки отличается в отдельных ячейках", PROJECTION,
    ),
    CountedRefs(
        "dangling_ref", "1", "mechanical", "high", (), "Ссылка на пустую или удалённую ячейку", SUMMARY,
        counter="dangling",
    ),
    CountedRefs(
        "unresolved_ref", "1", "mechanical", "high", (), "Ссылка не разрешена", SUMMARY, counter="unresolved",
    ),
    CountedRefs(
        "external_ref", "1", "qualitative", "medium", ("FAST 1.03-02", "FAST 1.03-04"),
        "Ссылка на внешнюю книгу", SUMMARY, counter="external",
    ),
    UnexpectedCycle(
        "unexpected_cycle", "1", "logic", "high", ("ICAEW avoid circular references",),
        "Непредусмотренная циклическая ссылка", SUMMARY,
    ),
    IterativeCalcEnabled(
        "iterative_calc_enabled", "1", "qualitative", "medium", ("ICAEW iterative calculation",),
        "Включены итеративные вычисления", SUMMARY,
    ),
    IterativeCycleWithoutIterate(
        "iterative_cycle_without_iterate", "1", "mechanical", "high", (),
        "Цикл при выключенных итеративных вычислениях", SUMMARY,
    ),
    CheckFailure(
        "check_failure", "1", "quantitative", "critical", ("ICAEW include checks",),
        "Проверка книги не сходится", PROJECTION,
    ),
    NoMasterCheck(
        "no_master_check", "1", "qualitative", "info", ("ICAEW master check", "FAST 2.03-05"),
        "В книге нет проверочных строк", PROJECTION,
    ),
    MissingCachedValue(
        "missing_cached_value", "1", "omission", "medium", (), "Формула без значения в кэше", GRAPH | SUMMARY,
    ),
    FunctionUsed(
        "offset_indirect_used", "1", "qualitative", "low", ("FAST 4.01-03",),
        "OFFSET или INDIRECT в формуле", GRAPH, names=frozenset({"OFFSET", "INDIRECT"}),
    ),
    FunctionUsed(
        "excel_npv_used", "1", "logic", "medium", ("FAST 4.01-02", "Mazars XNPV"),
        "Функция NPV вместо XNPV", GRAPH, names=frozenset({"NPV"}),
    ),
    NestedIf(
        "nested_if", "1", "qualitative", "low", ("FAST 3.03-07",), "Вложенные IF", GRAPH,
    ),
    LongFormula(
        "long_formula", "1", "qualitative", "info", ("FAST 3.03-01", "ICAEW minimise complexity"),
        "Длинная формула", GRAPH,
    ),
)
