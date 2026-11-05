"""Расхождения коэффициента, смесь маркеров и дыра в цепочке (§6.1, фаза 2)."""

from __future__ import annotations

import json
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
from finance_analysis.domain.model_type import sheet_name_key

_TOLERANCE = Decimal("0.005")
_BOUND = frozenset({"bound", "bound_with_warning"})
_EMPTY_REFERENCE = "справочная строка пуста"
_INCOMPLETE_NUMERATOR = "справочный расчёт книги неполон: числитель пуст"
_ICR_DIVERGENCE = "Справочный коэффициент книги расходится с расчётом FAS."
_ICR_AMBIGUOUS = "На оси расчёта ICR несколько справочных строк покрытия. Сверка не выполнена."
_STATEMENT_DIVERGENCE = "Строка модели расходится с отчётной формой на фактическом {grain}."
_ACTUAL_UNKNOWN = "фактические периоды не определены, сверка с отчётностью не выполнена"
# Проценты не сверяются: начисление и уплата — разные основания, это сравнение отложено.
_STATEMENT_CONCEPTS = ("revenue", "operating_profit", "net_income")
_GRAIN_WORD = {"quarter": "квартале", "month": "месяце", "year": "году"}


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
        ebitda = _primary(data, "ebitda")
        if ebitda is None or not data.periods:
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
                facts=_scaled_facts(data),
                bindings=data.bindings,
                periods=data.periods,
                period_phase=phases,
                explicit_phases=bool(phases),
            )
            computed = {(row["axis_id"], row["period_id"]): row for row in result["rows"] if row.get("value") is not None}
        fas_axes = {axis for axis, _period in computed}
        if not fas_axes:
            fas_axes = _row_axes(data, ebitda["row_key"])
        reference = _coverage_reference(data, fas_axes, None if interest is None else interest["row_key"])
        if reference is None:
            return []
        if reference == "ambiguous":
            return [
                self.finding(
                    data,
                    params={"cause": "ambiguous", "message": _ICR_AMBIGUOUS},
                )
            ]
        model_key = reference
        ref_axes = _row_axes(data, model_key) & fas_axes or _row_axes(data, model_key)
        if not ref_axes:
            ref_axes = {period["axis_id"] for period in data.periods if period.get("axis_id")}
        cached = _cached(data, model_key)
        source = _cached(data, ebitda["row_key"])
        children = [row for row in _child_rows(data, model_key) if interest is None or row != interest["row_key"]]
        findings = []
        seen: set[str] = set()
        for period in data.periods:
            if period["axis_id"] not in ref_axes:
                continue
            period_id = period["period_id"]
            if period_id in seen:
                continue
            seen.add(period_id)
            key = (period["axis_id"], period_id)
            book = cached.get(key)
            source_value = _same_period(source, key)
            if _blank(book) and _numerator_blank(data, children, period_id) and source_value is not None:
                findings.append(
                    self.finding(
                        data,
                        row_key=model_key,
                        axis_id=period["axis_id"],
                        period_id=period_id,
                        params={
                            "cause": "empty_numerator",
                            "message": _INCOMPLETE_NUMERATOR,
                            "cells": _named_cells(data, model_key, ebitda["row_key"], children, period_id),
                        },
                    )
                )
                continue
            if _blank(book) and source_value is None:
                findings.append(
                    self.finding(
                        data,
                        row_key=model_key,
                        axis_id=period["axis_id"],
                        period_id=period_id,
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
                    row_key=model_key,
                    axis_id=period["axis_id"],
                    period_id=period_id,
                    params={
                        "cause": "mismatch",
                        "message": _ICR_DIVERGENCE,
                        "fas": str(fas["value"]),
                        "model": str(book),
                    },
                )
            )
        return findings


def _scaled_facts(data: AuditInput) -> list[dict]:
    """Масштаб строки из проекции, как в расчёте коэффициентов.

    В факте масштаба нет: он лежит в строке. Без него нормализованная EBITDA
    делится на проценты в единицах листа, и справочный ICR расходится в тысячу раз.
    """

    scale_of = {
        str(row.get("row_key")): row.get("scale_factor")
        for row in data.rows
        if row.get("row_key") and row.get("scale_factor") not in (None, "")
    }
    if not scale_of:
        return data.facts
    stamped = []
    for fact in data.facts:
        if fact.get("scale_factor") not in (None, ""):
            stamped.append(fact)
            continue
        scale = scale_of.get(str(fact.get("row_key")))
        stamped.append(fact if scale is None else {**fact, "scale_factor": scale})
    return stamped


def _row_axes(data: AuditInput, row_key: str) -> set[str]:
    return {fact.get("axis_id") for fact in data.facts if fact.get("row_key") == row_key and fact.get("axis_id")}


def _bound_rows(data: AuditInput, concept: str) -> list[str]:
    found = []
    for row in data.bindings:
        if row.get("status") not in _BOUND:
            continue
        if (row.get("effective_concept") or row.get("concept")) != concept or not row.get("row_key"):
            continue
        if row["row_key"] not in found:
            found.append(row["row_key"])
    return found


def _coverage_reference(data: AuditInput, fas_axes: set[str], interest_key: str | None) -> str | None:
    """Строка покрытия на оси расчёта FAS.

    Сначала берётся формула, которая делит строку EBITDA на строку процентов.
    Если такой формулы нет, берётся привязка `icr` на той же оси. Строка `icr`
    на другой оси, в том числе на листе итогов, справочником не становится.
    Несколько кандидатов одного вида дают одну пометку неоднозначности.
    """

    ebitda_keys = set(_bound_rows(data, "ebitda"))
    if not fas_axes:
        labeled = _bound_rows(data, "icr")
        if len(labeled) > 1:
            return "ambiguous"
        return labeled[0] if labeled else None
    formula_rows = []
    if interest_key and ebitda_keys:
        children = _children_by_row(data)
        for row_key, refs in children.items():
            if row_key in ebitda_keys or row_key == interest_key:
                continue
            if interest_key not in refs or not (refs & ebitda_keys):
                continue
            if not (_row_axes(data, row_key) & fas_axes):
                continue
            if row_key not in formula_rows:
                formula_rows.append(row_key)
    if len(formula_rows) > 1:
        return "ambiguous"
    if len(formula_rows) == 1:
        return formula_rows[0]
    labeled = [
        row_key
        for row_key in _bound_rows(data, "icr")
        if _row_axes(data, row_key) & fas_axes
    ]
    if len(labeled) > 1:
        return "ambiguous"
    if len(labeled) == 1:
        return labeled[0]
    return None


def _children_by_row(data: AuditInput) -> dict[str, set[str]]:
    by_cell = {fact.get("cell_id"): fact.get("row_key") for fact in data.facts if fact.get("cell_id")}
    found: dict[str, set[str]] = {}
    for link in data.links:
        parent = link.get("row_key")
        child = by_cell.get(link.get("ref_cell"))
        if parent and child:
            found.setdefault(parent, set()).add(child)
    return found


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


class StatementReference(Rule):
    """Сверяет основную строку модели со строкой отчётной формы.

    Строка формы — привязанная строка того же понятия на листе формы. Роль
    `reference` по решению 40 остаётся только у копии, чьи значения уже совпали,
    и здесь заново не назначается. Сверяются фактические периоды той же
    зернистости, что у основной строки. Проценты в сверку не входят.
    Правило не переносит основную строку.
    """

    def check(self, data: AuditInput) -> list[Finding]:
        actual = [period for period in data.periods if period.get("marker_class") == "actual"]
        if not actual:
            if data.periods and _has_statement_pair(data):
                return [
                    self.finding(
                        data,
                        params={"cause": "actual_unknown", "message": _ACTUAL_UNKNOWN},
                    )
                ]
            return []
        findings = []
        for concept in _STATEMENT_CONCEPTS:
            primary = _primary(data, concept)
            if primary is None:
                continue
            grain = _primary_grain(data, primary)
            comparable = _same_grain(actual, grain)
            message = _STATEMENT_DIVERGENCE.format(grain=_grain_word(grain))
            model_values = _cached(data, primary["row_key"])
            for ref in _form_rows(data, concept, primary):
                reported = _cached(data, ref["row_key"])
                for period in comparable:
                    key = (period["axis_id"], period["period_id"])
                    left = _same_period(model_values, key)
                    right = _same_period(reported, key)
                    if left is None or right is None or _within(left, right):
                        continue
                    findings.append(
                        self.finding(
                            data,
                            row_key=primary["row_key"],
                            axis_id=period["axis_id"],
                            period_id=period["period_id"],
                            params={
                                "concept": concept,
                                "message": message,
                                "model": str(left),
                                "reported": str(right),
                                "cells": _named_cells(
                                    data, primary["row_key"], ref["row_key"], [], period["period_id"]
                                ),
                            },
                        )
                    )
        return findings


def _form_rows(data: AuditInput, concept: str, primary: dict) -> list[dict]:
    """Строки формы того же понятия, которые остались привязанными и не стали основными.

    Роль `reference` тоже принимается: это копия, и расхождение с ней всё ещё находка.
    Лист формы узнаётся по именам, которые передал аудит. Роль строке не назначается.
    """

    found = []
    for row in data.bindings:
        if not row.get("row_key") or row.get("row_key") == primary.get("row_key"):
            continue
        if (row.get("effective_concept") or row.get("concept")) != concept:
            continue
        if row.get("status") not in _BOUND:
            continue
        if _role(row) == "reference" or _on_statement_sheet(data, row["row_key"]):
            found.append(row)
    return found


def _has_statement_pair(data: AuditInput) -> bool:
    """Есть основная строка и строка формы одного понятия отчётности."""

    for concept in _STATEMENT_CONCEPTS:
        primary = _primary(data, concept)
        if primary is not None and _form_rows(data, concept, primary):
            return True
    return False


def _on_statement_sheet(data: AuditInput, row_key: str) -> bool:
    sheet = str((data.rows_by_key.get(row_key) or {}).get("sheet") or "")
    if not sheet:
        return False
    folded = sheet_name_key(sheet)
    return any(folded == sheet_name_key(name) for name in data.statement_sheets)


def _primary_grain(data: AuditInput, primary: dict) -> str | None:
    """Зернистость основной строки. Несколько зерён или их отсутствие не угадываются."""

    axes = {fact.get("axis_id") for fact in data.facts if fact.get("row_key") == primary.get("row_key")}
    grains = {
        str(period.get("grain")).lower()
        for period in data.periods
        if period.get("axis_id") in axes and period.get("grain")
    }
    if len(grains) == 1:
        return next(iter(grains))
    return None


def _same_grain(periods: list[dict], grain: str | None) -> list[dict]:
    """Оставляет периоды зернистости основной строки. Без известного зерна список не режется."""

    if grain is None:
        return periods
    return [period for period in periods if str(period.get("grain") or grain).lower() == grain]


def _grain_word(grain: str | None) -> str:
    return _GRAIN_WORD.get(grain or "", "квартале")


def _role(row: dict) -> str | None:
    evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
    if not evidence:
        raw = row.get("evidence_json")
        if isinstance(raw, str) and raw:
            try:
                loaded = json.loads(raw)
            except json.JSONDecodeError:
                loaded = {}
            evidence = loaded if isinstance(loaded, dict) else {}
    return evidence.get("role") or row.get("role")


def _within(left: Decimal, right: Decimal) -> bool:
    scale = max(abs(left), abs(right))
    if scale == 0:
        return True
    return abs(left - right) / scale <= _TOLERANCE


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


STATEMENT_REFERENCE = StatementReference(
    "statement_reference", "1", "quantitative", "low", ("actual quarter",),
    "На факте строка модели сверена с отчётной формой", ROWS, 2,
)
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
