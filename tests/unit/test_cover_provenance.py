"""ADSCR и свёртки DSCR несут свою улику, а не книгу DSCR."""

from datetime import date, timedelta
from decimal import Decimal

from finance_analysis.application.analyses import EVIDENCE_AVAILABLE
from finance_analysis.domain.cover_metrics import (
    WINDOW_MONTHS,
    add_months,
    adscr,
    dscr_reductions,
)
from finance_analysis.domain.metrics import calculate_coverage, calculate_dscr_pf
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
    assert [item.metric for item in collected] == ["dscr", "adscr"]
    published = next(row for row in traced["rows"] if row["period_id"] == "2025Q4")
    evidence = next(item for item in collected if item.metric == "adscr")
    period = next(item for item in evidence.period_results if item.period_id == "2025Q4")
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
    assert evidence.fact_observations
    assert evidence.fact_uses
    window_step = step
    source_periods = [
        item
        for item in evidence.period_results
        if not any(one.operation == "adscr_window" for one in item.steps)
    ]
    source_refs = {f"period:{item.axis_id}:{item.period_id}" for item in source_periods}
    assert set(window_step.input_refs) <= source_refs
    assert source_refs
    cited = {
        ref
        for item in source_periods
        for one in item.steps
        for ref in one.input_refs
        if ref.startswith(("cell:", "fact:"))
    }
    observed = {
        f"cell:{item.cell_id}" if item.cell_id else f"fact:{item.axis_id}:{item.period_id}"
        for item in evidence.fact_observations
    }
    assert cited & observed
    assert any(item.normalization_source for item in evidence.fact_observations)


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
        assert [item.metric for item in collected] == ["dscr", metric]
        evidence = next(item for item in collected if item.metric == metric)
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
        assert evidence.fact_observations
        assert evidence.fact_uses
        assert evidence.sums_additions > 0


def test_reduction_is_separate_per_axis_and_keeps_scale():
    periods = [
        _period(period_id="Y1", index=1, axis="Sheet!a"),
        _period(period_id="Y2", index=2, axis="Sheet!a"),
        _period(period_id="Y1", index=1, axis="Sheet!b"),
        _period(period_id="Y2", index=2, axis="Sheet!b"),
    ]
    facts = []
    for axis, cell in (("Sheet!a", "A"), ("Sheet!b", "B")):
        for period_id, earned, paid in (("Y1", "100", "50"), ("Y2", "90", "30")):
            for concept, value in (("cfads", earned), ("debt_service", paid)):
                fact = _fact(concept, value, period_id=period_id, axis=axis)
                fact["cell_id"] = f"{cell}!{period_id}:{concept}"
                fact["scale_factor"] = "1000"
                fact["value"] = value
                facts.append(fact)
    common = _common(periods, facts)
    collected: list = []
    traced = dscr_reductions("dscr_min", collect=collected, **common)
    plain = dscr_reductions("dscr_min", **common)
    assert traced["rows"] == plain["rows"]
    assert {row["axis_id"] for row in traced["rows"]} == {"Sheet!a", "Sheet!b"}
    evidence = next(item for item in collected if item.metric == "dscr_min")
    assert {item.cell_id for item in evidence.fact_observations} >= {"A!Y1:cfads", "B!Y1:debt_service"}
    assert any(item.scale_factor is not None for item in evidence.fact_observations)
    summaries = [item for item in evidence.period_results if item.period_id is None]
    assert {item.axis_id for item in summaries} == {"Sheet!a", "Sheet!b"}
    for summary in summaries:
        assert summary.steps
        for step in summary.steps:
            assert step.input_refs
            assert all(ref.startswith(f"period:{summary.axis_id}:") for ref in step.input_refs)


def _node_id(period) -> str:
    explicit = getattr(period, "node_id", None)
    if explicit:
        return explicit
    return f"period:{period.axis_id}:{period.period_id}"


def _available_evidence(metric: str, version: str):
    if metric == "adscr":
        periods, facts = _quarters()
        collected: list = []
        adscr(direction="lookback", collect=collected, **_common(periods, facts))
        return next(item for item in collected if item.metric == "adscr")
    if metric in {"dscr_min", "dscr_avg"}:
        periods = [_period(period_id="Y1", index=1), _period(period_id="Y2", index=2)]
        facts = [
            _fact("cfads", "100", period_id="Y1"),
            _fact("cfads", "100", period_id="Y2"),
            _fact("debt_service", "50", period_id="Y1"),
            _fact("debt_service", "25", period_id="Y2"),
        ]
        collected = []
        dscr_reductions(metric, collect=collected, **_common(periods, facts))
        return next(item for item in collected if item.metric == metric)
    periods = [_period(period_id="2025", index=0)]
    shared = {
        "periods": periods,
        "period_phase": {},
        "explicit_phases": False,
        "sign_convention": "outflow_negative",
        "marker_class": None,
        "absent": frozenset(),
    }
    if version == "dscr.pf@1":
        return calculate_dscr_pf(
            facts=[_fact("cfads", "10", period_id="2025"), _fact("debt_service", "5", period_id="2025")],
            bindings=[_bind("cfads"), _bind("debt_service")],
            evidence=True,
            **shared,
        ).evidence
    if metric == "icr":
        facts = [_fact("ebitda", "10", period_id="2025"), _fact("interest", "2", period_id="2025")]
        bindings = [_bind("ebitda"), _bind("interest")]
    elif metric == "icr_ebit":
        facts = [_fact("ebit", "10", period_id="2025"), _fact("interest", "2", period_id="2025")]
        bindings = [_bind("ebit"), _bind("interest")]
    else:
        facts = [_fact("cfads", "10", period_id="2025"), _fact("debt_service", "5", period_id="2025")]
        bindings = [_bind("cfads"), _bind("debt_service")]
    return calculate_coverage(
        metric=metric,
        facts=facts,
        bindings=bindings,
        evidence=True,
        **shared,
    ).evidence


def test_every_available_metric_has_unique_period_nodes():
    seen = set()
    for metric, version in sorted(EVIDENCE_AVAILABLE):
        evidence = _available_evidence(metric, version)
        assert evidence is not None
        assert evidence.evidence_status == "evidence_available"
        assert evidence.implementation == version
        ids = [_node_id(item) for item in evidence.period_results]
        assert len(ids) == len(set(ids))
        for period in evidence.period_results:
            for step in period.steps:
                for ref in step.input_refs:
                    if ref.startswith("period:"):
                        assert ids.count(ref) == 1
        seen.add((metric, version))
    assert seen == set(EVIDENCE_AVAILABLE)
