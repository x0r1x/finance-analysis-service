"""Контракт исполнения. Базовые DSCR, DSCR pf, ICR и ICR EBIT берут стороны отсюда.

Идентичность исполнителя — отдельный объект с одним методом, как в PEP 544:
https://peps.python.org/pep-0544/
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Protocol

from finance_analysis.domain.calculation_evidence import CalculationOutcome
from finance_analysis.domain.covenant import resolve_covenant
from finance_analysis.domain.metric_contract import formula_id_of
from finance_analysis.domain.model_type import Composed, MetricExpression
from finance_analysis.domain.resolved_plan import ResolvedMetricPlan, content_digest
from finance_analysis.domain.semantic_input import (
    _active,
    _interest_slot,
    with_profile_dscr,
)

_WINDOWS = frozenset({"LTM", "period"})


class ExecutionContractError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class ProfileDscrRecord:
    """Состав профиля целиком: стороны, окно, версия и ссылка на пункт."""

    expression: MetricExpression
    profile_ref: str
    window: str | None = None
    basis_ref: str | None = None


@dataclass(frozen=True)
class CatalogMetricRecord:
    """Одна запись каталога: идентичность и выражение вместе, не двумя аргументами."""

    metric_id: str
    expression: MetricExpression
    executor_key: str
    executor_id: str
    executor_version: str
    variant: str | None = None
    formula_id: str | None = None
    definition_version: str | None = None
    window: str | None = None
    applicability: str = "required"


@dataclass(frozen=True)
class NormalizedExpression:
    numerator_plus: tuple[str, ...] = ()
    numerator_minus: tuple[str, ...] = ()
    denominator_plus: tuple[str, ...] = ()
    denominator_minus: tuple[str, ...] = ()
    one_of: tuple[str, ...] = ()
    window: str | None = None
    base: str | None = None
    rate: str | None = None
    rates: tuple[str, ...] = ()
    aggregate: str | None = None
    terminal: str | None = None
    compare_with: str | None = None
    add_back: tuple[str, str] | None = None


@dataclass(frozen=True)
class EffectiveMetricDefinition:
    metric_id: str
    formula_id: str
    definition_version: str | None
    variant: str | None
    variant_source: str
    definition_source: str
    definition_ref: Mapping[str, str | None] | None
    definition_hash: str
    normalized_expression: NormalizedExpression
    applicability: str
    executor_key: str
    executor_id: str
    executor_version: str


@dataclass(frozen=True)
class ResolvedFormulaSlot:
    slot_id: str
    original_terms: tuple[str, ...]
    resolved_terms: tuple[str, ...]
    resolution_reason: str


@dataclass(frozen=True)
class ExecutionBranchDefinition:
    branch_id: str
    selection_basis: str
    required_inputs: tuple[str, ...]
    optional_inputs: tuple[str, ...]
    profile_dependencies: tuple[str, ...]


@dataclass(frozen=True)
class ExecutionTrace:
    branch_id: str
    actual_inputs: tuple[str, ...]
    actual_fact_uses: tuple[str, ...]
    actual_periods: tuple[str, ...]
    profile_values: tuple[tuple[str, object], ...]


@dataclass(frozen=True)
class MetricExecutionContext:
    definition: EffectiveMetricDefinition
    plan: ResolvedMetricPlan
    slots: tuple[ResolvedFormulaSlot, ...]
    calculation_origin: str


class MetricExecutor(Protocol):
    def execute(self, context: MetricExecutionContext) -> CalculationOutcome: ...


def compile_definition(
    record: CatalogMetricRecord,
    catalog: Mapping[str, CatalogMetricRecord] | None = None,
    *,
    profile: ProfileDscrRecord | None = None,
    covenant: Mapping[str, object] | None = None,
) -> EffectiveMetricDefinition:
    """Сборка из одной записи, ``_active``, замены ``plans_for`` и ``resolve_covenant``.

    Профиль передаётся одной записью. Окно и пункт не достраиваются из второго объекта.
    База наследует выражение и окно своей записи, не окна потомка.
    """

    expressions = _expression_map(record, catalog)
    override = profile.expression if profile is not None else None
    active_map = with_profile_dscr(record.metric_id, expressions, record.variant, override)
    chosen = _active(record.metric_id, record.variant, active_map or {})
    if chosen is None:
        raise ExecutionContractError("unknown_metric")
    expression, variant_source, source_key = chosen
    source_record = _record_map(record, catalog).get(source_key, record)
    window = profile.window if profile is not None and expression is profile.expression else source_record.window
    normalized = _from_expression(expression, window)
    source = (
        "profile"
        if profile is not None and record.metric_id == "dscr" and expression is profile.expression
        else "catalog"
    )
    ref = _profile_ref(profile.profile_ref, profile.basis_ref) if source == "profile" else None
    if covenant is not None:
        composed, covenant_source, covenant_ref, _notes = resolve_covenant(
            covenant.get("profile") if isinstance(covenant.get("profile"), dict) else None,
            covenant.get("profile_ref") if isinstance(covenant.get("profile_ref"), str) else None,
            _default_composed(covenant),
            concepts=_frozen(covenant.get("concepts")),
            money=_frozen(covenant.get("money")),
            composed=covenant.get("composed") if isinstance(covenant.get("composed"), dict) else None,
        )
        normalized = _overlay(normalized, composed)
        source = covenant_source
        ref = None if covenant_ref is None else MappingProxyType(dict(covenant_ref))
    version = record.definition_version
    definition_version = version if isinstance(version, str) and version else None
    body: dict[str, object] = {}
    if isinstance(record.formula_id, str) and record.formula_id:
        body["formula_id"] = record.formula_id
    formula_id = formula_id_of(record.metric_id, record.variant, body)
    if not record.executor_key or not record.executor_id or not record.executor_version:
        raise ExecutionContractError("executor_identity")
    hashed = _definition_body(
        metric_id=record.metric_id,
        formula_id=formula_id,
        definition_version=definition_version,
        variant=record.variant,
        variant_source=variant_source,
        definition_source=source,
        definition_ref=None if ref is None else dict(ref),
        expression=normalized,
        applicability=record.applicability,
        executor_key=record.executor_key,
        executor_id=record.executor_id,
        executor_version=record.executor_version,
    )
    return EffectiveMetricDefinition(
        metric_id=record.metric_id,
        formula_id=formula_id,
        definition_version=definition_version,
        variant=record.variant,
        variant_source=variant_source,
        definition_source=source,
        definition_ref=ref,
        definition_hash=content_digest(hashed),
        normalized_expression=normalized,
        applicability=record.applicability,
        executor_key=record.executor_key,
        executor_id=record.executor_id,
        executor_version=record.executor_version,
    )


def slots_for(
    definition: EffectiveMetricDefinition,
    plan: ResolvedMetricPlan,
) -> tuple[ResolvedFormulaSlot, ...]:
    found: list[ResolvedFormulaSlot] = []
    expression = definition.normalized_expression
    one_of_rows = [item for item in plan.inputs if item.role == "one_of"]
    if len(one_of_rows) > 1:
        raise ExecutionContractError("ambiguous_one_of")
    if expression.one_of and one_of_rows:
        chosen = one_of_rows[0]
        if chosen.concept not in expression.one_of:
            raise ExecutionContractError("undeclared_alternative")
        if not _is_confirmed(chosen):
            raise ExecutionContractError("inconsistent_fallback")
        found.append(ResolvedFormulaSlot("numerator", expression.one_of, (chosen.concept,), "one_of"))
    denominator = set(expression.denominator_plus) | set(expression.denominator_minus)
    confirmed = _confirmed_names(plan)
    seen: set[str] = set()
    for item in plan.fallbacks:
        allowed = _interest_slot(definition.metric_id, definition.variant)
        if item.replaced in seen or item.slot != allowed or item.replaced not in denominator:
            raise ExecutionContractError("inconsistent_fallback")
        if item.chosen not in confirmed:
            raise ExecutionContractError("inconsistent_fallback")
        seen.add(item.replaced)
        if item.replaced == "debt_service":
            if "principal" not in confirmed or _unconfirmed(plan, "principal"):
                raise ExecutionContractError("inconsistent_fallback")
            found.append(
                ResolvedFormulaSlot("debt_service", ("debt_service",), (item.chosen, "principal"), "fallback")
            )
        elif item.replaced == "interest":
            found.append(ResolvedFormulaSlot("interest", ("interest",), (item.chosen,), "fallback"))
        else:
            raise ExecutionContractError("inconsistent_fallback")
    return tuple(found)


def trace_for(
    branch: ExecutionBranchDefinition,
    profile_values: Mapping[str, object],
) -> ExecutionTrace:
    values = tuple(
        (name, profile_values[name]) for name in branch.profile_dependencies if name in profile_values
    )
    return ExecutionTrace(branch.branch_id, (), (), (), values)


def read_input(
    branch: ExecutionBranchDefinition,
    trace: ExecutionTrace,
    name: str,
) -> ExecutionTrace:
    # shortcut: анализ этот охранник не вызывает, PR 4 проводит его внутри каждой специализированной ветви
    allowed = set(branch.required_inputs) | set(branch.optional_inputs)
    if name not in allowed:
        raise ExecutionContractError("forbidden_input")
    return replace(trace, actual_inputs=(*trace.actual_inputs, name))


def execute_bound(
    executor: MetricExecutor,
    definition: EffectiveMetricDefinition,
    plan: ResolvedMetricPlan,
    *,
    calculation_origin: str = "calculated",
) -> CalculationOutcome:
    """Проверка до вызова. Статус кроме resolved — отказ здесь, не внутри исполнителя.

    Калькуляторы покрытия сюда не подключены.
    """

    if plan.metric_id != definition.metric_id:
        raise ExecutionContractError("metric_mismatch")
    if plan.variant != definition.variant or plan.variant_source != definition.variant_source:
        raise ExecutionContractError("variant_mismatch")
    if plan.definition_hash != definition.definition_hash:
        raise ExecutionContractError("definition_mismatch")
    if plan.status != "resolved":
        raise ExecutionContractError("plan_not_resolved")
    context = MetricExecutionContext(
        definition=definition,
        plan=plan,
        slots=slots_for(definition, plan),
        calculation_origin=calculation_origin,
    )
    return executor.execute(context)


def _expression_map(
    record: CatalogMetricRecord,
    catalog: Mapping[str, CatalogMetricRecord] | None,
) -> dict[str, MetricExpression]:
    found = {_record_key(item): item.expression for item in (catalog or {}).values()}
    found[_record_key(record)] = record.expression
    return found


def _record_map(
    record: CatalogMetricRecord,
    catalog: Mapping[str, CatalogMetricRecord] | None,
) -> dict[str, CatalogMetricRecord]:
    found = {_record_key(item): item for item in (catalog or {}).values()}
    found[_record_key(record)] = record
    return found


def _record_key(record: CatalogMetricRecord) -> str:
    if record.variant:
        return f"{record.metric_id}.{record.variant}"
    return record.metric_id


def _from_expression(expression: MetricExpression, window: str | None) -> NormalizedExpression:
    return NormalizedExpression(
        numerator_plus=expression.numerator_plus,
        numerator_minus=expression.numerator_minus,
        denominator_plus=expression.denominator_plus,
        denominator_minus=expression.denominator_minus,
        one_of=expression.one_of_order or tuple(sorted(expression.one_of)),
        window=window if isinstance(window, str) and window in _WINDOWS else None,
        base=expression.base,
        rate=expression.rate,
        rates=expression.rates,
        aggregate=expression.aggregate,
        terminal=expression.terminal,
        compare_with=expression.compare_with,
        add_back=expression.add_back,
    )


def _overlay(expression: NormalizedExpression, composed: Composed) -> NormalizedExpression:
    return replace(
        expression,
        numerator_plus=composed.numerator.plus,
        numerator_minus=composed.numerator.minus,
        denominator_plus=composed.denominator.plus,
        denominator_minus=composed.denominator.minus,
        one_of=(),
        window=composed.window,
    )


def _profile_ref(profile_ref: str | None, basis_ref: str | None = None) -> Mapping[str, str | None] | None:
    if not isinstance(profile_ref, str) or not profile_ref:
        return None
    profile_id = profile_ref.split("@", 1)[0] if "@" in profile_ref else profile_ref
    basis = basis_ref if isinstance(basis_ref, str) and basis_ref else None
    return MappingProxyType(
        {"profile_id": profile_id, "profile_version": profile_ref, "basis_ref": basis}
    )


def _default_composed(covenant: Mapping[str, object]) -> Composed:
    default = covenant.get("default")
    if not isinstance(default, Composed):
        raise ExecutionContractError("covenant_default")
    return default


def _frozen(value: object) -> frozenset[str]:
    if isinstance(value, frozenset):
        return value
    return frozenset()


def _is_confirmed(item: object) -> bool:
    return bool(getattr(item, "confirmed", False)) and not bool(getattr(item, "ambiguous", False))


def _confirmed_names(plan: ResolvedMetricPlan) -> set[str]:
    return {item.concept for item in plan.inputs if _is_confirmed(item)}


def _unconfirmed(plan: ResolvedMetricPlan, concept: str) -> bool:
    return any(item.concept == concept and not _is_confirmed(item) for item in plan.inputs)


def _definition_body(
    *,
    metric_id: str,
    formula_id: str,
    definition_version: str | None,
    variant: str | None,
    variant_source: str,
    definition_source: str,
    definition_ref: dict | None,
    expression: NormalizedExpression,
    applicability: str,
    executor_key: str,
    executor_id: str,
    executor_version: str,
) -> dict:
    add_back = list(expression.add_back) if expression.add_back else []
    return {
        "applicability": applicability,
        "definition_ref": definition_ref,
        "definition_source": definition_source,
        "definition_version": definition_version or "",
        "executor_id": executor_id,
        "executor_key": executor_key,
        "executor_version": executor_version,
        "expression": {
            "add_back": add_back,
            "aggregate": expression.aggregate or "",
            "base": expression.base or "",
            "compare_with": expression.compare_with or "",
            "denominator_minus": list(expression.denominator_minus),
            "denominator_plus": list(expression.denominator_plus),
            "numerator_minus": list(expression.numerator_minus),
            "numerator_plus": list(expression.numerator_plus),
            "one_of": list(expression.one_of),
            "rate": expression.rate or "",
            "rates": list(expression.rates),
            "terminal": expression.terminal or "",
            "window": expression.window or "",
        },
        "formula_id": formula_id,
        "metric_id": metric_id,
        "variant": variant or "",
        "variant_source": variant_source,
    }
