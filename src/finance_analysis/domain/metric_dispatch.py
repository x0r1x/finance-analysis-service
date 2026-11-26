"""Один диспетчер расчёта. Пять маршрутов — тонкие исполнители реестра.

Исполнитель — протокол с одним методом, PEP 544: https://peps.python.org/pep-0544/
Вызов ``execute`` — одна деятельность, не запасной путь:
https://www.w3.org/TR/prov-dm/#term-Activity
Идентичность алгоритма — запись реестра, а не вторая копия на определении:
https://openlineage.io/docs/spec/object-model/
Нет записи в реестре — отказ. Прежняя функция и ветка ``select_ratio`` не вызываются.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from finance_analysis.domain.calculation_evidence import CalculationOutcome
from finance_analysis.domain.cover_metrics import LOAN_LIFE, REDUCED
from finance_analysis.domain.execution_contract import MetricExecutionContext
from finance_analysis.domain.housing_cover import use_housing_cover

_CONFLICT = object()
# (executor_key, executor_id, executor_version) — алгоритм, который маршрут реально вызывает.
_SELECT_RATIO = (
    ("coverage", "calculate_coverage", "calculate_coverage@1"),
    ("composed", "composed_ratio", "composed_ratio@1"),
)


@dataclass(frozen=True)
class CalculationRequest:
    """Финансовые параметры вызова. Определение и план — на контексте исполнения."""

    metric: str
    variant: str | None = None
    metric_variant: str | None = None
    dscr_variant: str | None = None
    common: dict | None = None
    basis: str = "period_end"
    direction: str = "lookback"
    profile: dict | None = None
    profile_ref: str | None = None
    composed: dict | None = None
    concepts: frozenset[str] = frozenset()
    money: frozenset[str] = frozenset()
    aggregations: Mapping[str, str] | None = None
    interest_order: dict | None = None
    row_fallbacks: dict | None = None
    links: list | None = None
    statement_sheets: frozenset[str] | None = None
    collect: list | None = None
    definition: Any = None
    outflows: frozenset[str] | None = None


def route_for(metric: str, *, metric_variant, dscr_variant, profile) -> str:
    """Тот же порядок, что был у ``compute_metrics``. ``None`` от покрытия сюда не входит."""

    if use_housing_cover(metric, metric_variant, dscr_variant, profile):
        return "dispatch_cover"
    if metric in LOAN_LIFE:
        return "loan_life"
    if metric in REDUCED:
        return "reduced"
    if metric == "adscr":
        return "adscr"
    return "select_ratio"


def route_names() -> frozenset[str]:
    """Единственный список маршрутов: ключи реестра."""

    return frozenset(CALCULATION_EXECUTORS)


def _returns_of_route_for() -> frozenset[str]:
    tree = ast.parse(textwrap.dedent(inspect.getsource(route_for)))
    found = {
        node.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
    }
    return frozenset(found)


def run_calculation(
    route: str,
    request: CalculationRequest,
    context: MetricExecutionContext,
    *,
    executors: Mapping[str, Any] | None = None,
) -> CalculationOutcome:
    """Одно определение до проверки. Исполнитель получает тот же объект."""

    definition = _resolve_definition(request, context)
    if definition is _CONFLICT:
        return CalculationOutcome(_refusal(request.metric, "definition_mismatch"), None)
    context = replace(context, definition=definition)
    table = CALCULATION_EXECUTORS if executors is None else executors
    factory = table.get(route)
    if factory is None:
        return CalculationOutcome(_refusal(request.metric, "missing_executor"), None)
    executor = factory(request)
    rejected = _rejection(executor, context.definition)
    if rejected is not None:
        return CalculationOutcome(_refusal(request.metric, rejected), None)
    return executor.execute(context)


class DispatchCoverExecutor:
    compatible = frozenset({"dispatch_cover"})

    def __init__(self, request: CalculationRequest) -> None:
        self.request = request

    def execute(self, context: MetricExecutionContext) -> CalculationOutcome:
        # shortcut: функция не читает определение, поэтому любое определение — отказ; PR 4 называет ветвь
        if context.definition is not None:
            return CalculationOutcome(_refusal(self.request.metric, "unsupported_formula"), None)
        result = _call_dispatch_cover(self.request, context)
        if result is None:
            return CalculationOutcome(_refusal(self.request.metric, "missing_executor"), None)
        return CalculationOutcome(result, None)


class LoanLifeExecutor:
    compatible = frozenset({"loan_life"})

    def __init__(self, request: CalculationRequest) -> None:
        self.request = request

    def execute(self, context: MetricExecutionContext) -> CalculationOutcome:
        # shortcut: функция не читает определение, поэтому любое определение — отказ; PR 4 называет ветвь
        if context.definition is not None:
            return CalculationOutcome(_refusal(self.request.metric, "unsupported_formula"), None)
        return CalculationOutcome(_call_loan_life(self.request, context), None)


class ReducedExecutor:
    compatible = frozenset({"reduced"})

    def __init__(self, request: CalculationRequest) -> None:
        self.request = request

    def execute(self, context: MetricExecutionContext) -> CalculationOutcome:
        # shortcut: функция не читает определение, поэтому любое определение — отказ; PR 4 называет ветвь
        if context.definition is not None:
            return CalculationOutcome(_refusal(self.request.metric, "unsupported_formula"), None)
        return CalculationOutcome(_call_reduced(self.request, context), None)


class AdscrExecutor:
    compatible = frozenset({"adscr"})

    def __init__(self, request: CalculationRequest) -> None:
        self.request = request

    def execute(self, context: MetricExecutionContext) -> CalculationOutcome:
        # shortcut: функция не читает определение, поэтому любое определение — отказ; PR 4 называет ветвь
        if context.definition is not None:
            return CalculationOutcome(_refusal(self.request.metric, "unsupported_formula"), None)
        return CalculationOutcome(_call_adscr(self.request, context), None)


class SelectRatioExecutor:
    identities = _SELECT_RATIO
    compatible = frozenset(item[0] for item in identities)

    def __init__(self, request: CalculationRequest) -> None:
        self.request = request

    def execute(self, context: MetricExecutionContext) -> CalculationOutcome:
        return CalculationOutcome(_call_select_ratio(self.request, context), None)


CALCULATION_EXECUTORS: dict[str, type] = {
    "dispatch_cover": DispatchCoverExecutor,
    "loan_life": LoanLifeExecutor,
    "reduced": ReducedExecutor,
    "adscr": AdscrExecutor,
    "select_ratio": SelectRatioExecutor,
}


def _require_one_registry() -> None:
    returned = _returns_of_route_for()
    registered = frozenset(CALCULATION_EXECUTORS)
    if returned != registered:
        raise RuntimeError(f"маршруты разошлись: {sorted(returned ^ registered)}")


_require_one_registry()


def _resolve_definition(request: CalculationRequest, context: MetricExecutionContext):
    """Один объект. Два разных определения — отказ, а не выбор одного из них."""

    supplied = request.definition
    bound = context.definition
    if supplied is not None and bound is not None and supplied is not bound:
        return _CONFLICT
    if bound is not None:
        return bound
    return supplied


def _rejection(executor: Any, definition: Any) -> str | None:
    if definition is None:
        return None
    rows = tuple(getattr(executor, "identities", ()))
    if rows:
        for key, executor_id, executor_version in rows:
            if (
                key == definition.executor_key
                and executor_id == definition.executor_id
                and executor_version == definition.executor_version
            ):
                return None
        return "incompatible_executor"
    if definition.executor_key not in executor.compatible:
        return "incompatible_executor"
    return None


def _refusal(metric: str, reason: str) -> dict:
    return {
        "metric": metric,
        "rows": [],
        "needs_input": [],
        "missing_inputs": [],
        "warnings": [],
        "status": "not_computed",
        "reason": reason,
        "message": reason,
    }


def _common(request: CalculationRequest) -> dict:
    return request.common if request.common is not None else {}


def _call_dispatch_cover(request: CalculationRequest, context: MetricExecutionContext):
    from finance_analysis.domain.housing_cover import dispatch_cover

    return dispatch_cover(
        request.metric,
        metric_variant=request.metric_variant,
        dscr_variant=request.dscr_variant,
        profile=request.profile,
        basis=request.basis,
        direction=request.direction,
        common=_common(request),
        plan=context.plan,
    )


def _call_loan_life(request: CalculationRequest, context: MetricExecutionContext):
    from finance_analysis.domain.cover_metrics import loan_life_ratio

    return loan_life_ratio(request.metric, basis=request.basis, plan=context.plan, **_common(request))


def _call_reduced(request: CalculationRequest, context: MetricExecutionContext):
    from finance_analysis.domain.cover_metrics import dscr_reductions

    return dscr_reductions(request.metric, plan=context.plan, collect=request.collect, **_common(request))


def _call_adscr(request: CalculationRequest, context: MetricExecutionContext):
    from finance_analysis.domain.cover_metrics import adscr

    return adscr(direction=request.direction, plan=context.plan, collect=request.collect, **_common(request))


def _call_select_ratio(request: CalculationRequest, context: MetricExecutionContext):
    from finance_analysis.domain.covenant import select_ratio

    return select_ratio(
        request.metric,
        request.variant,
        _common(request),
        profile=request.profile,
        profile_ref=request.profile_ref,
        composed=request.composed,
        concepts=request.concepts,
        money=request.money,
        interest_order=request.interest_order,
        row_fallbacks=request.row_fallbacks,
        links=request.links,
        statement_sheets=request.statement_sheets,
        aggregations=request.aggregations,
        plan=context.plan,
        collect=request.collect,
        definition=context.definition,
        outflows=request.outflows,
    )
