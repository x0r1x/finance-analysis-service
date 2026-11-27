"""Контракт исполнения. Базовые DSCR, DSCR pf, ICR и ICR EBIT берут стороны отсюда.

Идентичность исполнителя — отдельный объект с одним методом, как в PEP 544:
https://peps.python.org/pep-0544/
"""

from __future__ import annotations

from collections.abc import Mapping
from contextvars import ContextVar
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
    profile_ref: str | None = None
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
    # (concept, binding_key, row_key). binding_key устойчив, row_key — текущая строка.
    # Чтение идёт из этого слота, план заново не выбирает строку.
    # https://www.w3.org/TR/prov-dm/#term-Plan
    term_rows: tuple[tuple[str, str | None, str | None], ...] = ()
    warning_code: str | None = None
    # Параметры предупреждения, уже собранные со плана. None — текста на слоте нет.
    # Связанный путь plan.warnings заново не читает.
    # https://www.w3.org/TR/prov-dm/#term-Plan
    warning_params: tuple[tuple[str, str], ...] | None = None


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
    actual_period_slots: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class MetricExecutionContext:
    definition: EffectiveMetricDefinition | None = None
    plan: ResolvedMetricPlan | None = None
    # None — слоты не переданы. Пустой кортеж — связанный план без подстановок.
    # https://www.w3.org/TR/prov-dm/#term-Plan
    slots: tuple[ResolvedFormulaSlot, ...] | None = None
    calculation_origin: str = "calculated"
    branch_id: str | None = None


class MetricExecutor(Protocol):
    def execute(self, context: MetricExecutionContext) -> CalculationOutcome: ...


# Идентификатор ветви, которую сейчас исполняет контекст. Пусто — охранник не сверяет.
_branch_context: ContextVar[str | None] = ContextVar("execution_branch_id", default=None)


def bind_branch(branch_id: str | None):
    """Привязывает след к ветви контекста на время прогона."""

    return _branch_context.set(branch_id)


def reset_branch(token) -> None:
    _branch_context.reset(token)


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
        found.append(
            ResolvedFormulaSlot(
                "numerator",
                expression.one_of,
                (chosen.concept,),
                "one_of",
                (_term_row(chosen),),
            )
        )
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
                ResolvedFormulaSlot(
                    "debt_service",
                    ("debt_service",),
                    (item.chosen, "principal"),
                    "fallback",
                    _rows_of(plan, (item.chosen, "principal")),
                    item.warning_code,
                    _ready_params(plan, item.warning_code),
                )
            )
        elif item.replaced == "interest":
            found.append(
                ResolvedFormulaSlot(
                    "interest",
                    ("interest",),
                    (item.chosen,),
                    "fallback",
                    _rows_of(plan, (item.chosen,)),
                    item.warning_code,
                    _ready_params(plan, item.warning_code),
                )
            )
        else:
            raise ExecutionContractError("inconsistent_fallback")
    covered = {concept for slot in found for concept, _key, _row in slot.term_rows}
    named = _expression_names(expression)
    for item in plan.inputs:
        if not _is_confirmed(item) or item.concept in covered or item.concept not in named:
            continue
        found.append(
            ResolvedFormulaSlot(
                f"input:{item.concept}",
                (item.concept,),
                (item.concept,),
                "confirmed",
                (_term_row(item),),
            )
        )
    _place_ready_warnings(found, plan)
    return tuple(found)


def trace_for(
    branch: ExecutionBranchDefinition,
    profile_values: Mapping[str, object],
) -> ExecutionTrace:
    """Значение каждой профильной зависимости. Пропуск имени — отказ, не дырка в следе."""

    missing = [name for name in branch.profile_dependencies if name not in profile_values]
    if missing:
        raise ExecutionContractError("missing_profile")
    values = tuple((name, profile_values[name]) for name in branch.profile_dependencies)
    return ExecutionTrace(branch.branch_id, (), (), (), values)


def read_input(
    branch: ExecutionBranchDefinition,
    trace: ExecutionTrace,
    name: str,
) -> ExecutionTrace:
    """Чтение входа ветви. Чужое имя и чужой контекст отказываются здесь, не после прогона."""

    expected = _branch_context.get()
    if expected is not None and expected != branch.branch_id:
        raise ExecutionContractError("branch_mismatch")
    if trace.branch_id != branch.branch_id:
        raise ExecutionContractError("branch_mismatch")
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

    Слоты собираются один раз и передаются исполнителю.
    """

    if plan.metric_id != definition.metric_id:
        raise ExecutionContractError("metric_mismatch")
    if plan.variant != definition.variant or plan.variant_source != definition.variant_source:
        raise ExecutionContractError("variant_mismatch")
    if plan.definition_hash != definition.definition_hash:
        raise ExecutionContractError("definition_mismatch")
    if plan.status != "resolved":
        raise ExecutionContractError("plan_not_resolved")
    # Слоты — уже решённый план, в том числе пустой кортеж. Исполнитель их не выбирает заново.
    # https://www.w3.org/TR/prov-dm/#term-Plan
    slots = slots_for(definition, plan)
    if definition.executor_key in {"coverage", "composed"}:
        from finance_analysis.domain.metric_contract import UndeclaredInput
        from finance_analysis.domain.metrics import _guard_declared

        # UndeclaredInput — это KeyError. Отказ деятельности должен остаться исходом.
        # https://www.w3.org/TR/prov-dm/#term-Activity
        try:
            _guard_declared(definition, plan, slots)
        except UndeclaredInput:
            raise ExecutionContractError("undeclared_input") from None
    context = MetricExecutionContext(
        definition=definition,
        plan=plan,
        slots=slots,
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


def _profile_ref(profile_ref: str | None, basis_ref: str | None = None) -> Mapping[str, str | None]:
    """Версия профиля, если она есть. Пустая строка не становится именем ``profile``."""

    version = profile_ref if isinstance(profile_ref, str) and profile_ref else None
    basis = basis_ref if isinstance(basis_ref, str) and basis_ref else None
    profile_id = version.split("@", 1)[0] if version and "@" in version else version
    return MappingProxyType(
        {"profile_id": profile_id, "profile_version": version, "basis_ref": basis}
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


def _ready_params(plan, code: str | None):
    """Параметры предупреждения с тем же кодом. Нет записи — на слоте текста нет."""

    if not code:
        return None
    found = next((item for item in plan.warnings if item.code == code), None)
    return None if found is None else found.params


# Код предупреждения называет слот. Свободный числитель не выбирается.
# https://www.w3.org/TR/prov-dm/#term-Plan
_WARNING_HOME = {
    "icr_numerator": frozenset({"numerator"}),
    "interest_basis_fallback": frozenset({"interest", "debt_service"}),
}


def _place_ready_warnings(slots: list, plan) -> None:
    """Предупреждение без своего запаса ложится на слот, который называет код.

    Предупреждение не всегда про числитель, поэтому свободный числитель его не принимает.
    Два кода остаются на двух слотах. Калькулятор потом читает слот, а не plan.warnings.
    https://www.w3.org/TR/prov-dm/#term-Plan
    """

    taken = {slot.warning_code for slot in slots if slot.warning_code}
    for item in plan.warnings:
        if item.code in taken:
            continue
        homes = _WARNING_HOME.get(item.code)
        if not homes:
            continue
        hits = [
            index
            for index, slot in enumerate(slots)
            if slot.slot_id in homes and slot.warning_code is None
        ]
        if len(hits) != 1:
            continue
        slots[hits[0]] = replace(slots[hits[0]], warning_code=item.code, warning_params=item.params)
        taken.add(item.code)


def _term_row(item) -> tuple[str, str | None, str | None]:
    return (item.concept, item.binding_key, item.row_key)


def _rows_of(plan: ResolvedMetricPlan, concepts: tuple[str, ...]) -> tuple[tuple[str, str | None, str | None], ...]:
    rows = []
    for concept in concepts:
        item = next((row for row in plan.inputs if row.concept == concept and _is_confirmed(row)), None)
        if item is not None:
            rows.append(_term_row(item))
    return tuple(rows)


def _expression_names(expression: NormalizedExpression) -> set[str]:
    return (
        set(expression.numerator_plus)
        | set(expression.numerator_minus)
        | set(expression.denominator_plus)
        | set(expression.denominator_minus)
        | set(expression.one_of)
    )


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
