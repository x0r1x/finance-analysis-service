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
from finance_analysis.domain.measure import (
    dependency_measure,
    metadata_factor,
    stamp_facts,
)
from finance_analysis.domain.metrics import coverage_ratio
from finance_analysis.domain.model_type import sheet_name_key
from finance_analysis.domain.period_basis import basis_of
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
_TRACED_AMBIGUOUS = "граница фактов неоднозначна, сверка с отчётностью не выполнена: {candidates}"
_FORECAST_ASSUMPTION = "допущения прогноза, не факт"
_CLASS_REPORTING = frozenset({"reporting", "отчетность"})
_CLASS_ASSUMPTIONS = frozenset({"assumptions", "предпосылки"})
_YTD_GAP = "для сверки нарастающего итога на {period} не хватает значения модели за {missing}, период пропущен"
_YTD_NO_YEAR = "для сверки нарастающего итога на {period} год не определён, период пропущен"
_NO_REPORTING = "на листах reporting нет ввода, который читают формулы"
_NO_YEAR = "year"
_AXIS_MISS = "значение границы фактов не попало на ось сверяемой строки"
_NO_OVERLAP = "факт заканчивается на {end}, форма начинается с {start}, общих периодов для сверки нет"
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
    Конкретная единица строки копируется на факт тем же шагом. Обход формулы
    остаётся у правила размерности и у масштаба формы, а не у каждого факта.
    """

    return stamp_facts(data.facts, data.rows, data.unit_dimensions)


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
    """Одинаковый `period_id` на разных осях — разные периоды."""

    seen: set[tuple] = set()
    found = []
    for period in _order(periods):
        key = (period.get("axis_id"), period.get("period_id"))
        if key in seen:
            continue
        seen.add(key)
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
    boundary = _structural_boundary(data)
    if boundary is None:
        return None
    if boundary[0] == "traced_ambiguous":
        return boundary
    source, end, cells, *rest = boundary
    resolved = _named_window(data, end, source)
    if resolved is None or resolved[0] != "window":
        return resolved
    return (*resolved, cells, rest[0] if rest else [])


def _named_window(data: AuditInput, value: str, source: str) -> tuple | None:
    window, ambiguous = _periods_through(data.periods, value)
    if ambiguous:
        return ("ambiguous", ambiguous, value)
    kept = _drop_plans(window, value if source == "explicit" else None)
    if not kept:
        return None
    return ("window", kept, source, value)


def _structural_boundary(data: AuditInput) -> tuple[str, str, list[str]] | None:
    """Срез по своей строке или по прослеженному вводу, если строка целиком из формул.

    Ненулевое значение прогноза фактом не считается. Строка целиком из ввода даёт
    последнюю ячейку ввода, которая питает цепочку, без перехода в формулу на ней.
    Несколько настоящих дат не выбираются молча: это «граница фактов неоднозначна».
    """

    formula = _agreed(_formula_cuts(data))
    span = _agreed(_span_cuts(data))
    if formula not in (None, _CONFLICT) and span not in (None, _CONFLICT) and formula == span:
        return "structural", formula, []
    if formula not in (None, _CONFLICT) or span == _CONFLICT:
        return None
    traced = _traced_boundary(data)
    if traced is None:
        return None
    if traced[0] == "ambiguous":
        return ("traced_ambiguous", traced[1], traced[2] if len(traced) > 2 else [])
    period_id, cells, both = traced[1], traced[2], traced[3]
    diagnostics = traced[4] if len(traced) > 4 else []
    if not _trace_accepted(data, period_id, span, both):
        return None
    return "structural_traced", period_id, cells, diagnostics


def _sheet_classes(data: AuditInput) -> dict[str, str]:
    """Класс листа из профиля `sheet_class`. Пустой словарь — класс по имени не угадывается."""

    raw = (data.profile or {}).get("sheet_class")
    if not isinstance(raw, dict):
        return {}
    found = {}
    for name, klass in raw.items():
        if not isinstance(name, str) or not name.strip():
            continue
        token = str(klass or "").casefold().replace("ё", "е").strip()
        if token in _CLASS_REPORTING:
            found[sheet_name_key(name)] = "reporting"
        elif token in _CLASS_ASSUMPTIONS:
            found[sheet_name_key(name)] = "assumptions"
    return found


def _cell_sheet(cell: str) -> str:
    return cell.split("!", 1)[0] if "!" in cell else ""


def _reporting_traced(data: AuditInput, classes: dict[str, str]) -> tuple | None:
    """Общая граница книги: последний ввод отчётности, который формулы реально читают.

    Более ранний ввод отчётности не спорит. Ввод допущений границу не двигает.
    """

    reporting: list[dict] = []
    assumptions: list[dict] = []
    seen: set[str] = set()
    targets: list[str] = []
    saw = False
    for concept in _STATEMENT_CONCEPTS:
        primary = _primary(data, concept)
        if primary is None or not _all_formula(data, primary.get("row_key")):
            continue
        saw = True
        targets.extend(_row_axes(data, primary.get("row_key")))
        keys = [primary.get("row_key")]
        keys.extend(ref.get("row_key") for ref in _form_rows(data, concept, primary))
        for key in keys:
            if not key:
                continue
            for refs in _precedent_refs(data, key).values():
                for ref in refs:
                    if not ref or ref in seen:
                        continue
                    fact = data.facts_by_cell.get(ref)
                    if fact is None or not fact.get("cell_id"):
                        continue
                    if _fact_formula(data, fact) or _fact_number(fact) is None:
                        continue
                    seen.add(ref)
                    kind = classes.get(sheet_name_key(_cell_sheet(ref)))
                    if kind == "reporting":
                        reporting.append(fact)
                    elif kind == "assumptions":
                        assumptions.append(fact)
    if not saw:
        return None
    notes = _assumption_notes(data, assumptions)
    if not reporting:
        return ("ambiguous", [], notes)
    latest = _tied_latest(data, reporting)
    mapped: list[str] = []
    cells: list[str] = []
    for fact in latest:
        boundary = _one_boundary(data, fact, targets)
        cell = str(fact.get("cell_id"))
        if boundary is None:
            return ("ambiguous", _cuts_of(data, latest), notes)
        mapped.append(boundary)
        if cell not in cells:
            cells.append(cell)
    agreed = _agree_boundaries(data, mapped)
    if agreed is None:
        grouped: dict[str, list[str]] = {}
        for period, cell in zip(mapped, cells, strict=True):
            _remember_cut(grouped, period, [cell])
        return ("ambiguous", _ordered_cuts(data, grouped), notes)
    return ("cut", agreed, cells, True, notes)


def _cuts_of(data: AuditInput, facts: list[dict]) -> list[tuple[str, list[str]]]:
    grouped: dict[str, list[str]] = {}
    for fact in facts:
        _remember_cut(grouped, str(fact.get("period_id")), [str(fact.get("cell_id"))])
    return _ordered_cuts(data, grouped)


def _one_boundary(data: AuditInput, fact: dict, targets: list[str]) -> str | None:
    """Один логический период на осях сверки. Разные `period_id` одной даты конца — не две границы."""

    periods = []
    seen: set[tuple] = set()
    for axis in dict.fromkeys(targets):
        item = _map_cut(data, str(fact.get("row_key")), str(fact.get("period_id")), axis)
        if not item or (axis, item) in seen:
            continue
        seen.add((axis, item))
        period = next(
            (row for row in data.periods if row.get("axis_id") == axis and str(row.get("period_id")) == str(item)),
            None,
        )
        if period is not None:
            periods.append(period)
    if not periods:
        return None
    ids = list(dict.fromkeys(str(period.get("period_id")) for period in periods))
    if len(ids) == 1:
        return ids[0]
    ends = [_period_end(period) for period in periods]
    if all(end is not None for end in ends) and len(set(ends)) == 1:
        return ends[0].isoformat()
    return None


def _agree_boundaries(data: AuditInput, values: list[str]) -> str | None:
    if not values:
        return None
    if len(set(values)) == 1:
        return values[0]
    ends = []
    for value in values:
        parsed = _iso_date(value)
        if parsed is not None:
            ends.append(parsed)
            continue
        found = {
            end
            for period in data.periods
            if str(period.get("period_id")) == value and (end := _period_end(period)) is not None
        }
        if len(found) != 1:
            return None
        ends.append(next(iter(found)))
    if len(set(ends)) != 1:
        return None
    return ends[0].isoformat()


def _assumption_notes(data: AuditInput, facts: list[dict]) -> list[dict]:
    notes = []
    seen: set[str] = set()
    for fact in sorted(facts, key=lambda item: (*_input_rank(data, item), str(item.get("cell_id") or ""))):
        cell = str(fact.get("cell_id"))
        if cell in seen:
            continue
        seen.add(cell)
        notes.append({"cell": cell, "period": str(fact.get("period_id")), "message": _FORECAST_ASSUMPTION})
    return notes


def _traced_boundary(data: AuditInput) -> tuple | None:
    classes = _sheet_classes(data)
    if classes:
        return _reporting_traced(data, classes)
    grouped: dict[str, list[str]] = {}
    main_ids: set[str] = set()
    form_ids: set[str] = set()
    saw = False
    for concept in _STATEMENT_CONCEPTS:
        primary = _primary(data, concept)
        if primary is None or not _all_formula(data, primary.get("row_key")):
            continue
        saw = True
        for period, group in _trace_row(data, primary.get("row_key")):
            main_ids.add(period)
            _remember_cut(grouped, period, group)
        for ref in _form_rows(data, concept, primary):
            for period, group in _trace_row(data, ref.get("row_key")):
                form_ids.add(period)
                _remember_cut(grouped, period, group)
    if not saw or not grouped:
        return None
    ordered = _ordered_cuts(data, grouped)
    if len(ordered) > 1:
        return ("ambiguous", ordered, [])
    period, cells = ordered[0]
    both = period in main_ids and form_ids == {period}
    return ("cut", period, cells, both, [])


def _remember_cut(grouped: dict[str, list[str]], period: str, cells: list[str]) -> None:
    bucket = grouped.setdefault(period, [])
    for cell in cells:
        if cell not in bucket:
            bucket.append(cell)


def _ordered_cuts(data: AuditInput, grouped: dict[str, list[str]]) -> list[tuple[str, list[str]]]:
    def rank(period_id: str) -> tuple:
        ends = []
        indexes = []
        for period in data.periods:
            if period.get("period_id") != period_id:
                continue
            end = _period_end(period)
            if end is not None:
                ends.append(end)
            index = period.get("period_index")
            if isinstance(index, int) and not isinstance(index, bool):
                indexes.append(index)
        return (min(ends) if ends else date.max, min(indexes) if indexes else 10**9, period_id)

    return [(period, sorted(grouped[period])) for period in sorted(grouped, key=rank)]


def _trace_accepted(data: AuditInput, period_id: str, span: str | None, both: bool) -> bool:
    if span == period_id:
        return True
    if span is not None:
        return False
    if both:
        return True
    return _form_starts_after(data, period_id)


def _all_formula(data: AuditInput, row_key: str | None) -> bool:
    saw = False
    for fact in data.facts:
        if fact.get("row_key") != row_key:
            continue
        if _fact_number(fact) is None and not _fact_formula(data, fact):
            continue
        if not _fact_formula(data, fact):
            return False
        saw = True
    return saw


def _trace_row(data: AuditInput, row_key: str | None) -> list[tuple[str, list[str]]]:
    """Срезы прецедентов, которые реально питают строку. Разные даты не схлопываются."""

    if not row_key:
        return []
    targets = _row_axes(data, row_key)
    found: list[tuple[str, list[str]]] = []
    for other, refs in _precedent_refs(data, row_key).items():
        chosen = _precedent_cut(data, other, refs)
        if chosen is None:
            continue
        cut, cells = chosen
        mapped = next((item for axis in targets if (item := _map_cut(data, other, cut, axis))), None)
        if mapped is None:
            continue
        found.append((mapped, cells))
    return found


def _precedent_cut(data: AuditInput, row_key: str, refs: list[str]) -> tuple[str, list[str]] | None:
    """Срез строки прецедента. Чужой период формулы и чужое понятие срез не дают."""

    switched = _row_switch(data, row_key)
    if switched is not None and _formula_periods_match(data, row_key):
        cells = [cell for cell in _input_cells(data, row_key, switched) if cell in refs]
        if cells:
            return switched, cells
    leaf = _latest_hardcoded(data, row_key, refs)
    if leaf is None:
        return None
    return str(leaf.get("period_id")), [str(leaf["cell_id"])]


def _formula_periods_match(data: AuditInput, row_key: str) -> bool:
    """Период формулы в графе совпадает с периодом её факта. Иначе смена ввода ложная."""

    saw = False
    for fact in data.facts:
        if fact.get("row_key") != row_key:
            continue
        cell = fact.get("cell_id")
        link = data.link_cells.get(cell) if cell else None
        if link is None:
            continue
        saw = True
        if not _link_period_on_axis(data, fact, link.period_id, cell):
            return False
    return saw


def _link_period_on_axis(data: AuditInput, fact: dict, period_id, cell: str | None) -> bool:
    """Период формулы — пара оси факта и `period_id`, а не одноимённый период чужой оси."""

    if period_id != fact.get("period_id"):
        return False
    axis = fact.get("axis_id")
    owner = data.facts_by_cell.get(cell) if cell else None
    if owner is not None and owner.get("axis_id") != axis:
        return False
    if axis is None:
        return True
    return any(item.get("axis_id") == axis and item.get("period_id") == period_id for item in data.periods)


def _row_switch(data: AuditInput, row_key: str) -> str | None:
    agreed = _agreed(
        [
            _formula_switch(
                data,
                row_key,
                _order([period for period in data.periods if period.get("axis_id") == axis]),
            )
            for axis in _row_axes(data, row_key)
        ]
    )
    return None if agreed in (None, _CONFLICT) else agreed


def _map_cut(data: AuditInput, source_row: str, period_id: str, target_axis: str) -> str | None:
    sources = [
        period
        for period in data.periods
        if period.get("period_id") == period_id and period.get("axis_id") in _row_axes(data, source_row)
    ]
    targets = [period for period in data.periods if period.get("axis_id") == target_axis]
    for source in sources:
        for target in targets:
            if target.get("period_id") == source.get("period_id"):
                return str(target.get("period_id"))
    for source in sources:
        end = _period_end(source)
        if end is None:
            continue
        for target in targets:
            if _period_end(target) == end:
                return str(target.get("period_id"))
    return None


def _input_cells(data: AuditInput, row_key: str, period_id: str) -> list[str]:
    cells = []
    for fact in data.facts:
        if fact.get("row_key") != row_key or fact.get("period_id") != period_id or _fact_formula(data, fact):
            continue
        cell = fact.get("cell_id")
        if cell and cell not in cells and _fact_number(fact) is not None:
            cells.append(cell)
    return cells


def _precedent_refs(data: AuditInput, row_key: str) -> dict[str, list[str]]:
    """Ячейки прецедентов, до которых доходит цепочка. Формулы проходятся, ввод — нет."""

    seen: set[str] = set()
    found: dict[str, list[str]] = {}
    stack = [fact.get("cell_id") for fact in data.facts if fact.get("row_key") == row_key and fact.get("cell_id")]
    while stack:
        cell = stack.pop()
        if not cell or cell in seen:
            continue
        seen.add(cell)
        for ref in _refs_of(data, cell):
            other = data.facts_by_cell.get(ref)
            if other is None or not other.get("row_key"):
                continue
            key = str(other.get("row_key"))
            if key != row_key:
                bucket = found.setdefault(key, [])
                if ref not in bucket:
                    bucket.append(ref)
            nxt = other.get("cell_id")
            if nxt and _fact_formula(data, other):
                stack.append(nxt)
    return found


def _latest_hardcoded(data: AuditInput, row_key: str, refs: list[str]) -> dict | None:
    """Последний ввод строки без формул среди ячеек, которые цепочка реально читает."""

    if any(fact.get("row_key") == row_key and _fact_formula(data, fact) for fact in data.facts):
        return None
    leaves = []
    for ref in refs:
        fact = data.facts_by_cell.get(ref)
        if fact is None or fact.get("row_key") != row_key or not fact.get("cell_id"):
            continue
        if _fact_formula(data, fact) or _fact_number(fact) is None:
            continue
        leaves.append(fact)
    if not leaves:
        return None
    latest = _tied_latest(data, leaves)
    if len(latest) == 1 or len({fact.get("axis_id") for fact in latest}) == 1:
        return latest[-1]
    ends = [_period_end(_fact_period(data, fact) or {}) for fact in latest]
    if any(end is None for end in ends) or len(set(ends)) != 1:
        return None
    return latest[0]


def _fact_period(data: AuditInput, fact: dict) -> dict | None:
    return next(
        (
            item
            for item in data.periods
            if item.get("axis_id") == fact.get("axis_id") and item.get("period_id") == fact.get("period_id")
        ),
        None,
    )


def _input_rank(data: AuditInput, fact: dict) -> tuple:
    """Дата конца. Индекс периода сравнивается только внутри одной оси, в `_tied_latest`."""

    end = _period_end(_fact_period(data, fact) or {})
    return (end is not None, end or date.min)


def _tied_latest(data: AuditInput, facts: list[dict]) -> list[dict]:
    """Последние по дате. Номер периода чужой оси эту дату не выбирает."""

    if not facts:
        return []
    best = max(_input_rank(data, fact) for fact in facts)
    latest = [fact for fact in facts if _input_rank(data, fact) == best]
    if len({fact.get("axis_id") for fact in latest}) != 1:
        return latest

    def index(fact: dict) -> int:
        period = _fact_period(data, fact)
        value = period.get("period_index") if period else None
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        return -1

    top = max(index(fact) for fact in latest)
    return [fact for fact in latest if index(fact) == top]


def _form_starts_after(data: AuditInput, period_id: str) -> bool:
    saw = False
    for concept in _STATEMENT_CONCEPTS:
        primary = _primary(data, concept)
        if primary is None:
            continue
        boundary = next(
            (
                period
                for period in data.periods
                if period.get("period_id") == period_id and period.get("axis_id") in _row_axes(data, primary.get("row_key"))
            ),
            None,
        )
        for ref in _form_rows(data, concept, primary):
            first = _first_filled(data, ref.get("row_key"))
            if first is None or boundary is None:
                continue
            saw = True
            if not _immediately_before(data, boundary, first):
                return False
    return saw


def _first_filled(data: AuditInput, row_key: str | None) -> dict | None:
    if not row_key:
        return None
    values = _cached(data, row_key)
    axes = _row_axes(data, row_key)
    for period in _order([item for item in data.periods if item.get("axis_id") in axes]):
        if (period.get("axis_id"), period.get("period_id")) in values:
            return period
    return None


def _immediately_before(data: AuditInput, earlier: dict, later: dict) -> bool:
    left = _period_end(earlier)
    right = _period_end(later)
    grain = str(earlier.get("grain") or later.get("grain") or "").lower()
    if left is not None and right is not None and left < right:
        for period in data.periods:
            if grain and str(period.get("grain") or "").lower() not in ("", grain):
                continue
            end = _period_end(period)
            if end is not None and left < end < right:
                return False
        return True
    if earlier.get("axis_id") != later.get("axis_id"):
        return False
    ordered = [item.get("period_id") for item in _order([item for item in data.periods if item.get("axis_id") == earlier.get("axis_id")])]
    if earlier.get("period_id") not in ordered or later.get("period_id") not in ordered:
        return False
    return ordered.index(later.get("period_id")) == ordered.index(earlier.get("period_id")) + 1


def _boundary_hits_axis(data: AuditInput, primary: dict, actual: list[dict]) -> bool:
    """Граница лежит на оси сверяемой строки. Тот же `period_id` чужой оси не считается."""

    axes = _row_axes(data, primary.get("row_key") or "")
    if not axes:
        return False
    owned = {
        (period.get("axis_id"), period.get("period_id"))
        for period in data.periods
        if period.get("axis_id") in axes
    }
    return any((period.get("axis_id"), period.get("period_id")) in owned for period in actual)


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
    axis = fact.get("axis_id")
    for link in data.links:
        if link.get("row_key") != fact.get("row_key") or link.get("period_id") != fact.get("period_id"):
            continue
        if not (link.get("formula") or link.get("cell")):
            continue
        owner = data.facts_by_cell.get(link.get("cell") or "")
        if owner is not None and owner.get("axis_id") != axis:
            continue
        if owner is None and link.get("cell") not in (None, cell):
            continue
        return True
    return False


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
        if resolved[0] == "traced_ambiguous":
            if not _has_statement_pair(data):
                return []
            return [_traced_ambiguous(self, data, resolved[1], resolved[2] if len(resolved) > 2 else [])]
        _kind, actual, source, end, *extra = resolved
        traced = extra[0] if extra else []
        notes = extra[1] if len(extra) > 1 else []
        noted = {"forecast_assumptions": notes} if notes else {}
        findings = []
        axis_miss = False
        compared = False
        for concept in _STATEMENT_CONCEPTS:
            primary = _primary(data, concept)
            if primary is None:
                continue
            grain = _primary_grain(data, primary)
            comparable = _on_row_axis(data, primary, _same_grain(actual, grain))
            if source == "explicit" and not _boundary_hits_axis(data, primary, actual):
                axis_miss = True
                findings.append(
                    self.finding(
                        data,
                        row_key=primary["row_key"],
                        params={
                            "cause": "actuals_end_axis_miss",
                            "message": _AXIS_MISS,
                            "actuals_end": end,
                            "grain": grain or "",
                            "axis_id": ",".join(sorted(_row_axes(data, primary.get("row_key") or ""))),
                        },
                    )
                )
                continue
            message = _STATEMENT_DIVERGENCE.format(grain=_grain_word(grain))
            model_values = _cached(data, primary["row_key"])
            for ref in _form_rows(data, concept, primary):
                reported, scale_source = _reported_values(data, concept, ref)
                overlap = False
                gaps = False
                for period in comparable:
                    left, right, missing = _aligned_values(data, primary, ref, period, model_values, reported)
                    if missing:
                        unknown_year = missing == [_NO_YEAR]
                        findings.append(
                            self.finding(
                                data,
                                row_key=primary["row_key"],
                                axis_id=period["axis_id"],
                                period_id=period["period_id"],
                                params={
                                    "cause": "ytd_incomplete",
                                    "concept": concept,
                                    "message": (
                                        _YTD_NO_YEAR.format(period=period["period_id"])
                                        if unknown_year
                                        else _YTD_GAP.format(period=period["period_id"], missing=", ".join(missing))
                                    ),
                                    "missing": [] if unknown_year else missing,
                                    "actuals_source": source,
                                    "actuals_end": end,
                                    **({"scale_source": scale_source} if scale_source else {}),
                                    **({"traced_cells": list(traced)} if traced else {}),
                                    **noted,
                                },
                            )
                        )
                        gaps = True
                        compared = True
                        continue
                    if left is None or right is None:
                        continue
                    overlap = True
                    compared = True
                    if _within(left, right):
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
                                **({"traced_cells": list(traced)} if traced else {}),
                                "cells": _named_cells(
                                    data, primary["row_key"], ref["row_key"], [], period["period_id"]
                                ),
                                **({"scale_source": scale_source} if scale_source else {}),
                                **noted,
                            },
                        )
                    )
                if not overlap and not gaps:
                    start = _first_filled(data, ref.get("row_key"))
                    finish = _order(comparable)[-1] if comparable else None
                    if start is not None and finish is not None:
                        findings.append(
                            self.finding(
                                data,
                                row_key=primary["row_key"],
                                params={
                                    "cause": "actuals_no_overlap",
                                    "message": _NO_OVERLAP.format(
                                        end=finish.get("period_id"), start=start.get("period_id")
                                    ),
                                    "actuals_source": source,
                                    "actuals_end": end,
                                    "fact_end": finish.get("period_id"),
                                    "form_start": start.get("period_id"),
                                    **({"traced_cells": list(traced)} if traced else {}),
                                    **noted,
                                },
                            )
                        )
                        compared = True
        if axis_miss and not compared and _has_statement_pair(data):
            findings.append(
                self.finding(data, params={"cause": "actual_unknown", "message": _ACTUAL_UNKNOWN})
            )
        return findings


def _reported_values(data: AuditInput, concept: str, ref: dict) -> tuple[dict[tuple[str, str], Decimal], str | None]:
    """Числа формы. Пустой масштаб строки берётся у строки-источника, если он один и тот же."""

    values = _cached(data, ref["row_key"])
    factor, source = _scale_for_form(data, concept, ref)
    if factor is None:
        return values, source
    return {key: value * factor for key, value in values.items()}, source


def _scale_for_form(data: AuditInput, concept: str, ref: dict) -> tuple[Decimal | None, str | None]:
    if _has_scale_hint(data, ref["row_key"]):
        return None, "given"
    factor = _dependency_scale(data, ref["row_key"])
    if factor is None or _scale_conflicts(data, concept, ref["row_key"], factor):
        return None, None
    return factor, "inferred_from_dependencies"


def _has_scale_hint(data: AuditInput, row_key: str) -> bool:
    row = data.rows_by_key.get(row_key) or {}
    if row.get("unit") or row.get("scale"):
        return True
    return _row_factor(data, row_key) is not None


def _row_factor(data: AuditInput, row_key: str) -> Decimal | None:
    """Масштаб строки: множитель строки важнее пустого множителя факта."""

    own = _metadata_factor(data.rows_by_key.get(row_key) or {})
    if own is not None:
        return own
    factors = []
    for fact in data.facts:
        if fact.get("row_key") != row_key:
            continue
        scale = _metadata_factor(fact)
        if scale is not None:
            factors.append(scale)
    if len(set(factors)) != 1:
        return None
    return factors[0]


def _metadata_factor(row: dict) -> Decimal | None:
    return metadata_factor(row)


def _dependency_scale(data: AuditInput, row_key: str) -> Decimal | None:
    """Общий масштаб строк, на которые ссылаются формулы. Разные масштабы не угадываются.

    Множитель лежит в строке-источнике. Пустой scale_factor факта его не отменяет,
    и формульная строка с известным масштабом дальше не разворачивается.
    Конкретная единица снимается тем же обходом (`dependency_measure`).
    """

    return dependency_measure(data, row_key, data.unit_dimensions)[0]


def _refs_of(data: AuditInput, cell: str) -> list[str]:
    found = []
    link = data.link_cells.get(cell)
    if link is not None:
        found.extend(link.refs)
    for row in data.links:
        ref = row.get("ref_cell")
        if row.get("cell") == cell and ref and ref not in found:
            found.append(ref)
    return found


def _scale_conflicts(data: AuditInput, concept: str, row_key: str, factor: Decimal) -> bool:
    """Другой множитель того же понятия отвергает масштаб. Без конфликта масштаб принимается."""

    for binding in data.bindings:
        other = binding.get("row_key")
        if not other or other == row_key or binding.get("status") not in _BOUND:
            continue
        if (binding.get("effective_concept") or binding.get("concept")) != concept:
            continue
        own = _row_factor(data, other)
        if own is not None and own != factor:
            return True
    return False


def _aligned_values(
    data: AuditInput,
    primary: dict,
    ref: dict,
    period: dict,
    model_values: dict[tuple[str, str], Decimal],
    reported: dict[tuple[str, str], Decimal],
) -> tuple[Decimal | None, Decimal | None, list[str]]:
    """Пара для сверки. Нарастающий итог сравнивается с суммой модели с начала календарного года."""

    key = (period.get("axis_id"), period.get("period_id"))
    right = _same_period(reported, key)
    if basis_of(ref)[0] == "ytd" and basis_of(primary)[0] == "period":
        total, missing = _year_to_date(data, primary.get("row_key"), model_values, period)
        if missing:
            return None, None, missing
        if total is not None:
            return total, right, []
    return _same_period(model_values, key), right, []


def _year_to_date(
    data: AuditInput, row_key: str | None, values: dict[tuple[str, str], Decimal], period: dict
) -> tuple[Decimal | None, list[str]]:
    """Сумма модели с начала календарного года. Без года пара пропускается, а не сравнивается с кварталом."""

    axes = set(_row_axes(data, row_key or ""))
    home = next(
        (
            item
            for item in data.periods
            if item.get("axis_id") in axes and item.get("period_id") == period.get("period_id")
        ),
        None,
    )
    if home is None:
        return None, []
    year = _calendar_year(home)
    if year is None:
        return None, [_NO_YEAR]
    ordered = _order(
        [
            item
            for item in data.periods
            if item.get("axis_id") == home.get("axis_id") and _calendar_year(item) == year
        ]
    )
    index = next((pos for pos, item in enumerate(ordered) if item.get("period_id") == home.get("period_id")), None)
    if index is None:
        return None, []
    missing = []
    total = Decimal(0)
    for item in ordered[: index + 1]:
        key = (item.get("axis_id"), item.get("period_id"))
        if key not in values:
            missing.append(str(item.get("period_id")))
            continue
        total += values[key]
    if missing:
        return None, missing
    return total, []


def _calendar_year(period: dict) -> int | None:
    year = period.get("calendar_year")
    if isinstance(year, int) and not isinstance(year, bool):
        return year
    for key in ("period_start", "period_end"):
        raw = period.get(key)
        if isinstance(raw, datetime):
            return raw.year
        if isinstance(raw, date):
            return raw.year
        if isinstance(raw, str):
            parsed = _iso_date(raw[:10])
            if parsed is not None:
                return parsed.year
    return None


def _traced_ambiguous(
    rule: StatementReference, data: AuditInput, cuts: list[tuple[str, list[str]]], notes: list[dict] | None = None
) -> Finding:
    """Несколько настоящих дат прослеженного ввода. Ни одну не выбираем и сверку не глушим общей фразой."""

    cells = [cell for _period, group in cuts for cell in group]
    if cuts:
        labels = [f"{period} ({', '.join(group)})" if group else period for period, group in cuts]
        message = _TRACED_AMBIGUOUS.format(candidates=", ".join(labels))
    else:
        message = _NO_REPORTING
    return rule.finding(
        data,
        locations=[_cell_location(data, cell) for cell in cells],
        params={
            "cause": "structural_traced_ambiguous",
            "message": message,
            "candidates": [period for period, _cells in cuts],
            "cells": cells,
            **({"forecast_assumptions": notes} if notes else {}),
        },
    )


def _cell_location(data: AuditInput, cell: str) -> Location:
    fact = data.facts_by_cell.get(cell) or {}
    return Location(cell, fact.get("row_key"), fact.get("axis_id"), fact.get("period_id"))


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


def _on_row_axis(data: AuditInput, primary: dict, periods: list[dict]) -> list[dict]:
    """Сверка идёт по периоду оси строки. Копия того же id с другой оси остаётся в окне, но не второй сверкой."""

    axes = _row_axes(data, primary.get("row_key") or "")
    on_row = [period for period in periods if period.get("axis_id") in axes]
    return on_row or periods


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
