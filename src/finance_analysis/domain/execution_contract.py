"""Контракт исполнения. Диспетчер расчёта его пока не вызывает.

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
from finance_analysis.domain.resolved_plan import (
    ResolvedMetricPlan,
    content_digest,
)
from finance_analysis.domain.semantic_input import _active, with_profile_dscr

_WINDOWS = frozenset({"LTM", "period"})


class ExecutionContractError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class NormalizedExpression:
    numerator_plus: tuple[str, ...] = ()
    numerator_minus: tuple[str, ...] = ()
    denominator_plus: tuple[str, ...] = ()
    denominator_minus: tuple[str, ...] = ()
    one_of: tuple[str, ...] = ()
    window: str | None = None
    base: str | None = None


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
    metric_id: str,
    expressions: Mapping[str, MetricExpression],
    *,
    variant: str | None = None,
    formula_body: Mapping[str, object] | None = None,
    dscr_expression: MetricExpression | None = None,
    applicability: str = "required",
    covenant: Mapping[str, object] | None = None,
) -> EffectiveMetricDefinition:
    """Сборка из ``_active``, замены ``plans_for`` и, когда передан, ``resolve_covenant``."""

    body = formula_body or {}
    active_map = with_profile_dscr(metric_id, expressions, variant, dscr_expression)
    chosen = _active(metric_id, variant, active_map or {})
    if chosen is None:
        raise ExecutionContractError("unknown_metric")
    expression, variant_source = chosen
    normalized = _from_expression(expression, body)
    source = "profile" if metric_id == "dscr" and dscr_expression is not None else "catalog"
    ref: Mapping[str, str | None] | None = None
    if covenant is not None:
        composed, covenant_source, covenant_ref, _notes = resolve_covenant(
            covenant.get("profile") if isinstance(covenant.get("profile"), dict) else None,
            covenant.get("profile_ref") if isinstance(covenant.get("profile_ref"), str) else None,
            _default_composed(covenant),
            concepts=_frozen(covenant.get("concepts")),
            money=_frozen(covenant.get("money")),
            composed=covenant.get("composed") if isinstance(covenant.get("composed"), dict) else None,
        )
        normalized = _from_composed(composed)
        source = covenant_source
        ref = None if covenant_ref is None else MappingProxyType(dict(covenant_ref))
    version = body.get("definition_version")
    definition_version = version if isinstance(version, str) and version else None
    formula_id = formula_id_of(metric_id, variant, body)
    hashed = _definition_body(
        metric_id=metric_id,
        formula_id=formula_id,
        definition_version=definition_version,
        variant=variant,
        variant_source=variant_source,
        definition_source=source,
        definition_ref=None if ref is None else dict(ref),
        expression=normalized,
        applicability=applicability,
        executor_key=formula_id,
    )
    return EffectiveMetricDefinition(
        metric_id=metric_id,
        formula_id=formula_id,
        definition_version=definition_version,
        variant=variant,
        variant_source=variant_source,
        definition_source=source,
        definition_ref=ref,
        definition_hash=content_digest(hashed),
        normalized_expression=normalized,
        applicability=applicability,
        executor_key=formula_id,
    )


def reference_definition(
    plan: ResolvedMetricPlan,
    definition: EffectiveMetricDefinition,
) -> ResolvedMetricPlan:
    """План хранит хеш определения и не копирует его стороны."""

    return replace(plan, definition_hash=definition.definition_hash)


def slots_for(
    definition: EffectiveMetricDefinition,
    plan: ResolvedMetricPlan,
) -> tuple[ResolvedFormulaSlot, ...]:
    found: list[ResolvedFormulaSlot] = []
    one_of = definition.normalized_expression.one_of
    if one_of:
        chosen = next((item.concept for item in plan.inputs if item.role == "one_of"), None)
        if chosen is not None:
            if chosen not in one_of:
                raise ExecutionContractError("undeclared_alternative")
            found.append(ResolvedFormulaSlot("numerator", one_of, (chosen,), "one_of"))
    for item in plan.fallbacks:
        if item.replaced == "debt_service":
            terms = [item.chosen]
            if any(row.concept == "principal" for row in plan.inputs):
                terms.append("principal")
            found.append(ResolvedFormulaSlot("debt_service", ("debt_service",), tuple(terms), "fallback"))
        elif item.replaced == "interest":
            found.append(
                ResolvedFormulaSlot("interest", ("interest",), (item.chosen,), "fallback")
            )
    return tuple(found)


def trace_for(
    branch: ExecutionBranchDefinition,
    profile_values: Mapping[str, object],
) -> ExecutionTrace:
    values = tuple(
        (name, profile_values[name])
        for name in branch.profile_dependencies
        if name in profile_values
    )
    return ExecutionTrace(branch.branch_id, (), (), (), values)


def read_input(
    branch: ExecutionBranchDefinition,
    trace: ExecutionTrace,
    name: str,
) -> ExecutionTrace:
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
    """Проверка до вызова. Калькуляторы покрытия сюда не подключены."""

    if plan.definition_hash != definition.definition_hash:
        raise ExecutionContractError("definition_mismatch")
    if plan.variant != definition.variant or plan.variant_source != definition.variant_source:
        raise ExecutionContractError("variant_mismatch")
    context = MetricExecutionContext(
        definition=definition,
        plan=plan,
        slots=slots_for(definition, plan),
        calculation_origin=calculation_origin,
    )
    return executor.execute(context)


def _from_expression(expression: MetricExpression, body: Mapping[str, object]) -> NormalizedExpression:
    window = body.get("window")
    return NormalizedExpression(
        numerator_plus=expression.numerator_plus,
        numerator_minus=expression.numerator_minus,
        denominator_plus=expression.denominator_plus,
        denominator_minus=expression.denominator_minus,
        one_of=expression.one_of_order or tuple(sorted(expression.one_of)),
        window=window if isinstance(window, str) and window in _WINDOWS else None,
        base=expression.base,
    )


def _from_composed(composed: Composed) -> NormalizedExpression:
    return NormalizedExpression(
        numerator_plus=composed.numerator.plus,
        numerator_minus=composed.numerator.minus,
        denominator_plus=composed.denominator.plus,
        denominator_minus=composed.denominator.minus,
        window=composed.window,
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
) -> dict:
    return {
        "applicability": applicability,
        "definition_ref": definition_ref,
        "definition_source": definition_source,
        "definition_version": definition_version or "",
        "executor_key": executor_key,
        "expression": {
            "base": expression.base or "",
            "denominator_minus": list(expression.denominator_minus),
            "denominator_plus": list(expression.denominator_plus),
            "numerator_minus": list(expression.numerator_minus),
            "numerator_plus": list(expression.numerator_plus),
            "one_of": list(expression.one_of),
            "window": expression.window or "",
        },
        "formula_id": formula_id,
        "metric_id": metric_id,
        "variant": variant or "",
        "variant_source": variant_source,
    }
