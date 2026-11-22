"""План разрешения: один объект, три списка, полный хеш."""

import pytest

from finance_analysis.domain.audit import AuditInput
from finance_analysis.domain.formula_origin import origin_view
from finance_analysis.domain.free_cash_flow import free_cash_flow
from finance_analysis.domain.graphs import trace_metric
from finance_analysis.domain.metrics import coverage_ratio
from finance_analysis.domain.model_type import MetricExpression
from finance_analysis.domain.semantic_input import (
    resolve_metric_plan,
    resolve_semantic_inputs,
)

EXPRESSIONS = {
    "dscr": MetricExpression(numerator_plus=("cfads",), denominator_plus=("debt_service",)),
    "icr": MetricExpression(
        one_of=frozenset({"ebitda", "ebit"}),
        one_of_order=("ebitda", "ebit"),
        denominator_plus=("interest",),
    ),
}


def _bind(concept: str, number: int, **extra) -> dict:
    return {
        "status": "bound",
        "is_primary": True,
        "effective_concept": concept,
        "row_key": extra.pop("row_key", f"S|{number}|a"),
        "binding_key": extra.pop("binding_key", f"bk-{concept}-{number}"),
        "source": "inferred",
        **extra,
    }


def test_confirmed_inputs_match_the_resolver_and_diagnostic_is_separate():
    first = _bind("cfads", 1, binding_key="bk-b", row_key="row-b")
    second = _bind("cfads", 2, binding_key="bk-a", row_key="row-a")
    debt = _bind("debt_service", 3)
    bindings = [first, second, debt]
    plan = resolve_metric_plan("dscr", bindings, EXPRESSIONS, catalog_version="cat", build_key="bld")
    resolved = resolve_semantic_inputs("dscr", bindings, EXPRESSIONS)
    assert plan is not None and resolved is not None
    assert plan.status == "needs_input"
    assert [item.concept for item in plan.inputs] == ["debt_service"]
    assert all(item.confirmed and not item.ambiguous for item in plan.inputs)
    assert plan.diagnostic[0].concept == "cfads"
    assert plan.diagnostic[0].binding_key == "bk-a"
    assert plan.diagnostic[0].reason == "ambiguous_primary_binding"
    assert {item.binding_key for item in plan.rejected} == {"bk-b"}
    assert plan.needs_input[0].subject == "cfads"
    assert plan.needs_input[0].reason == "ambiguous"
    confirmed = {item.concept for item in resolved if not item.ambiguous and item.row_key}
    assert {item.concept for item in plan.inputs} == confirmed


def test_hash_uses_engine_version_and_ignores_semantic_model_version_and_array_order():
    bindings = [_bind("cfads", 1), _bind("debt_service", 2)]
    left = resolve_metric_plan(
        "dscr",
        bindings,
        EXPRESSIONS,
        semantic_model_version="smv-a",
    )
    right = resolve_metric_plan(
        "dscr",
        list(reversed(bindings)),
        EXPRESSIONS,
        semantic_model_version="smv-b",
    )
    assert left is not None and right is not None
    assert left.content_sha256 == right.content_sha256
    assert left.plan_id == left.content_sha256[:16]
    assert len(left.plan_id) == 16
    assert left.semantic_model_version == "smv-a"
    assert left.resolution_engine_version
    assert "semantic_model_version" not in left.content_sha256


def test_engine_version_changes_the_digest():
    from finance_analysis.domain.resolved_plan import content_digest

    body = {"resolution_engine_version": "1", "metric_id": "dscr", "inputs": []}
    assert content_digest(body) != content_digest({**body, "resolution_engine_version": "2"})


def test_trace_and_origin_read_one_plan_and_do_not_select(monkeypatch):
    bindings = [_bind("ebitda", 1), _bind("ebit", 2), _bind("interest", 3)]
    facts = [{"row_key": "S|1|a", "cell_id": "P&L!D12"}]
    plan = resolve_metric_plan("icr", bindings, EXPRESSIONS, facts=facts)
    assert plan is not None
    before = trace_metric(
        "icr",
        inputs=None,
        bindings=bindings,
        facts=facts,
        expressions=EXPRESSIONS,
    )

    def boom(*_args, **_kwargs):
        raise AssertionError("selection repeated")

    for module, name in (
        ("finance_analysis.domain.binding_resolution", "select_primary"),
        ("finance_analysis.domain.metrics", "choose_one_of"),
        ("finance_analysis.domain.metrics", "dscr_denominator_plan"),
        ("finance_analysis.domain.metrics", "interest_choice"),
        ("finance_analysis.domain.metrics", "confirm_paid_interest"),
        ("finance_analysis.domain.free_cash_flow", "shield_concepts"),
        ("finance_analysis.domain.free_cash_flow", "_basis"),
        ("finance_analysis.domain.semantic_input", "resolve_semantic_inputs"),
        ("finance_analysis.domain.semantic_input", "resolve_metric_plan"),
        ("finance_analysis.domain.formula_origin", "resolve_semantic_inputs"),
    ):
        monkeypatch.setattr(f"{module}.{name}", boom)

    traced = trace_metric(
        "icr",
        inputs=None,
        bindings=bindings,
        facts=facts,
        expressions=EXPRESSIONS,
        plan=plan,
    )
    assert [(step.concept, step.row_key) for step in traced.steps] == [
        (step.concept, step.row_key) for step in before.steps
    ]
    ebitda = next(step for step in traced.steps if step.concept == "ebitda")
    assert ebitda.cell_ids == ("P&L!D12",)
    assert "plan_id" not in traced.as_dict()
    view = origin_view(
        AuditInput(bindings=list(bindings), facts=list(facts), applicable_metrics=frozenset({"icr"})),
        [],
        EXPRESSIONS,
        plans={"icr": plan},
    )
    assert "plan_id" not in view
    with pytest.raises(AssertionError, match="selection repeated"):
        origin_view(
            AuditInput(bindings=list(bindings), applicable_metrics=frozenset({"icr"})),
            [],
            EXPRESSIONS,
        )


def _period() -> dict:
    return {"axis_id": "a", "period_id": "Y1", "period_index": 1, "grain": "year", "timeline_id": "t"}


def _fact(row_key: str, concept: str) -> dict:
    return {
        "row_key": row_key,
        "axis_id": "a",
        "period_id": "Y1",
        "normalized_value": "40",
        "cell_id": f"S!{concept}",
    }


def _silence(monkeypatch) -> None:
    def boom(*_args, **_kwargs):
        raise AssertionError("selection repeated")

    for module, name in (
        ("finance_analysis.domain.binding_resolution", "select_primary"),
        ("finance_analysis.domain.metrics", "choose_one_of"),
        ("finance_analysis.domain.metrics", "dscr_denominator_plan"),
        ("finance_analysis.domain.metrics", "interest_choice"),
        ("finance_analysis.domain.metrics", "confirm_paid_interest"),
        ("finance_analysis.domain.free_cash_flow", "shield_concepts"),
        ("finance_analysis.domain.free_cash_flow", "_basis"),
        ("finance_analysis.domain.semantic_input", "resolve_metric_plan"),
    ):
        monkeypatch.setattr(f"{module}.{name}", boom)


def test_calculators_read_the_plan_and_do_not_select(monkeypatch):
    bindings = [_bind("ebitda", 1), _bind("ebit", 2), _bind("interest", 3)]
    facts = [_fact(row["row_key"], row["effective_concept"]) for row in bindings]
    periods = [_period()]
    plan = resolve_metric_plan("icr", bindings, EXPRESSIONS)
    assert plan is not None and plan.status == "resolved"
    assert plan.shield is None
    before = coverage_ratio(
        metric="icr",
        facts=facts,
        bindings=bindings,
        periods=periods,
        period_phase={},
        explicit_phases=False,
    )
    blocked = [
        _bind("cfads", 1, binding_key="bk-b", row_key="row-b"),
        _bind("cfads", 2, binding_key="bk-a", row_key="row-a"),
        _bind("debt_service", 3),
    ]
    blocked_plan = resolve_metric_plan("dscr", blocked, EXPRESSIONS)
    blocked_before = coverage_ratio(
        metric="dscr",
        facts=[_fact(row["row_key"], "cfads") for row in blocked],
        bindings=blocked,
        periods=periods,
        period_phase={},
        explicit_phases=False,
    )
    ocf = _bind("operating_cash_flow", 1)
    capex = _bind("capex", 2)
    fcff_bindings = [ocf, capex]
    fcff_facts = [_fact(row["row_key"], row["effective_concept"]) for row in fcff_bindings]
    fcff_plan = resolve_metric_plan(
        "fcff",
        fcff_bindings,
        None,
        inputs={"all_of": ("operating_cash_flow", "capex")},
    )
    assert fcff_plan is not None and fcff_plan.shield is not None
    assert fcff_plan.shield.basis == "unknown"
    fcff_before = free_cash_flow(facts=fcff_facts, bindings=fcff_bindings, periods=periods)
    _silence(monkeypatch)
    after = coverage_ratio(
        metric="icr",
        facts=facts,
        bindings=bindings,
        periods=periods,
        period_phase={},
        explicit_phases=False,
        plan=plan,
    )
    assert after["status"] == before["status"] == "succeeded"
    assert after["rows"] == before["rows"]
    assert after["warnings"] == before["warnings"]
    blocked_after = coverage_ratio(
        metric="dscr",
        facts=[_fact(row["row_key"], "cfads") for row in blocked],
        bindings=blocked,
        periods=periods,
        period_phase={},
        explicit_phases=False,
        plan=blocked_plan,
    )
    assert blocked_after["status"] == blocked_before["status"] == "needs_input"
    assert blocked_after["needs_input"] == blocked_before["needs_input"]
    assert blocked_after["missing_inputs"] == blocked_before["missing_inputs"]
    fcff_after = free_cash_flow(
        facts=fcff_facts,
        bindings=fcff_bindings,
        periods=periods,
        plan=fcff_plan,
    )
    assert fcff_after["status"] == fcff_before["status"]
    assert [row["status"] for row in fcff_after["rows"]] == [row["status"] for row in fcff_before["rows"]]


def test_covenant_reads_the_plan_and_ratios_primary_does_not_select(monkeypatch):
    from finance_analysis.application.model_types import (
        load_metric_catalog,
        load_model_types,
    )
    from finance_analysis.domain.covenant import covenant_dscr
    from finance_analysis.plugins.rules.ratios import _primary

    catalog = load_model_types()
    _inputs, _variants, _composed, _bases, _rates, expressions = load_metric_catalog()
    bindings = [
        _bind("ebitda", 1, row_key="e"),
        _bind("cash_taxes", 2, row_key="t"),
        _bind("capex", 3, row_key="c"),
        _bind("interest", 4, row_key="i"),
        _bind("principal", 5, row_key="p"),
    ]
    facts = [
        _fact("e", "ebitda") | {"normalized_value": "100"},
        _fact("t", "cash_taxes") | {"normalized_value": "10"},
        _fact("c", "capex") | {"normalized_value": "20"},
        _fact("i", "interest") | {"normalized_value": "15"},
        _fact("p", "principal") | {"normalized_value": "5"},
    ]
    periods = [_period()]
    plan = resolve_metric_plan(
        "dscr",
        bindings,
        expressions,
        variant="corporate_covenant",
        interest_order=catalog.interest_order,
        row_fallbacks=catalog.row_fallbacks,
    )
    assert plan is not None and plan.status == "resolved"
    before = covenant_dscr(
        facts=facts,
        bindings=bindings,
        periods=periods,
        default=catalog.composed["dscr.corporate_covenant"],
        concepts=frozenset({"ebitda", "cash_taxes", "capex", "interest", "principal", "dscr"}),
        money=frozenset({"ebitda", "cash_taxes", "capex", "interest", "principal"}),
        interest_order=catalog.interest_order,
        row_fallbacks=catalog.row_fallbacks,
    )
    data = AuditInput(bindings=list(bindings), plans={"dscr": plan})
    stale = _bind("cfads", 9, stale=True, row_key="stale")
    stale_data = AuditInput(bindings=[stale])
    assert _primary(stale_data, "cfads")["row_key"] == "stale"
    _silence(monkeypatch)

    def boom(*_args, **_kwargs):
        raise AssertionError("selection repeated")

    monkeypatch.setattr("finance_analysis.domain.covenant.confirm_paid_interest", boom)
    monkeypatch.setattr("finance_analysis.domain.covenant.interest_choice", boom)
    after = covenant_dscr(
        facts=facts,
        bindings=bindings,
        periods=periods,
        default=catalog.composed["dscr.corporate_covenant"],
        concepts=frozenset({"ebitda", "cash_taxes", "capex", "interest", "principal", "dscr"}),
        money=frozenset({"ebitda", "cash_taxes", "capex", "interest", "principal"}),
        interest_order=catalog.interest_order,
        row_fallbacks=catalog.row_fallbacks,
        plan=plan,
    )
    assert after["rows"] == before["rows"]
    assert after["definition_source"] == before["definition_source"]
    assert _primary(data, "ebitda", metric="dscr")["row_key"] == "e"
    assert _primary(data, "dscr", metric="dscr") is None


def test_one_plan_is_reused_and_trace_keeps_the_full_context(monkeypatch):
    from finance_analysis.domain.semantic_input import plans_for

    bindings = [_bind("ebitda", 1), _bind("interest", 2)]
    facts = [_fact(row["row_key"], row["effective_concept"]) for row in bindings]
    plans = plans_for(
        ["icr"],
        bindings,
        EXPRESSIONS,
        facts=facts,
        links=[{"cell": "S!ebitda", "ref_cell": "S!A1"}],
        statement_sheets=frozenset({"ОПиУ"}),
        interest_order={"icr": ("interest",)},
        catalog_version="cat",
        build_key="bld",
    )
    plan = plans["icr"]
    assert plan is plans["icr"]
    assert plan.catalog_version == "cat"
    assert plan.build_key == "bld"

    def boom(*_args, **_kwargs):
        raise AssertionError("selection repeated")

    monkeypatch.setattr("finance_analysis.domain.semantic_input.resolve_metric_plan", boom)
    monkeypatch.setattr("finance_analysis.domain.formula_origin.resolve_semantic_inputs", boom)
    traced = trace_metric(
        "icr",
        inputs=None,
        bindings=bindings,
        facts=facts,
        expressions=EXPRESSIONS,
        plan=plan,
    )
    assert any(step.cell_ids for step in traced.steps)
    origin_view(
        AuditInput(bindings=list(bindings), facts=list(facts), applicable_metrics=frozenset({"icr"})),
        [],
        EXPRESSIONS,
        plans=plans,
    )


def test_icr_keeps_only_the_chosen_numerator_in_inputs():
    bindings = [_bind("ebitda", 1), _bind("ebit", 2), _bind("interest", 3)]
    plan = resolve_metric_plan("icr", bindings, EXPRESSIONS)
    assert plan is not None
    assert plan.status == "resolved"
    assert {item.concept for item in plan.inputs} == {"ebitda", "interest"}
    assert {item.concept for item in plan.rejected} >= {"ebit"}
    assert any(item.reason == "not_selected_one_of" for item in plan.rejected)
