"""Один диспетчер расчёта. Пять маршрутов — тонкие исполнители реестра.

Исполнитель — протокол с одним методом, PEP 544: https://peps.python.org/pep-0544/
Вызов ``execute`` — одна деятельность, не запасной путь:
https://www.w3.org/TR/prov-dm/#term-Activity
Нет записи в реестре — отказ. Прежняя функция и ветка ``select_ratio`` не вызываются.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from finance_analysis.domain.calculation_evidence import CalculationOutcome
from finance_analysis.domain.cover_metrics import LOAN_LIFE, REDUCED
from finance_analysis.domain.execution_contract import MetricExecutionContext
from finance_analysis.domain.housing_cover import use_housing_cover

_ROUTES = frozenset({"dispatch_cover", "loan_life", "reduced", "adscr", "select_ratio"})


@dataclass(frozen=True)
class CalculationRequest:
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
    plan: Any = None
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


def run_calculation(
    route: str,
    request: CalculationRequest,
    context: MetricExecutionContext,
    *,
    executors: Mapping[str, Any] | None = None,
) -> CalculationOutcome:
    """Исполнитель из реестра. Нет его или ключ чужой — отказ, не следующая функция."""

    table = CALCULATION_EXECUTORS if executors is None else executors
    factory = table.get(route)
    if factory is None or route not in _ROUTES:
        return CalculationOutcome(_refusal(request.metric, "missing_executor"), None)
    executor = factory(request)
    key = None if context.definition is None else context.definition.executor_key
    if key is not None and key not in executor.compatible:
        return CalculationOutcome(_refusal(request.metric, "incompatible_executor"), None)
    return executor.execute(context)


class DispatchCoverExecutor:
    compatible = frozenset({"dispatch_cover"})

    def __init__(self, request: CalculationRequest) -> None:
        self.request = request

    def execute(self, context: MetricExecutionContext) -> CalculationOutcome:
        # shortcut: функция не читает определение, поэтому любое определение — отказ; PR 4 называет ветвь
        if context.definition is not None:
            return CalculationOutcome(_refusal(self.request.metric, "unsupported_formula"), None)
        result = _call_dispatch_cover(self.request)
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
        return CalculationOutcome(_call_loan_life(self.request), None)


class ReducedExecutor:
    compatible = frozenset({"reduced"})

    def __init__(self, request: CalculationRequest) -> None:
        self.request = request

    def execute(self, context: MetricExecutionContext) -> CalculationOutcome:
        # shortcut: функция не читает определение, поэтому любое определение — отказ; PR 4 называет ветвь
        if context.definition is not None:
            return CalculationOutcome(_refusal(self.request.metric, "unsupported_formula"), None)
        return CalculationOutcome(_call_reduced(self.request), None)


class AdscrExecutor:
    compatible = frozenset({"adscr"})

    def __init__(self, request: CalculationRequest) -> None:
        self.request = request

    def execute(self, context: MetricExecutionContext) -> CalculationOutcome:
        # shortcut: функция не читает определение, поэтому любое определение — отказ; PR 4 называет ветвь
        if context.definition is not None:
            return CalculationOutcome(_refusal(self.request.metric, "unsupported_formula"), None)
        return CalculationOutcome(_call_adscr(self.request), None)


class SelectRatioExecutor:
    compatible = frozenset({"select_ratio", "coverage", "composed"})

    def __init__(self, request: CalculationRequest) -> None:
        self.request = request

    def execute(self, context: MetricExecutionContext) -> CalculationOutcome:
        definition = context.definition if context.definition is not None else self.request.definition
        return CalculationOutcome(_call_select_ratio(self.request, definition), None)


CALCULATION_EXECUTORS: dict[str, type] = {
    "dispatch_cover": DispatchCoverExecutor,
    "loan_life": LoanLifeExecutor,
    "reduced": ReducedExecutor,
    "adscr": AdscrExecutor,
    "select_ratio": SelectRatioExecutor,
}


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


def _call_dispatch_cover(request: CalculationRequest):
    from finance_analysis.domain.housing_cover import dispatch_cover

    return dispatch_cover(
        request.metric,
        metric_variant=request.metric_variant,
        dscr_variant=request.dscr_variant,
        profile=request.profile,
        basis=request.basis,
        direction=request.direction,
        common=_common(request),
        plan=request.plan,
    )


def _call_loan_life(request: CalculationRequest):
    from finance_analysis.domain.cover_metrics import loan_life_ratio

    return loan_life_ratio(request.metric, basis=request.basis, plan=request.plan, **_common(request))


def _call_reduced(request: CalculationRequest):
    from finance_analysis.domain.cover_metrics import dscr_reductions

    return dscr_reductions(request.metric, plan=request.plan, collect=request.collect, **_common(request))


def _call_adscr(request: CalculationRequest):
    from finance_analysis.domain.cover_metrics import adscr

    return adscr(direction=request.direction, plan=request.plan, collect=request.collect, **_common(request))


def _call_select_ratio(request: CalculationRequest, definition):
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
        plan=request.plan,
        collect=request.collect,
        definition=definition,
        outflows=request.outflows,
    )
