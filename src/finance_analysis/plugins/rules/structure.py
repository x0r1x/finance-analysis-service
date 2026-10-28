"""Правила фазы 2 (§6.1): граф, строки, единицы, периоды, корпус, знак.

Понятия им не нужны (кроме знака строки из `row_semantics`), поэтому они
выполняются на любой книге (§5.10.5). Входы — проекция сборки: `dim_row`,
`dim_period`, `fact_observation`, `graph_links`. Где правило опирается на
текст формулы, разбор — только токены (§6.1), без полного парсера Excel.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from itertools import pairwise

from finance_analysis.domain.audit import (
    ROWS,
    ROWS_LINKS,
    ROWS_SEMANTICS,
    AuditInput,
    Finding,
    Location,
    Rule,
    group_cells,
    grouped_finding,
)
from finance_analysis.domain.book import norm
from finance_analysis.domain.formulas import analyze
from finance_analysis.domain.metrics import aligned_keys

_VALUED = frozenset({"cached", "zero_explicit"})
_BARE_REF = re.compile(r"^=\s*(?:'[^']+'!|[^'!=+\-*/^(),\s]+!)?\$?[A-Za-z]{1,3}\$?\d+\s*$")
_NOT_ADDITIVE = re.compile(r"[*/^]")
_ADDITIVE_FUNCTIONS = frozenset({"SUM"})
_RATE_UNITS = frozenset({"rate", "%", "percent", "ratio", "x"})
_MONEY_UNITS = frozenset({"money", "price"})
_GENERIC_LABELS = frozenset({"total", "итого", "всего", "sum", "сумма", "check", "проверка", "balance", "остаток"})
TOLERANCE = Decimal("0.005")
CELLS_SHOWN = 10


def _number(fact: dict | None) -> Decimal | None:
    if fact is None or fact.get("value_status") not in _VALUED:
        return None
    value = fact.get("normalized_value")
    if value is None:
        value = fact.get("value_dec")
    return None if value is None else Decimal(str(value))


def _is_bare_ref(formula: str | None) -> bool:
    return bool(formula) and bool(_BARE_REF.fullmatch(formula.strip()))


def _additive(formula: str | None) -> bool:
    """Сложение или вычитание: `+`, `-` между операндами или SUM; без `* / ^` и других функций.

    Голая ссылка `=X` — перенос значения, а не сумма: подсказка единицы у
    строки-копии могла разойтись с источником без ошибки в модели.
    """

    text = (formula or "").lstrip("=").strip()
    if not text or _NOT_ADDITIVE.search(text):
        return False
    functions = analyze(formula).functions
    if not functions <= _ADDITIVE_FUNCTIONS:
        return False
    return bool(functions) or bool(re.search(r"[^\s(][\s]*[+-]", text))


def _period_order(data: AuditInput) -> dict[tuple[str, str], int]:
    return {(period["axis_id"], period["period_id"]): int(period.get("period_index") or 0) for period in data.periods}


def _row_of_cell(data: AuditInput, cell: str) -> dict | None:
    fact = data.facts_by_cell.get(cell)
    if fact is not None:
        return data.rows_by_key.get(fact["row_key"])
    link = data.link_cells.get(cell)
    if link is not None and link.row_key:
        return data.rows_by_key.get(link.row_key)
    return None


@dataclass(frozen=True)
class CellRule(Rule):
    """Находка на строку и ось по набору ячеек; `params` — число ячеек и примеры."""

    def cells(self, data: AuditInput) -> dict[str, dict]:
        raise NotImplementedError

    def check(self, data: AuditInput) -> list[Finding]:
        matched = self.cells(data)
        findings = []
        for key, cells in group_cells(data.placed(cell) for cell in matched).items():
            details = [matched[item.cell_id] for item in cells if item.cell_id]
            findings.append(grouped_finding(self, data, key, cells, params=self.merge(details)))
        return findings

    def merge(self, details: list[dict]) -> dict:
        merged: dict = {"cells": len(details)}
        for name in sorted({name for item in details for name in item}):
            values = sorted({str(item[name]) for item in details if item.get(name) is not None})
            merged[name] = values[:CELLS_SHOWN]
        return merged


@dataclass(frozen=True)
class DaisyChain(CellRule):
    """Ссылка на ссылку: `=X`, где X сам `=Y` (FAST 3.06-02)."""

    def cells(self, data: AuditInput) -> dict[str, dict]:
        found = {}
        for cell, link in data.link_cells.items():
            if not _is_bare_ref(link.formula) or len(link.refs) != 1:
                continue
            target = data.link_cells.get(link.refs[0])
            if target is not None and _is_bare_ref(target.formula) and len(target.refs) == 1:
                found[cell] = {"via": link.refs[0], "source": target.refs[0]}
        return found


@dataclass(frozen=True)
class PartialRangeReference(Rule):
    """SUM вне серии по части оси строки: итог, который не видит хвост шкалы (FAST 3.02-03)."""

    def check(self, data: AuditInput) -> list[Finding]:
        valued: dict[tuple[str, str], set[str]] = {}
        for fact in data.facts:
            if fact.get("value_status") in _VALUED:
                valued.setdefault((fact["row_key"], fact["axis_id"]), set()).add(fact["cell_id"])
        findings = []
        for cell, link in sorted(data.link_cells.items()):
            if "SUM" not in analyze(link.formula).functions or cell in data.facts_by_cell:
                continue
            series: dict[tuple[str, str], set[str]] = {}
            for ref in link.refs:
                fact = data.facts_by_cell.get(ref)
                if fact is not None:
                    series.setdefault((fact["row_key"], fact["axis_id"]), set()).add(ref)
            for (row_key, axis_id), cells in sorted(series.items()):
                full = valued.get((row_key, axis_id), set())
                missed = full - cells
                if len(cells) < 2 or not missed:
                    continue
                findings.append(
                    self.finding(
                        data,
                        locations=[data.placed(cell)],
                        subject=f"cell:{cell}",
                        params={
                            "formula": link.formula,
                            "row_key": row_key,
                            "axis_id": axis_id,
                            "covered": len(cells),
                            "periods": len(full),
                            "missed": sorted(missed)[:CELLS_SHOWN],
                        },
                    )
                )
        return findings


@dataclass(frozen=True)
class RowTotalInLogic(CellRule):
    """Ячейка серии ссылается на колонку итога строки (SUM вне шкалы той же строки, FAST 3.01-04)."""

    def cells(self, data: AuditInput) -> dict[str, dict]:
        found = {}
        for cell, link in data.link_cells.items():
            own = _row_of_cell(data, cell)
            if cell not in data.facts_by_cell or own is None or own.get("check_row") or own.get("kind") != "fact":
                continue
            for ref in link.refs:
                target = data.link_cells.get(ref)
                if ref in data.facts_by_cell or target is None or not target.row_key:
                    continue
                if "SUM" not in analyze(target.formula).functions:
                    continue
                own = {item for item in target.refs if data.facts_by_cell.get(item, {}).get("row_key") == target.row_key}
                if len(own) >= 2:
                    found[cell] = {"total_cell": ref}
                    break
        return found


@dataclass(frozen=True)
class HiddenUsedInCalc(Rule):
    """Видимая формула берёт число из скрытой строки или скрытого периода (FAST 2.01-08)."""

    def check(self, data: AuditInput) -> list[Finding]:
        hidden_periods = {(period["axis_id"], period["period_id"]) for period in data.periods if period.get("hidden")}
        used: dict[str, set[str]] = {}
        for cell, link in data.link_cells.items():
            own = _row_of_cell(data, cell)
            if own is not None and own.get("hidden"):
                continue
            for ref in link.refs:
                row = _row_of_cell(data, ref)
                fact = data.facts_by_cell.get(ref)
                in_hidden_period = fact is not None and (fact["axis_id"], fact["period_id"]) in hidden_periods
                if row is not None and (row.get("hidden") or in_hidden_period):
                    used.setdefault(row["row_key"], set()).add(cell)
        return [
            self.finding(
                data,
                row_key=row_key,
                params={"used_by": len(cells), "cells": sorted(cells)[:CELLS_SHOWN]},
            )
            for row_key, cells in sorted(used.items())
        ]


@dataclass(frozen=True)
class DuplicateLabel(Rule):
    """Повтор метки в одном разделе листа: `binding_key.occurrence > 0` (FAST 3.05-03)."""

    def check(self, data: AuditInput) -> list[Finding]:
        seen: Counter[tuple] = Counter()
        findings = []
        for row in sorted(data.rows, key=lambda item: (item.get("sheet") or "", int(item.get("row_num") or 0))):
            if row.get("kind") != "fact":
                continue
            key = (row.get("sheet"), row.get("label_path_json"), norm(str(row.get("label") or "")))
            occurrence = seen[key]
            seen[key] += 1
            if occurrence:
                findings.append(
                    self.finding(data, row_key=row["row_key"], params={"label": row.get("label"), "occurrence": occurrence})
                )
        return findings


@dataclass(frozen=True)
class MissingUnit(Rule):
    """Строка с числами без единицы и валюты (FAST 3.05-04)."""

    def check(self, data: AuditInput) -> list[Finding]:
        findings = []
        for row in data.rows:
            if row.get("kind") != "fact" or row.get("check_row") or row.get("unit") or row.get("currency"):
                continue
            if not any(_number(fact) is not None for fact in data.facts_by_row.get(row["row_key"], ())):
                continue
            findings.append(self.finding(data, row_key=row["row_key"], params={"label": row.get("label")}))
        return findings


@dataclass(frozen=True)
class HardcodedValueInFormulaRow(CellRule):
    """Формула без ссылок (`=5*12`) в строке, где остальные ячейки считаются от ссылок."""

    def cells(self, data: AuditInput) -> dict[str, dict]:
        referenced: Counter[tuple] = Counter()
        literal: dict[str, tuple] = {}
        for cell, link in data.link_cells.items():
            fact = data.facts_by_cell.get(cell)
            if fact is None:
                continue
            key = (fact["row_key"], fact["axis_id"])
            facts = analyze(link.formula)
            if link.refs or facts.functions:
                referenced[key] += 1
            elif facts.operands:
                literal[cell] = key
        return {
            cell: {"formula": data.link_cells[cell].formula}
            for cell, key in literal.items()
            if referenced[key] > 0
        }


@dataclass(frozen=True)
class UnitRule(CellRule):
    """Сложение строк с разной мерой: масштаб (`scale_mismatch`) или единица (`unit_mismatch`)."""

    def mismatch(self, own: dict, other: dict) -> dict | None:
        raise NotImplementedError

    def cells(self, data: AuditInput) -> dict[str, dict]:
        found = {}
        for cell, link in data.link_cells.items():
            if not _additive(link.formula):
                continue
            own = _row_of_cell(data, cell)
            if own is None or len(set(link.refs)) < 2:
                continue
            for ref in link.refs:
                other = _row_of_cell(data, ref)
                if other is None or other["row_key"] == own["row_key"]:
                    continue
                differs = self.mismatch(own, other)
                if differs is not None:
                    found[cell] = differs
                    break
        return found


@dataclass(frozen=True)
class ScaleMismatch(UnitRule):
    def mismatch(self, own: dict, other: dict) -> dict | None:
        mine, theirs = own.get("scale_factor"), other.get("scale_factor")
        if mine is None or theirs is None or mine == theirs:
            return None
        if str(own.get("unit") or "") not in _MONEY_UNITS or str(other.get("unit") or "") not in _MONEY_UNITS:
            return None
        return {"scale": mine, "ref_scale": theirs, "ref_row": other["row_key"]}


@dataclass(frozen=True)
class UnitMismatch(UnitRule):
    def mismatch(self, own: dict, other: dict) -> dict | None:
        mine, theirs = str(own.get("unit") or "").lower(), str(other.get("unit") or "").lower()
        if mine and theirs and (mine in _MONEY_UNITS) != (theirs in _MONEY_UNITS) and {mine, theirs} & _RATE_UNITS:
            return {"unit": mine, "ref_unit": theirs, "ref_row": other["row_key"]}
        left, right = own.get("currency"), other.get("currency")
        if left and right and left != right:
            return {"currency": left, "ref_currency": right, "ref_row": other["row_key"]}
        return None


@dataclass(frozen=True)
class PeriodGap(Rule):
    """Соседние периоды оси с датами: дыра или нахлёст между концом и началом."""

    def check(self, data: AuditInput) -> list[Finding]:
        by_axis: dict[str, list[dict]] = {}
        for period in data.periods:
            if period.get("axis_kind") == "params":
                continue
            if period.get("period_start") is not None and period.get("period_end") is not None:
                by_axis.setdefault(period["axis_id"], []).append(period)
        findings = []
        for axis_id, periods in sorted(by_axis.items()):
            ordered = sorted(periods, key=lambda item: int(item.get("period_index") or 0))
            for before, after in pairwise(ordered):
                expected = before["period_end"] + timedelta(days=1)
                if after["period_start"] == expected:
                    continue
                findings.append(
                    self.finding(
                        data,
                        axis_id=axis_id,
                        period_id=after["period_id"],
                        params={
                            "previous": before["period_id"],
                            "gap_days": (after["period_start"] - expected).days,
                        },
                    )
                )
        return findings


@dataclass(frozen=True)
class RollforwardBreak(Rule):
    """Корпус: открывающая строка = закрывающая строка прошлого периода (FAST 2.02-05).

    Строка-«открытие» — та, где ≥ 2 ячейки серии — голые ссылки `=X` на ячейку
    одной и той же другой строки в предыдущем периоде. Разрыв — ячейка серии
    после первой, которая так не делает (константа или ссылка на другое), или
    число в кэше, расходящееся с закрытием прошлого периода.
    """

    def check(self, data: AuditInput) -> list[Finding]:
        order = _period_order(data)
        aligned = aligned_keys(data.periods)
        position = {(period["axis_id"], period["period_id"]): aligned.get((period["axis_id"], period["period_id"])) for period in data.periods}
        findings = []
        for (row_key, axis_id), facts in sorted(_series(data).items()):
            ordered = sorted(facts, key=lambda item: order.get((axis_id, item["period_id"]), 0))
            follows: dict[str, str] = {}
            for fact in ordered:
                link = data.link_cells.get(fact["cell_id"])
                if link is None or not _is_bare_ref(link.formula) or len(link.refs) != 1:
                    continue
                source = data.facts_by_cell.get(link.refs[0])
                if source is None or source["row_key"] == row_key:
                    continue
                if _step(position, order, fact, source) == 1:
                    follows[fact["cell_id"]] = source["row_key"]
            closing = Counter(follows.values()).most_common(1)
            if not closing or closing[0][1] < 2:
                continue
            close_row = closing[0][0]
            broken = []
            for fact in ordered[1:]:
                cell = fact["cell_id"]
                if follows.get(cell) != close_row:
                    if cell in data.link_cells or _number(fact) is not None:
                        broken.append((fact, "not_linked"))
                    continue
                source = data.facts_by_cell[data.link_cells[cell].refs[0]]
                opening, closed = _number(fact), _number(source)
                if opening is not None and closed is not None and abs(opening - closed) > TOLERANCE:
                    broken.append((fact, "value_differs"))
            for fact, reason in broken:
                findings.append(
                    self.finding(
                        data,
                        locations=[Location(fact["cell_id"], row_key, axis_id, fact["period_id"])],
                        row_key=row_key,
                        axis_id=axis_id,
                        period_id=fact["period_id"],
                        params={"closing_row": close_row, "reason": reason},
                    )
                )
        return findings


def _series(data: AuditInput) -> dict[tuple[str, str], list[dict]]:
    grouped: dict[tuple[str, str], list[dict]] = {}
    for fact in data.facts:
        grouped.setdefault((fact["row_key"], fact["axis_id"]), []).append(fact)
    return grouped


def _step(position: dict, order: dict, fact: dict, source: dict) -> int | None:
    """На сколько периодов шкалы ячейка позже источника (по `timeline_id` + индексу)."""

    mine = position.get((fact["axis_id"], fact["period_id"]))
    theirs = position.get((source["axis_id"], source["period_id"]))
    if mine is not None and theirs is not None:
        return mine[1] - theirs[1] if mine[0] == theirs[0] else None
    if fact["axis_id"] != source["axis_id"]:
        return None
    return order.get((fact["axis_id"], fact["period_id"]), 0) - order.get((source["axis_id"], source["period_id"]), 0)


def _signed(data: AuditInput) -> dict[str, tuple[str, set[int]]]:
    """Строки со знаком потока из `row_semantics` → (знак, знаки ненулевых чисел)."""

    found = {}
    for item in data.semantics:
        sign = item.get("sign")
        if sign not in {"inflow", "outflow"} or item.get("excluded") or not item.get("row_key"):
            continue
        signs = set()
        for fact in data.facts_by_row.get(item["row_key"], ()):
            number = _number(fact)
            if number:
                signs.add(1 if number > 0 else -1)
        if signs:
            found[item["row_key"]] = (sign, signs)
    return found


@dataclass(frozen=True)
class SignAnomaly(Rule):
    """Поток с обоими знаками в одной строке (ICAEW «clear sign convention»)."""

    def check(self, data: AuditInput) -> list[Finding]:
        return [
            self.finding(data, row_key=row_key, params={"sign": sign})
            for row_key, (sign, signs) in sorted(_signed(data).items())
            if len(signs) > 1
        ]


@dataclass(frozen=True)
class SignConventionMixed(Rule):
    """Оттоки книги записаны и с минусом, и с плюсом (FAST 3.04-04). Места — меньшая группа."""

    def check(self, data: AuditInput) -> list[Finding]:
        negative, positive = [], []
        for row_key, (sign, signs) in sorted(_signed(data).items()):
            if sign != "outflow" or len(signs) != 1:
                continue
            (negative if signs == {-1} else positive).append(row_key)
        if not negative or not positive:
            return []
        minority = positive if len(positive) <= len(negative) else negative
        return [
            self.finding(
                data,
                locations=[Location(None, row_key, None, None) for row_key in minority],
                subject="book",
                params={"negative": len(negative), "positive": len(positive)},
            )
        ]


@dataclass(frozen=True)
class CrossSheetInconsistency(Rule):
    """Одна и та же метка на двух листах, без ссылки между строками, с разными числами."""

    def check(self, data: AuditInput) -> list[Finding]:
        aligned = aligned_keys(data.periods)
        by_label: dict[str, list[dict]] = {}
        for row in data.rows:
            label = norm(str(row.get("label") or ""))
            if row.get("kind") != "fact" or len(label) < 4 or label in _GENERIC_LABELS:
                continue
            by_label.setdefault(label, []).append(row)
        linked = _linked_rows(data)
        findings = []
        for label, rows in sorted(by_label.items()):
            for index, left in enumerate(rows):
                for right in rows[index + 1 :]:
                    if left.get("sheet") == right.get("sheet") or str(left.get("unit") or "") != str(right.get("unit") or ""):
                        continue
                    if frozenset({left["row_key"], right["row_key"]}) in linked:
                        continue
                    differs = _differs(data, aligned, left["row_key"], right["row_key"])
                    if not differs:
                        continue
                    findings.append(
                        self.finding(
                            data,
                            locations=[Location(None, left["row_key"], None, None), Location(None, right["row_key"], None, None)],
                            row_key=left["row_key"],
                            params={"label": label, "other_row": right["row_key"], "periods": len(differs)},
                        )
                    )
        return findings


def _linked_rows(data: AuditInput) -> set[frozenset[str]]:
    pairs = set()
    for cell, link in data.link_cells.items():
        own = _row_of_cell(data, cell)
        if own is None:
            continue
        for ref in link.refs:
            other = _row_of_cell(data, ref)
            if other is not None and other["row_key"] != own["row_key"]:
                pairs.add(frozenset({own["row_key"], other["row_key"]}))
    return pairs


def _differs(data: AuditInput, aligned: dict, left: str, right: str) -> list:
    def values(row_key: str) -> dict:
        found = {}
        for fact in data.facts_by_row.get(row_key, ()):
            number = _number(fact)
            if number is not None:
                own = (fact["axis_id"], fact["period_id"])
                found[aligned.get(own, own)] = number
        return found

    # Модуль: строка, перенесённая с другим знаком, — вопрос конвенции (`sign_convention_mixed`).
    mine, theirs = values(left), values(right)
    shared = sorted(set(mine) & set(theirs), key=str)
    return [key for key in shared if abs(abs(mine[key]) - abs(theirs[key])) > TOLERANCE]


@dataclass(frozen=True)
class FormulaClassMismatch(CellRule):
    """Класс формулы ячейки (`graph.json`) отличается от основного класса серии.

    Первый период оси не проверяется: открытие корпуса и первая ячейка серии
    законно отличаются. Ячейки из `formula_exceptions` — уже
    `formula_inconsistent_in_row`.
    """

    def cells(self, data: AuditInput) -> dict[str, dict]:
        order = _period_order(data)
        found = {}
        for (row_key, axis_id), facts in _series(data).items():
            row = data.rows_by_key.get(row_key) or {}
            exceptions = set(row.get("formula_exceptions") or ())
            classes = {
                fact["cell_id"]: data.link_cells[fact["cell_id"]].formula_class
                for fact in facts
                if fact["cell_id"] in data.link_cells and data.link_cells[fact["cell_id"]].formula_class
            }
            if len(classes) < 3:
                continue
            dominant, count = Counter(classes.values()).most_common(1)[0]
            if count * 2 <= len(classes):
                continue
            first = min(facts, key=lambda item: order.get((axis_id, item["period_id"]), 0))["cell_id"]
            for cell, kind in classes.items():
                if kind != dominant and cell != first and cell not in exceptions:
                    found[cell] = {"formula_class": kind, "expected": dominant}
        return found


DAISY_CHAIN = DaisyChain("daisy_chain", "1", "qualitative", "info", ("FAST 3.06-02", "ICAEW"), "Ссылка на ссылку", ROWS_LINKS, 2)
PARTIAL_RANGE_REFERENCE = PartialRangeReference(
    "partial_range_reference", "1", "logic", "high", ("FAST 3.02-03",), "SUM по части оси", ROWS_LINKS, 2,
)
ROW_TOTAL_IN_LOGIC = RowTotalInLogic(
    "row_total_in_logic", "1", "logic", "medium", ("FAST 3.01-04",), "Расчёт ссылается на колонку итога", ROWS_LINKS, 2,
)
HIDDEN_USED_IN_CALC = HiddenUsedInCalc(
    "hidden_used_in_calc", "1", "qualitative", "low", ("ICAEW «don't hide things»", "FAST 2.01-08"),
    "Расчёт берёт скрытую строку или период", ROWS_LINKS, 2,
)
DUPLICATE_LABEL = DuplicateLabel("duplicate_label", "1", "qualitative", "info", ("FAST 3.05-03",), "Повтор метки", ROWS, 2)
MISSING_UNIT = MissingUnit("missing_unit", "1", "qualitative", "low", ("FAST 3.05-04", "ICAEW «clear units»"), "Нет единицы", ROWS, 2)
HARDCODED_VALUE_IN_FORMULA_ROW = HardcodedValueInFormulaRow(
    "hardcoded_value_in_formula_row", "1", "logic", "medium", ("ICAEW «avoid hardcoding»",),
    "Формула без ссылок в строке расчёта", ROWS_LINKS, 2,
)
SCALE_MISMATCH = ScaleMismatch(
    "scale_mismatch", "1", "logic", "high", ("ICAEW «clear units»",), "Сложение строк разного масштаба", ROWS_LINKS, 2,
)
UNIT_MISMATCH = UnitMismatch(
    "unit_mismatch", "1", "logic", "high", ("ICAEW «clear units»",), "Сложение строк разной единицы", ROWS_LINKS, 2,
)
PERIOD_GAP = PeriodGap("period_gap", "1", "logic", "medium", ("ICAEW",), "Дыра или нахлёст периодов", ROWS, 2)
ROLLFORWARD_BREAK = RollforwardBreak(
    "rollforward_break", "1", "logic", "high", ("FAST 2.02-05",), "Корпус не сходится", ROWS_LINKS, 2,
)
SIGN_ANOMALY = SignAnomaly(
    "sign_anomaly", "1", "logic", "medium", ("ICAEW «clear sign convention»",), "Поток с обоими знаками", ROWS_SEMANTICS, 2,
)
SIGN_CONVENTION_MIXED = SignConventionMixed(
    "sign_convention_mixed", "1", "qualitative", "low", ("ICAEW «clear sign convention»", "FAST 3.04-04"),
    "Оттоки записаны с разным знаком", ROWS_SEMANTICS, 2,
)
CROSS_SHEET_INCONSISTENCY = CrossSheetInconsistency(
    "cross_sheet_inconsistency", "1", "logic", "medium", ("graph",), "Одна величина на двух листах расходится", ROWS_LINKS, 2,
)
FORMULA_CLASS_MISMATCH = FormulaClassMismatch(
    "formula_class_mismatch", "1", "logic", "medium", ("graph",), "Класс формулы выбивается из серии", ROWS_LINKS, 2,
)
