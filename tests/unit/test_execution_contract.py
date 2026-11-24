"""Контракт исполнения. Калькуляторы его не вызывают."""

from finance_analysis.domain.calculation_evidence import CalculationOutcome
from finance_analysis.domain.execution_contract import (
    ExecutionBranchDefinition,
    ExecutionContractError,
    compile_definition,
    execute_bound,
    read_input,
    reference_definition,
    slots_for,
    trace_for,
)
from finance_analysis.domain.model_type import Composed, MetricExpression, Side
from finance_analysis.domain.resolved_plan import (
    AppliedFallback,
    ResolvedInput,
    seal,
)


def _expr(**kwargs) -> MetricExpression:
    return MetricExpression(**kwargs)


def _plan(metric: str, *, variant: str | None, source: str, inputs=(), fallbacks=()):
    return seal(
        metric_id=metric,
        variant=variant,
        variant_source=source,
        catalog_version=None,
        semantic_model_version=None,
        build_key=None,
        model_id=None,
        status="resolved",
        inputs=inputs,
        diagnostic=(),
        rejected=(),
        fallbacks=fallbacks,
        warnings=(),
        needs_input=(),
        shield=None,
    )


def _input(concept: str, role: str = "all_of") -> ResolvedInput:
    return ResolvedInput(concept, role, "formula", binding_key=f"bk-{concept}", row_key=f"row-{concept}")


class _Recorder:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, context) -> CalculationOutcome:
        self.calls += 1
        return CalculationOutcome(result={"metric": context.definition.metric_id, "rows": []}, evidence=None)


def test_catalog_dscr_resolves_formula_id_and_leaves_version_empty():
    definition = compile_definition(
        "dscr",
        {"dscr": _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",))},
        formula_body={},
    )
    assert definition.formula_id == "dscr"
    assert definition.definition_version is None
    assert definition.variant is None
    assert definition.variant_source == "formula"
    assert definition.definition_source == "catalog"
    assert definition.definition_ref is None
    assert definition.normalized_expression.numerator_plus == ("cfads",)
    assert definition.normalized_expression.denominator_plus == ("debt_service",)
    assert definition.definition_hash
    assert not hasattr(definition, "numerator_plus")


def test_declared_identity_is_kept_and_a_blank_version_is_not_invented():
    declared = compile_definition(
        "dscr",
        {"dscr": _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",))},
        formula_body={"formula_id": "dscr", "definition_version": "dscr@1"},
    )
    blank = compile_definition(
        "icr",
        {
            "icr": _expr(
                one_of=frozenset({"ebitda", "ebit"}),
                one_of_order=("ebitda", "ebit"),
                denominator_plus=("interest",),
            )
        },
        formula_body={"definition_version": ""},
    )
    assert declared.formula_id == "dscr"
    assert declared.definition_version == "dscr@1"
    assert blank.formula_id == "icr"
    assert blank.definition_version is None


def test_profile_override_and_base_use_the_same_resolution_as_the_plan():
    catalog = {
        "dscr": _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)),
        "adscr": _expr(base="dscr"),
    }
    override = _expr(numerator_plus=("ebitda",), denominator_plus=("interest",))
    replaced = compile_definition("dscr", catalog, dscr_expression=override)
    inherited = compile_definition("adscr", catalog)
    assert replaced.definition_source == "profile"
    assert replaced.normalized_expression.numerator_plus == ("ebitda",)
    assert replaced.normalized_expression.denominator_plus == ("interest",)
    assert replaced.variant_source == "formula"
    assert inherited.variant_source == "base:dscr"
    assert inherited.normalized_expression.numerator_plus == ("cfads",)
    assert inherited.definition_hash != replaced.definition_hash


def test_resolve_covenant_supplies_source_ref_and_sides():
    default = Composed(Side(("cfads",), ()), Side(("debt_service",), ()), "LTM")
    definition = compile_definition(
        "dscr",
        {"dscr": _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",))},
        variant="corporate_covenant",
        formula_body={"formula_id": "dscr.corporate_covenant"},
        covenant={
            "profile": {
                "dscr_definition": {
                    "numerator": {"plus": ["ebitda"]},
                    "denominator": {"plus": ["interest"]},
                    "window": "period",
                    "basis_ref": "clause-4",
                }
            },
            "profile_ref": "profile@3",
            "default": default,
            "concepts": frozenset({"ebitda", "interest", "cfads", "debt_service"}),
            "money": frozenset({"ebitda", "interest", "cfads", "debt_service"}),
        },
    )
    assert definition.formula_id == "dscr.corporate_covenant"
    assert definition.definition_source == "profile"
    assert definition.definition_ref == {
        "profile_id": "profile",
        "profile_version": "profile@3",
        "basis_ref": "clause-4",
    }
    assert definition.normalized_expression.numerator_plus == ("ebitda",)
    assert definition.normalized_expression.denominator_plus == ("interest",)
    assert definition.normalized_expression.window == "period"
    assert definition.variant == "corporate_covenant"


def test_plan_references_the_hash_and_execute_refuses_a_mismatch():
    definition = compile_definition(
        "dscr",
        {"dscr": _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",))},
    )
    plan = _plan("dscr", variant=None, source="formula")
    assert plan.content_sha256
    linked = reference_definition(plan, definition)
    assert linked.definition_hash == definition.definition_hash
    assert linked.content_sha256 == plan.content_sha256
    assert not hasattr(linked, "numerator_plus")
    recorder = _Recorder()
    outcome = execute_bound(recorder, definition, linked, calculation_origin="reported")
    assert recorder.calls == 1
    assert outcome.result["rows"] == []
    assert "calculation_origin" not in outcome.result
    drifted = reference_definition(
        _plan("dscr", variant="housing", source="variant:housing"),
        definition,
    )
    try:
        execute_bound(recorder, definition, drifted)
    except ExecutionContractError as exc:
        assert exc.reason == "variant_mismatch"
    else:
        raise AssertionError("variant mismatch must refuse")
    assert recorder.calls == 1


def test_slots_record_one_of_and_the_dscr_and_icr_fallbacks():
    dscr = compile_definition(
        "dscr",
        {"dscr": _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",))},
    )
    dscr_plan = _plan(
        "dscr",
        variant=None,
        source="formula",
        inputs=(
            _input("cfads"),
            _input("interest_paid"),
            _input("principal"),
        ),
        fallbacks=(AppliedFallback("pf", "debt_service", "interest_paid", "interest_paid_fallback"),),
    )
    icr = compile_definition(
        "icr",
        {
            "icr": _expr(
                one_of=frozenset({"ebitda", "ebit"}),
                one_of_order=("ebitda", "ebit"),
                denominator_plus=("interest",),
            )
        },
    )
    icr_plan = _plan(
        "icr",
        variant=None,
        source="formula",
        inputs=(_input("ebitda", "one_of"), _input("interest_paid")),
        fallbacks=(AppliedFallback("icr", "interest", "interest_paid", None),),
    )
    dscr_slots = {item.slot_id: item for item in slots_for(dscr, reference_definition(dscr_plan, dscr))}
    icr_slots = {item.slot_id: item for item in slots_for(icr, reference_definition(icr_plan, icr))}
    assert dscr_slots["debt_service"].original_terms == ("debt_service",)
    assert dscr_slots["debt_service"].resolved_terms == ("interest_paid", "principal")
    assert dscr_slots["debt_service"].resolution_reason == "fallback"
    assert icr_slots["numerator"].original_terms == ("ebitda", "ebit")
    assert icr_slots["numerator"].resolved_terms == ("ebitda",)
    assert icr_slots["numerator"].resolution_reason == "one_of"
    assert icr_slots["interest"].original_terms == ("interest",)
    assert icr_slots["interest"].resolved_terms == ("interest_paid",)
    assert icr_slots["interest"].resolution_reason == "fallback"


def test_branch_trace_stores_flag_values_and_blocks_a_forbidden_read():
    branch = ExecutionBranchDefinition(
        branch_id="dscr.housing",
        selection_basis="variant:housing",
        required_inputs=("cfo_statement",),
        optional_inputs=("senior_fees",),
        profile_dependencies=("include_senior_fees",),
    )
    trace = trace_for(branch, {"include_senior_fees": False})
    assert trace.actual_inputs == ()
    assert trace.profile_values == (("include_senior_fees", False),)
    allowed = read_input(branch, trace, "senior_fees")
    assert allowed.actual_inputs == ("senior_fees",)
    try:
        read_input(branch, trace, "ebitda")
    except ExecutionContractError as exc:
        assert exc.reason == "forbidden_input"
    else:
        raise AssertionError("forbidden input must refuse")
    assert trace.actual_inputs == ()
