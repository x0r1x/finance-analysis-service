"""Расхождения коэффициента, смесь маркеров и дыра в цепочке (§6.1, фаза 2)."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal

from finance_analysis.domain.audit import (
    ROWS,
    ROWS_LINKS,
    AuditInput,
    Finding,
    Location,
    Rule,
    project_finance_dscr,
)
from finance_analysis.domain.metrics import coverage_ratio
from finance_analysis.domain.model_type import sheet_name_key
from finance_analysis.domain.periods import marker_class, split_period_key

_TOLERANCE = Decimal("0.005")
_BOUND = frozenset({"bound", "bound_with_warning"})
_EMPTY_REFERENCE = "справочная строка пуста"
_INCOMPLETE_NUMERATOR = "справочный расчёт книги неполон: числитель пуст"
_ICR_DIVERGENCE = "Справочный коэффициент книги расходится с расчётом FAS."
_ICR_AMBIGUOUS = "На оси расчёта ICR несколько справочных строк покрытия. Сверка не выполнена."
_STATEMENT_DIVERGENCE = "Строка модели расходится с отчётной формой на фактическом {grain}."
_ACTUAL_UNKNOWN = "фактические периоды не определены, сверка с отчётностью не выполнена"
_ACTUAL_AMBIGUOUS = "граница факта «{value}» неоднозначна, сверка с отчётностью не выполнена: {candidates}"
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


_CONFLICT = "conflict"


def _text(value) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _iso_date(text: str) -> date | None:
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _period_end(period: dict) -> date | None:
    raw = period.get("period_end")
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    if isinstance(raw, str) and raw:
        return _iso_date(raw[:10])
    return None


def _order(periods: list[dict]) -> list[dict]:
    def key(period: dict) -> tuple:
        index = period.get("period_index")
        if isinstance(index, bool) or not isinstance(index, int):
            index = 10**9
        return index, str(period.get("period_id") or "")

    return sorted(periods, key=key)


def _dedupe(periods: list[dict]) -> list[dict]:
    seen: set = set()
    found = []
    for period in _order(periods):
        pid = period.get("period_id")
        if pid in seen:
            continue
        seen.add(pid)
        found.append(period)
    return found


def _periods_through(periods: list[dict], value: str) -> tuple[list[dict], list[dict]]:
    """Периоды до границы включительно и кандидаты, если база на оси неоднозначна.

    Граница — `period_id`, `period_key_base` или дата конца. Ось без этой
    границы пропускается: `period_id` уникален только вместе с `axis_id`.
    Непустой второй список значит, что базу нельзя выбрать и окно пустое.
    """

    selected = []
    ambiguous: list[dict] = []
    by_axis: dict[str, list[dict]] = {}
    for period in periods:
        by_axis.setdefault(period.get("axis_id"), []).append(period)
    named = False
    for rows in by_axis.values():
        ordered = _order(rows)
        cut, extra = _boundary_cut(ordered, value)
        if extra:
            ambiguous.extend(extra)
            continue
        if cut is None:
            continue
        named = True
        selected.extend(ordered[: cut + 1])
    if ambiguous:
        return [], _unique_axis_periods(ambiguous)
    if named:
        return _dedupe(selected), []
    boundary = _iso_date(value)
    if boundary is None:
        return [], []
    return (
        _dedupe([period for period in periods if (end := _period_end(period)) is not None and end <= boundary]),
        [],
    )


def _boundary_cut(ordered: list[dict], value: str) -> tuple[int | None, list[dict]]:
    """Индекс границы на одной оси. Точный `period_id` важнее общей базы.

    Несколько периодов одной базы режутся только по единственному явному факту.
    Иначе второй элемент — все такие периоды, и границу не выбирают.
    """

    keys = [row.get("period_id") for row in ordered]
    if value in keys:
        return keys.index(value), []
    matches = [index for index, row in enumerate(ordered) if row.get("period_key_base") == value]
    if not matches:
        return None, []
    if len(matches) == 1:
        return matches[0], []
    actual = [index for index in matches if _clearly_actual(ordered[index])]
    if len(actual) == 1:
        return actual[0], []
    return None, [ordered[index] for index in matches]


_PLAN_CLASSES = frozenset({"plan", "estimate"})


def _marker_signals(period: dict) -> list[str]:
    """Класс, маркер и суффикс `period_id`, как их читает словарь маркеров."""

    seen = []
    klass = period.get("marker_class")
    if isinstance(klass, str) and klass.strip():
        seen.append(klass.strip())
    marker = period.get("period_marker")
    if isinstance(marker, str) and marker.strip():
        seen.append(marker_class(marker) or "other")
    suffix = _period_suffix(period.get("period_id"))
    if suffix:
        seen.append(marker_class(suffix) or "other")
    return seen


def _clearly_actual(period: dict) -> bool:
    """Класс `actual`, явный маркер факта или суффикс `period_id`. Противоречие — не факт."""

    seen = _marker_signals(period)
    return bool(seen) and set(seen) == {"actual"}


def _clearly_plan(period: dict) -> bool:
    """План или прогноз: достаточно одного сигнала класса `plan` или `estimate`."""

    return any(item in _PLAN_CLASSES for item in _marker_signals(period))


def _drop_plans(window: list[dict], keep_id: str | None) -> list[dict]:
    """План и прогноз из окна факта. Точный `period_id` явной границы остаётся сам."""

    return [
        period
        for period in window
        if not _clearly_plan(period) or (keep_id is not None and period.get("period_id") == keep_id)
    ]


def _period_suffix(period_id) -> str | None:
    if not isinstance(period_id, str):
        return None
    _base, marker = split_period_key(period_id)
    return marker


def _unique_axis_periods(periods: list[dict]) -> list[dict]:
    seen = set()
    found = []
    for period in periods:
        key = (period.get("axis_id"), period.get("period_id"))
        if key in seen:
            continue
        seen.add(key)
        found.append(period)
    return found


def _resolve_actuals(data: AuditInput) -> tuple | None:
    """Каскад границы факта: явное решение, маркер, профиль, затем структура.

    `("window", периоды, источник, граница)` — окно сверки. `("ambiguous",
    кандидаты, граница)` — база назвала несколько периодов и фактический не
    один. `None` — граница не определена: значение без периода или окно из одних планов.
    """

    decision = _text(data.actuals_end)
    marked = [period for period in data.periods if period.get("marker_class") == "actual"]
    config = _text((data.profile or {}).get("actuals_end"))
    if decision:
        return _named_window(data, decision, "explicit")
    if marked:
        ordered = _drop_plans(_dedupe(marked), None)
        if not ordered:
            return None
        return ("window", ordered, "explicit", str(ordered[-1].get("period_id")))
    if config:
        return _named_window(data, config, "explicit")
    end = _structural_end(data)
    if end is None:
        return None
    return _named_window(data, end, "structural")


def _named_window(data: AuditInput, value: str, source: str) -> tuple | None:
    window, ambiguous = _periods_through(data.periods, value)
    if ambiguous:
        return ("ambiguous", ambiguous, value)
    kept = _drop_plans(window, value if source == "explicit" else None)
    if not kept:
        return None
    return ("window", kept, source, value)


def _structural_end(data: AuditInput) -> str | None:
    """Последний фактический период, если смена формулы и охват формы называют одно и то же."""

    formula = _agreed(_formula_cuts(data))
    span = _agreed(_span_cuts(data))
    if formula in (None, _CONFLICT) or span in (None, _CONFLICT) or formula != span:
        return None
    return formula


def _agreed(cuts: list[str | None]) -> str | None:
    present = [cut for cut in cuts if cut]
    if not present:
        return None
    if len(set(present)) != 1:
        return _CONFLICT
    return present[0]


def _formula_cuts(data: AuditInput) -> list[str | None]:
    cuts = []
    for concept in _STATEMENT_CONCEPTS:
        primary = _primary(data, concept)
        if primary is None:
            continue
        cuts.append(_formula_cut(data, primary))
    return cuts


def _formula_cut(data: AuditInput, primary: dict) -> str | None:
    """Последний ввод перед формулами на оси основной строки. Смешанный ряд границу не даёт."""

    grain = _primary_grain(data, primary)
    row_key = primary.get("row_key")
    if not row_key:
        return None
    agreed = _agreed(
        [_formula_switch(data, row_key, _axis_periods(data, axis, grain)) for axis in _row_axes(data, row_key)]
    )
    return None if agreed in (None, _CONFLICT) else agreed


def _formula_switch(data: AuditInput, row_key: str | None, timeline: list[dict]) -> str | None:
    kinds = [_cell_kind(data, row_key, period) for period in timeline]
    compact = [(period, kind) for period, kind in zip(timeline, kinds, strict=True) if kind != "blank"]
    if not compact:
        return None
    labels = [kind for _, kind in compact]
    inputs = labels.count("input")
    if inputs == 0 or "formula" not in labels:
        return None
    if labels != ["input"] * inputs + ["formula"] * (len(labels) - inputs):
        return None
    return str(compact[inputs - 1][0].get("period_id"))


def _cell_kind(data: AuditInput, row_key: str | None, period: dict) -> str:
    facts = [
        fact
        for fact in data.facts
        if fact.get("row_key") == row_key
        and fact.get("period_id") == period.get("period_id")
        and fact.get("axis_id") == period.get("axis_id")
    ]
    if not facts:
        return "blank"
    if any(_fact_formula(data, fact) for fact in facts):
        return "formula"
    if any(_fact_number(fact) is not None for fact in facts):
        return "input"
    return "blank"


def _fact_formula(data: AuditInput, fact: dict) -> bool:
    cell = fact.get("cell_id")
    if cell and cell in data.link_cells:
        return True
    return any(
        link.get("row_key") == fact.get("row_key")
        and link.get("period_id") == fact.get("period_id")
        and (link.get("formula") or link.get("cell"))
        for link in data.links
    )


def _span_cuts(data: AuditInput) -> list[str | None]:
    cuts = []
    for concept in _STATEMENT_CONCEPTS:
        primary = _primary(data, concept)
        if primary is None:
            continue
        grain = _primary_grain(data, primary)
        for ref in _form_rows(data, concept, primary):
            for axis in _row_axes(data, ref["row_key"]):
                cuts.append(_span_cut(data, _axis_periods(data, axis, grain), ref["row_key"]))
    return cuts


def _span_cut(data: AuditInput, timeline: list[dict], row_key: str) -> str | None:
    """Последний заполненный период формы перед пустым хвостом. Только ось этой строки."""

    if not timeline:
        return None
    values = _cached(data, row_key)
    filled = [(period.get("axis_id"), period.get("period_id")) in values for period in timeline]
    if not any(filled) or all(filled):
        return None
    gap = filled.index(False)
    if any(filled[gap:]):
        return None
    return str(timeline[gap - 1].get("period_id"))


def _axis_periods(data: AuditInput, axis_id: str, grain: str | None) -> list[dict]:
    return _order(
        [period for period in data.periods if period.get("axis_id") == axis_id and _grain_ok(period, grain)]
    )


def _grain_ok(period: dict, grain: str | None) -> bool:
    if grain is None:
        return True
    return str(period.get("grain") or grain).lower() == grain


class StatementReference(Rule):
    """Сверяет основную строку модели со строкой отчётной формы.

    Строка формы — привязанная строка того же понятия на листе формы. Роль
    `reference` по решению 40 остаётся только у копии, чьи значения уже совпали,
    и здесь заново не назначается. Сверяются фактические периоды той же
    зернистости, что у основной строки. Граница факта — каскад `actuals_end`:
    решение, маркер или профиль, иначе согласованный структурный срез.
    Проценты в сверку не входят. Правило не переносит основную строку.
    """

    def check(self, data: AuditInput) -> list[Finding]:
        resolved = _resolve_actuals(data)
        if resolved is None:
            if data.periods and _has_statement_pair(data):
                return [
                    self.finding(
                        data,
                        params={"cause": "actual_unknown", "message": _ACTUAL_UNKNOWN},
                    )
                ]
            return []
        if resolved[0] == "ambiguous":
            if not _has_statement_pair(data):
                return []
            return [_ambiguous_boundary(self, data, resolved[1], resolved[2])]
        _kind, actual, source, end = resolved
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
                                "actuals_source": source,
                                "actuals_end": end,
                                "cells": _named_cells(
                                    data, primary["row_key"], ref["row_key"], [], period["period_id"]
                                ),
                            },
                        )
                    )
        return findings


def _ambiguous_boundary(rule: StatementReference, data: AuditInput, periods: list[dict], value: str) -> Finding:
    """Одна находка: база назвала несколько периодов, и фактический среди них не один."""

    labels = [_candidate_label(data, period) for period in periods]
    cells = [cell for period in periods for cell in _period_cells(data, period)]
    return rule.finding(
        data,
        locations=_candidate_locations(data, periods),
        params={
            "cause": "actuals_end_ambiguous",
            "message": _ACTUAL_AMBIGUOUS.format(value=value, candidates=", ".join(labels)),
            "actuals_end": value,
            "candidates": [str(period.get("period_id")) for period in periods],
            "cells": cells,
        },
    )


def _candidate_label(data: AuditInput, period: dict) -> str:
    pid = str(period.get("period_id"))
    cells = _period_cells(data, period)
    if not cells:
        return pid
    return f"{pid} ({', '.join(cells)})"


def _period_cells(data: AuditInput, period: dict) -> list[str]:
    cells = []
    for fact in data.facts:
        cell = fact.get("cell_id")
        if (
            cell
            and fact.get("axis_id") == period.get("axis_id")
            and fact.get("period_id") == period.get("period_id")
            and cell not in cells
        ):
            cells.append(cell)
    return cells


def _candidate_locations(data: AuditInput, periods: list[dict]) -> list[Location]:
    found = []
    seen = set()
    for period in periods:
        axis = period.get("axis_id")
        pid = period.get("period_id")
        placed = False
        for fact in data.facts:
            cell = fact.get("cell_id")
            key = (cell, fact.get("row_key"), axis, pid)
            if fact.get("axis_id") != axis or fact.get("period_id") != pid or not cell or key in seen:
                continue
            seen.add(key)
            found.append(Location(cell, fact.get("row_key"), axis, pid))
            placed = True
        if not placed:
            found.append(Location(None, None, axis, pid))
    return found


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
