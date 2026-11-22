"""Один разбор семантического входа метрики.

След, происхождение формулы и цепь находки читают этот список, а не собирают
его заново. Строка входа — не-stale основная привязка ``_select_primary``.
Полнота физической цепи тоже считается здесь один раз.

OpenLineage записывает входы выхода в одном фасете и запрещает потребителю
достраивать рёбра из общих списков. MetricFlow так же один раз раскрывает
определение метрики в запрос.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from finance_analysis.domain.binding_resolution import declared_concept
from finance_analysis.domain.binding_resolution import select_primary as _select_primary
from finance_analysis.domain.free_cash_flow import shield_concepts
from finance_analysis.domain.metrics import (
    HUMAN_SOURCES,
    _primaries,
    choose_one_of,
    confirm_paid_interest,
    dscr_denominator_plan,
    interest_choice,
)
from finance_analysis.domain.model_type import MetricExpression

# ADSCR и сводки наследуют housing, как housing_cover._FAMILY.
_HOUSING = frozenset({"adscr", "dscr_min", "dscr_avg"})


@dataclass(frozen=True)
class SemanticInput:
    """Понятие, которое расчёт взял, и откуда оно взялось."""

    concept: str
    source: str
    role: str
    row_key: str | None = None
    binding_key: str | None = None
    missing: str | None = None
    ambiguous: bool = False

    def as_origin(self) -> dict[str, str | bool | None]:
        body: dict[str, str | bool | None] = {
            "concept": self.concept,
            "source": self.source,
            "row_key": self.row_key,
        }
        if self.ambiguous:
            body["ambiguous"] = True
            body["confirmed"] = False
        return body


@dataclass(frozen=True)
class LineageCompleteness:
    """Три факта. ``physical_lineage_complete`` не шире двух проверок."""

    graph_available: bool
    graph_truncation_free: bool
    physical_lineage_complete: bool
    truncated_links: int
    note: str | None


@dataclass(frozen=True)
class FormulaOrigin:
    """Пометки формул в зависимостях метрики. Прямые входы — для отчёта."""

    metric: str
    closure: int
    inputs: tuple[SemanticInput, ...]
    counts: tuple[tuple[str, str, int], ...]
    direct: tuple[dict, ...]

    def as_dict(self) -> dict:
        return {
            "metric": self.metric,
            "closure": self.closure,
            "inputs": [item.as_origin() for item in self.inputs if item.row_key],
            "counts": [
                {"code": code, "severity": severity, "count": count}
                for code, severity, count in self.counts
            ],
            "direct": list(self.direct),
        }


@dataclass(frozen=True)
class FormulaChain:
    """Как находка дошла до метрики: глубина, семя и источник семени."""

    metric: str
    code: str
    severity: str
    fingerprint: str
    depth: int
    via: str | None
    input: str | None
    source: str | None
    cells: tuple[str, ...]
    confirmed: bool = True

    def as_dict(self) -> dict:
        body = {
            "metric": self.metric,
            "code": self.code,
            "severity": self.severity,
            "fingerprint": self.fingerprint,
            "depth": self.depth,
            "via": self.via,
            "input": self.input,
            "source": self.source,
            "cells": list(self.cells),
        }
        if not self.confirmed:
            body["confirmed"] = False
            body["ambiguous"] = True
        return body


def lineage_completeness(*, graph_links_available: bool, truncated_links: int) -> LineageCompleteness:
    """Две проверки и их соединение.

    ``graph_available`` — файл ``graph_links`` загружен, в том числе пустой.
    ``graph_truncation_free`` — файл загружен и у этой сборки нет обрезанной
    ссылки. Нет файла — флаг ложен: обрезание не проверялось.
    ``physical_lineage_complete`` истинен только когда оба флага истинны.
    Это не доказательство, что разбор нашёл каждую зависимость Excel.
    """

    available = bool(graph_links_available)
    free = available and truncated_links == 0
    if not available:
        note = "физическая трассировка недоступна: graph_links не загружен"
    elif not free:
        note = f"цепь может быть неполной: обрезано ссылок {truncated_links}"
    else:
        note = None
    return LineageCompleteness(
        graph_available=available,
        graph_truncation_free=free,
        physical_lineage_complete=available and free,
        truncated_links=truncated_links,
        note=note,
    )


def resolve_semantic_inputs(
    metric: str,
    bindings: Sequence[Mapping[str, Any]],
    expressions: Mapping[str, MetricExpression] | None,
    *,
    variant: str | None = None,
    dscr_variant: str | None = None,
    interest_order: Mapping[str, Sequence[str]] | None = None,
    row_fallbacks: Mapping[str, Any] | None = None,
    absent: frozenset[str] = frozenset(),
    inputs: Mapping[str, Sequence[str]] | None = None,
    row_keys: Mapping[str, str] | None = None,
    facts: Sequence[Mapping[str, Any]] = (),
    links: Sequence[Mapping[str, Any]] = (),
    statement_sheets: frozenset[str] = frozenset(),
) -> tuple[SemanticInput, ...] | None:
    """Входы, которые расчёт реально берёт. None — метрики нет в этом вызове.

    ``expressions`` раскрывают вариант, one_of и запасной путь. Без них список
    ``inputs`` связывается как есть: так старый след не меняет набор понятий.
    """

    chosen = variant if variant else _implied_variant(metric, dscr_variant)
    active = _active(metric, chosen, expressions) if expressions else None
    visible = _with_confirmed_paid(_visible(bindings, absent), absent)
    if active is None:
        if inputs is None:
            return None
        listed = _listed(inputs, visible, row_keys)
        return _with_shield(
            listed, metric, visible, absent, facts, links, statement_sheets, row_keys
        )
    expr, source = active
    specs = _specs(expr, source, metric, chosen, visible, interest_order, row_fallbacks)
    chosen_inputs = tuple(
        _materialize(name, src, role, visible, row_keys) for name, src, role in specs
    )
    return _with_shield(
        chosen_inputs, metric, visible, absent, facts, links, statement_sheets, row_keys
    )


def _implied_variant(metric: str, dscr_variant: str | None) -> str | None:
    if not dscr_variant:
        return None
    if metric == "dscr":
        return dscr_variant
    if metric in _HOUSING and dscr_variant == "housing":
        return "housing"
    return None


def _active(
    metric: str,
    variant: str | None,
    expressions: Mapping[str, MetricExpression],
) -> tuple[MetricExpression, str] | None:
    if variant:
        chosen = expressions.get(f"{metric}.{variant}")
        if chosen is not None and not chosen.base:
            return chosen, f"variant:{variant}"
    expr = expressions.get(metric)
    if expr is None:
        return None
    if expr.base:
        base = expressions.get(expr.base)
        if base is not None:
            return base, f"base:{expr.base}"
    return expr, "formula"


def _listed(
    inputs: Mapping[str, Sequence[str]],
    bindings: Sequence[Mapping[str, Any]],
    row_keys: Mapping[str, str] | None,
) -> tuple[SemanticInput, ...]:
    found: list[SemanticInput] = []
    for role in ("all_of", "one_of"):
        for concept in inputs.get(role) or ():
            found.append(_materialize(str(concept), "formula", role, bindings, row_keys))
    return tuple(found)


def _specs(
    expr: MetricExpression,
    source: str,
    metric: str,
    variant: str | None,
    bindings: Sequence[Mapping[str, Any]],
    interest_order: Mapping[str, Sequence[str]] | None,
    row_fallbacks: Mapping[str, Any] | None,
) -> list[tuple[str, str, str]]:
    specs: list[tuple[str, str, str]] = []

    def add(name: str | None, src: str, role: str = "all_of") -> None:
        if name and all(item[0] != name for item in specs):
            specs.append((name, src, role))

    for name in (
        *expr.numerator_plus,
        *expr.numerator_minus,
        *expr.denominator_plus,
        *expr.denominator_minus,
        *expr.rates,
    ):
        add(name, source)
    add(expr.rate, source)
    add(expr.terminal, source)
    add(expr.compare_with, source)
    if expr.add_back:
        add(expr.add_back[0], source)
        add(expr.add_back[1], source)
    members = expr.one_of_order or tuple(sorted(expr.one_of))
    if members:
        present = {name for name in members if _select_primary(bindings, name)[0] is not None}
        chosen_name = choose_one_of(members, present)
        if chosen_name:
            for index, (name, src, _role) in enumerate(specs):
                if name == chosen_name:
                    specs[index] = (name, src, "one_of")
                    break
            else:
                specs.append((chosen_name, source, "one_of"))
    return _fallbacks(metric, variant, specs, bindings, interest_order, row_fallbacks)


def _fallbacks(
    metric: str,
    variant: str | None,
    specs: list[tuple[str, str, str]],
    bindings: Sequence[Mapping[str, Any]],
    interest_order: Mapping[str, Sequence[str]] | None,
    row_fallbacks: Mapping[str, Any] | None,
) -> list[tuple[str, str, str]]:
    """Замена interest и debt_service — та же, что у coverage_ratio, один раз.

    debt_service меняется только у dscr (база и pf): ADSCR эту замену не читает.
    """

    order = interest_order or {}
    names = [name for name, _src, _role in specs]
    slot = _interest_slot(metric, variant)
    if "interest" in names and slot and order.get(slot) and _select_primary(bindings, "interest")[0] is None:
        chosen = _interest_pick(bindings, order[slot], row_fallbacks)
        if chosen and chosen != "interest":
            specs = [
                (chosen, "fallback", role) if name == "interest" else (name, src, role)
                for name, src, role in specs
            ]
    if metric == "dscr" and variant in {None, "pf"} and "debt_service" in names:
        specs = _dscr_plan(specs, bindings, order, row_fallbacks)
    return specs


def _dscr_plan(
    specs: list[tuple[str, str, str]],
    bindings: Sequence[Mapping[str, Any]],
    order: Mapping[str, Sequence[str]],
    row_fallbacks: Mapping[str, Any] | None,
) -> list[tuple[str, str, str]]:
    """Состав DSCR из dscr_denominator_plan. ADSCR сюда не заходит."""

    watch = ("cfads", "debt_service", "principal", "interest", "interest_paid", *order.get("pf", ()))
    primaries: dict[str, Mapping[str, Any]] = {}
    for name in dict.fromkeys(watch):
        row, _missing, _ambiguous = _select_primary(bindings, name)
        if row is not None:
            primaries[name] = row
    concepts, _denominator, _parts, _warnings = dscr_denominator_plan(primaries, order, row_fallbacks)
    previous = {name: (src, role) for name, src, role in specs}
    return [
        (name, *previous[name]) if name in previous else (name, "fallback", "all_of")
        for name in concepts
    ]


def _interest_slot(metric: str, variant: str | None) -> str | None:
    if metric in {"icr", "icr_ebit"}:
        return metric
    if metric == "dscr" and variant in {None, "pf", "corporate_covenant", "ocf_covenant"}:
        return "pf" if variant in {None, "pf"} else variant
    return None


def _interest_pick(
    bindings: Sequence[Mapping[str, Any]],
    order: Sequence[str],
    row_fallbacks: Mapping[str, Any] | None,
) -> str | None:
    primaries: dict[str, Mapping[str, Any]] = {}
    for name in order:
        row, _, _ = _select_primary(bindings, name)
        if row is not None:
            primaries[name] = row
        fallback = (row_fallbacks or {}).get(name)
        canonical = getattr(fallback, "canonical", None) if fallback is not None else (
            "interest" if name == "interest_paid" else None
        )
        if canonical and canonical not in primaries:
            canonical_row, _, _ = _select_primary(bindings, canonical)
            if canonical_row is not None:
                primaries[canonical] = canonical_row
    chosen, _warning = interest_choice(primaries, order, row_fallbacks=dict(row_fallbacks or {}))
    return chosen


def _materialize(
    concept: str,
    source: str,
    role: str,
    bindings: Sequence[Mapping[str, Any]],
    row_keys: Mapping[str, str] | None,
) -> SemanticInput:
    primary, missing, ambiguous = _select_primary(bindings, concept)
    if primary is None:
        return SemanticInput(concept, source, role, None, None, missing or "no_primary_binding", False)
    raw_key = primary.get("binding_key")
    binding_key = str(raw_key) if raw_key else None
    row_key = str(primary.get("row_key") or (row_keys or {}).get(binding_key or "") or "") or None
    return SemanticInput(concept, source, role, row_key, binding_key, None, ambiguous)


def _with_confirmed_paid(
    bindings: Sequence[Mapping[str, Any]], absent: frozenset[str]
) -> list[Mapping[str, Any]]:
    """Та же подстановка 4123, что ``confirm_paid_interest`` кладёт в primaries.

    Копия снимает stale: расчёт вставляет строку уже после фильтра stale.
    Чужой список привязок не меняется. Занятый interest_paid не переписывается.
    """

    rows = [dict(row) for row in bindings]
    injected = confirm_paid_interest(_primaries(rows, absent), rows, absent)
    if injected is None:
        return list(bindings)
    return [*bindings, {**injected, "stale": False}]


def _with_shield(
    items: tuple[SemanticInput, ...],
    metric: str,
    bindings: Sequence[Mapping[str, Any]],
    absent: frozenset[str],
    facts: Sequence[Mapping[str, Any]],
    links: Sequence[Mapping[str, Any]],
    statement_sheets: frozenset[str],
    row_keys: Mapping[str, str] | None,
) -> tuple[SemanticInput, ...]:
    """Добавить понятия щита, которых нет в формуле. Базис берёт расчёт."""

    have = {item.concept for item in items}
    extra = shield_concepts(
        metric,
        [dict(row) for row in bindings],
        absent,
        list(facts),
        list(links),
        statement_sheets,
    )
    added = [
        _materialize(name, "paid_interest", "all_of", bindings, row_keys)
        for name in extra
        if name not in have
    ]
    return (*items, *added)


def _visible(
    bindings: Sequence[Mapping[str, Any]], absent: frozenset[str]
) -> list[Mapping[str, Any]]:
    if not absent:
        return list(bindings)
    kept: list[Mapping[str, Any]] = []
    for row in bindings:
        concept = declared_concept(row)
        if concept in absent and row.get("source") not in HUMAN_SOURCES:
            continue
        kept.append(row)
    return kept
