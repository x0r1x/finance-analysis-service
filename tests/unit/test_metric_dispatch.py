"""Один диспетчер compute_metrics. Маршрут — исполнитель реестра, не прямой вызов.

Протокол — PEP 544: https://peps.python.org/pep-0544/
Один вызов execute — одна деятельность: https://www.w3.org/TR/prov-dm/#term-Activity
"""

import ast
import inspect
import textwrap
from decimal import Decimal

import pytest

from finance_analysis.application.analyses import Analyses
from finance_analysis.domain.execution_contract import (
    CatalogMetricRecord,
    MetricExecutionContext,
    compile_definition,
)
from finance_analysis.domain.metric_contract import UndeclaredInput
from finance_analysis.domain.model_type import MetricExpression
from finance_analysis.domain.resolved_plan import ResolvedInput, seal
from finance_analysis.domain.semantic_input import resolve_metric_plan

_OLD_CALLS = frozenset(
    {
        "dispatch_cover",
        "loan_life_ratio",
        "dscr_reductions",
        "adscr",
        "select_ratio",
    }
)


def _called_names(function) -> set[str]:
    found = set()
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    for child in ast.walk(tree):
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
            found.add(child.func.id)
        elif isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
            found.add(child.func.attr)
    return found


def test_compute_metrics_does_not_call_the_old_routes():
    names = _called_names(Analyses.compute_metrics)
    assert names.isdisjoint(_OLD_CALLS)


def _dispatch():
    from finance_analysis.domain.metric_dispatch import (
        CALCULATION_EXECUTORS,
        CalculationRequest,
        route_for,
        run_calculation,
    )

    return CALCULATION_EXECUTORS, CalculationRequest, route_for, run_calculation


def _expr(**kwargs) -> MetricExpression:
    return MetricExpression(**kwargs)


def _definition(metric: str, expression: MetricExpression, *, executor_key: str, **kwargs):
    return compile_definition(
        CatalogMetricRecord(
            metric_id=metric,
            expression=expression,
            executor_key=executor_key,
            executor_id=kwargs.pop("executor_id", executor_key),
            executor_version=kwargs.pop("executor_version", f"{executor_key}@1"),
            **kwargs,
        )
    )


def _year_period() -> list[dict]:
    return [{"axis_id": "a", "period_id": "Y1", "period_index": 1, "grain": "year", "timeline_id": "t"}]


def _common(facts, bindings) -> dict:
    return {
        "facts": facts,
        "bindings": bindings,
        "periods": _year_period(),
        "period_phase": {},
        "explicit_phases": False,
        "sign_convention": "outflow_negative",
        "marker_class": None,
        "absent": frozenset(),
    }


def _bind(concept: str, row: str) -> dict:
    return {
        "effective_concept": concept,
        "row_key": row,
        "binding_key": row,
        "is_primary": True,
        "status": "bound",
        "source": "inferred",
    }


def _fact(row: str, value: str) -> dict:
    return {"row_key": row, "axis_id": "a", "period_id": "Y1", "normalized_value": value}


def _plan_for(definition, bindings):
    expression = _expr(
        numerator_plus=definition.normalized_expression.numerator_plus,
        numerator_minus=definition.normalized_expression.numerator_minus,
        denominator_plus=definition.normalized_expression.denominator_plus,
        denominator_minus=definition.normalized_expression.denominator_minus,
        one_of=frozenset(definition.normalized_expression.one_of),
        one_of_order=definition.normalized_expression.one_of,
    )
    key = definition.metric_id if definition.variant is None else f"{definition.metric_id}.{definition.variant}"
    return resolve_metric_plan(
        definition.metric_id,
        bindings,
        {key: expression},
        variant=definition.variant,
        definition=definition,
    )


def _request(metric: str, **kwargs):
    _, calculation_request, _, _ = _dispatch()
    return calculation_request(metric=metric, **kwargs)


def _context(definition=None, plan=None) -> MetricExecutionContext:
    return MetricExecutionContext(definition=definition, plan=plan)


@pytest.mark.parametrize(
    ("metric", "metric_variant", "dscr_variant", "profile", "route"),
    [
        ("adscr", None, None, None, "adscr"),
        ("adscr", "housing", None, None, "dispatch_cover"),
        ("dscr_min", None, None, None, "reduced"),
        ("dscr_avg", None, "housing", None, "dispatch_cover"),
        ("llcr", None, None, None, "loan_life"),
        ("plcr", None, None, None, "loan_life"),
        ("llcr", "cbr590", None, None, "dispatch_cover"),
        ("escrow_blended_rate", None, None, None, "dispatch_cover"),
        ("dscr", None, None, None, "select_ratio"),
        ("net_debt_ebitda", None, None, None, "select_ratio"),
        ("icr", None, None, None, "select_ratio"),
    ],
)
def test_route_for_names_the_current_calculation_route(metric, metric_variant, dscr_variant, profile, route):
    _, _, route_for, _ = _dispatch()
    assert route_for(metric, metric_variant=metric_variant, dscr_variant=dscr_variant, profile=profile) == route


def test_registered_routes_are_metric_executors():
    executors, calculation_request, _, _ = _dispatch()
    request = calculation_request(metric="dscr")
    assert set(executors) == {"dispatch_cover", "loan_life", "reduced", "adscr", "select_ratio"}
    for factory in executors.values():
        executor = factory(request)
        assert callable(getattr(executor, "execute", None))


@pytest.mark.parametrize("route", ["dispatch_cover", "loan_life", "reduced", "adscr", "select_ratio"])
def test_a_missing_executor_refuses_without_the_old_call(route, monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError(route)

    monkeypatch.setattr("finance_analysis.domain.housing_cover.dispatch_cover", boom)
    monkeypatch.setattr("finance_analysis.domain.cover_metrics.loan_life_ratio", boom)
    monkeypatch.setattr("finance_analysis.domain.cover_metrics.dscr_reductions", boom)
    monkeypatch.setattr("finance_analysis.domain.cover_metrics.adscr", boom)
    monkeypatch.setattr("finance_analysis.domain.covenant.select_ratio", boom)
    _, _, _, run_calculation = _dispatch()
    outcome = run_calculation(route, _request("dscr"), _context(), executors={})
    assert outcome.result["status"] == "not_computed"
    assert outcome.result["reason"] == "missing_executor"
    assert outcome.result["rows"] == []
    assert outcome.evidence is None


def test_an_incompatible_executor_does_not_fall_through_to_select_ratio(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("select_ratio")

    monkeypatch.setattr("finance_analysis.domain.covenant.select_ratio", boom)
    monkeypatch.setattr("finance_analysis.domain.metrics.calculate_coverage", boom)
    definition = _definition(
        "dscr",
        _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)),
        executor_key="loan_life",
    )
    _, _, _, run_calculation = _dispatch()
    outcome = run_calculation(
        "select_ratio",
        _request("dscr", common=_common([], []), composed={}),
        _context(definition),
    )
    assert outcome.result["status"] == "not_computed"
    assert outcome.result["reason"] == "incompatible_executor"
    assert outcome.result["rows"] == []


def test_an_in_memory_definition_change_changes_the_result():
    facts = [_fact("c", "80"), _fact("e", "40"), _fact("d", "-10")]
    bindings = [_bind("cfads", "c"), _bind("ebitda", "e"), _bind("debt_service", "d")]
    catalog = _definition(
        "dscr",
        _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)),
        executor_key="coverage",
        executor_id="calculate_coverage",
        executor_version="calculate_coverage@1",
    )
    changed = _definition(
        "dscr",
        _expr(numerator_plus=("ebitda",), denominator_plus=("debt_service",)),
        executor_key="coverage",
        executor_id="calculate_coverage",
        executor_version="calculate_coverage@1",
    )
    _, _, _, run_calculation = _dispatch()

    def run(definition):
        plan = _plan_for(definition, bindings)
        outcome = run_calculation(
            "select_ratio",
            _request(
                "dscr",
                common=_common(facts, bindings),
                plan=plan,
                definition=definition,
                composed={},
                concepts=frozenset({"cfads", "ebitda", "debt_service"}),
                money=frozenset({"cfads", "ebitda", "debt_service"}),
            ),
            _context(definition, plan),
        )
        return outcome.result

    assert run(catalog)["rows"][0]["value"] == Decimal("8.0000000000")
    assert run(changed)["rows"][0]["value"] == Decimal("4.0000000000")


def test_an_undeclared_concept_refuses_through_the_dispatcher():
    definition = _definition(
        "dscr",
        _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)),
        executor_key="coverage",
        executor_id="calculate_coverage",
        executor_version="calculate_coverage@1",
    )
    facts = [_fact("c", "80"), _fact("e", "40"), _fact("d", "-10")]
    bindings = [_bind("cfads", "c"), _bind("ebitda", "e"), _bind("debt_service", "d")]
    foreign = seal(
        metric_id="dscr",
        variant=None,
        variant_source="formula",
        catalog_version=None,
        semantic_model_version=None,
        build_key=None,
        model_id=None,
        status="resolved",
        inputs=(
            ResolvedInput("cfads", "all_of", "formula", "c", "c", None, False, True),
            ResolvedInput("debt_service", "all_of", "formula", "d", "d", None, False, True),
            ResolvedInput("ebitda", "all_of", "formula", "e", "e", None, False, True),
        ),
        diagnostic=(),
        rejected=(),
        fallbacks=(),
        warnings=(),
        needs_input=(),
        shield=None,
        definition_hash=definition.definition_hash,
    )
    _, _, _, run_calculation = _dispatch()
    with pytest.raises(UndeclaredInput) as raised:
        run_calculation(
            "select_ratio",
            _request(
                "dscr",
                common=_common(facts, bindings),
                plan=foreign,
                definition=definition,
                composed={},
            ),
            _context(definition, foreign),
        )
    assert raised.value.name == "ebitda"


def test_a_definition_the_specialized_executor_cannot_run_is_not_computed(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("adscr")

    monkeypatch.setattr("finance_analysis.domain.cover_metrics.adscr", boom)
    definition = _definition(
        "adscr",
        _expr(numerator_plus=("ebitda",), denominator_plus=("debt_service",)),
        executor_key="adscr",
    )
    _, _, _, run_calculation = _dispatch()
    outcome = run_calculation("adscr", _request("adscr", common=_common([], [])), _context(definition))
    assert outcome.result["status"] == "not_computed"
    assert outcome.result["reason"] == "unsupported_formula"
    assert outcome.result["rows"] == []


def test_specialized_routes_keep_the_same_call_without_a_definition(monkeypatch):
    seen = {}

    def cover(*_args, **kwargs):
        seen["cover"] = kwargs
        return {"metric": "llcr", "rows": [], "needs_input": [], "warnings": [], "status": "succeeded"}

    def life(metric, **kwargs):
        seen["life"] = (metric, kwargs)
        return {"metric": metric, "rows": [], "needs_input": [], "warnings": [], "status": "missing_input"}

    def reduced(metric, **kwargs):
        seen["reduced"] = (metric, kwargs)
        return {"metric": metric, "rows": [], "needs_input": [], "warnings": [], "status": "missing_input"}

    def annual(**kwargs):
        seen["adscr"] = kwargs
        return {"metric": "adscr", "rows": [], "needs_input": [], "warnings": [], "status": "missing_input"}

    monkeypatch.setattr("finance_analysis.domain.housing_cover.dispatch_cover", cover)
    monkeypatch.setattr("finance_analysis.domain.cover_metrics.loan_life_ratio", life)
    monkeypatch.setattr("finance_analysis.domain.cover_metrics.dscr_reductions", reduced)
    monkeypatch.setattr("finance_analysis.domain.cover_metrics.adscr", annual)
    plan = object()
    common = _common([], [])
    collected: list = []
    _, _, _, run_calculation = _dispatch()
    run_calculation(
        "dispatch_cover",
        _request(
            "llcr",
            metric_variant="cbr590",
            dscr_variant=None,
            profile={"llcr_definition": {"variant": "cbr590"}},
            basis="period_end",
            direction="lookback",
            common=common,
            plan=plan,
        ),
        _context(plan=plan),
    )
    run_calculation(
        "loan_life",
        _request("plcr", basis="period_start", common=common, plan=plan),
        _context(plan=plan),
    )
    run_calculation(
        "reduced",
        _request("dscr_min", common=common, plan=plan, collect=collected),
        _context(plan=plan),
    )
    run_calculation(
        "adscr",
        _request("adscr", direction="lookforward", common=common, plan=plan, collect=collected),
        _context(plan=plan),
    )
    assert seen["cover"]["plan"] is plan
    assert seen["cover"]["metric_variant"] == "cbr590"
    assert seen["cover"]["common"] is common
    assert seen["life"] == (
        "plcr",
        {**common, "basis": "period_start", "plan": plan},
    )
    assert seen["reduced"][0] == "dscr_min"
    assert seen["reduced"][1]["plan"] is plan
    assert seen["reduced"][1]["collect"] is collected
    assert seen["adscr"]["direction"] == "lookforward"
    assert seen["adscr"]["plan"] is plan
    assert seen["adscr"]["collect"] is collected


async def test_compute_metrics_shows_a_missing_executor(monkeypatch):
    from finance_analysis.application.analyses import Analyses, Target
    from finance_analysis.application.catalog import load_catalog
    from finance_analysis.application.model_types import load_model_types
    from finance_analysis.domain import metric_dispatch
    from finance_analysis.domain.book import Head
    from finance_analysis.domain.errors import NotFound
    from finance_analysis.domain.model_type import Effective

    monkeypatch.setitem(metric_dispatch.CALCULATION_EXECUTORS, "select_ratio", None)

    class _Guard:
        async def read_all(self, _job_id):
            return []

    class _Glossary:
        async def profile_body(self, _profile_id):
            return {}

    class _Service:
        async def _dataset_rows(self, _job_id, _head, dataset):
            if dataset in {"bindings", "fact_observation", "dim_period", "dim_row", "period_semantics", "graph_links"}:
                return []
            raise NotFound(dataset)

        async def resolve_model_type(self, _job_id, _head):
            return Effective(("corporate",), "corporate", "confirmed", None, 1, None, 1.0, {"corporate": 1.0}, ())

    service = _Service()
    service.model_types = load_model_types()
    service.catalog = load_catalog()
    service.financial_catalog = None
    service.guard = _Guard()
    service.glossary = _Glossary()
    head = Head(build_key="build", state_seq=1, derive_key="derive", versions={})
    got = await Analyses(service).compute_metrics(
        "job", Target(head=head, build="build", manifest={}, fresh=True), ["dscr"]
    )
    assert got["rows"] == []
    assert {"code": "missing_executor", "params": {"metric": "dscr"}} in got["warnings"]


def test_dispatch_cover_none_is_a_refusal_not_the_next_route(monkeypatch):
    def none_cover(*_args, **_kwargs):
        return None

    def boom(*_args, **_kwargs):
        raise AssertionError("next route")

    monkeypatch.setattr("finance_analysis.domain.housing_cover.dispatch_cover", none_cover)
    monkeypatch.setattr("finance_analysis.domain.cover_metrics.loan_life_ratio", boom)
    monkeypatch.setattr("finance_analysis.domain.cover_metrics.adscr", boom)
    monkeypatch.setattr("finance_analysis.domain.covenant.select_ratio", boom)
    _, _, _, run_calculation = _dispatch()
    outcome = run_calculation("dispatch_cover", _request("llcr", common=_common([], [])), _context())
    assert outcome.result["status"] == "not_computed"
    assert outcome.result["reason"] == "missing_executor"
