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
        "_side_refs",
        "_period_steps",
        "_origin_refs",
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
