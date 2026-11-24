"""Один проход коэффициента возвращает улику. Словарь для прежних вызывающих тот же."""

from __future__ import annotations

import ast
import hashlib
import inspect
import textwrap
from datetime import date, timedelta
from decimal import Decimal

from finance_analysis.domain.cover_metrics import add_months
from finance_analysis.domain.metrics import (
    _payment,
    coverage_ratio,
    dscr_pf,
    quantize_ratio,
)
from finance_analysis.domain.model_type import MetricExpression
from finance_analysis.domain.semantic_input import resolve_metric_plan

AXIS = "Debt!r3"
EXPRESSIONS = {
    "icr": MetricExpression(
        one_of=frozenset({"ebitda", "ebit"}),
        one_of_order=("ebitda", "ebit"),
        denominator_plus=("interest",),
    ),
}
# Выбор входа уже в штампе разрешения. Адреса ячеек на число не влияют.
# Ранний заслон методики и типы улики не входят в хеш арифметики.
EXCLUDED = frozenset(
    {
        "choose_one_of",
        "interest_choice",
        "dscr_denominator_plan",
        "confirm_paid_interest",
        "_primaries",
        "_groups",
        "declared_concept",
        "absent_concepts",
        "_plan_rows",
        "_plan_roles",
        "_roles_from_definition",
        "_not_computed",
        "_coverage_from_plan",
        "BoundInputs",
        "methodology_block",
        "_component_cells",
        "CalculationOutcome",
        "EvidenceBook",
        "FactUse",
        "PeriodResult",
        "TransformationStep",
        "_step",
        "_remember",
        "_seal",
        "_note",
        "_uses",
        "_restate_step",
        "_exclusion",
        "_ytd_note",
        "_scale_steps",
        "_bound_rows",
        "_consider",
        "_adopt_side",
        "_denominator_names",
        "_part_terminal",
        "_skipped_restatement",
        "_period_steps",
        "_origin_refs",
        "_finish",
        "_numerator_steps",
        "_adopt",
        "_cell_roles",
        "_scale_mark",
        "_window_gap",
        "FactObservation",
    }
)


def _binding(concept: str, row_key: str, **extra) -> dict:
    return {
        "row_key": row_key,
        "binding_key": row_key,
        "is_primary": True,
        "status": "bound",
        "effective_concept": concept,
        "source": "inferred",
        **extra,
    }


def _period(period_id: str, index: int, **extra) -> dict:
    return {
        "axis_id": AXIS,
        "timeline_id": AXIS,
        "period_id": period_id,
        "period_index": index,
        "period_key_base": period_id,
        "grain": "year",
        **extra,
    }


def _fact(row_key: str, period_id: str, normalized: str, **extra) -> dict:
    return {
        "row_key": row_key,
        "axis_id": extra.pop("axis_id", AXIS),
        "period_id": period_id,
        "normalized_value": Decimal(normalized),
        "cell_id": extra.pop("cell_id", f"{row_key}!{period_id}"),
        **extra,
    }


def _call(**overrides):
    from finance_analysis.domain.metrics import calculate_coverage

    payload = {
        "metric": "dscr",
        "facts": [],
        "bindings": [],
        "periods": [],
        "period_phase": {},
        "explicit_phases": False,
    }
    payload.update(overrides)
    return calculate_coverage(**payload)


def _ops(period) -> list[str]:
    return [step.operation for step in period.steps]


def test_ordinary_dscr_records_material_steps_once():
    periods = [_period("2025", 0)]
    facts = [
        _fact("c", "2025", "10", cell_id="CFS!N"),
        _fact("d", "2025", "-1", cell_id="Debt!A"),
        _fact("d", "2025", "-2", cell_id="Debt!B"),
    ]
    bindings = [_binding("cfads", "c"), _binding("debt_service", "d")]
    outcome = _call(facts=facts, bindings=bindings, periods=periods)
    result = outcome.result
    assert result["status"] == "succeeded"
    assert result["warnings"] == []
    assert result["rows"][0]["reason"] is None
    assert result["rows"][0]["value"] == quantize_ratio(Decimal(10) / Decimal(3))
    assert coverage_ratio(
        metric="dscr",
        facts=facts,
        bindings=bindings,
        periods=periods,
        period_phase={},
        explicit_phases=False,
    ) == result
    evidence = outcome.evidence
    assert evidence is not None
    assert evidence.execution_status == "succeeded"
    assert evidence.implementation == "dscr@1"
    assert len(evidence.calculation_stamp) == 16
    period = evidence.period_results[0]
    assert period.status == "computed"
    assert _ops(period) == ["aggregation", "sign_conversion", "division", "quantization"]
    aggregation, sign, division, quantum = period.steps
    assert aggregation.output_value == Decimal(-3)
    assert {ref for ref in aggregation.input_refs} == {"cell:Debt!A", "cell:Debt!B"}
    assert sign.parameters["rule"] == "outflow_negative"
    assert sign.parameters["before"] == Decimal(-3)
    assert sign.output_value == Decimal(3)
    assert division.parameters["numerator"] == Decimal(10)
    assert division.parameters["denominator"] == Decimal(3)
    assert quantum.parameters["precision"] == 38
    assert quantum.parameters["quantum"] == Decimal("0.0000000001")
    assert quantum.parameters["rounding"] == "ROUND_HALF_EVEN"
    assert quantum.output_value == result["rows"][0]["value"]
    assert division.output_value != quantum.output_value


def test_fallback_denominator_signs_parts_and_skips_identity_payment():
    periods = [_period("2025", 0)]
    facts = [
        _fact("c", "2025", "10"),
        _fact("i", "2025", "-2", cell_id="Debt!I"),
        _fact("p", "2025", "-4", cell_id="Debt!P"),
    ]
    bindings = [_binding("cfads", "c"), _binding("interest", "i"), _binding("principal", "p")]
    outcome = _call(
        facts=facts,
        bindings=bindings,
        periods=periods,
        interest_order={"pf": ("interest",)},
    )
    period = outcome.evidence.period_results[0]
    assert _ops(period) == [
        "sign_conversion",
        "sign_conversion",
        "denominator_assembly",
        "division",
        "quantization",
    ]
    assembled = next(step for step in period.steps if step.operation == "denominator_assembly")
    signs = [step for step in period.steps if step.operation == "sign_conversion"]
    assert assembled.output_value == Decimal(6)
    payment = _payment(assembled.output_value, "outflow_negative")
    if payment == assembled.output_value:
        assert len(signs) == 2
        assert all(step.step_id < assembled.step_id for step in signs)
    else:
        assert signs[-1].step_id > assembled.step_id
        assert signs[-1].output_value == payment
    assert outcome.result["rows"][0]["value"] == quantize_ratio(Decimal(10) / Decimal(6))


def test_ytd_quarter_keeps_both_cells_and_the_difference():
    periods = [
        _period("2026Q1", 0, calendar_year=2026, grain="quarter"),
        _period("2026Q2", 1, calendar_year=2026, grain="quarter"),
    ]
    facts = [
        _fact("c", "2026Q1", "50"),
        _fact("c", "2026Q2", "30"),
        _fact("d", "2026Q1", "100", cell_id="Debt!Q1"),
        _fact("d", "2026Q2", "250", cell_id="Debt!Q2"),
    ]
    bindings = [
        _binding("cfads", "c"),
        _binding("debt_service", "d", evidence={"period_basis": "ytd", "period_basis_source": "header"}),
    ]
    outcome = _call(facts=facts, bindings=bindings, periods=periods)
    second = next(item for item in outcome.evidence.period_results if item.period_id == "2026Q2")
    step = next(item for item in second.steps if item.operation == "period_restatement")
    assert step.output_value == Decimal(150)
    assert step.parameters["current_cells"] == ("Debt!Q2",)
    assert step.parameters["previous_cells"] == ("Debt!Q1",)
    assert step.parameters["current_raw"] == Decimal(250)
    assert step.parameters["previous_raw"] == Decimal(100)
    assert step.parameters["current_effective"] == Decimal(250)
    assert step.parameters["previous_effective"] == Decimal(100)
    assert step.parameters["difference"] == Decimal(150)
    assert step.parameters["year"] == 2026
    assert step.parameters["reset_rule"] == "subtract_only_within_year"
    division = next(item for item in second.steps if item.operation == "division")
    assert division.parameters["denominator"] == Decimal(150)
    assert outcome.result["rows"][1]["value"] == quantize_ratio(Decimal(30) / Decimal(150))


def test_missing_previous_ytd_excludes_the_period():
    periods = [
        _period("2026Q1", 0, calendar_year=2026, grain="quarter"),
        _period("2026Q2", 1, calendar_year=2026, grain="quarter"),
    ]
    facts = [
        _fact("c", "2026Q2", "30"),
        _fact("d", "2026Q2", "250", cell_id="Debt!Q2"),
    ]
    bindings = [
        _binding("cfads", "c"),
        _binding("debt_service", "d", evidence={"period_basis": "ytd", "period_basis_source": "header"}),
    ]
    outcome = _call(facts=facts, bindings=bindings, periods=periods)
    assert outcome.result["rows"] == []
    excluded = next(item for item in outcome.evidence.period_results if item.period_id == "2026Q2")
    assert excluded.status == "skipped"
    assert excluded.reason == "previous_ytd_missing"
    step = excluded.steps[0]
    assert step.operation == "period_restatement"
    assert step.output_value is None
    assert step.parameters["reason"] == "previous_ytd_missing"
    assert step.parameters["year"] == 2026
    assert step.parameters["reset_rule"] == "subtract_only_within_year"
    assert all(item.operation != "division" for item in outcome.evidence.period_results for item in item.steps)


def test_scale_assumed_uses_the_sheet_field_once():
    periods = [_period("2025", 0)]
    facts = [
        _fact(
            "c",
            "2025",
            "2000",
            value_dec=Decimal(2),
            scale_factor=Decimal(1000),
            cell_id="CFS!A",
        ),
        _fact("d", "2025", "1", cell_id="Debt!A"),
    ]
    bindings = [_binding("cfads", "c"), _binding("debt_service", "d")]
    outcome = _call(facts=facts, bindings=bindings, periods=periods)
    assert [item["code"] for item in outcome.result["warnings"]] == ["scale_assumed"]
    used = next(item for item in outcome.evidence.fact_uses if item.concept == "cfads")
    assert used.field == "value_dec"
    assert used.sheet is True
    assert used.raw_value == Decimal(2)
    assert used.effective_value == Decimal(2)
    assert outcome.result["rows"][0]["value"] == Decimal("2.0000000000")


def test_figure_names_the_field_that_entered_the_sum():
    periods = [_period("2025", 0)]
    already = [
        _fact(
            "c",
            "2025",
            "2000",
            value_dec=Decimal(2),
            value=Decimal(9),
            scale_factor=Decimal(1000),
            cell_id="CFS!N",
        ),
        _fact("d", "2025", "1000", value_dec=Decimal(1000), scale_factor=Decimal(1), cell_id="Debt!D"),
    ]
    applied = [
        _fact(
            "c",
            "2025",
            "2",
            value_dec=Decimal(2),
            scale_factor=Decimal(1000),
            cell_id="CFS!R",
        ),
        _fact("d", "2025", "500", value_dec=Decimal(500), scale_factor=Decimal(1), cell_id="Debt!R"),
    ]
    bindings = [_binding("cfads", "c"), _binding("debt_service", "d")]
    scaled = _call(facts=already, bindings=bindings, periods=periods)
    raw = _call(facts=applied, bindings=bindings, periods=periods)
    scaled_use = next(item for item in scaled.evidence.fact_uses if item.concept == "cfads")
    raw_use = next(item for item in raw.evidence.fact_uses if item.concept == "cfads")
    assert scaled_use.field == "normalized_value"
    assert scaled_use.sheet is False
    assert scaled_use.effective_value == Decimal(2000)
    assert scaled.result["rows"][0]["value"] == Decimal("2.0000000000")
    assert raw_use.field == "value_dec"
    assert raw_use.raw_value == Decimal(2)
    assert raw_use.effective_value == Decimal(2000)
    assert raw.result["rows"][0]["value"] == Decimal("4.0000000000")


def test_ltm_numerator_is_one_period_and_window_keeps_the_other_axis():
    periods = []
    for index in range(12):
        start = add_months(date(2025, 1, 1), index)
        end = add_months(start, 1) - timedelta(days=1)
        periods.append(
            _period(
                f"2025-{index + 1:02d}",
                index,
                grain="month",
                period_start=start,
                period_end=end,
            )
        )
    last = periods[-1]["period_id"]
    periods.append(
        {
            "axis_id": "Other!r1",
            "timeline_id": AXIS,
            "period_id": "other-0",
            "period_index": 0,
            "period_key_base": "other-0",
            "grain": "month",
        }
    )
    facts = [_fact("c", last, "120", cell_id="CFS!LTM")]
    facts.extend(_fact("d", period["period_id"], "10", cell_id=f"Debt!{period['period_id']}") for period in periods[:12])
    facts.append(
        _fact("d", "other-0", "0", axis_id="Other!r1", cell_id="Other!M1")
    )
    bindings = [
        _binding("cfads", "c", evidence={"period_basis": "ltm", "period_basis_source": "header"}),
        _binding("debt_service", "d"),
    ]
    outcome = _call(facts=facts, bindings=bindings, periods=periods)
    assert outcome.result["status"] == "succeeded"
    numerator = [item for item in outcome.evidence.fact_uses if item.concept == "cfads"]
    assert len(numerator) == 1
    assert numerator[0].period_id == last
    other = next(item for item in outcome.evidence.fact_uses if item.cell_id == "Other!M1")
    assert other.axis_id == "Other!r1"
    assert other.timeline_id == AXIS
    assert other.period_index == 0
    computed = next(item for item in outcome.evidence.period_results if item.status == "computed")
    window = next(step for step in computed.steps if step.operation == "aggregation")
    assert "cell:Other!M1" in window.input_refs
    assert len(window.input_refs) > 1


def test_skipped_periods_stay_in_period_results():
    periods = [
        _period("2025", 0),
        _period("2026", 1, marker_class="forecast"),
        {**_period("2027", 2), "axis_id": "Other!r9"},
    ]
    facts = [
        _fact("c", "2025", "10"),
        _fact("d", "2025", "-5"),
        _fact("c", "2026", "10"),
        _fact("d", "2026", "-5"),
    ]
    bindings = [_binding("cfads", "c"), _binding("debt_service", "d")]
    outcome = _call(facts=facts, bindings=bindings, periods=periods, marker_class="actual")
    found = {item.period_id: item for item in outcome.evidence.period_results}
    assert found["2025"].status == "computed"
    assert found["2026"].status == "skipped"
    assert found["2026"].reason == "marker_mismatch"
    assert found["2027"].status == "skipped"
    assert found["2027"].reason == "axis_not_home"
    assert [row["period_id"] for row in outcome.result["rows"]] == ["2025"]
    phases = _call(
        facts=facts[:2],
        bindings=bindings,
        periods=periods[:1],
        explicit_phases=True,
    )
    assert phases.result["rows"] == []
    assert phases.evidence.period_results[0].status == "skipped"
    assert phases.evidence.period_results[0].reason == "not_coverage_test_period"
    assert phases.evidence.execution_status == "succeeded"


def test_unresolved_plan_does_not_run_or_divide():
    class _Need:
        subject = "cfads"

        def as_dict(self):
            return {"kind": "concept", "reason": "concept_unknown", "subject": "cfads"}

    class _Plan:
        status = "needs_input"
        warnings = ()
        needs_input = (_Need(),)
        content_sha256 = "abc123"

    outcome = _call(plan=_Plan(), periods=[_period("2025", 0)])
    assert outcome.result["status"] == "needs_input"
    assert outcome.result["rows"] == []
    assert outcome.evidence.execution_status == "not_run"
    assert outcome.evidence.plan_content_sha256 == "abc123"
    assert outcome.evidence.period_results == ()


def test_scale_unconfirmed_and_basis_mismatch_refuse_before_division():
    periods = [_period("2025", 0)]
    facts = [
        _fact("c", "2025", "5", value_dec=Decimal(2), scale_factor=Decimal(1000), cell_id="CFS!A"),
        _fact("d", "2025", "1", value_dec=Decimal(1), scale_factor=Decimal(1), cell_id="Debt!A"),
    ]
    bindings = [_binding("cfads", "c"), _binding("debt_service", "d")]
    refused = _call(facts=facts, bindings=bindings, periods=periods)
    assert refused.result["status"] == "scale_unconfirmed"
    assert refused.evidence.execution_status == "refused"
    assert refused.evidence.period_results[0].status == "scale_unconfirmed"
    assert refused.evidence.period_results[0].status != "not_computed"
    assert all(step.operation != "division" for period in refused.evidence.period_results for step in period.steps)
    mismatched = _call(
        facts=[_fact("c", "2025", "10"), _fact("d", "2025", "5")],
        bindings=[
            _binding("cfads", "c"),
            _binding("debt_service", "d", evidence={"period_basis": "ytd", "period_basis_source": "label"}),
        ],
        periods=periods,
    )
    assert mismatched.result["status"] == "basis_mismatch"
    assert mismatched.evidence.execution_status == "refused"
    assert mismatched.evidence.period_results[0].status == "basis_mismatch"
    assert mismatched.evidence.period_results[0].status != "not_computed"
    assert all(step.operation != "division" for period in mismatched.evidence.period_results for step in period.steps)


def test_icr_plan_inputs_are_the_facts_and_choice_is_not_repeated(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("selection repeated")

    both = [_binding("ebitda", "e"), _binding("ebit", "b"), _binding("interest", "i")]
    ebit_only = [_binding("ebit", "b"), _binding("interest", "i")]
    periods = [_period("2025", 0)]

    def facts_for(bindings):
        return [_fact(row["row_key"], "2025", "40", cell_id=f"S!{row['effective_concept']}") for row in bindings]

    plan = resolve_metric_plan("icr", both, EXPRESSIONS)
    only = resolve_metric_plan("icr", ebit_only, EXPRESSIONS)
    assert plan is not None and plan.status == "resolved"
    assert only is not None and only.status == "resolved"
    monkeypatch.setattr("finance_analysis.domain.metrics.interest_choice", boom)
    monkeypatch.setattr("finance_analysis.domain.metrics.choose_one_of", boom)
    full = _call(metric="icr", facts=facts_for(both), bindings=both, periods=periods, plan=plan)
    single = _call(metric="icr", facts=facts_for(ebit_only), bindings=ebit_only, periods=periods, plan=only)
    assert {item.concept for item in full.evidence.fact_uses} == {item.concept for item in plan.inputs if item.row_key}
    assert {item.concept for item in single.evidence.fact_uses} == {item.concept for item in only.inputs if item.row_key}
    assert "ebit" not in {item.concept for item in full.evidence.fact_uses}
    assert {item.concept for item in single.evidence.fact_uses} == {"ebit", "interest"}


def _months(year: int = 2025, count: int = 12, *, skip: set[int] | None = None) -> list[dict]:
    found = []
    skipped = skip or set()
    for index in range(count):
        if index in skipped:
            continue
        start = add_months(date(year, 1, 1), index)
        end = add_months(start, 1) - timedelta(days=1)
        found.append(
            _period(
                f"{year}-{index + 1:02d}",
                index,
                grain="month",
                period_start=start,
                period_end=end,
            )
        )
    return found


def test_ytd_numerator_restates_and_several_facts_assemble():
    periods = [
        _period("2026Q1", 0, calendar_year=2026, grain="quarter"),
        _period("2026Q2", 1, calendar_year=2026, grain="quarter"),
    ]
    ytd = {"period_basis": "ytd", "period_basis_source": "header"}
    outcome = _call(
        facts=[
            _fact("c", "2026Q1", "50", cell_id="CFS!Q1"),
            _fact("c", "2026Q2", "80", cell_id="CFS!Q2"),
            _fact("d", "2026Q1", "10", cell_id="Debt!Q1"),
            _fact("d", "2026Q2", "10", cell_id="Debt!Q2"),
        ],
        bindings=[
            _binding("cfads", "c", evidence=ytd),
            _binding("debt_service", "d"),
        ],
        periods=periods,
    )
    second = next(item for item in outcome.evidence.period_results if item.period_id == "2026Q2")
    step = next(item for item in second.steps if item.operation == "period_restatement" and item.output_value == Decimal(30))
    assert step.parameters["current_cells"] == ("CFS!Q2",)
    assert step.parameters["previous_cells"] == ("CFS!Q1",)
    assert step.parameters["current_raw"] == Decimal(80)
    assert step.parameters["previous_raw"] == Decimal(50)
    assert step.parameters["current_effective"] == Decimal(80)
    assert step.parameters["previous_effective"] == Decimal(50)
    assert step.parameters["difference"] == Decimal(30)
    assert step.parameters["year"] == 2026
    assert step.parameters["reset_rule"] == "subtract_only_within_year"
    division = next(item for item in second.steps if item.operation == "division")
    assert division.parameters["numerator"] == Decimal(30)
    assert outcome.result["rows"][1]["value"] == quantize_ratio(Decimal(30) / Decimal(10))
    icr = _call(
        metric="icr",
        facts=[
            _fact("e", "2026Q1", "50", cell_id="PL!Q1"),
            _fact("e", "2026Q2", "80", cell_id="PL!Q2"),
            _fact("i", "2026Q1", "10", cell_id="PL!I1"),
            _fact("i", "2026Q2", "10", cell_id="PL!I2"),
        ],
        bindings=[
            _binding("ebitda", "e", evidence=ytd),
            _binding("interest", "i"),
        ],
        periods=periods,
    )
    icr_step = next(
        item
        for item in next(row for row in icr.evidence.period_results if row.period_id == "2026Q2").steps
        if item.operation == "period_restatement"
    )
    assert icr_step.output_value == Decimal(30)
    assert icr_step.parameters["current_cells"] == ("PL!Q2",)
    assembled = _call(
        facts=[
            _fact("c", "2025", "6", cell_id="CFS!A"),
            _fact("c", "2025", "4", cell_id="CFS!B"),
            _fact("d", "2025", "-5", cell_id="Debt!A"),
        ],
        bindings=[_binding("cfads", "c"), _binding("debt_service", "d")],
        periods=[_period("2025", 0)],
    )
    built = next(item for item in assembled.evidence.period_results[0].steps if item.operation == "numerator_assembly")
    assert built.output_value == Decimal(10)
    assert set(built.input_refs) == {"cell:CFS!A", "cell:CFS!B"}
    assert assembled.result["rows"][0]["value"] == quantize_ratio(Decimal(10) / Decimal(5))


def test_ltm_keeps_numerator_scale_ytd_and_the_window():
    periods = _months()
    last = periods[-1]["period_id"]
    facts = [
        _fact("c", last, "120", value_dec=Decimal(120), scale_factor=Decimal(1), cell_id="CFS!LTM"),
    ]
    for period in periods:
        if period["period_id"] == "2025-01":
            facts.append(
                _fact(
                    "d",
                    period["period_id"],
                    "1",
                    value_dec=Decimal(1),
                    scale_factor=Decimal(1000),
                    cell_id="Debt!2025-01",
                )
            )
        else:
            facts.append(
                _fact(
                    "d",
                    period["period_id"],
                    "10",
                    value_dec=Decimal(10),
                    scale_factor=Decimal(1),
                    cell_id=f"Debt!{period['period_id']}",
                )
            )
    bindings = [
        _binding("cfads", "c", evidence={"period_basis": "ltm", "period_basis_source": "header"}),
        _binding("debt_service", "d"),
    ]
    outcome = _call(facts=facts, bindings=bindings, periods=periods)
    computed = next(item for item in outcome.evidence.period_results if item.status == "computed")
    division = next(item for item in computed.steps if item.operation == "division")
    aggregation = next(item for item in computed.steps if item.operation == "aggregation")
    assert "cell:CFS!LTM" in division.input_refs
    assert f"step:{aggregation.step_id}" in division.input_refs
    assert "cell:Debt!2025-12" not in division.input_refs
    assert "cell:Debt!2025-12" in aggregation.input_refs
    scaled = next(item for item in computed.steps if item.operation == "scale_normalization")
    assert f"step:{scaled.step_id}" in aggregation.input_refs
    assert scaled.output_value == Decimal(1000)
    assert scaled.parameters["raw"] == Decimal(1)
    assert computed.window_periods == tuple(item["period_id"] for item in periods)
    assert computed.window_missing == ()
    ytd_facts = [_fact("c", last, "120", cell_id="CFS!LTM")]
    for index, period in enumerate(periods):
        ytd_facts.append(_fact("d", period["period_id"], str(10 * (index + 1)), cell_id=f"Debt!{period['period_id']}"))
    ytd = _call(
        facts=ytd_facts,
        bindings=[
            _binding("cfads", "c", evidence={"period_basis": "ltm", "period_basis_source": "header"}),
            _binding("debt_service", "d", evidence={"period_basis": "ytd", "period_basis_source": "header"}),
        ],
        periods=periods,
    )
    ytd_period = next(item for item in ytd.evidence.period_results if item.status == "computed")
    restated = [item for item in ytd_period.steps if item.operation == "period_restatement"]
    assert restated
    assert restated[-1].output_value == Decimal(10)
    assert restated[-1].parameters["difference"] == Decimal(10)
    ytd_division = next(item for item in ytd_period.steps if item.operation == "division")
    ytd_total = next(item for item in ytd_period.steps if item.operation == "aggregation")
    assert "cell:CFS!LTM" in ytd_division.input_refs
    assert f"step:{ytd_total.step_id}" in ytd_division.input_refs
    assert f"step:{restated[-1].step_id}" in ytd_total.input_refs
    partial_periods = _months(skip={5})
    partial = _call(
        facts=[_fact("c", "2025-12", "120", cell_id="CFS!LTM")]
        + [_fact("d", item["period_id"], "10", cell_id=f"Debt!{item['period_id']}") for item in partial_periods],
        bindings=bindings,
        periods=partial_periods,
    )
    gap = next(item for item in partial.evidence.period_results if item.status == "partial_window")
    assert gap.steps == ()
    assert "2025-06" not in gap.window_periods
    assert "2025-06-01" in gap.window_missing
    assert ("2025-06-01", ("debt_service",)) in gap.missing_concepts
    assert "2025-01" in gap.window_periods and "2025-12" in gap.window_periods
    hole_periods = _months()
    hole = _call(
        facts=[_fact("c", last, "120", cell_id="CFS!LTM")]
        + [
            _fact("d", item["period_id"], "10", cell_id=f"Debt!{item['period_id']}")
            for item in hole_periods
            if item["period_id"] != "2025-06"
        ],
        bindings=bindings,
        periods=hole_periods,
    )
    missing_value = next(item for item in hole.evidence.period_results if item.status == "partial_window")
    assert "2025-06" in missing_value.window_periods
    assert "2025-06" in missing_value.window_missing
    assert ("2025-06", ("debt_service",)) in missing_value.missing_concepts
    assert hole.evidence.fact_uses == ()


def test_scale_decision_is_stored_when_no_step_is_written():
    periods = [_period("2025", 0)]
    bindings = [_binding("cfads", "c"), _binding("debt_service", "d")]
    already = _call(
        facts=[
            _fact("c", "2025", "2000", value_dec=Decimal(2), scale_factor=Decimal(1000), cell_id="CFS!N"),
            _fact("d", "2025", "1000", value_dec=Decimal(1000), scale_factor=Decimal(1), cell_id="Debt!D"),
        ],
        bindings=bindings,
        periods=periods,
    )
    used = next(item for item in already.evidence.fact_uses if item.concept == "cfads")
    assert used.scale_factor == Decimal(1000)
    assert used.scale_policy == "apply"
    assert used.scale_applied is True
    assert used.normalization_source == "normalized_value"
    assert all(step.operation != "scale_normalization" for step in already.evidence.period_results[0].steps)
    plain = _call(
        facts=[_fact("c", "2025", "10", cell_id="CFS!P"), _fact("d", "2025", "5", cell_id="Debt!P")],
        bindings=bindings,
        periods=periods,
    )
    bare = next(item for item in plain.evidence.fact_uses if item.concept == "cfads")
    assert bare.scale_factor is None
    assert bare.scale_policy == "plain"
    assert bare.scale_applied is False
    assert bare.normalization_source == "unset"
    multiplied = _call(
        facts=[
            _fact("c", "2025", "2", value_dec=Decimal(2), scale_factor=Decimal(1000), cell_id="CFS!R"),
            _fact("d", "2025", "500", value_dec=Decimal(500), scale_factor=Decimal(1), cell_id="Debt!R"),
        ],
        bindings=bindings,
        periods=periods,
    )
    grown = next(item for item in multiplied.evidence.fact_uses if item.concept == "cfads")
    assert grown.scale_factor == Decimal(1000)
    assert grown.scale_policy == "apply"
    assert grown.scale_applied is True
    assert grown.normalization_source == "multiplied"
    assert any(
        step.operation == "scale_normalization" and step.output_value == Decimal(2000)
        for step in multiplied.evidence.period_results[0].steps
    )
    sheet = _call(
        facts=[
            _fact("c", "2025", "2000", value_dec=Decimal(2), scale_factor=Decimal(1000), cell_id="CFS!S"),
            _fact("d", "2025", "1", cell_id="Debt!S"),
        ],
        bindings=bindings,
        periods=periods,
    )
    assumed = next(item for item in sheet.evidence.fact_uses if item.concept == "cfads")
    assert assumed.scale_factor == Decimal(1000)
    assert assumed.scale_policy == "sheet"
    assert assumed.scale_applied is False
    assert assumed.normalization_source == "sheet"
    assert all(step.operation != "scale_normalization" for step in sheet.evidence.period_results[0].steps)


def test_fact_read_is_not_a_use_until_it_enters_a_period():
    periods = [
        _period("2025", 0),
        _period("2026", 1, marker_class="forecast"),
    ]
    outcome = _call(
        facts=[
            _fact("c", "2025", "10", cell_id="CFS!2025"),
            _fact("d", "2025", "-5", cell_id="Debt!2025"),
            _fact("c", "2026", "99", cell_id="CFS!2026"),
            _fact("d", "2026", "-7", cell_id="Debt!2026"),
        ],
        bindings=[_binding("cfads", "c"), _binding("debt_service", "d")],
        periods=periods,
        marker_class="actual",
    )
    assert {item.cell_id for item in outcome.evidence.fact_observations} == {
        "CFS!2025",
        "Debt!2025",
        "CFS!2026",
        "Debt!2026",
    }
    assert {item.cell_id for item in outcome.evidence.fact_uses} == {"CFS!2025", "Debt!2025"}
    assert {item.result_period_id for item in outcome.evidence.fact_uses} == {"2025"}
    operands = {item.cell_id: item.operand for item in outcome.evidence.fact_uses}
    assert operands == {"CFS!2025": "numerator", "Debt!2025": "denominator"}


def test_dscr_pf_outcome_has_its_own_identity():
    from finance_analysis.domain.metrics import calculate_dscr_pf

    periods = [_period("2025", 0)]
    facts = [_fact("c", "2025", "10"), _fact("d", "2025", "-5")]
    bindings = [_binding("cfads", "c"), _binding("debt_service", "d")]
    kwargs = {
        "facts": facts,
        "bindings": bindings,
        "periods": periods,
        "period_phase": {},
        "explicit_phases": False,
    }
    outcome = calculate_dscr_pf(**kwargs)
    plain = _call(**kwargs)
    assert outcome.result == dscr_pf(**kwargs)
    assert outcome.result == plain.result
    assert outcome.result["metric"] == "dscr"
    assert outcome.evidence is not None
    assert outcome.evidence.metric == "dscr.pf"
    assert outcome.evidence.implementation == "dscr.pf@1"
    assert plain.evidence.implementation == "dscr@1"
    assert plain.evidence.metric == "dscr"


def test_facade_does_not_build_the_evidence_book(monkeypatch):
    from finance_analysis.domain import metrics

    def boom(*_args, **_kwargs):
        raise AssertionError("EvidenceBook")

    periods = [_period("2025", 0)]
    facts = [_fact("c", "2025", "10"), _fact("d", "2025", "-5")]
    bindings = [_binding("cfads", "c"), _binding("debt_service", "d")]
    kwargs = {
        "facts": facts,
        "bindings": bindings,
        "periods": periods,
        "period_phase": {},
        "explicit_phases": False,
    }
    monkeypatch.setattr(metrics, "EvidenceBook", boom)
    facade = coverage_ratio(metric="dscr", **kwargs)
    project = dscr_pf(**kwargs)
    monkeypatch.undo()
    outcome = _call(**kwargs)
    assert facade == outcome.result
    assert project == outcome.result
    assert outcome.evidence is not None


def test_public_ratio_calculates_once(monkeypatch):
    from finance_analysis.domain import metrics

    calls = {"n": 0}
    real = metrics._sums

    def wrapped(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(metrics, "_sums", wrapped)
    periods = [_period("2025", 0)]
    facts = [_fact("c", "2025", "10"), _fact("d", "2025", "-5")]
    bindings = [_binding("cfads", "c"), _binding("debt_service", "d")]
    coverage_ratio(
        metric="dscr",
        facts=facts,
        bindings=bindings,
        periods=periods,
        period_phase={},
        explicit_phases=False,
    )
    assert calls["n"] == 2
    calls["n"] = 0
    dscr_pf(
        facts=facts,
        bindings=bindings,
        periods=periods,
        period_phase={},
        explicit_phases=False,
    )
    assert calls["n"] == 2


def _raw_fact(row_key: str, period_id: str, raw: str, scale: str, cell_id: str) -> dict:
    return {
        "row_key": row_key,
        "axis_id": AXIS,
        "period_id": period_id,
        "value_dec": Decimal(raw),
        "scale_factor": Decimal(scale),
        "cell_id": cell_id,
    }


def _assert_transformed_cell_is_cited_once(steps) -> None:
    """Ячейка с узлом масштаба в этом же графе больше нигде ячейкой не цитируется."""

    owner: dict[str, int] = {}
    for step in steps:
        if step.operation != "scale_normalization":
            continue
        for ref in step.input_refs:
            assert ref not in owner
            owner[ref] = step.step_id
    for step in steps:
        for ref in step.input_refs:
            assert owner.get(ref) in (None, step.step_id)


def _reachable(steps, refs) -> set[str]:
    by_id = {step.step_id: step for step in steps}
    seen: set[str] = set()
    pending = list(refs)
    while pending:
        ref = pending.pop()
        if ref in seen:
            continue
        seen.add(ref)
        if ref.startswith("step:"):
            pending.extend(by_id[int(ref.removeprefix("step:"))].input_refs)
    return seen


def test_division_cites_the_terminal_of_each_side():
    periods = [_period("2025", 0)]
    ordinary = _call(
        facts=[
            _fact("c", "2025", "10", cell_id="CFS!N"),
            _fact("d", "2025", "-1", cell_id="Debt!A"),
            _fact("d", "2025", "-2", cell_id="Debt!B"),
        ],
        bindings=[_binding("cfads", "c"), _binding("debt_service", "d")],
        periods=periods,
    )
    steps = ordinary.evidence.period_results[0].steps
    aggregation = next(item for item in steps if item.operation == "aggregation")
    sign = next(item for item in steps if item.operation == "sign_conversion")
    division = next(item for item in steps if item.operation == "division")
    quantum = next(item for item in steps if item.operation == "quantization")
    assert set(aggregation.input_refs) == {"cell:Debt!A", "cell:Debt!B"}
    assert sign.input_refs == (f"step:{aggregation.step_id}",)
    assert set(division.input_refs) == {"cell:CFS!N", f"step:{sign.step_id}"}
    assert quantum.input_refs == (f"step:{division.step_id}",)
    assert "cell:Debt!A" in _reachable(steps, division.input_refs)

    quarters = [
        _period("2026Q1", 0, calendar_year=2026, grain="quarter"),
        _period("2026Q2", 1, calendar_year=2026, grain="quarter"),
    ]
    ytd = _call(
        facts=[
            _fact("c", "2026Q1", "50", cell_id="CFS!Q1"),
            _fact("c", "2026Q2", "80", cell_id="CFS!Q2"),
            _fact("d", "2026Q1", "10", cell_id="Debt!Q1"),
            _fact("d", "2026Q2", "10", cell_id="Debt!Q2"),
        ],
        bindings=[
            _binding("cfads", "c", evidence={"period_basis": "ytd", "period_basis_source": "header"}),
            _binding("debt_service", "d"),
        ],
        periods=quarters,
    )
    second = next(item for item in ytd.evidence.period_results if item.period_id == "2026Q2")
    restated = next(item for item in second.steps if item.operation == "period_restatement")
    ytd_division = next(item for item in second.steps if item.operation == "division")
    assert set(restated.input_refs) == {"cell:CFS!Q1", "cell:CFS!Q2"}
    assert set(ytd_division.input_refs) == {f"step:{restated.step_id}", "cell:Debt!Q2"}
    assert "cell:CFS!Q2" not in ytd_division.input_refs
    assert "cell:CFS!Q1" in _reachable(second.steps, ytd_division.input_refs)

    from finance_analysis.domain.metrics import calculate_dscr_pf

    project = calculate_dscr_pf(
        facts=[
            _fact("c", "2025", "10", cell_id="CFS!N"),
            _fact("i", "2025", "-2", cell_id="Debt!I"),
            _fact("p", "2025", "-4", cell_id="Debt!P"),
        ],
        bindings=[_binding("cfads", "c"), _binding("interest", "i"), _binding("principal", "p")],
        periods=periods,
        period_phase={},
        explicit_phases=False,
        interest_order={"pf": ("interest",)},
    )
    pf = project.evidence.period_results[0].steps
    signs = [item for item in pf if item.operation == "sign_conversion"]
    assembly = next(item for item in pf if item.operation == "denominator_assembly")
    pf_division = next(item for item in pf if item.operation == "division")
    assert {ref for step in signs for ref in step.input_refs} == {"cell:Debt!I", "cell:Debt!P"}
    assert set(assembly.input_refs) == {f"step:{item.step_id}" for item in signs}
    assert set(pf_division.input_refs) == {"cell:CFS!N", f"step:{assembly.step_id}"}
    assert "cell:Debt!P" not in pf_division.input_refs
    assert "cell:Debt!P" in _reachable(pf, pf_division.input_refs)


def test_preflight_refusal_observes_the_facts_it_read():
    periods = [_period("2025", 0)]
    refused = _call(
        facts=[
            _fact("c", "2025", "5", value_dec=Decimal(2), scale_factor=Decimal(1000), cell_id="CFS!A"),
            _fact("d", "2025", "1", value_dec=Decimal(1), scale_factor=Decimal(1), cell_id="Debt!A"),
        ],
        bindings=[_binding("cfads", "c"), _binding("debt_service", "d")],
        periods=periods,
    )
    assert refused.result["status"] == "scale_unconfirmed"
    assert refused.evidence.fact_uses == ()
    assert {item.cell_id for item in refused.evidence.fact_observations} == {"CFS!A", "Debt!A"}
    assert {item.considered for item in refused.evidence.fact_observations} == {"scale"}

    mismatched = _call(
        facts=[_fact("c", "2025", "10", cell_id="CFS!B"), _fact("d", "2025", "5", cell_id="Debt!B")],
        bindings=[
            _binding("cfads", "c", evidence={"period_basis": "period", "period_basis_source": "header"}),
            _binding("debt_service", "d", evidence={"period_basis": "ytd", "period_basis_source": "label"}),
        ],
        periods=periods,
    )
    assert mismatched.result["status"] == "basis_mismatch"
    assert mismatched.evidence.fact_uses == ()
    assert {item.considered for item in mismatched.evidence.fact_observations} == {"basis"}
    sides = {item.concept: item for item in mismatched.evidence.basis_sides}
    assert (sides["cfads"].period_basis, sides["cfads"].source) == ("period", "header")
    assert (sides["debt_service"].period_basis, sides["debt_service"].source) == ("ytd", "label")

    formula = _call(
        metric="icr",
        facts=[_fact("e", "2025", "10", cell_id="PL!E"), _fact("i", "2025", "4", cell_id="PL!I")],
        bindings=[
            _binding("ebitda", "e", evidence={"period_basis": "period", "period_basis_source": "formula"}),
            _binding("interest", "i", evidence={"period_basis": "ltm", "period_basis_source": "header"}),
        ],
        periods=periods,
    )
    assert formula.result["status"] == "basis_mismatch"
    formula_sides = {item.concept: item for item in formula.evidence.basis_sides}
    assert (formula_sides["ebitda"].period_basis, formula_sides["ebitda"].source) == ("period", "formula")
    assert (formula_sides["interest"].period_basis, formula_sides["interest"].source) == ("ltm", "header")

    principal = _call(
        facts=[
            _fact("c", "2025", "10", cell_id="CFS!C"),
            _fact("i", "2025", "2", cell_id="Debt!I"),
            _fact("p", "2025", "4", cell_id="Debt!P"),
        ],
        bindings=[
            _binding("cfads", "c", evidence={"period_basis": "period", "period_basis_source": "header"}),
            _binding("interest", "i", evidence={"period_basis": "period", "period_basis_source": "header"}),
            _binding("principal", "p", evidence={"period_basis": "ytd", "period_basis_source": "label"}),
        ],
        periods=periods,
        interest_order={"pf": ("interest",)},
    )
    assert principal.result["status"] == "basis_mismatch"
    project_sides = {item.concept: item for item in principal.evidence.basis_sides}
    assert project_sides["principal"].period_basis == "ytd"
    assert project_sides["principal"].source == "label"
    assert project_sides["interest"].period_basis == "period"
    assert {item.concept for item in principal.evidence.fact_observations} >= {"interest", "principal"}
    assert principal.evidence.fact_uses == ()

    missing = _call(
        facts=[_fact("c", "2025", "10", cell_id="CFS!M")],
        bindings=[_binding("cfads", "c")],
        periods=periods,
    )
    assert missing.result["status"] == "missing_input"
    assert [item.cell_id for item in missing.evidence.fact_observations] == ["CFS!M"]
    assert missing.evidence.fact_observations[0].considered == "input"
    assert missing.evidence.fact_uses == ()


def test_zero_denominator_uses_only_the_denominator():
    periods = [_period("2025", 0), _period("2026", 1)]
    ordinary = _call(
        facts=[
            _fact("c", "2025", "10", cell_id="CFS!2025"),
            _fact("d", "2025", "-5", cell_id="Debt!2025"),
            _fact("c", "2026", "8", cell_id="CFS!2026"),
            _fact("d", "2026", "0", cell_id="Debt!2026"),
        ],
        bindings=[_binding("cfads", "c"), _binding("debt_service", "d")],
        periods=periods,
    )
    assert ordinary.result["rows"][0]["period_id"] == "2025"
    assert [row["period_id"] for row in ordinary.result["rows"]] == ["2025"]
    zero = next(item for item in ordinary.evidence.period_results if item.period_id == "2026")
    assert zero.reason == "not_coverage_test_period"
    assert {item.cell_id for item in ordinary.evidence.fact_uses if item.result_period_id == "2026"} == {"Debt!2026"}
    assert {item.operand for item in ordinary.evidence.fact_uses if item.result_period_id == "2026"} == {"denominator"}
    assert {item.cell_id for item in ordinary.evidence.fact_uses if item.result_period_id == "2025"} == {
        "CFS!2025",
        "Debt!2025",
    }

    icr = _call(
        metric="icr",
        facts=[_fact("e", "2025", "10", cell_id="PL!N"), _fact("i", "2025", "0", cell_id="PL!D")],
        bindings=[_binding("ebitda", "e"), _binding("interest", "i")],
        periods=[_period("2025", 0)],
    )
    assert icr.result["rows"][0]["reason"] == "zero_denominator"
    assert {item.cell_id for item in icr.evidence.fact_uses} == {"PL!D"}
    assert {item.operand for item in icr.evidence.fact_uses} == {"denominator"}
    assert "PL!N" in {item.cell_id for item in icr.evidence.fact_observations}

    months = _months()
    last = months[-1]["period_id"]
    ltm = _call(
        metric="icr",
        facts=[_fact("e", last, "120", cell_id="PL!LTM"), _fact("e", "2025-01", "4", cell_id="PL!JAN")]
        + [_fact("i", item["period_id"], "0", cell_id=f"PL!{item['period_id']}") for item in months],
        bindings=[
            _binding("ebitda", "e", evidence={"period_basis": "ltm", "period_basis_source": "header"}),
            _binding("interest", "i"),
        ],
        periods=months,
    )
    ltm_zero = next(item for item in ltm.evidence.period_results if item.reason == "zero_denominator")
    used = {item.cell_id for item in ltm.evidence.fact_uses if item.result_period_id == ltm_zero.period_id}
    assert used == {f"PL!{item['period_id']}" for item in months}
    assert "PL!LTM" not in used and "PL!JAN" not in used
    assert {item.operand for item in ltm.evidence.fact_uses} == {"denominator"}
    assert {"PL!LTM", "PL!JAN"} <= {item.cell_id for item in ltm.evidence.fact_observations}


def test_evidence_names_the_registered_implementation():
    from finance_analysis.domain import metrics
    from finance_analysis.domain.metric_contract import REGISTRY, load_implementations
    from finance_analysis.domain.metrics import calculate_dscr_pf

    load_implementations()
    before = tuple(
        (key, item.implementation_version, item.function.__name__) for key, item in sorted(REGISTRY.items())
    )
    periods = [_period("2025", 0)]
    shared = {"periods": periods, "period_phase": {}, "explicit_phases": False}
    dscr = _call(
        facts=[_fact("c", "2025", "10"), _fact("d", "2025", "-5")],
        bindings=[_binding("cfads", "c"), _binding("debt_service", "d")],
        **shared,
    )
    project = calculate_dscr_pf(
        facts=[_fact("c", "2025", "10"), _fact("d", "2025", "-5")],
        bindings=[_binding("cfads", "c"), _binding("debt_service", "d")],
        **shared,
    )
    icr = _call(
        metric="icr",
        facts=[_fact("e", "2025", "10"), _fact("i", "2025", "-2")],
        bindings=[_binding("ebitda", "e"), _binding("interest", "i")],
        **shared,
    )
    ebit = _call(
        metric="icr_ebit",
        facts=[_fact("b", "2025", "10"), _fact("i", "2025", "-2")],
        bindings=[_binding("ebit", "b"), _binding("interest", "i")],
        **shared,
    )
    assert dscr.evidence.implementation == REGISTRY[("dscr", "dscr")].implementation_version
    assert project.evidence.implementation == REGISTRY[("dscr", "dscr.pf")].implementation_version
    assert icr.evidence.implementation == REGISTRY[("icr", "icr")].implementation_version
    assert ebit.evidence.implementation == REGISTRY[("icr_ebit", "icr_ebit")].implementation_version
    after = tuple((key, item.implementation_version, item.function.__name__) for key, item in sorted(REGISTRY.items()))
    assert before == after
    assert "_IMPLEMENTATION" not in inspect.getsource(metrics)
    source = inspect.getsource(metrics.calculate_dscr_pf)
    assert 'implementation="dscr.pf@1"' not in source
    assert "implementation='dscr.pf@1'" not in source


def test_ltm_gap_names_the_missing_concept():
    periods = _months()
    facts = [_fact("c", "2025-12", "120", cell_id="CFS!LTM")]
    for period in periods:
        facts.append(_fact("i", period["period_id"], "1", cell_id=f"I!{period['period_id']}"))
        if period["period_id"] != "2025-06":
            facts.append(_fact("p", period["period_id"], "1", cell_id=f"P!{period['period_id']}"))
    outcome = _call(
        facts=facts,
        bindings=[
            _binding("cfads", "c", evidence={"period_basis": "ltm", "period_basis_source": "header"}),
            _binding("interest", "i"),
            _binding("principal", "p"),
        ],
        periods=periods,
        interest_order={"pf": ("interest",)},
    )
    gap = next(item for item in outcome.evidence.period_results if item.status == "partial_window")
    assert ("2025-06", ("principal",)) in gap.missing_concepts
    assert "interest" not in dict(gap.missing_concepts)["2025-06"]
    assert any(item.cell_id == "I!2025-06" for item in outcome.evidence.fact_observations)
    assert all(item.cell_id != "I!2025-06" for item in outcome.evidence.fact_uses)
    assert outcome.evidence.fact_uses == ()


def test_ytd_restatement_cites_the_scale_of_both_periods():
    quarters = [
        _period("2026Q1", 0, calendar_year=2026, grain="quarter"),
        _period("2026Q2", 1, calendar_year=2026, grain="quarter"),
    ]
    ytd = {"period_basis": "ytd", "period_basis_source": "header"}
    outcome = _call(
        facts=[
            _raw_fact("c", "2026Q1", "10", "1", "CFS!Q1"),
            _raw_fact("c", "2026Q2", "10", "1", "CFS!Q2"),
            _raw_fact("d", "2026Q1", "10000", "1000", "Debt!Q1"),
            _raw_fact("d", "2026Q2", "15000", "1000", "Debt!Q2"),
        ],
        bindings=[
            _binding("cfads", "c", evidence=ytd),
            _binding("debt_service", "d", evidence=ytd),
        ],
        periods=quarters,
    )
    second = next(item for item in outcome.evidence.period_results if item.period_id == "2026Q2")
    restated = [
        item
        for item in second.steps
        if item.operation == "period_restatement" and item.parameters.get("current_cells") == ("Debt!Q2",)
    ]
    assert len(restated) == 1
    step = restated[0]
    assert step.output_value == Decimal(5_000_000)
    scales = {
        item.input_refs[0]: item
        for item in second.steps
        if item.operation == "scale_normalization" and item.input_refs[0] in {"cell:Debt!Q1", "cell:Debt!Q2"}
    }
    assert scales["cell:Debt!Q1"].output_value == Decimal(10_000_000)
    assert scales["cell:Debt!Q2"].output_value == Decimal(15_000_000)
    assert set(step.input_refs) == {f"step:{scales['cell:Debt!Q1'].step_id}", f"step:{scales['cell:Debt!Q2'].step_id}"}
    assert "cell:Debt!Q1" not in step.input_refs
    assert "cell:Debt!Q2" not in step.input_refs
    for period in outcome.evidence.period_results:
        _assert_transformed_cell_is_cited_once(period.steps)

    months = _months()
    last = months[-1]["period_id"]
    ltm_facts = [_raw_fact("c", last, "120", "1", "CFS!LTM")]
    for index, period in enumerate(months):
        ltm_facts.append(_raw_fact("d", period["period_id"], str(1000 * (index + 1)), "1000", f"Debt!{period['period_id']}"))
    ltm = _call(
        facts=ltm_facts,
        bindings=[
            _binding("cfads", "c", evidence={"period_basis": "ltm", "period_basis_source": "header"}),
            _binding("debt_service", "d", evidence=ytd),
        ],
        periods=months,
    )
    computed = next(item for item in ltm.evidence.period_results if item.status == "computed")
    window_restated = [
        item
        for item in computed.steps
        if item.operation == "period_restatement" and item.parameters.get("current_cells") == (f"Debt!{last}",)
    ]
    assert len(window_restated) == 1
    window_scales = {
        item.input_refs[0]: item
        for item in computed.steps
        if item.operation == "scale_normalization"
        and item.input_refs[0] in {"cell:Debt!2025-11", "cell:Debt!2025-12"}
    }
    assert window_restated[0].output_value == Decimal(1_000_000)
    assert set(window_restated[0].input_refs) == {
        f"step:{window_scales['cell:Debt!2025-11'].step_id}",
        f"step:{window_scales['cell:Debt!2025-12'].step_id}",
    }
    _assert_transformed_cell_is_cited_once(computed.steps)

    missing = _call(
        facts=[
            _raw_fact("c", "2026Q2", "10", "1", "CFS!Q2"),
            _raw_fact("d", "2026Q2", "15000", "1000", "Debt!Q2"),
        ],
        bindings=[
            _binding("cfads", "c"),
            _binding("debt_service", "d", evidence=ytd),
        ],
        periods=quarters,
    )
    excluded = next(item for item in missing.evidence.period_results if item.period_id == "2026Q2")
    assert excluded.reason == "previous_ytd_missing"
    excluded_scale = next(item for item in excluded.steps if item.operation == "scale_normalization")
    excluded_note = next(item for item in excluded.steps if item.operation == "period_restatement")
    assert excluded_scale.input_refs == ("cell:Debt!Q2",)
    assert excluded_note.input_refs == (f"step:{excluded_scale.step_id}",)
    _assert_transformed_cell_is_cited_once(excluded.steps)


def test_phase_exclusion_uses_the_denominator_for_eligibility():
    built = _call(
        facts=[
            _fact("c", "2025", "10", cell_id="CFS!N"),
            _fact("d", "2025", "-4", cell_id="Debt!D"),
        ],
        bindings=[_binding("cfads", "c"), _binding("debt_service", "d")],
        periods=[_period("2025", 0)],
        explicit_phases=True,
        period_phase={(AXIS, "2025"): "construction"},
    )
    assert built.result["rows"] == []
    assert built.evidence.period_results[0].reason == "not_coverage_test_period"
    assert {item.cell_id for item in built.evidence.fact_uses} == {"Debt!D"}
    assert {item.operand for item in built.evidence.fact_uses} == {"eligibility"}

    zero = _call(
        facts=[
            _fact("c", "2025", "10", cell_id="CFS!Z"),
            _fact("d", "2025", "0", cell_id="Debt!Z"),
        ],
        bindings=[_binding("cfads", "c"), _binding("debt_service", "d")],
        periods=[_period("2025", 0)],
        explicit_phases=True,
        period_phase={(AXIS, "2025"): "construction"},
    )
    assert zero.evidence.period_results[0].reason == "not_coverage_test_period"
    assert {item.cell_id for item in zero.evidence.fact_uses} == {"Debt!Z"}
    assert {item.operand for item in zero.evidence.fact_uses} == {"denominator"}

    months = _months()
    last = months[-1]["period_id"]
    ltm = _call(
        facts=[_fact("c", last, "120", cell_id="CFS!LTM")]
        + [_fact("d", item["period_id"], "1", cell_id=f"Debt!{item['period_id']}") for item in months],
        bindings=[
            _binding("cfads", "c", evidence={"period_basis": "ltm", "period_basis_source": "header"}),
            _binding("debt_service", "d"),
        ],
        periods=months,
        explicit_phases=True,
        period_phase={(AXIS, last): "construction"},
    )
    assert ltm.result["status"] == "partial_window"
    assert [row["period_id"] for row in ltm.result["rows"] if row.get("status") == "computed"] == []
    skipped = next(item for item in ltm.evidence.period_results if item.period_id == last)
    assert skipped.reason == "not_coverage_test_period"
    uses = [item for item in ltm.evidence.fact_uses if item.result_period_id == last]
    assert {item.operand for item in uses} == {"eligibility"}
    assert {item.cell_id for item in uses} == {f"Debt!{item['period_id']}" for item in months}
    assert all(item.concept != "cfads" for item in ltm.evidence.fact_uses)

    icr = _call(
        metric="icr",
        facts=[_fact("e", "2025", "10", cell_id="PL!N"), _fact("i", "2025", "-2", cell_id="PL!D")],
        bindings=[_binding("ebitda", "e"), _binding("interest", "i")],
        periods=[_period("2025", 0)],
        explicit_phases=True,
        period_phase={(AXIS, "2025"): "construction"},
    )
    assert icr.result["rows"][0]["status"] == "computed"
    assert {item.operand for item in icr.evidence.fact_uses} == {"numerator", "denominator"}


def test_stamp_rejects_an_unlisted_call_and_does_not_hash_metrics():
    from finance_analysis.domain import metrics
    from finance_analysis.domain.calculation_evidence import (
        calculation_sources,
        calculation_stamp,
        declared_calculation_dependencies,
    )

    declared = {name for name, _obj in declared_calculation_dependencies()}
    calls = set()
    for _name, obj in declared_calculation_dependencies():
        if inspect.isfunction(obj):
            calls |= _project_calls(obj)
    unknown = calls - declared - EXCLUDED
    assert unknown == set()
    material = "\n".join(source for _name, source in calculation_sources())
    file_text = inspect.getsource(metrics)
    assert file_text not in material
    assert "def lease_interest_coverage" not in material
    assert hashlib.sha256(file_text.encode("utf-8")).hexdigest()[:16] != calculation_stamp()
    planted = _project_calls_from_source(
        "def probe():\n    _brand_new_helper(1)\n",
        defined={"_brand_new_helper"},
    )
    assert planted - declared == {"_brand_new_helper"}


def _project_calls(fn: object) -> set[str]:
    module = inspect.getmodule(fn)
    assert module is not None
    defined, imported = _module_names(module)
    return _project_calls_from_source(inspect.getsource(fn), defined=defined, imported=imported)


def _module_names(module: object) -> tuple[set[str], set[str]]:
    tree = ast.parse(inspect.getsource(module))
    defined = set()
    imported = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("finance_analysis."):
            imported.update(alias.asname or alias.name for alias in node.names)
    return defined, imported


def _project_calls_from_source(
    source: str,
    *,
    defined: set[str] | None = None,
    imported: set[str] | None = None,
) -> set[str]:
    tree = ast.parse(textwrap.dedent(source))
    known = set(defined or set())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("finance_analysis."):
            known.update(alias.asname or alias.name for alias in node.names)
    known.update(imported or set())
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in known:
            found.add(node.func.id)
    return found
