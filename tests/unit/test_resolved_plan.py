"""План разрешения: один объект, три списка, полный хеш."""

import pytest

from finance_analysis.domain.audit import AuditInput
from finance_analysis.domain.formula_origin import origin_view
from finance_analysis.domain.graphs import trace_metric
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


def test_icr_keeps_only_the_chosen_numerator_in_inputs():
    bindings = [_bind("ebitda", 1), _bind("ebit", 2), _bind("interest", 3)]
    plan = resolve_metric_plan("icr", bindings, EXPRESSIONS)
    assert plan is not None
    assert plan.status == "resolved"
    assert {item.concept for item in plan.inputs} == {"ebitda", "interest"}
    assert {item.concept for item in plan.rejected} >= {"ebit"}
    assert any(item.reason == "not_selected_one_of" for item in plan.rejected)
