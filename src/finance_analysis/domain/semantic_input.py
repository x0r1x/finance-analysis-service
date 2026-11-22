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
from dataclasses import dataclass, field
from typing import Any

from finance_analysis.domain.binding_resolution import declared_concept
from finance_analysis.domain.binding_resolution import select_primary as _select_primary
from finance_analysis.domain.free_cash_flow import (
    _ambiguous_primary,
    _basis,
)
from finance_analysis.domain.metrics import (
    HUMAN_SOURCES,
    _groups,
    _primaries,
    choose_one_of,
    confirm_paid_interest,
    dscr_denominator_plan,
    interest_choice,
)
from finance_analysis.domain.model_type import MetricExpression, sheet_name_key
from finance_analysis.domain.resolved_plan import (
    RESOLUTION_ENGINE_VERSION,
    AppliedFallback,
    DiagnosticCandidate,
    LineageRow,
    NeedsInput,
    PlanWarning,
    RejectedAlternative,
    ResolvedInput,
    ResolvedMetricPlan,
    ShieldDecision,
    recover_row,
    seal,
)


@dataclass
class _Selection:
    """Один проход выбора. Поля плана — проекция, а не второй вызов правил."""

    warnings: list[PlanWarning] = field(default_factory=list)
    fallbacks: list[AppliedFallback] = field(default_factory=list)
    shield: ShieldDecision | None = None

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
    include_shield: bool = True,
    selection: _Selection | None = None,
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
        if not include_shield:
            return listed
        return _with_shield(
            listed,
            metric,
            visible,
            absent,
            facts,
            links,
            statement_sheets,
            row_keys,
            selection,
        )
    expr, source = active
    specs = _specs(
        expr, source, metric, chosen, visible, interest_order, row_fallbacks, selection
    )
    chosen_inputs = tuple(
        _materialize(name, src, role, visible, row_keys) for name, src, role in specs
    )
    if not include_shield:
        return chosen_inputs
    return _with_shield(
        chosen_inputs,
        metric,
        visible,
        absent,
        facts,
        links,
        statement_sheets,
        row_keys,
        selection,
    )


_PAID_BASES = frozenset({"interest_included", "candidate"})
_SHIELD_REASON = {
    "interest_included": "statement_4100_with_4123",
    "interest_excluded": "financing_without_4123",
    "candidate": "formula_candidate",
    "unknown": "no_basis",
}


def resolve_metric_plan(
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
    catalog_version: str | None = None,
    semantic_model_version: str | None = None,
    build_key: str | None = None,
    model_id: str | None = None,
) -> ResolvedMetricPlan | None:
    """Один проход выбора. Потребители читают план и эти функции больше не вызывают."""

    chosen_variant = variant if variant else _implied_variant(metric, dscr_variant)
    active = _active(metric, chosen_variant, expressions) if expressions else None
    variant_source = active[1] if active else "formula"
    selection = _Selection()
    items = resolve_semantic_inputs(
        metric,
        bindings,
        expressions,
        variant=variant,
        dscr_variant=dscr_variant,
        interest_order=interest_order,
        row_fallbacks=row_fallbacks,
        absent=absent,
        inputs=inputs,
        row_keys=row_keys,
        facts=facts,
        links=links,
        statement_sheets=statement_sheets,
        selection=selection,
    )
    if items is None:
        return None
    shield = selection.shield
    confirmed, diagnostic = _split(items)
    rejected = _rejected(metric, items, bindings, expressions, chosen_variant, interest_order, shield)
    status, needs, warnings, fallbacks = _outcome(metric, bindings, items, absent, selection, chosen_variant)
    return seal(
        metric_id=metric,
        variant=chosen_variant,
        variant_source=variant_source,
        catalog_version=catalog_version,
        semantic_model_version=semantic_model_version,
        build_key=build_key,
        model_id=model_id,
        status=status,
        inputs=confirmed,
        diagnostic=diagnostic,
        rejected=rejected,
        fallbacks=fallbacks,
        warnings=warnings,
        needs_input=needs,
        shield=shield,
        lineage=tuple(
            LineageRow(
                item.concept,
                item.source,
                item.role,
                item.row_key,
                item.binding_key,
                item.missing,
                item.ambiguous,
            )
            for item in items
        ),
        resolution_engine_version=RESOLUTION_ENGINE_VERSION,
    )


def _split(
    items: tuple[SemanticInput, ...],
) -> tuple[tuple[ResolvedInput, ...], tuple[DiagnosticCandidate, ...]]:
    confirmed: list[ResolvedInput] = []
    diagnostic: list[DiagnosticCandidate] = []
    for item in items:
        if item.ambiguous:
            diagnostic.append(
                DiagnosticCandidate(item.concept, item.binding_key, item.row_key)
            )
            continue
        if item.row_key is None:
            continue
        confirmed.append(
            ResolvedInput(
                item.concept,
                item.role,
                item.source,
                item.binding_key,
                item.row_key,
                None,
                False,
                True,
            )
        )
    return tuple(confirmed), tuple(diagnostic)


def _outcome(
    metric: str,
    bindings: Sequence[Mapping[str, Any]],
    items: tuple[SemanticInput, ...],
    absent: frozenset[str],
    selection: _Selection,
    variant: str | None = None,
) -> tuple[str, tuple[NeedsInput, ...], tuple[PlanWarning, ...], tuple[AppliedFallback, ...]]:
    if metric == "fcff":
        return _fcff_outcome(bindings, items, absent)
    warnings = tuple(selection.warnings)
    fallbacks = tuple(selection.fallbacks)
    if metric == "dscr" and variant in {None, "pf"} or metric in {"icr", "icr_ebit"}:
        return _coverage_status(items, bindings, absent, warnings, fallbacks)
    if any(item.ambiguous for item in items):
        return (
            "needs_input",
            tuple(NeedsInput("concept", "ambiguous", item.concept) for item in items if item.ambiguous),
            warnings,
            fallbacks,
        )
    missing = [item.concept for item in items if item.row_key is None]
    if missing:
        return (
            "missing_input",
            tuple(NeedsInput("concept", "concept_unknown", name) for name in missing),
            warnings,
            fallbacks,
        )
    return "resolved", (), warnings, fallbacks


def _coverage_status(
    items: tuple[SemanticInput, ...],
    bindings: Sequence[Mapping[str, Any]],
    absent: frozenset[str],
    warnings: tuple[PlanWarning, ...],
    fallbacks: tuple[AppliedFallback, ...],
) -> tuple[str, tuple[NeedsInput, ...], tuple[PlanWarning, ...], tuple[AppliedFallback, ...]]:
    """Статус покрытия по уже выбранным входам. Повторный выбор не делает.

    Неоднозначность и отсутствие читаются со строк. Это диагностика, не правило выбора.
    """

    rows = [dict(row) for row in bindings]
    watched = {item.concept for item in items} | {"ebitda", "ebit"}
    ambiguous = [name for name, grouped in _groups(rows).items() if len(grouped) > 1 and name in watched]
    if not ambiguous:
        ambiguous = [
            declared_concept(row)
            for row in rows
            if row.get("status") == "ambiguous" and declared_concept(row) in watched
        ]
    if ambiguous:
        return "needs_input", (NeedsInput("concept", "ambiguous", ambiguous[0]),), warnings, fallbacks
    missing = [item.concept for item in items if item.row_key is None]
    if missing:
        subject = missing[0]
        reason = "absent_in_book" if subject in _absent_names(rows, absent) else "concept_unknown"
        return (
            "missing_input",
            tuple(
                NeedsInput("concept", reason if name == subject else "concept_unknown", name)
                for name in missing
            ),
            warnings,
            fallbacks,
        )
    return "resolved", (), warnings, fallbacks


def _absent_names(rows: Sequence[Mapping[str, Any]], absent: frozenset[str]) -> set[str]:
    marked = {
        declared_concept(row)
        for row in rows
        if row.get("source") == "confirmed" and row.get("status") == "unknown" and declared_concept(row)
    }
    restored = {
        declared_concept(row)
        for row in rows
        if row.get("is_primary")
        and row.get("status") in {"bound", "bound_with_warning"}
        and not row.get("stale")
        and declared_concept(row)
        and row.get("source") in HUMAN_SOURCES
    }
    return (marked | set(absent)) - restored


def _fcff_outcome(
    bindings: Sequence[Mapping[str, Any]],
    items: tuple[SemanticInput, ...],
    absent: frozenset[str],
) -> tuple[str, tuple[NeedsInput, ...], tuple[PlanWarning, ...], tuple[AppliedFallback, ...]]:
    clash = _ambiguous_primary([dict(row) for row in bindings], absent)
    if clash:
        return "needs_input", (NeedsInput("concept", "ambiguous", clash),), (), ()
    present = {item.concept for item in items if item.row_key and not item.ambiguous}
    for name in ("operating_cash_flow", "capex"):
        if name not in present:
            return "missing_input", (NeedsInput("concept", "concept_unknown", name),), (), ()
    return "resolved", (), (), ()


def _plan_warning(item: dict) -> PlanWarning:
    params = item.get("params") or {}
    pairs = tuple(sorted((str(key), str(value)) for key, value in params.items()))
    return PlanWarning(str(item["code"]), pairs)


def _rejected(
    metric: str,
    items: tuple[SemanticInput, ...],
    bindings: Sequence[Mapping[str, Any]],
    expressions: Mapping[str, MetricExpression] | None,
    variant: str | None,
    interest_order: Mapping[str, Sequence[str]] | None,
    shield: ShieldDecision | None,
) -> tuple[RejectedAlternative, ...]:
    found: list[RejectedAlternative] = []
    seen: set[tuple[str, str, str]] = set()

    def add(reason: str, concept: str, binding_key: str | None, row_key: str | None) -> None:
        key = (reason, concept, binding_key or "")
        if key in seen:
            return
        seen.add(key)
        found.append(RejectedAlternative(reason, concept, binding_key, row_key))

    for item in items:
        if not item.ambiguous:
            continue
        for row in _fresh(bindings, item.concept):
            key = str(row.get("binding_key") or "")
            if key and key != item.binding_key:
                add("not_min_binding_key", item.concept, key, str(row.get("row_key") or "") or None)
    chosen = {item.concept for item in items if item.row_key}
    active = _active(metric, variant, expressions) if expressions else None
    if active is not None:
        expr = active[0]
        members = expr.one_of_order or tuple(sorted(expr.one_of))
        for name in members:
            if name in chosen:
                continue
            row = _named_row(bindings, name)
            if row is not None:
                add(
                    "not_selected_one_of",
                    name,
                    str(row.get("binding_key") or "") or None,
                    str(row.get("row_key") or "") or None,
                )
    slot = _interest_slot(metric, variant)
    order = (interest_order or {}).get(slot or "", ())
    picked = next((item.concept for item in items if item.source == "fallback"), None)
    if picked and order:
        for name in order:
            if name == picked or name in chosen:
                continue
            row = _named_row(bindings, name)
            if row is not None:
                add(
                    "interest_order_skipped",
                    name,
                    str(row.get("binding_key") or "") or None,
                    str(row.get("row_key") or "") or None,
                )
    if metric == "dscr" and "debt_service" in chosen:
        row = _named_row(bindings, "interest_paid")
        if row is not None and "interest_paid" not in chosen:
            add(
                "debt_service_present",
                "interest_paid",
                str(row.get("binding_key") or "") or None,
                str(row.get("row_key") or "") or None,
            )
    if shield is not None and shield.basis not in _PAID_BASES:
        add("shield_not_applied", "interest_paid", None, None)
    return tuple(found)


def _named_row(bindings: Sequence[Mapping[str, Any]], concept: str) -> Mapping[str, Any] | None:
    """Свежая строка для диагноза отвергнутого пути. Правило выбора не вызывает."""

    rows = _fresh(bindings, concept)
    if not rows:
        return None
    return min(rows, key=lambda row: str(row.get("binding_key") or ""))


def _fresh(bindings: Sequence[Mapping[str, Any]], concept: str) -> list[Mapping[str, Any]]:
    return [
        row
        for row in bindings
        if row.get("is_primary")
        and row.get("status") in {"bound", "bound_with_warning"}
        and not row.get("stale")
        and declared_concept(row) == concept
    ]


def plans_for(
    metrics: Sequence[str],
    bindings: Sequence[Mapping[str, Any]],
    expressions: Mapping[str, MetricExpression] | None,
    *,
    variant_of: Mapping[str, str | None] | None = None,
    dscr_variant: str | None = None,
    interest_order: Mapping[str, Sequence[str]] | None = None,
    row_fallbacks: Mapping[str, Any] | None = None,
    absent: frozenset[str] = frozenset(),
    facts: Sequence[Mapping[str, Any]] = (),
    links: Sequence[Mapping[str, Any]] = (),
    statement_sheets: frozenset[str] = frozenset(),
    catalog_version: str | None = None,
    semantic_model_version: str | None = None,
    build_key: str | None = None,
    model_id: str | None = None,
) -> dict[str, ResolvedMetricPlan]:
    """Один план на метрику. Вызывающий передаёт этот словарь дальше как есть."""

    found: dict[str, ResolvedMetricPlan] = {}
    for metric in metrics:
        variant = dscr_variant if metric == "dscr" else (variant_of or {}).get(metric)
        plan = resolve_metric_plan(
            metric,
            bindings,
            expressions,
            variant=variant,
            dscr_variant=dscr_variant,
            interest_order=interest_order,
            row_fallbacks=row_fallbacks,
            absent=absent,
            facts=facts,
            links=links,
            statement_sheets=statement_sheets,
            catalog_version=catalog_version,
            semantic_model_version=semantic_model_version,
            build_key=build_key,
            model_id=model_id,
        )
        if plan is not None:
            found[metric] = plan
    return found


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
    selection: _Selection | None = None,
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
        if (
            selection is not None
            and metric == "icr"
            and chosen_name == "ebitda"
            and "ebit" in present
        ):
            selection.warnings.append(PlanWarning("icr_numerator", (("concept", "ebitda"),)))
    return _fallbacks(metric, variant, specs, bindings, interest_order, row_fallbacks, selection)


def _fallbacks(
    metric: str,
    variant: str | None,
    specs: list[tuple[str, str, str]],
    bindings: Sequence[Mapping[str, Any]],
    interest_order: Mapping[str, Sequence[str]] | None,
    row_fallbacks: Mapping[str, Any] | None,
    selection: _Selection | None = None,
) -> list[tuple[str, str, str]]:
    """Замена interest и debt_service — та же, что у coverage_ratio, один раз.

    debt_service меняется только у dscr (база и pf): ADSCR эту замену не читает.
    """

    order = interest_order or {}
    names = [name for name, _src, _role in specs]
    slot = _interest_slot(metric, variant)
    if "interest" in names and slot and order.get(slot) and _select_primary(bindings, "interest")[0] is None:
        chosen, warning = _interest_pick(bindings, order[slot], row_fallbacks)
        if chosen and chosen != "interest":
            specs = [
                (chosen, "fallback", role) if name == "interest" else (name, src, role)
                for name, src, role in specs
            ]
            if selection is not None:
                code = warning["code"] if warning else None
                if warning:
                    selection.warnings.append(_plan_warning(warning))
                selection.fallbacks.append(AppliedFallback(slot, "interest", chosen, code))
    if metric == "dscr" and variant in {None, "pf"} and "debt_service" in names:
        specs = _dscr_plan(specs, bindings, order, row_fallbacks, selection)
    return specs


def _dscr_plan(
    specs: list[tuple[str, str, str]],
    bindings: Sequence[Mapping[str, Any]],
    order: Mapping[str, Sequence[str]],
    row_fallbacks: Mapping[str, Any] | None,
    selection: _Selection | None = None,
) -> list[tuple[str, str, str]]:
    """Состав DSCR из dscr_denominator_plan. ADSCR сюда не заходит."""

    watch = ("cfads", "debt_service", "principal", "interest", "interest_paid", *order.get("pf", ()))
    primaries: dict[str, Mapping[str, Any]] = {}
    for name in dict.fromkeys(watch):
        row, _missing, _ambiguous = _select_primary(bindings, name)
        if row is not None:
            primaries[name] = row
    concepts, _denominator, parts, warnings = dscr_denominator_plan(primaries, order, row_fallbacks)
    if selection is not None:
        selection.warnings.extend(_plan_warning(item) for item in warnings)
        if parts is not None:
            code = warnings[0]["code"] if warnings else None
            selection.fallbacks.append(AppliedFallback("pf", "debt_service", parts[0], code))
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
) -> tuple[str | None, dict | None]:
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
    return interest_choice(primaries, order, row_fallbacks=dict(row_fallbacks or {}))


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
    selection: _Selection | None = None,
) -> tuple[SemanticInput, ...]:
    """Добавить понятия щита, которых нет в формуле. Базис считается один раз."""

    if metric != "fcff":
        return items
    rows = [dict(row) for row in bindings]
    statement = frozenset(sheet_name_key(name) for name in statement_sheets)
    ocf_item = next(
        (item for item in items if item.concept == "operating_cash_flow" and item.row_key),
        None,
    )
    ocf = recover_row(rows, ocf_item) if ocf_item is not None else None
    if ocf is None:
        basis = "unknown"
    else:
        basis = _basis(dict(ocf), rows, absent, list(facts), list(links), statement)
    if selection is not None:
        selection.shield = ShieldDecision(basis, _SHIELD_REASON[basis])
    if basis not in _PAID_BASES or any(item.concept == "interest_paid" for item in items):
        return items
    return (
        *items,
        _materialize("interest_paid", "paid_interest", "all_of", bindings, row_keys),
    )


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
