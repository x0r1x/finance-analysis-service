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
from finance_analysis.domain.resolved_plan import AppliedFallback, ResolvedInput, seal
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


def test_a_request_definition_is_checked_when_the_context_has_none(monkeypatch):
    """Контекст пуст, а определение лежит на запросе. Проверка и вызов — один объект.

    Ключ, которого нет у маршрута, — отказ. Калькулятор не вызывается.
    """

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
        _request("dscr", common=_common([], []), composed={}, definition=definition),
        _context(),
    )
    assert outcome.result["status"] == "not_computed"
    assert outcome.result["reason"] == "incompatible_executor"
    assert outcome.result["rows"] == []


def test_two_different_definitions_refuse_before_the_calculator(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("select_ratio")

    monkeypatch.setattr("finance_analysis.domain.covenant.select_ratio", boom)
    one = _definition(
        "dscr",
        _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)),
        executor_key="coverage",
        executor_id="calculate_coverage",
        executor_version="calculate_coverage@1",
    )
    other = _definition(
        "dscr",
        _expr(numerator_plus=("ebitda",), denominator_plus=("debt_service",)),
        executor_key="coverage",
        executor_id="calculate_coverage",
        executor_version="calculate_coverage@1",
    )
    assert one is not other
    _, _, _, run_calculation = _dispatch()
    outcome = run_calculation(
        "select_ratio",
        _request("dscr", common=_common([], []), composed={}, definition=one),
        _context(other),
    )
    assert outcome.result["status"] == "not_computed"
    assert outcome.result["reason"] == "definition_mismatch"
    assert outcome.result["rows"] == []


def test_two_compilations_of_the_same_inputs_share_definition_hash_and_resolve():
    """Один definition_hash — одно содержание, даже если объекты собраны раздельно."""

    expression = _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",))
    supplied = _definition(
        "dscr",
        expression,
        executor_key="coverage",
        executor_id="calculate_coverage",
        executor_version="calculate_coverage@1",
    )
    bound = _definition(
        "dscr",
        expression,
        executor_key="coverage",
        executor_id="calculate_coverage",
        executor_version="calculate_coverage@1",
    )
    assert supplied is not bound
    assert supplied.definition_hash == bound.definition_hash
    facts = [_fact("c", "80"), _fact("d", "-10")]
    bindings = [_bind("cfads", "c"), _bind("debt_service", "d")]
    plan = _plan_for(bound, bindings)
    _, _, _, run_calculation = _dispatch()
    outcome = run_calculation(
        "select_ratio",
        _request(
            "dscr",
            common=_common(facts, bindings),
            definition=supplied,
            composed={},
            concepts=frozenset({"cfads", "debt_service"}),
            money=frozenset({"cfads", "debt_service"}),
        ),
        _context(bound, plan),
    )
    assert outcome.result.get("reason") != "definition_mismatch"
    assert outcome.result["rows"][0]["value"] == Decimal("8.0000000000")


def test_a_changed_formula_changes_definition_hash_and_refuses(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("select_ratio")

    monkeypatch.setattr("finance_analysis.domain.covenant.select_ratio", boom)
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
    assert catalog.definition_hash != changed.definition_hash
    _, _, _, run_calculation = _dispatch()
    outcome = run_calculation(
        "select_ratio",
        _request("dscr", common=_common([], []), composed={}, definition=catalog),
        _context(changed),
    )
    assert outcome.result["status"] == "not_computed"
    assert outcome.result["reason"] == "definition_mismatch"
    assert outcome.result["rows"] == []


def test_the_executor_receives_the_definition_that_was_checked():
    definition = _definition(
        "dscr",
        _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)),
        executor_key="coverage",
        executor_id="calculate_coverage",
        executor_version="calculate_coverage@1",
    )
    seen = {}

    class _Spy:
        identities = (("coverage", "calculate_coverage", "calculate_coverage@1"),)
        compatible = frozenset({"coverage"})

        def __init__(self, _request):
            return None

        def execute(self, context):
            seen["definition"] = context.definition
            return CalculationOutcome(
                {"metric": "dscr", "rows": [], "needs_input": [], "warnings": [], "status": "succeeded"},
                None,
            )

    from finance_analysis.domain.calculation_evidence import CalculationOutcome

    _, _, _, run_calculation = _dispatch()
    run_calculation(
        "select_ratio",
        _request("dscr", definition=definition),
        _context(),
        executors={"select_ratio": _Spy},
    )
    assert seen["definition"] is definition


def test_an_unregistered_executor_version_refuses(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("select_ratio")

    monkeypatch.setattr("finance_analysis.domain.covenant.select_ratio", boom)
    definition = _definition(
        "dscr",
        _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)),
        executor_key="coverage",
        executor_id="calculate_coverage",
        executor_version="calculate_coverage@2",
    )
    _, _, _, run_calculation = _dispatch()
    outcome = run_calculation(
        "select_ratio",
        _request("dscr", common=_common([], []), composed={}),
        _context(definition),
    )
    assert outcome.result["status"] == "not_computed"
    assert outcome.result["reason"] == "incompatible_executor"


def test_the_plan_stays_on_the_context_not_the_request():
    """План — контракт исполнения. Финансовые параметры остаются на запросе."""

    _, calculation_request, _, _ = _dispatch()
    assert "plan" not in calculation_request.__dataclass_fields__


def test_route_for_and_the_registry_are_one_registration():
    import finance_analysis.domain.metric_dispatch as dispatch

    assert dispatch.route_names() == frozenset(dispatch.CALCULATION_EXECUTORS)
    assert dispatch.route_names() == frozenset(dispatch._returns_of_route_for())


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
        ),
        _context(plan=plan),
    )
    run_calculation(
        "loan_life",
        _request("plcr", basis="period_start", common=common),
        _context(plan=plan),
    )
    run_calculation(
        "reduced",
        _request("dscr_min", common=common, collect=collected),
        _context(plan=plan),
    )
    run_calculation(
        "adscr",
        _request("adscr", direction="lookforward", common=common, collect=collected),
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


def _seal_plan(metric: str, definition, concepts: tuple[str, ...], **kwargs):
    return seal(
        metric_id=metric,
        variant=kwargs.get("variant", definition.variant),
        variant_source=kwargs.get("variant_source", definition.variant_source),
        catalog_version=None,
        semantic_model_version=None,
        build_key=None,
        model_id=None,
        status=kwargs.get("status", "resolved"),
        inputs=tuple(
            ResolvedInput(name, "all_of", "formula", name, name, None, False, True) for name in concepts
        ),
        diagnostic=(),
        rejected=(),
        fallbacks=kwargs.get("fallbacks", ()),
        warnings=(),
        needs_input=(),
        shield=None,
        definition_hash=kwargs.get("definition_hash", definition.definition_hash),
    )


def _watch_bound(monkeypatch) -> list:
    from finance_analysis.domain import metric_dispatch

    seen: list = []
    real = metric_dispatch.execute_bound

    def wrapped(executor, definition, plan, **kwargs):
        seen.append(definition.metric_id)
        return real(executor, definition, plan, **kwargs)

    monkeypatch.setattr(metric_dispatch, "execute_bound", wrapped)
    return seen


def _coverage_definition(metric: str, expression: MetricExpression):
    return _definition(
        metric,
        expression,
        executor_key="coverage",
        executor_id="calculate_coverage",
        executor_version="calculate_coverage@1",
    )


def _ratio_request(metric: str, facts, bindings, **kwargs):
    return _request(
        metric,
        common=_common(facts, bindings),
        composed={},
        concepts=frozenset(name for name in ("cfads", "ebitda", "ebit", "debt_service", "interest", "principal")),
        money=frozenset(name for name in ("cfads", "ebitda", "ebit", "debt_service", "interest", "principal")),
        **kwargs,
    )


def test_a_missing_plan_stays_on_todays_calculator(monkeypatch):
    """Плана нет — прежний калькулятор. Связанный путь не открывается."""

    seen = _watch_bound(monkeypatch)
    calls = []

    def select_ratio(*_args, **_kwargs):
        calls.append("select_ratio")
        return {"metric": "dscr", "rows": [], "needs_input": [], "warnings": [], "status": "missing_input"}

    monkeypatch.setattr("finance_analysis.domain.covenant.select_ratio", select_ratio)
    definition = _coverage_definition(
        "dscr",
        _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)),
    )
    _, _, _, run_calculation = _dispatch()
    outcome = run_calculation(
        "select_ratio",
        _ratio_request("dscr", [], []),
        _context(definition, None),
    )
    assert calls == ["select_ratio"]
    assert seen == []
    assert outcome.result["status"] == "missing_input"


def test_an_unresolved_plan_stays_on_todays_calculator(monkeypatch):
    """Статус не resolved — прежний калькулятор, даже если хеш совпал."""

    seen = _watch_bound(monkeypatch)
    calls = []

    def select_ratio(*_args, **_kwargs):
        calls.append("select_ratio")
        return {"metric": "dscr", "rows": [], "needs_input": [], "warnings": [], "status": "needs_input"}

    monkeypatch.setattr("finance_analysis.domain.covenant.select_ratio", select_ratio)
    definition = _coverage_definition(
        "dscr",
        _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)),
    )
    plan = _seal_plan("dscr", definition, ("cfads", "debt_service"), status="needs_input")
    _, _, _, run_calculation = _dispatch()
    outcome = run_calculation(
        "select_ratio",
        _ratio_request("dscr", [], []),
        _context(definition, plan),
    )
    assert calls == ["select_ratio"]
    assert seen == []
    assert outcome.result["status"] == "needs_input"


def test_a_resolved_plan_without_a_definition_stays_on_todays_calculator(monkeypatch):
    """Решённый план без определения — прежний калькулятор. Сверять не с чем."""

    seen = _watch_bound(monkeypatch)
    calls = []

    def select_ratio(*_args, **_kwargs):
        calls.append("select_ratio")
        return {"metric": "dscr", "rows": [], "needs_input": [], "warnings": [], "status": "missing_input"}

    monkeypatch.setattr("finance_analysis.domain.covenant.select_ratio", select_ratio)
    definition = _coverage_definition(
        "dscr",
        _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)),
    )
    plan = _seal_plan("dscr", definition, ("cfads", "debt_service"))
    _, _, _, run_calculation = _dispatch()
    outcome = run_calculation("select_ratio", _ratio_request("dscr", [], []), _context(None, plan))
    assert calls == ["select_ratio"]
    assert seen == []
    assert outcome.result["status"] == "missing_input"


def test_a_resolved_matching_plan_runs_the_bound_path_and_keeps_the_ratio(monkeypatch):
    """Совпали метрика, вариант и хеш — связанный путь. Число остаётся числом калькулятора.

    Подстановок нет, поэтому кортеж слотов пуст. Калькулятор получает его и не вызывает slots_for снова.
    """

    from finance_analysis.domain.metric_dispatch import SelectRatioExecutor
    from finance_analysis.domain.metrics import coverage_from_definition

    seen = _watch_bound(monkeypatch)
    entered = {}
    real_execute = SelectRatioExecutor.execute

    def execute(self, context):
        entered["slots"] = tuple(slot.resolution_reason for slot in context.slots)
        return real_execute(self, context)

    monkeypatch.setattr(SelectRatioExecutor, "execute", execute)
    definition = _coverage_definition(
        "dscr",
        _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)),
    )
    facts = [_fact("c", "80"), _fact("d", "-10")]
    bindings = [_bind("cfads", "c"), _bind("debt_service", "d")]
    plan = _plan_for(definition, bindings)
    periods = _year_period()
    direct = coverage_from_definition(
        definition,
        plan,
        facts=facts,
        bindings=bindings,
        periods=periods,
        period_phase={},
        explicit_phases=False,
    )
    _, _, _, run_calculation = _dispatch()
    outcome = run_calculation(
        "select_ratio",
        _ratio_request("dscr", facts, bindings),
        _context(definition, plan),
    )
    assert seen == ["dscr"]
    assert entered["slots"] == ()
    assert outcome.result["rows"][0]["value"] == direct["rows"][0]["value"] == Decimal("8.0000000000")


def test_a_matched_fallback_slot_is_passed_to_the_calculator(monkeypatch):
    """Запасной путь виден на контексте и уходит в вызов калькулятора."""

    from finance_analysis.domain.covenant import select_ratio
    from finance_analysis.domain.metric_dispatch import SelectRatioExecutor
    from finance_analysis.domain.metrics import coverage_from_definition

    seen = _watch_bound(monkeypatch)
    entered = {}
    passed = {}
    real_execute = SelectRatioExecutor.execute
    real_select = select_ratio

    def execute(self, context):
        entered["reasons"] = tuple(slot.resolution_reason for slot in context.slots)
        return real_execute(self, context)

    def wrapped(metric, variant, common, **kwargs):
        passed["slots"] = kwargs.get("slots")
        return real_select(metric, variant, common, **kwargs)

    monkeypatch.setattr(SelectRatioExecutor, "execute", execute)
    monkeypatch.setattr("finance_analysis.domain.covenant.select_ratio", wrapped)
    definition = _coverage_definition(
        "dscr",
        _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)),
    )
    plan = _seal_plan(
        "dscr",
        definition,
        ("cfads", "interest", "principal"),
        fallbacks=(AppliedFallback("pf", "debt_service", "interest", None),),
    )
    facts = [_fact("cfads", "40"), _fact("interest", "-10"), _fact("principal", "-4")]
    bindings = [_bind(name, name) for name in ("cfads", "interest", "principal")]
    periods = _year_period()
    order = {"pf": ("interest",)}
    direct = coverage_from_definition(
        definition,
        plan,
        facts=facts,
        bindings=bindings,
        periods=periods,
        period_phase={},
        explicit_phases=False,
        interest_order=order,
    )
    _, _, _, run_calculation = _dispatch()
    outcome = run_calculation(
        "select_ratio",
        _ratio_request("dscr", facts, bindings, interest_order=order),
        _context(definition, plan),
    )
    assert seen == ["dscr"]
    assert entered["reasons"] == ("fallback",)
    assert passed["slots"][0].resolution_reason == "fallback"
    assert passed["slots"][0].resolved_terms == ("interest", "principal")
    assert outcome.result["rows"][0]["value"] == direct["rows"][0]["value"]


def test_a_matched_one_of_slot_is_passed_to_the_calculator(monkeypatch):
    """one_of виден на контексте и уходит в вызов калькулятора. Числитель из слота."""

    from finance_analysis.domain.covenant import select_ratio
    from finance_analysis.domain.metric_dispatch import SelectRatioExecutor
    from finance_analysis.domain.metrics import coverage_from_definition

    seen = _watch_bound(monkeypatch)
    entered = {}
    passed = {}
    real_execute = SelectRatioExecutor.execute
    real_select = select_ratio

    def execute(self, context):
        entered["slots"] = tuple((slot.slot_id, slot.resolution_reason, slot.resolved_terms) for slot in context.slots)
        return real_execute(self, context)

    def wrapped(metric, variant, common, **kwargs):
        passed["slots"] = kwargs.get("slots")
        return real_select(metric, variant, common, **kwargs)

    monkeypatch.setattr(SelectRatioExecutor, "execute", execute)
    monkeypatch.setattr("finance_analysis.domain.covenant.select_ratio", wrapped)
    definition = _coverage_definition(
        "icr",
        _expr(
            one_of=frozenset({"ebitda", "ebit"}),
            one_of_order=("ebitda", "ebit"),
            denominator_plus=("interest",),
        ),
    )
    facts = [_fact("e", "80"), _fact("b", "20"), _fact("i", "-10")]
    bindings = [_bind("ebitda", "e"), _bind("ebit", "b"), _bind("interest", "i")]
    plan = _plan_for(definition, bindings)
    periods = _year_period()
    direct = coverage_from_definition(
        definition,
        plan,
        facts=facts,
        bindings=bindings,
        periods=periods,
        period_phase={},
        explicit_phases=False,
    )
    _, _, _, run_calculation = _dispatch()
    outcome = run_calculation(
        "select_ratio",
        _ratio_request("icr", facts, bindings),
        _context(definition, plan),
    )
    assert seen == ["icr"]
    assert entered["slots"] == (("numerator", "one_of", ("ebitda",)),)
    assert passed["slots"][0].resolved_terms == ("ebitda",)
    assert outcome.result["rows"][0]["value"] == direct["rows"][0]["value"] == Decimal("8.0000000000")


def _count_second_choice(monkeypatch):
    """Второй slots_for отказывается. Повторный выбор one_of и запаса тоже считается."""

    from finance_analysis.domain import execution_contract, metrics
    from finance_analysis.domain.execution_contract import ExecutionContractError

    state = {"slots": 0, "one_of": 0, "fallback": 0, "interest": 0}
    real_slots = execution_contract.slots_for
    real_one = metrics.choose_one_of
    real_fallback = metrics.dscr_denominator_plan
    real_interest = metrics.interest_choice

    def slots_for(definition, plan):
        state["slots"] += 1
        if state["slots"] > 1:
            raise ExecutionContractError("inconsistent_fallback")
        return real_slots(definition, plan)

    def choose_one_of(*args, **kwargs):
        state["one_of"] += 1
        return real_one(*args, **kwargs)

    def dscr_denominator_plan(*args, **kwargs):
        state["fallback"] += 1
        return real_fallback(*args, **kwargs)

    def interest_choice(*args, **kwargs):
        state["interest"] += 1
        return real_interest(*args, **kwargs)

    monkeypatch.setattr(execution_contract, "slots_for", slots_for)
    monkeypatch.setattr(metrics, "choose_one_of", choose_one_of)
    monkeypatch.setattr(metrics, "dscr_denominator_plan", dscr_denominator_plan)
    monkeypatch.setattr(metrics, "interest_choice", interest_choice)
    return state


def _spy_select(monkeypatch):
    from finance_analysis.domain.covenant import select_ratio

    passed = {}

    def wrapped(metric, variant, common, **kwargs):
        passed["slots"] = kwargs.get("slots")
        return select_ratio(metric, variant, common, **kwargs)

    monkeypatch.setattr("finance_analysis.domain.covenant.select_ratio", wrapped)
    return passed


def test_bound_one_of_is_not_chosen_again_and_the_evidence_records_the_read(monkeypatch):
    """Калькулятор получает слот one_of. Второй slots_for и choose_one_of не выбирают числитель.

    actual_inputs — понятия, чьи факты прочитаны. Отклонённый член one_of туда не входит.
    Решённый план не перерешивается: https://www.w3.org/TR/prov-dm/#term-Plan
    """

    state = _count_second_choice(monkeypatch)
    passed = _spy_select(monkeypatch)
    definition = _coverage_definition(
        "icr",
        _expr(
            one_of=frozenset({"ebitda", "ebit"}),
            one_of_order=("ebitda", "ebit"),
            denominator_plus=("interest",),
        ),
    )
    facts = [
        {**_fact("e", "80"), "cell_id": "IS!EBITDA"},
        {**_fact("b", "20"), "cell_id": "IS!EBIT"},
        {**_fact("i", "-10"), "cell_id": "IS!INT"},
    ]
    bindings = [_bind("ebitda", "e"), _bind("ebit", "b"), _bind("interest", "i")]
    plan = _plan_for(definition, bindings)
    collected: list = []
    _, _, _, run_calculation = _dispatch()
    outcome = run_calculation(
        "select_ratio",
        _ratio_request("icr", facts, bindings, collect=collected),
        _context(definition, plan),
    )
    evidence = collected[0]
    assert state == {"slots": 1, "one_of": 0, "fallback": 0, "interest": 0}
    assert passed["slots"][0].resolution_reason == "one_of"
    assert passed["slots"][0].resolved_terms == ("ebitda",)
    assert outcome.result["rows"][0]["value"] == Decimal("8.0000000000")
    assert evidence.actual_inputs == ("ebitda", "interest")
    assert {item.concept for item in evidence.fact_uses} == {"ebitda", "interest"}
    assert {item.cell_id for item in evidence.fact_uses} == {"IS!EBITDA", "IS!INT"}
    assert "ebit" not in evidence.actual_inputs


def test_bound_fallback_is_not_chosen_again_and_the_evidence_records_the_read(monkeypatch):
    """Калькулятор получает слот запаса. Второй slots_for и dscr_denominator_plan его не выбирают.

    actual_inputs — прочитанные факты, не исходный debt_service и не другая строка процентов.
    Решённый план не перерешивается: https://www.w3.org/TR/prov-dm/#term-Plan
    """

    state = _count_second_choice(monkeypatch)
    passed = _spy_select(monkeypatch)
    definition = _coverage_definition(
        "dscr",
        _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)),
    )
    plan = _seal_plan(
        "dscr",
        definition,
        ("cfads", "interest", "principal"),
        fallbacks=(AppliedFallback("pf", "debt_service", "interest", None),),
    )
    facts = [
        {**_fact("cfads", "40"), "cell_id": "CFS!CF"},
        {**_fact("debt_service", "-99"), "cell_id": "Debt!DS"},
        {**_fact("interest", "-10"), "cell_id": "Debt!INT"},
        {**_fact("interest_paid", "-2"), "cell_id": "Debt!PAID"},
        {**_fact("principal", "-4"), "cell_id": "Debt!PR"},
    ]
    bindings = [_bind(name, name) for name in ("cfads", "debt_service", "interest", "interest_paid", "principal")]
    collected: list = []
    order = {"pf": ("interest_paid", "interest")}
    _, _, _, run_calculation = _dispatch()
    outcome = run_calculation(
        "select_ratio",
        _ratio_request("dscr", facts, bindings, interest_order=order, collect=collected),
        _context(definition, plan),
    )
    evidence = collected[0]
    assert state == {"slots": 1, "one_of": 0, "fallback": 0, "interest": 0}
    assert passed["slots"][0].resolution_reason == "fallback"
    assert passed["slots"][0].resolved_terms == ("interest", "principal")
    assert outcome.result["rows"][0]["value"] == Decimal("2.8571428571")
    assert evidence.actual_inputs == ("cfads", "interest", "principal")
    assert {item.concept for item in evidence.fact_uses} == {"cfads", "interest", "principal"}
    assert {item.cell_id for item in evidence.fact_uses} == {"CFS!CF", "Debt!INT", "Debt!PR"}
    assert "debt_service" not in evidence.actual_inputs
    assert "interest_paid" not in evidence.actual_inputs


@pytest.mark.parametrize(
    ("plan_metric", "variant", "source", "digest", "reason"),
    [
        ("icr", None, "formula", None, "metric_mismatch"),
        ("dscr", "housing", "variant:housing", None, "variant_mismatch"),
        ("dscr", None, "formula", "other-hash", "definition_mismatch"),
    ],
)
def test_a_resolved_mismatch_is_an_integrity_error(monkeypatch, plan_metric, variant, source, digest, reason):
    """Решённый план, который не совпал, — явный отказ. Калькулятор не вызывается."""

    def boom(*_args, **_kwargs):
        raise AssertionError("calculator")

    monkeypatch.setattr("finance_analysis.domain.covenant.select_ratio", boom)
    monkeypatch.setattr("finance_analysis.domain.metrics.calculate_coverage", boom)
    definition = _coverage_definition(
        "dscr",
        _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)),
    )
    plan = _seal_plan(
        plan_metric,
        definition,
        ("cfads", "debt_service"),
        variant=variant,
        variant_source=source,
        definition_hash=definition.definition_hash if digest is None else digest,
    )
    _, _, _, run_calculation = _dispatch()
    outcome = run_calculation(
        "select_ratio",
        _ratio_request("dscr", [], []),
        _context(definition, plan),
    )
    assert outcome.result["status"] == "not_computed"
    assert outcome.result["reason"] == reason
    assert outcome.result["rows"] == []
    assert outcome.evidence is None


@pytest.mark.parametrize(
    ("metric", "other", "executor_key", "executor_id", "executor_version", "numerator", "denominator"),
    [
        ("icr", "dscr", "coverage", "calculate_coverage", "calculate_coverage@1", "cfads", "debt_service"),
        (
            "net_debt_ebitda",
            "total_debt_ebitda",
            "composed",
            "composed_ratio",
            "composed_ratio@1",
            "total_debt",
            "ebitda",
        ),
    ],
)
def test_a_definition_of_another_metric_is_an_integrity_error(
    monkeypatch,
    metric,
    other,
    executor_key,
    executor_id,
    executor_version,
    numerator,
    denominator,
):
    """Запрошена одна метрика, определение и план — другая. Исполнитель при этом тот же.

    ``_plan_matches`` сверяет план с определением. ``_rejection`` сверяет исполнителя, не метрику.
    https://www.w3.org/TR/prov-dm/#term-Activity
    """

    seen = _watch_bound(monkeypatch)

    def boom(*_args, **_kwargs):
        raise AssertionError("calculator")

    monkeypatch.setattr("finance_analysis.domain.covenant.select_ratio", boom)
    monkeypatch.setattr("finance_analysis.domain.metrics.calculate_coverage", boom)
    definition = _definition(
        other,
        _expr(numerator_plus=(numerator,), denominator_plus=(denominator,)),
        executor_key=executor_key,
        executor_id=executor_id,
        executor_version=executor_version,
    )
    plan = _seal_plan(other, definition, (numerator, denominator))
    _, _, _, run_calculation = _dispatch()
    outcome = run_calculation(
        "select_ratio",
        _ratio_request(metric, [], []),
        _context(definition, plan),
    )
    assert seen == []
    assert outcome.result["status"] == "not_computed"
    assert outcome.result["reason"] == "metric_mismatch"
    assert outcome.result["metric"] == metric
    assert outcome.result["rows"] == []
    assert outcome.evidence is None


@pytest.mark.parametrize("metric", ["adscr", "dscr_min", "dscr_avg"])
def test_a_derived_metric_keeps_todays_calculator_on_the_dscr_plan(monkeypatch, metric):
    """План DSCR и определение производной метрики различаются. Это не связанное исполнение.

    Определение не подменяется определением DSCR. Калькулятор остаётся сегодняшним.
    """

    from finance_analysis.domain.cover_metrics import adscr, dscr_reductions
    from finance_analysis.domain.metric_dispatch import AdscrExecutor, ReducedExecutor

    seen = _watch_bound(monkeypatch)
    entered = {}
    route = "adscr" if metric == "adscr" else "reduced"
    executor_type = AdscrExecutor if metric == "adscr" else ReducedExecutor
    real_execute = executor_type.execute

    def execute(self, context):
        entered["metric"] = context.definition.metric_id
        entered["slots"] = context.slots
        entered["plan"] = context.plan.metric_id
        return real_execute(self, context)

    monkeypatch.setattr(executor_type, "execute", execute)
    definition = _definition(
        metric,
        _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)),
        executor_key=route,
    )
    dscr = _coverage_definition(
        "dscr",
        _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)),
    )
    plan = _seal_plan("dscr", dscr, ("cfads", "debt_service"))
    common = _common([], [])
    if metric == "adscr":
        direct = adscr(direction="lookback", plan=plan, collect=None, **common)
        request = _request(metric, direction="lookback", common=common)
    else:
        direct = dscr_reductions(metric, plan=plan, collect=None, **common)
        request = _request(metric, common=common)
    _, _, _, run_calculation = _dispatch()
    outcome = run_calculation(route, request, _context(definition, plan))
    assert seen == []
    assert entered == {"metric": metric, "slots": (), "plan": "dscr"}
    assert outcome.result == direct
    assert outcome.result.get("reason") != "metric_mismatch"


def test_a_derived_metric_with_a_foreign_plan_is_an_integrity_error(monkeypatch):
    """Чужой план производной метрики — отказ. Исключение есть только у плана DSCR."""

    def boom(*_args, **_kwargs):
        raise AssertionError("calculator")

    monkeypatch.setattr("finance_analysis.domain.cover_metrics.adscr", boom)
    definition = _definition(
        "adscr",
        _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)),
        executor_key="adscr",
    )
    foreign = _coverage_definition(
        "icr",
        _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)),
    )
    plan = _seal_plan("icr", foreign, ("cfads", "debt_service"))
    _, _, _, run_calculation = _dispatch()
    outcome = run_calculation(
        "adscr",
        _request("adscr", common=_common([], [])),
        _context(definition, plan),
    )
    assert outcome.result["status"] == "not_computed"
    assert outcome.result["reason"] == "metric_mismatch"
    assert outcome.result["rows"] == []


def test_two_one_of_on_a_matched_plan_keeps_the_calculator_reason():
    """Два one_of отвергаются до калькулятора. Причина та же, что у прямого прохода."""

    from finance_analysis.domain.metrics import coverage_from_definition

    definition = _coverage_definition(
        "icr",
        _expr(
            one_of=frozenset({"ebitda", "ebit"}),
            one_of_order=("ebitda", "ebit"),
            denominator_plus=("interest",),
        ),
    )
    plan = seal(
        metric_id="icr",
        variant=None,
        variant_source="formula",
        catalog_version=None,
        semantic_model_version=None,
        build_key=None,
        model_id=None,
        status="resolved",
        inputs=(
            ResolvedInput("ebitda", "one_of", "formula", "e", "e", None, False, True),
            ResolvedInput("ebit", "one_of", "formula", "b", "b", None, False, True),
            ResolvedInput("interest", "all_of", "formula", "i", "i", None, False, True),
        ),
        diagnostic=(),
        rejected=(),
        fallbacks=(),
        warnings=(),
        needs_input=(),
        shield=None,
        definition_hash=definition.definition_hash,
    )
    facts = [_fact("e", "80"), _fact("b", "20"), _fact("i", "-10")]
    bindings = [_bind("ebitda", "e"), _bind("ebit", "b"), _bind("interest", "i")]
    periods = _year_period()
    direct = coverage_from_definition(
        definition,
        plan,
        facts=facts,
        bindings=bindings,
        periods=periods,
        period_phase={},
        explicit_phases=False,
    )
    _, _, _, run_calculation = _dispatch()
    outcome = run_calculation(
        "select_ratio",
        _ratio_request("icr", facts, bindings),
        _context(definition, plan),
    )
    assert outcome.result["status"] == direct["status"] == "not_computed"
    assert outcome.result["reason"] == direct["reason"] == "ambiguous_one_of"
    assert outcome.result["rows"] == []


def test_execute_bound_is_reached_only_from_the_dispatcher():
    """Второй диспетчер не появляется. Вызов один, внутри run_calculation."""

    import ast
    from pathlib import Path

    root = Path("src/finance_analysis")
    found = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "execute_bound":
                found.append(path.as_posix())
    assert found == ["src/finance_analysis/domain/metric_dispatch.py"]


@pytest.mark.parametrize("reason", ["metric_mismatch", "variant_mismatch"])
async def test_compute_metrics_shows_a_plan_integrity_error(monkeypatch, reason):
    from finance_analysis.application.analyses import Analyses, Target
    from finance_analysis.application.catalog import load_catalog
    from finance_analysis.application.model_types import load_model_types
    from finance_analysis.domain.book import Head
    from finance_analysis.domain.calculation_evidence import CalculationOutcome
    from finance_analysis.domain.errors import NotFound
    from finance_analysis.domain.model_type import Effective

    def refuse(*_args, **_kwargs):
        return CalculationOutcome(
            {
                "metric": "dscr",
                "rows": [],
                "needs_input": [],
                "missing_inputs": [],
                "warnings": [],
                "status": "not_computed",
                "reason": reason,
                "message": reason,
            },
            None,
        )

    monkeypatch.setattr("finance_analysis.application.analyses.run_calculation", refuse)

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
    assert {"code": reason, "params": {"metric": "dscr"}} in got["warnings"]


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
