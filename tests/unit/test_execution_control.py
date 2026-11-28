"""Вспомогательный вход LLCR и PLCR. Он не слагаемое формулы."""

from datetime import date
from decimal import Decimal

from finance_analysis.domain.cover_metrics import loan_life_ratio
from finance_analysis.domain.graphs import trace_metric
from finance_analysis.domain.metrics import quantize_ratio
from finance_analysis.domain.model_type import MetricExpression
from finance_analysis.domain.resolved_plan import ExecutionConfiguration, run_identity
from finance_analysis.domain.semantic_input import resolve_metric_plan

_LOAN = {
    "llcr": MetricExpression(
        numerator_plus=("cfads",),
        denominator_plus=("debt_outstanding",),
        rate="discount_rate",
    ),
    "plcr": MetricExpression(
        numerator_plus=("cfads",),
        denominator_plus=("debt_outstanding",),
        rate="discount_rate",
    ),
}


def _bind(concept: str, row_key: str, binding_key: str | None = None) -> dict:
    return {
        "status": "bound",
        "is_primary": True,
        "effective_concept": concept,
        "row_key": row_key,
        "binding_key": binding_key or row_key,
        "source": "inferred",
    }


def _loan_bindings(debt_row: str = "debt") -> list[dict]:
    return [
        _bind("cfads", "cfads"),
        _bind("debt_outstanding", "balance"),
        _bind("discount_rate", "rate"),
        _bind("debt_service", debt_row),
    ]


def _roles(plan) -> set[tuple[str, str]]:
    return {(item.concept, item.role) for item in getattr(plan, "execution_control", ())}


def test_llcr_and_plcr_record_debt_service_as_execution_control():
    bindings = _loan_bindings()
    llcr = resolve_metric_plan("llcr", bindings, _LOAN)
    plcr = resolve_metric_plan("plcr", bindings, _LOAN)
    assert llcr is not None and plcr is not None

    assert _roles(llcr) == {
        ("debt_service", "coverage_test_eligibility"),
        ("debt_service", "horizon_boundary"),
    }
    assert _roles(plcr) == {("debt_service", "coverage_test_eligibility")}
    assert {item.row_key for item in llcr.execution_control} == {"debt"}
    assert {item.row_key for item in plcr.execution_control} == {"debt"}
    assert "debt_service" not in {item.concept for item in (*llcr.inputs, *plcr.inputs)}

    traced = trace_metric(
        "llcr",
        inputs=None,
        bindings=bindings,
        expressions=_LOAN,
        plan=llcr,
    )
    published = traced.as_dict()
    assert "execution_control" not in published
    assert "debt_service" not in {step["concept"] for step in published["steps"]}


def test_debt_service_row_change_is_visible_on_the_plan():
    first = resolve_metric_plan("llcr", _loan_bindings("debt-a"), _LOAN)
    second = resolve_metric_plan("llcr", _loan_bindings("debt-b"), _LOAN)
    assert first is not None and second is not None
    assert {item.row_key for item in first.execution_control} == {"debt-a"}
    assert {item.row_key for item in second.execution_control} == {"debt-b"}
    assert first.content_sha256 != second.content_sha256


def test_basis_changes_run_identity_not_the_plan_hash():
    plan = resolve_metric_plan("llcr", _loan_bindings(), _LOAN)
    assert plan is not None
    again = resolve_metric_plan("llcr", _loan_bindings(), _LOAN)
    assert again is not None
    assert plan.content_sha256 == again.content_sha256
    end = ExecutionConfiguration(basis="period_end")
    start = ExecutionConfiguration(basis="period_start")
    assert end.fingerprint() != start.fingerprint()
    assert run_identity(plan.content_sha256, end) != run_identity(plan.content_sha256, start)
    assert ExecutionConfiguration(sign_convention="outflow_positive").fingerprint() != end.fingerprint()
    assert ExecutionConfiguration(explicit_phases=True).fingerprint() != end.fingerprint()
    assert ExecutionConfiguration(marker_class="actual").fingerprint() != end.fingerprint()
    assert ExecutionConfiguration(profile=(("lease_mode", "direct"),)).fingerprint() != end.fingerprint()


def test_the_same_plan_repeats_the_same_window():
    periods, facts, bindings = _horizon_book()
    plan = resolve_metric_plan("llcr", bindings, _LOAN)
    assert plan is not None
    assert {item.row_key for item in plan.execution_control} == {"debt-short"}
    extra = [*bindings, _bind("debt_service", "debt-long", "bk-b")]
    common = {
        "facts": facts,
        "bindings": extra,
        "periods": periods,
        "period_phase": {},
        "explicit_phases": False,
        "plan": plan,
    }
    first = loan_life_ratio("llcr", **common)
    second = loan_life_ratio("llcr", **common)
    assert first["status"] == "succeeded"
    assert second["status"] == "succeeded"
    assert _window(first, "2025") == _window(second, "2025") == ["2026"]
    row = next(item for item in first["rows"] if item["period_id"] == "2025")
    assert "debt_service" not in row["inputs"]
    assert row["value"] == quantize_ratio(
        Decimal(row["inputs"]["npv_cfads"]) / Decimal(row["inputs"]["debt_outstanding"])
    )


def test_ambiguous_debt_service_does_not_become_a_ratio():
    periods, facts, bindings = _horizon_book()
    both = [*bindings, _bind("debt_service", "debt-long", "bk-b")]
    plan = resolve_metric_plan("llcr", both, _LOAN)
    assert plan is not None
    assert _roles(plan) == {
        ("debt_service", "coverage_test_eligibility"),
        ("debt_service", "horizon_boundary"),
    }
    assert {item.row_key for item in plan.execution_control} == {None}
    result = loan_life_ratio(
        "llcr",
        facts=facts,
        bindings=both,
        periods=periods,
        period_phase={},
        explicit_phases=False,
        plan=plan,
    )
    assert result["rows"] == []
    assert result["status"] == "needs_input"


def _horizon_book():
    periods = [
        {
            "axis_id": "Debt!r3",
            "timeline_id": "Debt!r3",
            "period_id": str(year),
            "period_index": index,
            "period_key_base": str(year),
            "grain": "year",
            "period_start": date(year, 1, 1),
            "period_end": date(year, 12, 31),
        }
        for index, year in enumerate((2025, 2026, 2027))
    ]
    facts = (
        _series("cfads", periods, ["100", "100", "100"])
        + _series("debt-short", periods, ["-50", "-50", "0"])
        + _series("debt-long", periods, ["-50", "-50", "-50"])
        + _series("balance", periods, ["140", "140", "140"])
        + _series("rate", periods, ["0", "0", "0"])
    )
    bindings = [
        _bind("cfads", "cfads"),
        _bind("debt_outstanding", "balance"),
        _bind("discount_rate", "rate"),
        _bind("debt_service", "debt-short", "bk-a"),
    ]
    return periods, facts, bindings


def _series(row_key: str, periods: list[dict], values: list[str]) -> list[dict]:
    return [
        {
            "row_key": row_key,
            "axis_id": period["axis_id"],
            "period_id": period["period_id"],
            "normalized_value": Decimal(value),
        }
        for period, value in zip(periods, values, strict=True)
    ]


def _window(result: dict, period_id: str) -> list[str]:
    row = next(item for item in result["rows"] if item["period_id"] == period_id)
    return list(row["window"])
