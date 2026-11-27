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
