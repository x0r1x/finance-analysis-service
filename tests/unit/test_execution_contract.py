"""Контракт исполнения. Калькуляторы его не вызывают."""

from finance_analysis.domain.calculation_evidence import CalculationOutcome
from finance_analysis.domain.execution_contract import (
    CatalogMetricRecord,
    ExecutionBranchDefinition,
    ExecutionContractError,
    ProfileDscrRecord,
    compile_definition,
    execute_bound,
    read_input,
    slots_for,
    trace_for,
)
from finance_analysis.domain.model_type import Composed, MetricExpression, Side
from finance_analysis.domain.resolved_plan import (
    AppliedFallback,
    ResolvedInput,
    seal,
)
from finance_analysis.domain.semantic_input import resolve_metric_plan


def _expr(**kwargs) -> MetricExpression:
    return MetricExpression(**kwargs)


def _record(metric: str, expression: MetricExpression, **kwargs) -> CatalogMetricRecord:
    return CatalogMetricRecord(
        metric_id=metric,
        expression=expression,
        executor_key=kwargs.pop("executor_key", "coverage"),
        executor_id=kwargs.pop("executor_id", "calculate_coverage"),
        executor_version=kwargs.pop("executor_version", "calculate_coverage@1"),
        **kwargs,
    )


def _compile(metric: str, expression: MetricExpression, catalog=None, **kwargs):
    return compile_definition(_record(metric, expression, **kwargs), catalog)


def _plan(metric: str, *, variant: str | None, source: str, inputs=(), fallbacks=(), status="resolved", definition_hash=None):
    return seal(
        metric_id=metric,
        variant=variant,
        variant_source=source,
        catalog_version=None,
        semantic_model_version=None,
        build_key=None,
        model_id=None,
        status=status,
        inputs=inputs,
        diagnostic=(),
        rejected=(),
        fallbacks=fallbacks,
        warnings=(),
        needs_input=(),
        shield=None,
        definition_hash=definition_hash,
    )


def _input(concept: str, role: str = "all_of", *, confirmed: bool = True) -> ResolvedInput:
    return ResolvedInput(
        concept,
        role,
        "formula",
        binding_key=f"bk-{concept}",
        row_key=f"row-{concept}",
        confirmed=confirmed,
    )


def _bind(concept: str, number: int) -> dict:
    return {
        "status": "bound",
        "is_primary": True,
        "effective_concept": concept,
        "row_key": f"S|{number}|a",
        "binding_key": f"bk-{concept}-{number}",
        "source": "inferred",
    }


class _Recorder:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, context) -> CalculationOutcome:
        self.calls += 1
        return CalculationOutcome(result={"metric": context.definition.metric_id, "rows": []}, evidence=None)


def test_catalog_dscr_resolves_formula_id_and_leaves_version_empty():
    definition = _compile("dscr", _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)))
    assert definition.formula_id == "dscr"
    assert definition.definition_version is None
    assert definition.variant is None
    assert definition.variant_source == "formula"
    assert definition.definition_source == "catalog"
    assert definition.definition_ref is None
    assert definition.normalized_expression.numerator_plus == ("cfads",)
    assert definition.normalized_expression.denominator_plus == ("debt_service",)
    assert definition.definition_hash
    assert definition.executor_key != definition.formula_id
    assert not hasattr(definition, "numerator_plus")


def test_declared_identity_is_kept_and_a_blank_version_is_not_invented():
    declared = _compile(
        "dscr",
        _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)),
        formula_id="dscr",
        definition_version="dscr@1",
    )
    blank = _compile(
        "icr",
        _expr(
            one_of=frozenset({"ebitda", "ebit"}),
            one_of_order=("ebitda", "ebit"),
            denominator_plus=("interest",),
        ),
        definition_version="",
    )
    assert declared.formula_id == "dscr"
    assert declared.definition_version == "dscr@1"
    assert blank.formula_id == "icr"
    assert blank.definition_version is None


def test_profile_override_and_base_use_the_same_resolution_as_the_plan():
    dscr = _record("dscr", _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)))
    adscr = _record("adscr", _expr(base="dscr"))
    catalog = {dscr.metric_id: dscr, adscr.metric_id: adscr}
    override = _expr(numerator_plus=("ebitda",), denominator_plus=("interest",))
    replaced = compile_definition(
        dscr,
        catalog,
        profile=ProfileDscrRecord(expression=override, profile_ref="profile@1"),
    )
    inherited = compile_definition(adscr, catalog)
    assert replaced.definition_source == "profile"
    assert replaced.normalized_expression.numerator_plus == ("ebitda",)
    assert replaced.normalized_expression.denominator_plus == ("interest",)
    assert replaced.variant_source == "formula"
    assert inherited.variant_source == "base:dscr"
    assert inherited.normalized_expression.numerator_plus == ("cfads",)
    assert inherited.definition_hash != replaced.definition_hash


def test_resolve_covenant_supplies_source_ref_and_sides():
    default = Composed(Side(("cfads",), ()), Side(("debt_service",), ()), "LTM")
    record = _record(
        "dscr",
        _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)),
        variant="corporate_covenant",
        formula_id="dscr.corporate_covenant",
    )
    definition = compile_definition(
        record,
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
    expression = _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",))
    definition = _compile("dscr", expression)
    bindings = [_bind("cfads", 1), _bind("debt_service", 2)]
    bare = resolve_metric_plan("dscr", bindings, {"dscr": expression})
    linked = resolve_metric_plan("dscr", bindings, {"dscr": expression}, definition=definition)
    assert bare is not None and linked is not None
    assert linked.definition_hash == definition.definition_hash
    assert linked.content_sha256 == bare.content_sha256
    assert linked.status == "resolved"
    assert not hasattr(linked, "numerator_plus")
    recorder = _Recorder()
    outcome = execute_bound(recorder, definition, linked, calculation_origin="reported")
    assert recorder.calls == 1
    assert outcome.result["rows"] == []
    assert "calculation_origin" not in outcome.result
    drifted = _plan(
        "dscr",
        variant="housing",
        source="variant:housing",
        definition_hash=definition.definition_hash,
    )
    try:
        execute_bound(recorder, definition, drifted)
    except ExecutionContractError as exc:
        assert exc.reason == "variant_mismatch"
    else:
        raise AssertionError("variant mismatch must refuse")
    assert recorder.calls == 1


def test_slots_record_one_of_and_the_dscr_and_icr_fallbacks():
    dscr = _compile("dscr", _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)))
    dscr_plan = _plan(
        "dscr",
        variant=None,
        source="formula",
        inputs=(_input("cfads"), _input("interest_paid"), _input("principal")),
        fallbacks=(AppliedFallback("pf", "debt_service", "interest_paid", "interest_paid_fallback"),),
    )
    icr = _compile(
        "icr",
        _expr(
            one_of=frozenset({"ebitda", "ebit"}),
            one_of_order=("ebitda", "ebit"),
            denominator_plus=("interest",),
        ),
    )
    icr_plan = _plan(
        "icr",
        variant=None,
        source="formula",
        inputs=(_input("ebitda", "one_of"), _input("interest_paid")),
        fallbacks=(AppliedFallback("icr", "interest", "interest_paid", None),),
    )
    dscr_slots = {item.slot_id: item for item in slots_for(dscr, dscr_plan)}
    icr_slots = {item.slot_id: item for item in slots_for(icr, icr_plan)}
    assert dscr_slots["debt_service"].original_terms == ("debt_service",)
    assert dscr_slots["debt_service"].resolved_terms == ("interest_paid", "principal")
    assert dscr_slots["debt_service"].resolution_reason == "fallback"
    assert dscr_slots["debt_service"].term_rows == (
        ("interest_paid", "bk-interest_paid", "row-interest_paid"),
        ("principal", "bk-principal", "row-principal"),
    )
    assert dscr_slots["input:cfads"].term_rows == (("cfads", "bk-cfads", "row-cfads"),)
    assert icr_slots["numerator"].original_terms == ("ebitda", "ebit")
    assert icr_slots["numerator"].resolved_terms == ("ebitda",)
    assert icr_slots["numerator"].resolution_reason == "one_of"
    assert icr_slots["numerator"].term_rows == (("ebitda", "bk-ebitda", "row-ebitda"),)
    assert icr_slots["interest"].original_terms == ("interest",)
    assert icr_slots["interest"].resolved_terms == ("interest_paid",)
    assert icr_slots["interest"].resolution_reason == "fallback"
    assert icr_slots["interest"].term_rows == (("interest_paid", "bk-interest_paid", "row-interest_paid"),)


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


def test_semantic_fields_change_definition_hash():
    sides = {"numerator_plus": ("cfads",), "denominator_plus": ("debt_service",)}
    base = _compile("dscr", _expr(**sides))
    changed = {
        "rate": _expr(**sides, rate="discount_rate"),
        "rates": _expr(**sides, rates=("discount_rate",)),
        "aggregate": _expr(**sides, aggregate="stock"),
        "terminal": _expr(**sides, terminal="terminal_value"),
        "compare_with": _expr(**sides, compare_with="ebitda"),
        "add_back": _expr(**sides, add_back=("interest", "income_tax_rate")),
    }
    for name, expression in changed.items():
        other = _compile("dscr", expression)
        assert other.definition_hash != base.definition_hash, name


def test_metric_id_mismatch_refuses():
    expression = _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",))
    dscr = _compile("dscr", expression)
    icr_expression = _expr(
        one_of=frozenset({"ebitda", "ebit"}),
        one_of_order=("ebitda", "ebit"),
        denominator_plus=("interest",),
    )
    try:
        resolve_metric_plan(
            "icr",
            [_bind("ebitda", 1), _bind("interest", 2)],
            {"icr": icr_expression},
            definition=dscr,
        )
    except ExecutionContractError as exc:
        assert exc.reason == "metric_mismatch"
    else:
        raise AssertionError("resolution must refuse a foreign definition")
    icr_plan = _plan("icr", variant=None, source="formula", definition_hash=dscr.definition_hash)
    recorder = _Recorder()
    try:
        execute_bound(recorder, dscr, icr_plan)
    except ExecutionContractError as exc:
        assert exc.reason == "metric_mismatch"
    else:
        raise AssertionError("metric_id mismatch must refuse")
    assert recorder.calls == 0


def test_unresolved_plan_refuses_before_execute():
    definition = _compile("dscr", _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)))
    plan = _plan(
        "dscr",
        variant=None,
        source="formula",
        status="needs_input",
        definition_hash=definition.definition_hash,
    )
    recorder = _Recorder()
    try:
        execute_bound(recorder, definition, plan)
    except ExecutionContractError as exc:
        assert exc.reason == "plan_not_resolved"
    else:
        raise AssertionError("an unresolved plan must refuse")
    assert recorder.calls == 0


def test_profile_versions_change_definition_hash():
    catalog_expression = _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",))
    record = _record("dscr", catalog_expression)
    override = _expr(numerator_plus=("ebitda",), denominator_plus=("interest",))
    first = compile_definition(
        record,
        profile=ProfileDscrRecord(expression=override, profile_ref="profile@1"),
    )
    second = compile_definition(
        record,
        profile=ProfileDscrRecord(expression=override, profile_ref="profile@2"),
    )
    assert first.definition_hash != second.definition_hash
    assert first.normalized_expression.numerator_plus == second.normalized_expression.numerator_plus
    assert first.definition_ref["profile_version"] == "profile@1"
    assert second.definition_ref["profile_version"] == "profile@2"


def test_inconsistent_slot_or_two_one_of_refuses():
    icr = _compile(
        "icr",
        _expr(
            one_of=frozenset({"ebitda", "ebit"}),
            one_of_order=("ebitda", "ebit"),
            denominator_plus=("interest",),
        ),
    )
    two = _plan(
        "icr",
        variant=None,
        source="formula",
        inputs=(_input("ebitda", "one_of"), _input("ebit", "one_of"), _input("interest")),
    )
    try:
        slots_for(icr, two)
    except ExecutionContractError as exc:
        assert exc.reason == "ambiguous_one_of"
    else:
        raise AssertionError("two one_of inputs must refuse")
    dscr = _compile("dscr", _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)))
    foreign = _plan(
        "dscr",
        variant=None,
        source="formula",
        inputs=(_input("interest_paid"),),
        fallbacks=(AppliedFallback("pf", "ebitda", "interest_paid", None),),
    )
    missing_principal = _plan(
        "dscr",
        variant=None,
        source="formula",
        inputs=(_input("interest_paid"),),
        fallbacks=(AppliedFallback("pf", "debt_service", "interest_paid", None),),
    )
    try:
        slots_for(dscr, foreign)
    except ExecutionContractError as exc:
        assert exc.reason == "inconsistent_fallback"
    else:
        raise AssertionError("a fallback off the denominator must refuse")
    try:
        slots_for(dscr, missing_principal)
    except ExecutionContractError as exc:
        assert exc.reason == "inconsistent_fallback"
    else:
        raise AssertionError("a debt-service fallback without confirmed principal must refuse")


def test_executor_identity_is_separate_from_formula_id():
    expression = _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",))
    coverage = _compile(
        "dscr",
        expression,
        executor_key="coverage",
        executor_id="calculate_coverage",
        executor_version="calculate_coverage@1",
    )
    composed = _compile(
        "dscr",
        expression,
        executor_key="composed",
        executor_id="composed_ratio",
        executor_version="composed_ratio@1",
    )
    assert coverage.formula_id == composed.formula_id == "dscr"
    assert coverage.executor_key != coverage.formula_id
    assert coverage.executor_id != coverage.formula_id
    assert coverage.executor_version != coverage.formula_id
    assert coverage.definition_hash != composed.definition_hash


def test_resolver_takes_the_expression_from_the_definition():
    catalog = _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",))
    definition = _compile("dscr", catalog)
    other = {"dscr": _expr(numerator_plus=("ebitda",), denominator_plus=("interest",))}
    try:
        resolve_metric_plan(
            "dscr",
            [
                _bind("ebitda", 1),
                _bind("interest", 2),
                _bind("cfads", 3),
                _bind("debt_service", 4),
            ],
            other,
            definition=definition,
        )
    except ExecutionContractError as exc:
        assert exc.reason == "definition_mismatch"
    else:
        raise AssertionError("a map that disagrees with the definition must not build a plan")
    plan = resolve_metric_plan(
        "dscr",
        [_bind("cfads", 3), _bind("debt_service", 4)],
        None,
        definition=definition,
    )
    assert plan is not None
    assert plan.definition_hash == definition.definition_hash
    assert {item.concept for item in plan.inputs} == {"cfads", "debt_service"}


def test_profile_record_keeps_window_and_basis_ref():
    sides = _expr(numerator_plus=("ebitda",), denominator_plus=("interest",))
    record = _record(
        "dscr",
        _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)),
        window="LTM",
    )
    clause = ProfileDscrRecord(
        expression=sides,
        profile_ref="profile@1",
        window="period",
        basis_ref="clause-4",
    )
    other_clause = ProfileDscrRecord(
        expression=sides,
        profile_ref="profile@1",
        window="period",
        basis_ref="clause-9",
    )
    other_window = ProfileDscrRecord(
        expression=sides,
        profile_ref="profile@1",
        window="LTM",
        basis_ref="clause-4",
    )
    first = compile_definition(record, profile=clause)
    second = compile_definition(record, profile=other_clause)
    third = compile_definition(record, profile=other_window)
    assert first.definition_source == "profile"
    assert first.normalized_expression.window == "period"
    assert first.normalized_expression.numerator_plus == ("ebitda",)
    assert first.definition_ref["profile_version"] == "profile@1"
    assert first.definition_ref["basis_ref"] == "clause-4"
    assert first.definition_hash != second.definition_hash
    assert first.definition_hash != third.definition_hash


def test_base_inherits_the_source_window():
    base = _record(
        "metric_a",
        _expr(
            numerator_plus=("cfads",),
            denominator_plus=("debt_service",),
            rate="discount_rate",
        ),
        window="LTM",
    )
    child = _record("metric_b", _expr(base="metric_a"), window="period")
    compiled = compile_definition(child, {"metric_a": base, "metric_b": child})
    assert compiled.variant_source == "base:metric_a"
    assert compiled.normalized_expression.numerator_plus == ("cfads",)
    assert compiled.normalized_expression.rate == "discount_rate"
    assert compiled.normalized_expression.window == "LTM"
    assert compiled.formula_id == "metric_b"


def test_fallback_slot_must_be_the_metric_slot():
    dscr = _compile("dscr", _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)))
    foreign = _plan(
        "dscr",
        variant=None,
        source="formula",
        inputs=(_input("cfads"), _input("interest_paid"), _input("principal")),
        fallbacks=(AppliedFallback("other", "debt_service", "interest_paid", None),),
    )
    try:
        slots_for(dscr, foreign)
    except ExecutionContractError as exc:
        assert exc.reason == "inconsistent_fallback"
    else:
        raise AssertionError("a slot outside the metric's fallback ids must refuse")
    covenant = _compile(
        "dscr",
        _expr(numerator_plus=("ebitda",), denominator_plus=("interest",)),
        variant="corporate_covenant",
    )
    wrong = _plan(
        "dscr",
        variant="corporate_covenant",
        source="variant:corporate_covenant",
        inputs=(_input("ebitda"), _input("interest_paid")),
        fallbacks=(AppliedFallback("pf", "interest", "interest_paid", None),),
    )
    try:
        slots_for(covenant, wrong)
    except ExecutionContractError as exc:
        assert exc.reason == "inconsistent_fallback"
    else:
        raise AssertionError("DSCR PF slot does not apply to corporate_covenant")
