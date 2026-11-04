"""Расхождения коэффициента, смесь маркеров и дыра в цепочке (§6.1, фаза 2)."""

from __future__ import annotations

from decimal import Decimal

from finance_analysis.domain.audit import (
    ROWS,
    ROWS_LINKS,
    AuditInput,
    Finding,
    Rule,
    project_finance_dscr,
)
from finance_analysis.domain.metrics import coverage_ratio

_TOLERANCE = Decimal("0.005")
_BOUND = frozenset({"bound", "bound_with_warning"})
_EMPTY_REFERENCE = "справочная строка пуста"
_INCOMPLETE_NUMERATOR = "справочный расчёт книги неполон: числитель пуст"
_ICR_DIVERGENCE = "Справочный коэффициент книги расходится с расчётом FAS."


def _primary(data: AuditInput, concept: str) -> dict | None:
    found = [
        row
        for row in data.bindings
        if row.get("is_primary") and row.get("status") in _BOUND and (row.get("effective_concept") or row.get("concept")) == concept
    ]
    return found[0] if len(found) == 1 else None


def _cached(data: AuditInput, row_key: str) -> dict[tuple[str, str], Decimal]:
    values = {}
    for fact in data.facts:
        if fact.get("row_key") != row_key:
            continue
        number = fact.get("normalized_value")
        if number is None:
            number = fact.get("value_dec")
        if number is None:
            continue
        values[(fact["axis_id"], fact["period_id"])] = Decimal(str(number))
    return values


class RatioMismatch(Rule):
    def check(self, data: AuditInput) -> list[Finding]:
        if not data.bindings or not project_finance_dscr(data):
            return []
        model = _primary(data, "dscr")
        if model is None or _primary(data, "cfads") is None or _primary(data, "debt_service") is None:
            return []
        phases = {}
        for row in data.periods:
            phase = row.get("phase")
            if not phase:
                continue
            phases[(row["axis_id"], row["period_id"])] = phase
            base = row.get("period_key_base")
            if base:
                phases[(row["axis_id"], base)] = phase
        result = coverage_ratio(
            metric="dscr",
            facts=data.facts,
            bindings=data.bindings,
            periods=data.periods,
            period_phase=phases,
            explicit_phases=bool(phases),
        )
        cached = _cached(data, model["row_key"])
        findings = []
        for row in result["rows"]:
            if row.get("value") is None:
                continue
            key = (row["axis_id"], row["period_id"])
            other = cached.get(key)
            if other is None or abs(Decimal(row["value"]) - other) <= _TOLERANCE:
                continue
            findings.append(
                self.finding(
                    data,
                    row_key=model["row_key"],
                    axis_id=row["axis_id"],
                    period_id=row["period_id"],
                    params={"metric": "dscr", "fas": str(row["value"]), "model": str(other)},
                )
            )
        return findings


def _marker_of(data: AuditInput) -> dict[str, str]:
    period_marker = {
        (row.get("axis_id"), row.get("period_id")): row.get("marker_class")
        for row in data.periods
        if row.get("marker_class")
    }
    found = {}
    for fact in data.facts:
        cell = fact.get("cell_id")
        marker = period_marker.get((fact.get("axis_id"), fact.get("period_id")))
        if cell and marker:
            found[cell] = marker
    return found


def _parents(data: AuditInput) -> dict[str, set[str]]:
    cell_row = {fact.get("cell_id"): fact.get("row_key") for fact in data.facts if fact.get("cell_id")}
    parents: dict[str, set[str]] = {}
    for link in data.links:
        parent = link.get("row_key")
        child = cell_row.get(link.get("ref_cell"))
        if parent and child and parent != child:
            parents.setdefault(child, set()).add(parent)
    return parents


def _ancestors(parents: dict[str, set[str]], row_key: str) -> set[str]:
    seen: set[str] = set()
    stack = list(parents.get(row_key, ()))
    while stack:
        parent = stack.pop()
        if parent in seen:
            continue
        seen.add(parent)
        stack.extend(parents.get(parent, ()))
    return seen


class MarkerMix(Rule):
    def check(self, data: AuditInput) -> list[Finding]:
        markers_of = _marker_of(data)
        by_formula: dict[tuple[str, str], set[str]] = {}
        owners: dict[tuple[str, str], str] = {}
        for link in data.links:
            row_key = link.get("row_key")
            marker = markers_of.get(link.get("ref_cell"))
            if not row_key or not marker:
                continue
            key = (row_key, str(link.get("cell") or ""))
            by_formula.setdefault(key, set()).add(marker)
            owners[key] = row_key
        return [
            self.finding(data, row_key=owners[key], params={"markers": sorted(markers)})
            for key, markers in by_formula.items()
            if len(markers) > 1
        ]


def _chain_concepts(data: AuditInput) -> set[str]:
    """Понятия цепочки только тех метрик, которые применимы к типу модели."""

    metrics = data.applicable_metrics
    watched = set()
    dscr_family = {"dscr", "adscr", "dscr_min", "dscr_avg", "llcr", "plcr"}
    if metrics is None or metrics & dscr_family:
        watched.update({"debt_service", "dscr"})
    if metrics is None or "icr" in metrics:
        watched.update({"interest", "icr"})
    return watched


class IcrReference(Rule):
    """Сверяет ICR FAS со строкой коэффициента книги.

    Ноль или пустое значение книги не считается расхождением, если пуст источник
    EBITDA либо строка числителя, на которую ссылается формула.
    """

    def check(self, data: AuditInput) -> list[Finding]:
        if data.applicable_metrics is not None and "icr" not in data.applicable_metrics:
            return []
        model = _primary(data, "icr")
        ebitda = _primary(data, "ebitda")
        if model is None or ebitda is None or not data.periods:
            return []
        interest = _primary(data, "interest")
        computed = {}
        if interest is not None:
            phases = {}
            for row in data.periods:
                phase = row.get("phase")
                if phase:
                    phases[(row["axis_id"], row["period_id"])] = phase
            result = coverage_ratio(
                metric="icr",
                facts=data.facts,
                bindings=data.bindings,
                periods=data.periods,
                period_phase=phases,
                explicit_phases=bool(phases),
            )
            computed = {(row["axis_id"], row["period_id"]): row for row in result["rows"] if row.get("value") is not None}
        cached = _cached(data, model["row_key"])
        source = _cached(data, ebitda["row_key"])
        children = [row for row in _child_rows(data, model["row_key"]) if interest is None or row != interest["row_key"]]
        findings = []
        for period in data.periods:
            key = (period["axis_id"], period["period_id"])
            book = cached.get(key)
            source_value = _same_period(source, key)
            if _blank(book) and _numerator_blank(data, children, period["period_id"]) and source_value is not None:
                findings.append(
                    self.finding(
                        data,
                        row_key=model["row_key"],
                        axis_id=period["axis_id"],
                        period_id=period["period_id"],
                        params={
                            "cause": "empty_numerator",
                            "message": _INCOMPLETE_NUMERATOR,
                            "cells": _named_cells(
                                data, model["row_key"], ebitda["row_key"], children, period["period_id"]
                            ),
                        },
                    )
                )
                continue
            if _blank(book) and source_value is None:
                findings.append(
                    self.finding(
                        data,
                        row_key=model["row_key"],
                        axis_id=period["axis_id"],
                        period_id=period["period_id"],
                        params={"cause": "empty_source", "message": _EMPTY_REFERENCE, "cells": []},
                    )
                )
                continue
            fas = computed.get(key)
            if book is None or fas is None or abs(Decimal(fas["value"]) - book) <= _TOLERANCE:
                continue
            findings.append(
                self.finding(
                    data,
                    row_key=model["row_key"],
                    axis_id=period["axis_id"],
                    period_id=period["period_id"],
                    params={
                        "cause": "mismatch",
                        "message": _ICR_DIVERGENCE,
                        "fas": str(fas["value"]),
                        "model": str(book),
                    },
                )
            )
        return findings


def _blank(value: Decimal | None) -> bool:
    return value is None or value == 0


def _same_period(values: dict[tuple[str, str], Decimal], key: tuple[str, str]) -> Decimal | None:
    if key in values:
        return values[key]
    return next((item for (axis, period), item in values.items() if period == key[1] and axis != key[0]), None)


def _child_rows(data: AuditInput, row_key: str) -> list[str]:
    by_cell = {fact.get("cell_id"): fact.get("row_key") for fact in data.facts if fact.get("cell_id")}
    found: list[str] = []
    for link in data.links:
        if link.get("row_key") != row_key:
            continue
        child = by_cell.get(link.get("ref_cell"))
        if child and child not in found:
            found.append(child)
    return found


def _numerator_blank(data: AuditInput, rows: list[str], period_id: str) -> bool:
    if not rows:
        return False
    for row_key in rows:
        for fact in data.facts:
            if fact.get("row_key") == row_key and fact.get("period_id") == period_id and _fact_number(fact) is not None:
                return False
    return True


def _fact_number(fact: dict) -> Decimal | None:
    number = fact.get("normalized_value")
    if number is None:
        number = fact.get("value_dec")
    if number is None:
        return None
    return Decimal(str(number))


def _named_cells(
    data: AuditInput, ratio_row: str, ebitda_row: str, numerator_rows: list[str], period_id: str
) -> list[str]:
    cells = []
    for fact in data.facts:
        if fact.get("period_id") != period_id or not fact.get("cell_id"):
            continue
        if fact.get("row_key") == ebitda_row or fact.get("row_key") in numerator_rows:
            cells.append(fact["cell_id"])
    watched = {ratio_row, *numerator_rows}
    for link in data.links:
        ref = link.get("ref_cell")
        if link.get("row_key") in watched and ref and ref not in cells:
            cells.append(ref)
    return cells


class UnmappedInMetricChain(Rule):
    def check(self, data: AuditInput) -> list[Finding]:
        if not data.bindings:
            return []
        concept_of = {
            row["row_key"]: row.get("effective_concept") or row.get("concept")
            for row in data.bindings
            if row.get("is_primary") and row.get("status") in _BOUND and row.get("row_key")
        }
        watched = _chain_concepts(data)
        if not ({"dscr", "icr"} & watched) & set(concept_of.values()):
            return []
        parents = _parents(data)
        findings = []
        for row in data.bindings:
            if row.get("status") != "unknown" or not row.get("row_key"):
                continue
            reached = {concept_of[key] for key in _ancestors(parents, row["row_key"]) if key in concept_of}
            if {"debt_service", "interest"} & reached & watched:
                severity = "high"
            elif {"dscr", "icr"} & reached & watched:
                severity = "medium"
            else:
                continue
            findings.append(
                self.finding(
                    data,
                    row_key=row["row_key"],
                    severity=severity,
                    params={"status": "unknown"},
                )
            )
        return findings


ICR_REFERENCE = IcrReference(
    "icr_reference", "1", "quantitative", "low", ("ICR reference row",),
    "Справочный ICR книги сверен с расчётом FAS", ROWS_LINKS, 2,
)
RATIO_MISMATCH = RatioMismatch(
    "ratio_mismatch", "1", "quantitative", "high", ("DSCR model cache",),
    "Коэффициент расходится с кэшем модели", ROWS, 2,
)
MARKER_MIX = MarkerMix(
    "marker_mix", "1", "logic", "medium", ("period marker",),
    "В одном окне смешаны маркеры", ROWS_LINKS, 2,
)
UNMAPPED_IN_METRIC_CHAIN = UnmappedInMetricChain(
    "unmapped_in_metric_chain", "1", "omission", "medium", ("metric chain",),
    "В цепочке коэффициента есть непривязанная строка", ROWS_LINKS, 2,
)
