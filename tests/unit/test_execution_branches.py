"""Специализированные ветви. Чтение вне ветви отказывается в прогоне.

dynamic_names объединяет все ветки сразу и этим проверку не заменяет:
https://www.w3.org/TR/prov-dm/#term-usage
"""

from decimal import Decimal

import pytest

from finance_analysis.domain.execution_contract import (
    CatalogMetricRecord,
    ExecutionContractError,
    compile_definition,
    trace_for,
)
from finance_analysis.domain.metric_contract import (
    UndeclaredInput,
    dynamic_names,
    load_implementations,
)
from finance_analysis.domain.model_type import MetricExpression
from finance_analysis.domain.resolved_plan import ResolvedInput, seal


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


def _flags(fees: bool = False, swaps: bool = False, addback: bool = False) -> dict:
    return {
        "interest_addback": addback,
        "include_senior_fees": fees,
        "include_senior_swaps": swaps,
    }


def _plan(metric: str, concepts: tuple[str, ...], definition_hash: str, *, variant=None, source="formula"):
    return seal(
        metric_id=metric,
        variant=variant,
        variant_source=source,
        catalog_version=None,
        semantic_model_version=None,
        build_key=None,
        model_id=None,
        status="resolved",
        inputs=tuple(
            ResolvedInput(name, "all_of", "formula", name, name, None, False, True) for name in concepts
        ),
        diagnostic=(),
        rejected=(),
        fallbacks=(),
        warnings=(),
        needs_input=(),
        shield=None,
        definition_hash=definition_hash,
    )


def test_each_specialized_branch_has_its_own_definition():
    from finance_analysis.domain.execution_branches import branch_for

    found = [
        branch_for("adscr"),
        branch_for("dscr_min"),
        branch_for("dscr_avg"),
        branch_for("dscr", variant="housing", profile=_flags()),
        branch_for("adscr", variant="housing", profile=_flags(fees=True)),
        branch_for("dscr_min", variant="housing", profile=_flags(swaps=True)),
        branch_for("dscr_avg", variant="housing", profile=_flags(fees=True, swaps=True)),
        branch_for("icr", variant="bank", profile={"icr_definition": {"variant": "bank", "lease_mode": "in_interest"}}),
        branch_for(
            "icr",
            variant="bank",
            profile={
                "ebitda_definition": "ras",
                "icr_definition": {"variant": "bank", "lease_mode": "add_interest"},
            },
        ),
        branch_for(
            "icr",
            variant="bank",
            profile={
                "ebitda_definition": "ifrs",
                "icr_definition": {"variant": "bank", "lease_mode": "in_interest"},
            },
        ),
        branch_for("dscr", variant="cash_covenant"),
        branch_for("llcr"),
        branch_for("plcr"),
        branch_for("llcr", variant="cbr590"),
        branch_for("llcr", variant="domrf"),
        branch_for("fcff"),
        branch_for("npv"),
        branch_for("irr"),
        branch_for("icr_lease", lease_mode="direct"),
        branch_for("icr_lease", lease_mode="pair"),
        branch_for("escrow_blended_rate"),
    ]
    ids = [item.branch_id for item in found]
    assert len(ids) == len(set(ids))
    assert "adscr" in ids
    assert "dscr_min" in ids and "dscr_avg" in ids
    assert "dscr.housing" in ids
    assert "adscr.housing.fees" in ids
    assert "llcr" in ids and "plcr" in ids and "llcr.cbr590" in ids and "llcr.domrf" in ids
    assert "npv" in ids and "irr" in ids
    assert "icr_lease.direct" in ids and "icr_lease.pair" in ids


def test_dynamic_names_is_not_the_branch_check():
    from finance_analysis.domain.execution_branches import (
        claim,
        housing_branch,
        use_branch,
    )
    from finance_analysis.domain.metric_contract import REGISTRY

    load_implementations()
    names, _missing = dynamic_names(REGISTRY[("dscr", "dscr.housing")], REGISTRY, set())
    assert "senior_fees" in names and "senior_swaps" in names
    branch = housing_branch(False, False)
    assert "senior_fees" not in set(branch.required_inputs) | set(branch.optional_inputs)
    with use_branch(branch, _flags()):
        claim("cfo_statement")
        with pytest.raises(UndeclaredInput) as raised:
            claim("senior_fees")
    assert raised.value.name == "senior_fees"


def test_profile_values_are_stored_and_a_missing_one_refuses():
    from finance_analysis.domain.execution_branches import housing_branch

    branch = housing_branch(False, False)
    trace = trace_for(branch, _flags(fees=False, swaps=False, addback=True))
    assert trace.branch_id == "dscr.housing"
    assert trace.profile_values == (
        ("interest_addback", True),
        ("include_senior_fees", False),
        ("include_senior_swaps", False),
    )
    with pytest.raises(ExecutionContractError) as raised:
        trace_for(branch, {"interest_addback": False})
    assert raised.value.reason == "missing_profile"


def test_a_read_is_checked_against_the_active_branch():
    from finance_analysis.domain.execution_branches import housing_branch, use_branch
    from finance_analysis.domain.execution_contract import read_input

    bare = housing_branch(False, False)
    fees = housing_branch(True, False)
    trace = trace_for(bare, _flags())
    with use_branch(fees, _flags(fees=True)), pytest.raises(ExecutionContractError) as raised:
        read_input(bare, trace, "cfo_statement")
    assert raised.value.reason == "branch_mismatch"


def test_irr_refuses_the_discount_rate_npv_reads():
    from finance_analysis.domain.execution_branches import branch_for, claim, use_branch

    irr = branch_for("irr")
    npv = branch_for("npv")
    assert "discount_rate" in npv.required_inputs
    assert "discount_rate" not in irr.required_inputs
    with use_branch(irr, {}):
        claim("project_fcf")
        with pytest.raises(UndeclaredInput) as raised:
            claim("discount_rate")
    assert raised.value.name == "discount_rate"


def test_an_undeclared_plan_concept_refuses_before_the_calculator(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("adscr")

    monkeypatch.setattr("finance_analysis.domain.cover_metrics.adscr", boom)
    definition = _definition(
        "adscr",
        _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)),
        executor_key="adscr",
    )
    plan = _plan("adscr", ("cfads", "debt_service", "ebitda"), definition.definition_hash)
    from finance_analysis.domain.execution_contract import MetricExecutionContext
    from finance_analysis.domain.metric_dispatch import (
        CalculationRequest,
        run_calculation,
    )

    with pytest.raises(UndeclaredInput) as raised:
        run_calculation(
            "adscr",
            CalculationRequest(metric="adscr", common={}),
            MetricExecutionContext(definition=definition, plan=plan),
        )
    assert raised.value.name == "ebitda"


def test_an_unexecutable_housing_formula_is_not_computed(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("housing_dscr")

    monkeypatch.setattr("finance_analysis.domain.housing_dscr.housing_dscr", boom)
    definition = _definition(
        "dscr",
        _expr(numerator_plus=("ebitda",), denominator_plus=("debt_service",)),
        executor_key="coverage",
        executor_id="calculate_coverage",
        executor_version="calculate_coverage@1",
        variant="housing",
    )
    from finance_analysis.domain.execution_contract import MetricExecutionContext
    from finance_analysis.domain.metric_dispatch import (
        CalculationRequest,
        run_calculation,
    )

    outcome = run_calculation(
        "select_ratio",
        CalculationRequest(
            metric="dscr",
            variant="housing",
            common={
                "facts": [],
                "bindings": [],
                "periods": [],
                "sign_convention": "outflow_negative",
                "marker_class": None,
                "absent": frozenset(),
            },
            profile=_flags(),
            composed={},
        ),
        MetricExecutionContext(definition=definition),
    )
    assert outcome.result["status"] == "not_computed"
    assert outcome.result["reason"] == "unsupported_formula"
    assert outcome.result["rows"] == []


def test_a_reduction_run_records_inputs_periods_and_facts():
    from finance_analysis.domain.cover_metrics import dscr_reductions
    from finance_analysis.domain.execution_branches import take_trace

    periods = [
        {
            "axis_id": "a",
            "timeline_id": "a",
            "period_id": "2025",
            "period_index": 0,
            "grain": "year",
            "period_start": __import__("datetime").date(2025, 1, 1),
            "period_end": __import__("datetime").date(2025, 12, 31),
        }
    ]
    facts = [
        {
            "row_key": "c",
            "axis_id": "a",
            "period_id": "2025",
            "normalized_value": Decimal(10),
            "cell_id": "a!c",
        },
        {
            "row_key": "d",
            "axis_id": "a",
            "period_id": "2025",
            "normalized_value": Decimal(-5),
            "cell_id": "a!d",
        },
    ]
    bindings = [
        {
            "row_key": "c",
            "binding_key": "c",
            "is_primary": True,
            "status": "bound",
            "effective_concept": "cfads",
            "source": "inferred",
        },
        {
            "row_key": "d",
            "binding_key": "d",
            "is_primary": True,
            "status": "bound",
            "effective_concept": "debt_service",
            "source": "inferred",
        },
    ]
    result = dscr_reductions(
        "dscr_min",
        facts=facts,
        bindings=bindings,
        periods=periods,
        period_phase={},
        explicit_phases=False,
    )
    trace = take_trace()
    assert result["rows"][0]["value"] == Decimal("2.0000000000")
    assert trace is not None
    assert trace.branch_id == "dscr_min"
    assert "cfads" in trace.actual_inputs and "debt_service" in trace.actual_inputs
    assert "2025" in trace.actual_periods
    assert "a!c" in trace.actual_fact_uses and "a!d" in trace.actual_fact_uses


def test_effective_rate_is_read_only_on_the_escrow_branch():
    from finance_analysis.domain.execution_branches import (
        DSCR_MIN,
        ESCROW,
        claim,
        take_trace,
        use_branch,
    )
    from finance_analysis.domain.housing_cover import housing_cover

    scale = {"base_rate": "0.10", "special_rate": "0.05"}
    with use_branch(ESCROW, {"escrow_rate_scale": scale}):
        claim("escrow_balance")
        claim("effective_rate")
    with use_branch(DSCR_MIN, {}), pytest.raises(UndeclaredInput) as raised:
        claim("effective_rate")
    assert raised.value.name == "effective_rate"
    periods = [
        {
            "axis_id": "a",
            "timeline_id": "t",
            "period_id": "2025",
            "period_index": 0,
            "grain": "year",
        }
    ]
    bindings = [
        {"effective_concept": "debt_outstanding", "row_key": "d", "is_primary": True, "status": "bound"},
        {"effective_concept": "escrow_balance", "row_key": "e", "is_primary": True, "status": "bound"},
        {"effective_concept": "effective_rate", "row_key": "r", "is_primary": True, "status": "bound"},
    ]
    facts = [
        {"row_key": "d", "axis_id": "a", "period_id": "2025", "normalized_value": Decimal(100), "cell_id": "d!2025"},
        {"row_key": "e", "axis_id": "a", "period_id": "2025", "normalized_value": Decimal(40), "cell_id": "e!2025"},
        {"row_key": "r", "axis_id": "a", "period_id": "2025", "normalized_value": Decimal("0.20"), "cell_id": "r!2025"},
    ]
    housing_cover(
        "escrow_blended_rate",
        facts=facts,
        bindings=bindings,
        periods=periods,
        profile={"escrow_rate_scale": scale},
    )
    trace = take_trace()
    assert trace is not None
    assert trace.branch_id == "escrow_blended_rate"
    assert "effective_rate" in trace.actual_inputs
    assert "r!2025" in trace.actual_fact_uses


def test_a_shared_period_id_does_not_pull_the_other_axis():
    from finance_analysis.domain.execution_branches import (
        DSCR_MIN,
        claim,
        run_branch,
        take_trace,
    )

    def body():
        claim("cfads")
        return {"rows": [{"axis_id": "a", "period_id": "2025"}]}

    facts = [
        {"row_key": "c", "axis_id": "a", "period_id": "2025", "cell_id": "a!c"},
        {"row_key": "e", "axis_id": "b", "period_id": "2025", "cell_id": "b!c"},
    ]
    bindings = [
        {"row_key": "c", "effective_concept": "cfads"},
        {"row_key": "e", "effective_concept": "cfads"},
    ]
    run_branch(DSCR_MIN, {}, facts, bindings, body)
    trace = take_trace()
    assert trace is not None
    assert "a!c" in trace.actual_fact_uses
    assert "b!c" not in trace.actual_fact_uses


def test_no_result_rows_do_not_mark_every_fact_used():
    from finance_analysis.domain.execution_branches import (
        DSCR_MIN,
        claim,
        run_branch,
        take_trace,
    )

    def body():
        claim("cfads")
        return {"rows": []}

    facts = [{"row_key": "c", "axis_id": "a", "period_id": "2025", "cell_id": "a!c"}]
    bindings = [{"row_key": "c", "effective_concept": "cfads"}]
    run_branch(DSCR_MIN, {}, facts, bindings, body)
    trace = take_trace()
    assert trace is not None
    assert trace.actual_fact_uses == ()


@pytest.mark.asyncio
async def test_compute_metrics_keeps_the_branch_trace_off_the_public_row(monkeypatch):
    from finance_analysis.application.analyses import Analyses, Target
    from finance_analysis.application.catalog import load_catalog
    from finance_analysis.application.model_types import load_model_types
    from finance_analysis.domain.book import Head
    from finance_analysis.domain.calculation_evidence import CalculationOutcome
    from finance_analysis.domain.errors import NotFound
    from finance_analysis.domain.execution_contract import ExecutionTrace
    from finance_analysis.domain.model_type import Effective

    kept = ExecutionTrace("dscr_min", ("cfads", "debt_service"), ("a!c",), ("2025",), (("llcr_basis", "period_end"),))

    def fake(*_args, **_kwargs):
        return CalculationOutcome(
            {
                "metric": "dscr",
                "rows": [
                    {
                        "metric": "dscr",
                        "axis_id": "a",
                        "period_id": "2025",
                        "value": Decimal(1),
                        "status": "computed",
                    }
                ],
                "needs_input": [],
                "warnings": [],
                "status": "succeeded",
            },
            None,
            kept,
        )

    monkeypatch.setattr("finance_analysis.application.analyses.run_calculation", fake)

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
    assert got["rows"][0].get("trace") is None
    assert "trace" not in got["rows"][0]
    assert got["branch_traces"] == [{"metric": "dscr", "trace": kept}]
    assert got["branch_traces"][0]["trace"].profile_values == (("llcr_basis", "period_end"),)


def test_an_aligned_axis_keeps_the_fact_the_result_used():
    from finance_analysis.domain.execution_branches import (
        DSCR_MIN,
        claim,
        run_branch,
        take_trace,
    )

    periods = [
        {"axis_id": "a", "period_id": "A1", "timeline_id": "t", "period_index": 0},
        {"axis_id": "b", "period_id": "B1", "timeline_id": "t", "period_index": 0},
        {"axis_id": "b", "period_id": "B2", "timeline_id": "t", "period_index": 1},
    ]

    def body():
        claim("cfads")
        return {"rows": [{"axis_id": "a", "period_id": "A1"}]}

    facts = [
        {"row_key": "c", "axis_id": "a", "period_id": "A1", "cell_id": "a!c"},
        {"row_key": "c", "axis_id": "b", "period_id": "B1", "cell_id": "b!c"},
        {"row_key": "c", "axis_id": "b", "period_id": "B2", "cell_id": "b!later"},
    ]
    bindings = [{"row_key": "c", "effective_concept": "cfads"}]
    run_branch(DSCR_MIN, {}, facts, bindings, body, periods=periods)
    trace = take_trace()
    assert trace is not None
    assert "a!c" in trace.actual_fact_uses
    assert "b!c" in trace.actual_fact_uses
    assert "b!later" not in trace.actual_fact_uses


def test_period_slots_keep_the_axis_when_period_ids_match():
    from finance_analysis.domain.execution_branches import (
        DSCR_MIN,
        claim,
        run_branch,
        take_trace,
    )

    def body():
        claim("cfads")
        return {
            "rows": [
                {"axis_id": "a", "period_id": "2025"},
                {"axis_id": "b", "period_id": "2025"},
            ]
        }

    run_branch(DSCR_MIN, {}, [], [], body)
    trace = take_trace()
    assert trace is not None
    assert trace.actual_periods == ("2025",)
    assert trace.actual_period_slots == (("a", "2025"), ("b", "2025"))


def _llcr_book(limit: str | None):
    from finance_analysis.domain.housing_cover import housing_cover

    periods = [
        {"axis_id": "a", "period_id": "Q1", "period_index": 1, "timeline_id": "t", "grain": "quarter"},
        {"axis_id": "a", "period_id": "Q2", "period_index": 2, "timeline_id": "t", "grain": "quarter"},
        {"axis_id": "b", "period_id": "B1", "period_index": 1, "timeline_id": "t", "grain": "quarter"},
    ]
    roles = (
        ("cfo_statement", "cfo"),
        ("cfi_statement", "cfi"),
        ("financing_inflows", "inflow"),
        ("senior_principal", "prin"),
        ("senior_interest_paid", "intr"),
    )
    numbers = {
        "cfo": ("100", "80"),
        "cfi": ("0", "0"),
        "inflow": ("0", "0"),
        "prin": ("40", "32"),
        "intr": ("10", "8"),
    }
    bindings = [
        {
            "effective_concept": concept,
            "row_key": row,
            "is_primary": True,
            "status": "bound",
            "source": "inferred",
        }
        for concept, row in roles
    ]
    facts = []
    for _concept, row in roles:
        for period, value in zip(("Q1", "Q2"), numbers[row], strict=True):
            facts.append(
                {
                    "row_key": row,
                    "axis_id": "a",
                    "period_id": period,
                    "value": value,
                    "normalized_value": value,
                    "cell_id": f"{row}!{period}",
                }
            )
    facts.append(
        {
            "row_key": "cfo",
            "axis_id": "b",
            "period_id": "B1",
            "value": "50",
            "normalized_value": "50",
            "cell_id": "b!cfo",
        }
    )
    profile = {"guaranteed_funds_none": True}
    variant = "cbr590"
    if limit is not None:
        bindings.append(
            {
                "effective_concept": "credit_limit",
                "row_key": "lim",
                "is_primary": True,
                "status": "bound",
                "source": "inferred",
            }
        )
        facts.append(
            {
                "row_key": "lim",
                "axis_id": "a",
                "period_id": "Q2",
                "value": limit,
                "normalized_value": limit,
                "cell_id": "lim!Q2",
            }
        )
        profile = None
        variant = "domrf"
    got = housing_cover(
        "llcr",
        facts=facts,
        bindings=bindings,
        periods=periods,
        sign_convention="outflow_negative",
        absent=frozenset(),
        profile=profile,
        variant=variant,
    )
    return got


def test_nominal_llcr_trace_covers_the_horizon_without_a_public_over():
    from finance_analysis.domain.execution_branches import take_trace
    from finance_analysis.domain.metrics import quantize_ratio

    cbr = _llcr_book(None)
    cbr_trace = take_trace()
    assert cbr["rows"][0]["value"] == quantize_ratio(Decimal(230) / Decimal(90))
    assert cbr["rows"][0]["variant"] == "cbr590"
    assert "over" not in cbr["rows"][0]
    assert "_trace_periods" not in cbr["rows"][0]
    assert cbr_trace is not None
    assert cbr_trace.branch_id == "llcr.cbr590"
    for cell in ("cfo!Q1", "cfo!Q2", "prin!Q1", "intr!Q2", "b!cfo"):
        assert cell in cbr_trace.actual_fact_uses
    assert "Q1" in cbr_trace.actual_periods and "Q2" in cbr_trace.actual_periods

    domrf = _llcr_book("100")
    domrf_trace = take_trace()
    assert domrf["rows"][0]["value"] == quantize_ratio(Decimal(230) / Decimal(118))
    assert domrf["rows"][0]["variant"] == "domrf"
    assert "over" not in domrf["rows"][0]
    assert "_trace_periods" not in domrf["rows"][0]
    assert domrf_trace is not None
    assert domrf_trace.branch_id == "llcr.domrf"
    for cell in ("cfo!Q1", "cfo!Q2", "intr!Q1", "lim!Q2", "b!cfo"):
        assert cell in domrf_trace.actual_fact_uses
    assert ("a", "Q1") in domrf_trace.actual_period_slots
    assert ("a", "Q2") in domrf_trace.actual_period_slots
