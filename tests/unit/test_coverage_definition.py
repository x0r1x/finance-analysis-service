"""DSCR и ICR считают стороны из определения, не из литералов _plan_roles."""

from datetime import date, timedelta
from decimal import Decimal

from finance_analysis.domain.cover_metrics import add_months
from finance_analysis.domain.execution_contract import (
    CatalogMetricRecord,
    ProfileDscrRecord,
    compile_definition,
)
from finance_analysis.domain.metric_contract import UndeclaredInput
from finance_analysis.domain.metrics import calculate_coverage, coverage_from_definition
from finance_analysis.domain.model_type import MetricExpression
from finance_analysis.domain.resolved_plan import AppliedFallback, ResolvedInput, seal
from finance_analysis.domain.semantic_input import resolve_metric_plan


def _expr(**kwargs) -> MetricExpression:
    return MetricExpression(**kwargs)


def _definition(metric: str, expression: MetricExpression, **kwargs):
    return compile_definition(
        CatalogMetricRecord(
            metric_id=metric,
            expression=expression,
            executor_key="coverage",
            executor_id="calculate_coverage",
            executor_version="calculate_coverage@1",
            **kwargs,
        )
    )


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


def _calc(definition, bindings, facts, *, plan=None):
    if plan is None:
        expressions = {definition.metric_id: _expr(
            numerator_plus=definition.normalized_expression.numerator_plus,
            numerator_minus=definition.normalized_expression.numerator_minus,
            denominator_plus=definition.normalized_expression.denominator_plus,
            denominator_minus=definition.normalized_expression.denominator_minus,
            one_of=frozenset(definition.normalized_expression.one_of),
            one_of_order=definition.normalized_expression.one_of,
        )}
        if definition.variant:
            expressions = {f"{definition.metric_id}.{definition.variant}": next(iter(expressions.values()))}
        plan = resolve_metric_plan(
            definition.metric_id,
            bindings,
            expressions,
            variant=definition.variant,
            definition=definition,
        )
    return coverage_from_definition(
        definition,
        plan,
        facts=facts,
        bindings=bindings,
        periods=[{"axis_id": "a", "period_id": "Y1", "period_index": 1, "grain": "year", "timeline_id": "t"}],
        period_phase={},
        explicit_phases=False,
    )


def _value(result) -> Decimal:
    return result["rows"][0]["value"]


def test_changing_a_numerator_or_denominator_changes_the_quotient():
    facts = [_fact("c", "80"), _fact("e", "40"), _fact("d", "-10"), _fact("i", "-5")]
    bindings = [
        _bind("cfads", "c"),
        _bind("ebitda", "e"),
        _bind("debt_service", "d"),
        _bind("interest", "i"),
    ]
    cfads = _definition("dscr", _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)))
    ebitda = _definition("dscr", _expr(numerator_plus=("ebitda",), denominator_plus=("debt_service",)))
    interest = _definition("dscr", _expr(numerator_plus=("cfads",), denominator_plus=("interest",)))
    assert _value(_calc(cfads, bindings, facts)) == Decimal("8.0000000000")
    assert _value(_calc(ebitda, bindings, facts)) == Decimal("4.0000000000")
    assert _value(_calc(interest, bindings, facts)) == Decimal("16.0000000000")
    pf = _definition(
        "dscr",
        _expr(numerator_plus=("ebitda",), denominator_plus=("debt_service",)),
        variant="pf",
    )
    assert pf.variant_source == "variant:pf"
    assert _value(_calc(pf, bindings, facts)) == Decimal("4.0000000000")
    ebit_facts = [*facts, _fact("b", "20")]
    ebit_bindings = [*bindings, _bind("ebit", "b")]
    by_ebit = _definition("icr_ebit", _expr(numerator_plus=("ebit",), denominator_plus=("interest",)))
    by_ebitda = _definition("icr_ebit", _expr(numerator_plus=("ebitda",), denominator_plus=("interest",)))
    assert _value(_calc(by_ebit, ebit_bindings, ebit_facts)) == Decimal("4.0000000000")
    assert _value(_calc(by_ebitda, ebit_bindings, ebit_facts)) == Decimal("8.0000000000")


def test_an_undeclared_concept_refuses_instead_of_the_old_quotient():
    definition = _definition("dscr", _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)))
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
    try:
        coverage_from_definition(
            definition,
            foreign,
            facts=facts,
            bindings=bindings,
            periods=[{"axis_id": "a", "period_id": "Y1", "period_index": 1, "grain": "year", "timeline_id": "t"}],
            period_phase={},
            explicit_phases=False,
        )
    except UndeclaredInput as exc:
        assert exc.name == "ebitda"
    else:
        raise AssertionError("an input outside the definition must refuse")


def test_an_unsupported_formula_is_not_computed():
    definition = _definition(
        "dscr",
        _expr(numerator_plus=("ebitda",), numerator_minus=("cash_taxes",), denominator_plus=("interest", "principal")),
    )
    facts = [_fact("e", "80"), _fact("t", "-10"), _fact("i", "-10"), _fact("p", "-10")]
    bindings = [_bind("ebitda", "e"), _bind("cash_taxes", "t"), _bind("interest", "i"), _bind("principal", "p")]
    plan = seal(
        metric_id="dscr",
        variant=None,
        variant_source="formula",
        catalog_version=None,
        semantic_model_version=None,
        build_key=None,
        model_id=None,
        status="resolved",
        inputs=tuple(
            ResolvedInput(name, "all_of", "formula", name, name, None, False, True)
            for name in ("ebitda", "cash_taxes", "interest", "principal")
        ),
        diagnostic=(),
        rejected=(),
        fallbacks=(),
        warnings=(),
        needs_input=(),
        shield=None,
        definition_hash=definition.definition_hash,
    )
    result = coverage_from_definition(
        definition,
        plan,
        facts=facts,
        bindings=bindings,
        periods=[{"axis_id": "a", "period_id": "Y1", "period_index": 1, "grain": "year", "timeline_id": "t"}],
        period_phase={},
        explicit_phases=False,
    )
    assert result["status"] == "not_computed"
    assert result["reason"] == "unsupported_formula"
    assert result["rows"] == []


def test_profile_override_uses_the_profile_sides():
    catalog = _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",))
    override = _expr(numerator_plus=("ebitda",), denominator_plus=("interest",))
    definition = compile_definition(
        CatalogMetricRecord(
            metric_id="dscr",
            expression=catalog,
            executor_key="coverage",
            executor_id="calculate_coverage",
            executor_version="calculate_coverage@1",
        ),
        profile=ProfileDscrRecord(expression=override, profile_ref="profile@1", window="period", basis_ref="clause-4"),
    )
    facts = [_fact("c", "80"), _fact("e", "40"), _fact("d", "-10"), _fact("i", "-4")]
    bindings = [_bind("cfads", "c"), _bind("ebitda", "e"), _bind("debt_service", "d"), _bind("interest", "i")]
    result = _calc(definition, bindings, facts)
    assert definition.definition_source == "profile"
    assert definition.definition_ref["basis_ref"] == "clause-4"
    assert _value(result) == Decimal("10.0000000000")
    assert "ebitda" in result["rows"][0]["components"]


def test_one_of_uses_the_slot_and_leaves_the_other_rejected():
    definition = _definition(
        "icr",
        _expr(
            one_of=frozenset({"ebitda", "ebit"}),
            one_of_order=("ebitda", "ebit"),
            denominator_plus=("interest",),
        ),
    )
    bindings = [_bind("ebitda", "e"), _bind("ebit", "b"), _bind("interest", "i")]
    expressions = {
        "icr": _expr(
            one_of=frozenset({"ebitda", "ebit"}),
            one_of_order=("ebitda", "ebit"),
            denominator_plus=("interest",),
        )
    }
    plan = resolve_metric_plan("icr", bindings, expressions, definition=definition)
    assert plan is not None
    assert any(item.concept == "ebit" for item in plan.rejected)
    facts = [_fact("e", "40"), _fact("b", "20"), _fact("i", "-10")]
    result = coverage_from_definition(
        definition,
        plan,
        facts=facts,
        bindings=bindings,
        periods=[{"axis_id": "a", "period_id": "Y1", "period_index": 1, "grain": "year", "timeline_id": "t"}],
        period_phase={},
        explicit_phases=False,
    )
    assert _value(result) == Decimal("4.0000000000")


def test_recorded_fallback_is_applied_once(monkeypatch):
    def chosen_again(*_args, **_kwargs):
        raise AssertionError("fallback chosen again")

    monkeypatch.setattr("finance_analysis.domain.metrics.dscr_denominator_plan", chosen_again)
    definition = _definition("dscr", _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)))
    plan = seal(
        metric_id="dscr",
        variant=None,
        variant_source="formula",
        catalog_version=None,
        semantic_model_version=None,
        build_key=None,
        model_id=None,
        status="resolved",
        inputs=tuple(
            ResolvedInput(name, "all_of", "formula", name, name, None, False, True)
            for name in ("cfads", "interest", "principal")
        ),
        diagnostic=(),
        rejected=(),
        fallbacks=(AppliedFallback("pf", "debt_service", "interest", None),),
        warnings=(),
        needs_input=(),
        shield=None,
        definition_hash=definition.definition_hash,
    )
    facts = [_fact("cfads", "40"), _fact("interest", "-10"), _fact("interest_paid", "-2"), _fact("principal", "-4")]
    bindings = [_bind(name, name) for name in ("cfads", "interest", "interest_paid", "principal")]
    result = coverage_from_definition(
        definition,
        plan,
        facts=facts,
        bindings=bindings,
        periods=[{"axis_id": "a", "period_id": "Y1", "period_index": 1, "grain": "year", "timeline_id": "t"}],
        period_phase={},
        explicit_phases=False,
        interest_order={"pf": ("interest_paid", "interest")},
    )
    assert "interest" in result["rows"][0]["components"]
    assert result["rows"][0]["value"] == Decimal("2.8571428571")


def test_missing_and_ambiguous_inputs_keep_their_status():
    definition = _definition("dscr", _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)))
    missing = resolve_metric_plan(
        "dscr",
        [_bind("cfads", "c")],
        {"dscr": _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",))},
        definition=definition,
    )
    missing_result = coverage_from_definition(
        definition,
        missing,
        facts=[_fact("c", "80")],
        bindings=[_bind("cfads", "c")],
        periods=[{"axis_id": "a", "period_id": "Y1", "period_index": 1, "grain": "year", "timeline_id": "t"}],
        period_phase={},
        explicit_phases=False,
    )
    assert missing_result["status"] == "missing_input"
    assert missing_result["rows"] == []
    ambiguous_bindings = [
        _bind("cfads", "c1"),
        {**_bind("cfads", "c2"), "binding_key": "c2"},
        _bind("debt_service", "d"),
    ]
    ambiguous = resolve_metric_plan(
        "dscr",
        ambiguous_bindings,
        {"dscr": _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",))},
        definition=definition,
    )
    ambiguous_result = coverage_from_definition(
        definition,
        ambiguous,
        facts=[_fact("c1", "80"), _fact("c2", "70"), _fact("d", "-10")],
        bindings=ambiguous_bindings,
        periods=[{"axis_id": "a", "period_id": "Y1", "period_index": 1, "grain": "year", "timeline_id": "t"}],
        period_phase={},
        explicit_phases=False,
    )
    assert ambiguous_result["status"] == "needs_input"
    assert ambiguous_result["rows"] == []


def test_select_ratio_reads_the_four_definitions():
    from finance_analysis.domain.covenant import select_ratio

    facts = [_fact("c", "80"), _fact("e", "40"), _fact("b", "20"), _fact("d", "-10"), _fact("i", "-5")]
    bindings = [
        _bind("cfads", "c"),
        _bind("ebitda", "e"),
        _bind("ebit", "b"),
        _bind("debt_service", "d"),
        _bind("interest", "i"),
    ]
    common = {
        "facts": facts,
        "bindings": bindings,
        "periods": [{"axis_id": "a", "period_id": "Y1", "period_index": 1, "grain": "year", "timeline_id": "t"}],
        "period_phase": {},
        "explicit_phases": False,
        "sign_convention": "outflow_negative",
        "marker_class": None,
        "absent": frozenset(),
    }
    cases = (
        ("dscr", None, _expr(numerator_plus=("ebitda",), denominator_plus=("interest",)), Decimal("8.0000000000")),
        ("dscr", "pf", _expr(numerator_plus=("ebit",), denominator_plus=("debt_service",)), Decimal("2.0000000000")),
        ("icr", None, _expr(numerator_plus=("ebit",), denominator_plus=("interest",)), Decimal("4.0000000000")),
        ("icr_ebit", None, _expr(numerator_plus=("ebitda",), denominator_plus=("interest",)), Decimal("8.0000000000")),
    )
    for metric, variant, expression, expected in cases:
        definition = _definition(metric, expression, **({} if variant is None else {"variant": variant}))
        got = select_ratio(
            metric,
            variant,
            common,
            profile=None,
            profile_ref=None,
            composed={},
            concepts=frozenset(),
            money=frozenset(),
            plan=_calc_plan(definition, bindings),
            definition=definition,
        )
        assert got["status"] == "succeeded"
        assert got["rows"][0]["value"] == expected


def _calc_plan(definition, bindings):
    expression = _expr(
        numerator_plus=definition.normalized_expression.numerator_plus,
        denominator_plus=definition.normalized_expression.denominator_plus,
        one_of=frozenset(definition.normalized_expression.one_of),
        one_of_order=definition.normalized_expression.one_of,
    )
    key = f"{definition.metric_id}.{definition.variant}" if definition.variant else definition.metric_id
    return resolve_metric_plan(
        definition.metric_id,
        bindings,
        {key: expression},
        variant=definition.variant,
        definition=definition,
    )


def _profile_body(numerator: str, denominator: str, window: str) -> dict:
    return {
        "dscr_definition": {
            "numerator": {"plus": [numerator]},
            "denominator": {"plus": [denominator]},
            "window": window,
        }
    }


def _definitions(
    profile: dict,
    *,
    profile_ref: str | None = "desk@1",
    concepts=None,
    money=None,
    warnings=None,
    catalog=None,
    variants=None,
):
    from finance_analysis.application.analyses import _coverage_definitions

    kwargs = {}
    if variants is not None:
        kwargs["variants"] = variants
    found, _accepted = _coverage_definitions(
        ["dscr"],
        {"dscr": _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",))},
        dscr_variant=None,
        variant_of={},
        profile=profile,
        profile_ref=profile_ref,
        concepts=concepts if concepts is not None else frozenset({"cfads", "debt_service", "interest", "ebitda"}),
        money=money if money is not None else frozenset({"cfads", "debt_service", "interest", "ebitda"}),
        warnings=warnings if warnings is not None else [],
        catalog=catalog,
        **kwargs,
    )
    return found


def test_unknown_concept_is_not_compiled_into_the_profile():
    warnings: list[dict] = []
    found = _definitions(_profile_body("not_a_concept", "interest", "period"), warnings=warnings)
    assert found["dscr"].definition_source == "catalog"
    assert found["dscr"].normalized_expression.numerator_plus == ("cfads",)
    assert any(item["code"] == "dscr_definition_invalid" for item in warnings)


def test_non_monetary_concept_is_not_compiled_into_the_profile():
    warnings: list[dict] = []
    found = _definitions(
        _profile_body("headcount", "interest", "period"),
        concepts=frozenset({"cfads", "debt_service", "interest", "ebitda", "headcount"}),
        money=frozenset({"cfads", "debt_service", "interest", "ebitda"}),
        warnings=warnings,
    )
    assert found["dscr"].definition_source == "catalog"
    assert found["dscr"].normalized_expression.numerator_plus == ("cfads",)
    assert any(item["code"] == "dscr_definition_invalid" for item in warnings)


def test_invalid_window_is_not_compiled_into_the_profile():
    warnings: list[dict] = []
    found = _definitions(_profile_body("ebitda", "interest", "quarter"), warnings=warnings)
    assert found["dscr"].definition_source == "catalog"
    assert found["dscr"].normalized_expression.numerator_plus == ("cfads",)
    assert any(item["code"] == "dscr_definition_invalid" for item in warnings)


def test_same_sides_and_different_windows_change_the_hash_and_the_result():
    expression = _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",))
    period = _definition("dscr", expression, window="period")
    ltm = _definition("dscr", expression, window="LTM")
    assert period.definition_hash != ltm.definition_hash
    periods = [
        {
            "axis_id": "a",
            "period_id": "M1",
            "period_index": 1,
            "grain": "month",
            "timeline_id": "t",
            "period_start": date(2024, 1, 1),
            "period_end": date(2024, 1, 31),
        },
        {
            "axis_id": "a",
            "period_id": "M2",
            "period_index": 2,
            "grain": "month",
            "timeline_id": "t",
            "period_start": date(2024, 2, 1),
            "period_end": date(2024, 2, 29),
        },
    ]
    facts = [_fact("c", "10"), _fact("c", "40"), _fact("d", "-1"), _fact("d", "-1")]
    facts[0]["period_id"] = "M1"
    facts[1]["period_id"] = "M2"
    facts[2]["period_id"] = "M1"
    facts[3]["period_id"] = "M2"
    bindings = [_bind("cfads", "c"), _bind("debt_service", "d")]

    def run(definition):
        plan = resolve_metric_plan(
            "dscr",
            bindings,
            {"dscr": expression},
            definition=definition,
        )
        return coverage_from_definition(
            definition,
            plan,
            facts=facts,
            bindings=bindings,
            periods=periods,
            period_phase={},
            explicit_phases=False,
        )

    period_values = {row["value"] for row in run(period)["rows"] if row.get("value") is not None}
    ltm_values = {row["value"] for row in run(ltm)["rows"] if row.get("value") is not None}
    assert Decimal("40.0000000000") in period_values
    assert Decimal("40.0000000000") not in ltm_values


def test_missing_profile_ref_is_not_replaced_with_a_placeholder():
    found = _definitions(_profile_body("ebitda", "interest", "period"), profile_ref=None)
    ref = found["dscr"].definition_ref
    assert found["dscr"].definition_source == "profile"
    assert ref["profile_version"] is None
    assert ref["profile_id"] is None
    assert "profile" not in ref.values()


def test_base_metric_is_compiled_from_the_catalog_record():
    parent = CatalogMetricRecord(
        metric_id="dscr",
        expression=_expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)),
        executor_key="coverage",
        executor_id="calculate_coverage",
        executor_version="calculate_coverage@1",
        formula_id="dscr",
        definition_version="dscr@1",
        window="LTM",
    )
    child = CatalogMetricRecord(
        metric_id="icr",
        expression=_expr(base="dscr"),
        executor_key="coverage",
        executor_id="calculate_coverage",
        executor_version="calculate_coverage@1",
        formula_id="icr",
        definition_version="icr@1",
    )
    from finance_analysis.application.analyses import _coverage_definitions

    found, _accepted = _coverage_definitions(
        ["icr"],
        {"dscr": parent.expression, "icr": child.expression},
        dscr_variant=None,
        variant_of={},
        profile=None,
        profile_ref=None,
        catalog={"dscr": parent, "icr": child},
    )
    assert found["icr"].normalized_expression.numerator_plus == ("cfads",)
    assert found["icr"].normalized_expression.base is None
    assert found["icr"].normalized_expression.window == "LTM"
    assert found["icr"].formula_id == "icr"
    assert found["icr"].definition_version == "icr@1"
    assert found["icr"].variant_source == "base:dscr"


def test_ltm_evidence_names_every_window_fact_and_the_steps():
    expression = _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",))
    definition = _definition("dscr", expression, window="LTM")
    periods = []
    facts = []
    for index in range(12):
        start = add_months(date(2024, 1, 1), index)
        end = add_months(start, 1) - timedelta(days=1)
        period_id = f"M{index + 1}"
        periods.append(
            {
                "axis_id": "a",
                "period_id": period_id,
                "period_index": index,
                "grain": "month",
                "timeline_id": "t",
                "period_start": start,
                "period_end": end,
            }
        )
        facts.append({**_fact("c", "10"), "period_id": period_id, "cell_id": f"CFS!{period_id}"})
        facts.append({**_fact("d", "-1"), "period_id": period_id, "cell_id": f"Debt!{period_id}"})
    bindings = [_bind("cfads", "c"), _bind("debt_service", "d")]
    plan = resolve_metric_plan("dscr", bindings, {"dscr": expression}, definition=definition)
    outcome = calculate_coverage(
        metric="dscr",
        facts=facts,
        bindings=bindings,
        periods=periods,
        period_phase={},
        explicit_phases=False,
        plan=plan,
        definition=definition,
        evidence=True,
    )
    row = next(item for item in outcome.result["rows"] if item["value"] is not None)
    assert row["value"] == Decimal("10.0000000000")
    assert row["period_id"] == "M12"
    evidence = outcome.evidence
    assert evidence is not None
    computed = next(item for item in evidence.period_results if item.status == "computed")
    assert computed.window_periods == tuple(f"M{index + 1}" for index in range(12))
    uses = [item for item in evidence.fact_uses if item.result_period_id == "M12"]
    assert {item.cell_id for item in uses if item.operand == "numerator"} == {f"CFS!M{index + 1}" for index in range(12)}
    assert {item.cell_id for item in uses if item.operand == "denominator"} == {f"Debt!M{index + 1}" for index in range(12)}
    operations = [step.operation for step in computed.steps]
    assert "sign_conversion" in operations
    assert "division" in operations
    sides = [step.parameters.get("side") for step in computed.steps if step.operation == "aggregation"]
    assert "numerator" in sides
    assert "denominator" in sides


def test_a_known_variant_is_accepted_and_an_unknown_one_is_not():
    known: list[dict] = []
    found = _definitions({"dscr_definition": {"variant": "pf"}}, warnings=known, variants=frozenset({"pf"}))
    assert found["dscr"].definition_source == "catalog"
    assert found["dscr"].normalized_expression.numerator_plus == ("cfads",)
    assert not any(item["code"] == "dscr_definition_invalid" for item in known)
    unknown: list[dict] = []
    found = _definitions({"dscr_definition": {"variant": "no_such"}}, warnings=unknown, variants=frozenset({"pf"}))
    assert found["dscr"].definition_source == "catalog"
    assert any(
        item["code"] == "dscr_definition_invalid" and item["params"]["reason"] == "dscr_definition: неизвестный вариант"
        for item in unknown
    )


def test_a_subtraction_profile_is_not_compiled_into_an_executable_definition():
    warnings: list[dict] = []
    found = _definitions(
        {
            "dscr_definition": {
                "numerator": {"plus": ["ebitda"], "minus": ["cash_taxes"]},
                "denominator": {"plus": ["interest"]},
                "window": "period",
            }
        },
        concepts=frozenset({"cfads", "debt_service", "interest", "ebitda", "cash_taxes"}),
        money=frozenset({"cfads", "debt_service", "interest", "ebitda", "cash_taxes"}),
        warnings=warnings,
    )
    assert found["dscr"].definition_source == "catalog"
    assert found["dscr"].normalized_expression.numerator_plus == ("cfads",)
    assert found["dscr"].normalized_expression.numerator_minus == ()
    assert any(item["code"] == "dscr_definition_invalid" for item in warnings)
