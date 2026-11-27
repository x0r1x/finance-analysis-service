"""Провенанс лежит на улике. Публичная строка коэффициента его не получает.

Версия определения и версия исполнителя — разные поля. Одно не подставляется вместо другого.
Родитель ADSCR — улика DSCR. Родители min и avg — периоды, которые они сворачивают, и та же улика.
https://www.w3.org/TR/prov-dm/#term-Communication
https://openlineage.io/docs/spec/facets/run-facets/parent_run/
"""

from decimal import Decimal

from finance_analysis.application.model_types import load_model_types
from finance_analysis.domain.calculation_evidence import CalculationEvidence
from finance_analysis.domain.covenant import select_ratio
from finance_analysis.domain.cover_metrics import adscr, dscr_reductions
from finance_analysis.domain.execution_contract import (
    CatalogMetricRecord,
    MetricExecutionContext,
    compile_definition,
)
from finance_analysis.domain.metrics import calculate_coverage
from finance_analysis.domain.model_type import MetricExpression
from finance_analysis.domain.semantic_input import resolve_metric_plan
from finance_analysis.domain.trace_limit import view_from_evidence
from tests.unit.test_cover_provenance import _common, _quarters

_ROW_FIELDS = (
    "definition_version",
    "definition_source",
    "definition_ref",
    "definition_hash",
    "executor_id",
    "executor_version",
    "branch_id",
    "actual_inputs",
    "actual_fact_uses",
    "actual_periods",
    "actual_period_slots",
    "profile_values",
    "parent_evidence_ids",
    "calculation_origin",
    "evidence_id",
    "plan_content_sha256",
)


def _expr(**kwargs) -> MetricExpression:
    return MetricExpression(**kwargs)


def _definition(expression: MetricExpression, **kwargs) -> object:
    return compile_definition(
        CatalogMetricRecord(
            metric_id="dscr",
            expression=expression,
            executor_key="coverage",
            executor_id="calculate_coverage",
            executor_version="calculate_coverage@1",
            **kwargs,
        )
    )


def _plan(definition, bindings):
    expression = definition.normalized_expression
    return resolve_metric_plan(
        "dscr",
        bindings,
        {
            "dscr": _expr(
                numerator_plus=expression.numerator_plus,
                denominator_plus=expression.denominator_plus,
            )
        },
        definition=definition,
    )


def _bindings():
    return [
        {
            "effective_concept": "cfads",
            "row_key": "c",
            "binding_key": "c",
            "is_primary": True,
            "status": "bound",
            "source": "inferred",
        },
        {
            "effective_concept": "debt_service",
            "row_key": "d",
            "binding_key": "d",
            "is_primary": True,
            "status": "bound",
            "source": "inferred",
        },
    ]


def _facts():
    return [
        {"row_key": "c", "axis_id": "a", "period_id": "Y1", "normalized_value": "80"},
        {"row_key": "d", "axis_id": "a", "period_id": "Y1", "normalized_value": "-10"},
    ]


def _run(definition):
    from finance_analysis.domain.metric_dispatch import (
        CalculationRequest,
        run_calculation,
    )

    bindings = _bindings()
    plan = _plan(definition, bindings)
    collect: list = []
    outcome = run_calculation(
        "select_ratio",
        CalculationRequest(
            metric="dscr",
            common={
                "facts": _facts(),
                "bindings": bindings,
                "periods": [{"axis_id": "a", "period_id": "Y1", "period_index": 1, "grain": "year", "timeline_id": "t"}],
                "period_phase": {},
                "explicit_phases": False,
                "sign_convention": "outflow_negative",
                "marker_class": None,
                "absent": frozenset(),
            },
            definition=definition,
            composed={},
            concepts=frozenset({"cfads", "debt_service"}),
            money=frozenset({"cfads", "debt_service"}),
            collect=collect,
        ),
        MetricExecutionContext(definition=definition, plan=plan, calculation_origin="calculated"),
    )
    return outcome.result, collect[0], plan


def _row_is_public(row: dict) -> None:
    for name in _ROW_FIELDS:
        assert name not in row


def test_coverage_evidence_keeps_definition_and_executor_apart():
    definition = _definition(
        _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)),
        definition_version="dscr@1",
        formula_id="dscr",
    )
    result, evidence, plan = _run(definition)
    assert result["rows"][0]["value"] == Decimal("8.0000000000")
    assert evidence.definition_version == "dscr@1"
    assert evidence.executor_id == "calculate_coverage"
    assert evidence.executor_version == "calculate_coverage@1"
    assert evidence.definition_version != evidence.executor_version
    assert evidence.definition_source == "catalog"
    assert evidence.definition_ref is None
    assert evidence.definition_hash == definition.definition_hash
    assert evidence.plan_content_sha256 == plan.content_sha256
    assert evidence.calculation_origin == "calculated"
    assert evidence.evidence_id
    for row in result["rows"]:
        _row_is_public(row)
    view = view_from_evidence(evidence)
    assert view["definition_version"] == "dscr@1"
    assert view["executor_version"] == "calculate_coverage@1"
    assert view["definition_hash"] == definition.definition_hash
    assert view["calculation_origin"] == "calculated"


def test_unset_definition_version_is_not_replaced_by_the_executor():
    definition = _definition(_expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)))
    _result, evidence, _plan = _run(definition)
    assert evidence.definition_version is None
    assert evidence.executor_version == "calculate_coverage@1"
    assert evidence.executor_id == "calculate_coverage"
    assert view_from_evidence(evidence).get("definition_version") is None


def test_adscr_points_at_the_dscr_evidence_and_keeps_the_branch_trace():
    periods, facts = _quarters()
    common = _common(periods, facts)
    source = calculate_coverage(metric="dscr", evidence=True, **common).evidence
    assert isinstance(source, CalculationEvidence)
    collected: list = []
    traced = adscr(direction="lookback", collect=collected, **common)
    evidence = collected[0]
    assert evidence.parent_evidence_ids == (source.evidence_id,)
    assert evidence.evidence_id != source.evidence_id
    assert evidence.definition_version is None
    assert evidence.executor_id == "adscr"
    assert evidence.executor_version == "adscr@1"
    assert evidence.executor_version != evidence.definition_version
    assert evidence.branch_id == "adscr"
    assert ("adscr_direction", "lookback") in evidence.profile_values
    assert "cfads" in evidence.actual_inputs
    assert "debt_service" in evidence.actual_inputs
    assert evidence.actual_periods
    assert evidence.actual_period_slots
    assert evidence.plan_content_sha256 == source.plan_content_sha256
    assert evidence.calculation_origin == "calculated"
    for row in traced["rows"]:
        _row_is_public(row)


def test_reductions_point_at_the_periods_and_the_dscr_evidence():
    periods, facts = _quarters()
    common = _common(periods, facts)
    source = calculate_coverage(metric="dscr", evidence=True, **common).evidence
    period_ids = tuple(
        item.node_id or f"period:{item.axis_id}:{item.period_id}"
        for item in source.period_results
        if item.status == "computed" and item.period_id
    )
    assert period_ids
    for metric in ("dscr_min", "dscr_avg"):
        collected: list = []
        traced = dscr_reductions(metric, collect=collected, **common)
        evidence = collected[0]
        assert evidence.parent_evidence_ids[:-1] == period_ids
        assert evidence.parent_evidence_ids[-1] == source.evidence_id
        assert evidence.branch_id == metric
        assert evidence.executor_id == metric
        assert evidence.executor_version == f"{metric}@1"
        assert evidence.definition_version is None
        assert evidence.calculation_origin == "calculated"
        for row in traced["rows"]:
            _row_is_public(row)


def test_reported_origin_stays_on_the_publication_evidence():
    class _Need:
        subject = "cash_taxes"
        reason = "concept_unknown"

        def as_dict(self):
            return {"kind": "concept", "reason": self.reason, "subject": self.subject}

    class _Plan:
        status = "missing_input"
        content_sha256 = "plan-digest-corporate"
        needs_input = (_Need(),)
        warnings = ()
        inputs = ()
        diagnostic = ()
        rejected = ()
        fallbacks = ()

    types = load_model_types()
    collect: list = []
    got = select_ratio(
        "dscr",
        "corporate_covenant",
        {
            "facts": [
                {
                    "row_key": "book-dscr",
                    "axis_id": "Outputs!r1",
                    "period_id": "2016",
                    "cell_id": "Outputs!D20",
                    "normalized_value": "1.476",
                    "value_status": "cached",
                }
            ],
            "bindings": [
                {
                    "row_key": "book-dscr",
                    "binding_key": "book-dscr",
                    "is_primary": True,
                    "status": "bound",
                    "effective_concept": "dscr",
                    "source": "inferred",
                }
            ],
            "periods": [{"axis_id": "Outputs!r1", "period_id": "2016", "period_key_base": "2016"}],
            "period_phase": {},
            "explicit_phases": False,
            "sign_convention": "outflow_negative",
            "marker_class": None,
            "absent": frozenset(),
        },
        profile=None,
        profile_ref=None,
        composed=types.composed,
        concepts=frozenset({"ebitda", "cash_taxes", "capex", "interest", "principal", "dscr"}),
        money=frozenset({"ebitda", "cash_taxes", "capex", "interest", "principal"}),
        interest_order=types.interest_order,
        row_fallbacks=types.row_fallbacks,
        plan=_Plan(),
        collect=collect,
    )
    assert got["definition_source"] == "reported"
    row = got["rows"][0]
    assert row["reason"] == "reported"
    assert row["variant"] == "reported"
    assert row["status"] == "computed"
    _row_is_public(row)
    _attempt, published = collect
    assert published.execution_status == "published"
    assert published.calculation_origin == "reported"
    assert published.definition_source == "reported"
    assert published.definition_version is None
    assert published.executor_version is None
    assert view_from_evidence(published)["calculation_origin"] == "reported"
