"""ADSCR и свёртки DSCR несут свою улику, а не книгу DSCR."""

from datetime import date, timedelta
from decimal import Decimal

from finance_analysis.domain.cover_metrics import (
    WINDOW_MONTHS,
    add_months,
    adscr,
    dscr_reductions,
)
from tests.unit.test_metric_golden import _bind, _fact, _period


def _quarters() -> tuple[list[dict], list[dict]]:
    periods = []
    for index in range(4):
        start = add_months(date(2025, 1, 1), 3 * index)
        end = add_months(start, 3) - timedelta(days=1)
        quarter = (start.month - 1) // 3 + 1
        periods.append(
            _period(
                period_id=f"{start.year}Q{quarter}",
                index=index,
                grain="quarter",
                start=start,
                end=end,
            )
        )
    series = {"cfads": ["25", "25", "25", "25"], "debt_service": ["20", "20", "20", "20"]}
    facts = []
    for name, column in series.items():
        for period, value in zip(periods, column, strict=True):
            facts.append(_fact(name, value, period_id=period["period_id"], axis=period["axis_id"]))
    return periods, facts


def _common(periods, facts) -> dict:
    return {
        "facts": facts,
        "bindings": [_bind(name) for name in ("cfads", "debt_service")],
        "periods": periods,
        "period_phase": {},
        "explicit_phases": False,
        "sign_convention": "outflow_negative",
        "marker_class": None,
        "absent": frozenset(),
    }


def test_adscr_evidence_names_the_window_and_the_sums():
    periods, facts = _quarters()
    common = _common(periods, facts)
    plain = adscr(direction="lookback", **common)
    collected: list = []
    traced = adscr(direction="lookback", collect=collected, **common)
    assert traced["rows"] == plain["rows"]
    assert [item.metric for item in collected] == ["adscr"]
    published = next(row for row in traced["rows"] if row["period_id"] == "2025Q4")
    period = next(item for item in collected[0].period_results if item.period_id == "2025Q4")
    step = period.steps[0]
    assert step.operation == "adscr_window"
    assert step.output_value == published["value"]
    assert step.parameters["window_months"] == WINDOW_MONTHS
    assert step.parameters["input_periods"] == published["window"]
    assert step.parameters["direction"] == "lookback"
    assert period.numerator == step.parameters["cfads_sum"]
    assert period.denominator == step.parameters["debt_service_sum"]
    assert period.numerator == Decimal(100)
    assert period.denominator == Decimal(80)


def test_dscr_min_and_avg_link_the_published_value_to_source_periods():
    periods = [_period(period_id="Y1", index=1), _period(period_id="Y2", index=2)]
    facts = [
        _fact("cfads", "100", period_id="Y1"),
        _fact("cfads", "100", period_id="Y2"),
        _fact("debt_service", "50", period_id="Y1"),
        _fact("debt_service", "25", period_id="Y2"),
    ]
    common = _common(periods, facts)
    for metric, expected in (
        ("dscr_min", {Decimal("2.0000000000")}),
        ("dscr_avg", {Decimal("3.0000000000"), Decimal("2.6666666667")}),
    ):
        plain = dscr_reductions(metric, **common)
        collected: list = []
        traced = dscr_reductions(metric, collect=collected, **common)
        assert traced["rows"] == plain["rows"]
        assert [item.metric for item in collected] == [metric]
        evidence = collected[0]
        summary = evidence.period_results[-1]
        linked = {
            f"period:{item.axis_id}:{item.period_id}": item.value
            for item in evidence.period_results
            if item.period_id is not None
        }
        assert summary.steps
        for step in summary.steps:
            assert step.output_value in expected
            assert step.input_refs
            assert set(step.input_refs) <= set(linked)
            assert step.output_value in set(linked.values()) or metric == "dscr_avg"
