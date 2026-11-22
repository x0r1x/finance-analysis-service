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

from finance_analysis.domain.graphs import _select_primary
from finance_analysis.domain.metrics import HUMAN_SOURCES, interest_choice
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

    def as_origin(self) -> dict[str, str | None]:
        return {"concept": self.concept, "source": self.source, "row_key": self.row_key}


@dataclass(frozen=True)
class LineageCompleteness:
    """Одна оценка: загружен ли graph_links и не обрезана ли ссылка."""

    graph_links_available: bool
    truncated_links: int
    physical_lineage_complete: bool
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

    def as_dict(self) -> dict:
        return {
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


def lineage_completeness(*, graph_links_available: bool, truncated_links: int) -> LineageCompleteness:
    """Пустой загруженный граф полон. Нет файла или обрезанная ссылка — нет."""

    if not graph_links_available:
        return LineageCompleteness(
            False,
            truncated_links,
            False,
            "физическая трассировка недоступна: graph_links не загружен",
        )
    if truncated_links:
        return LineageCompleteness(
            True,
            truncated_links,
            False,
            f"цепь может быть неполной: обрезано ссылок {truncated_links}",
        )
    return LineageCompleteness(True, truncated_links, True, None)


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
) -> tuple[SemanticInput, ...] | None:
    """Входы, которые расчёт реально берёт. None — метрики нет в этом вызове.

    ``expressions`` раскрывают вариант, one_of и запасной путь. Без них список
    ``inputs`` связывается как есть: так старый след не меняет набор понятий.
    """

    chosen = variant if variant else _implied_variant(metric, dscr_variant)
    active = _active(metric, chosen, expressions) if expressions else None
    visible = _visible(bindings, absent)
    if active is None:
        if inputs is None:
            return None
        return _listed(inputs, visible, row_keys)
    expr, source = active
    specs = _specs(expr, source, metric, chosen, visible, interest_order, row_fallbacks)
    return tuple(_materialize(name, src, role, visible, row_keys) for name, src, role in specs)


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
    order = expr.one_of_order or tuple(sorted(expr.one_of))
    present = [name for name in order if _select_primary(bindings, name)[0] is not None]
    if present:
        add(present[0], "one_of", "one_of")
    elif order:
        add(order[0], "one_of", "one_of")
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
    if (
        metric == "dscr"
        and variant in {None, "pf"}
        and "debt_service" in names
        and _select_primary(bindings, "debt_service")[0] is None
        and order.get("pf")
    ):
        chosen = _interest_pick(bindings, order["pf"], row_fallbacks)
        if chosen and _select_primary(bindings, "principal")[0] is not None:
            specs = [item for item in specs if item[0] != "debt_service"]
            have = {name for name, _src, _role in specs}
            if chosen not in have:
                specs.append((chosen, "fallback", "all_of"))
            if "principal" not in have:
                specs.append(("principal", "fallback", "all_of"))
    return specs


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


def _visible(
    bindings: Sequence[Mapping[str, Any]], absent: frozenset[str]
) -> list[Mapping[str, Any]]:
    if not absent:
        return list(bindings)
    kept: list[Mapping[str, Any]] = []
    for row in bindings:
        concept = str(row.get("effective_concept") or row.get("concept") or "")
        if concept in absent and row.get("source") not in HUMAN_SOURCES:
            continue
        kept.append(row)
    return kept
