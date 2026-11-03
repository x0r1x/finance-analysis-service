"""DSCR и ICR: частное Decimal, без второй формулы и без нуля-заглушки."""

from decimal import Decimal

from finance_analysis.domain.audit import AuditInput
from finance_analysis.domain.metrics import coverage_ratio
from finance_analysis.domain.rematch import pair_status
from finance_analysis.plugins.rules.coverage import (
    PERIOD_GRAIN_MISMATCH,
    SCULPTING_DEVIATION,
    dscr_rows,
)
from finance_analysis.plugins.rules.ratios import (
    MARKER_MIX,
    RATIO_MISMATCH,
    UNMAPPED_IN_METRIC_CHAIN,
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


def _fact(row_key: str, value: str, period: str = "p") -> dict:
    return {
        "row_key": row_key,
        "axis_id": "Sheet!r1",
        "period_id": period,
        "normalized_value": value,
        "value_status": "cached",
    }


def _period(period: str = "p", marker: str | None = None) -> dict:
    return {"axis_id": "Sheet!r1", "period_id": period, "period_key_base": period, "marker_class": marker}


def test_negative_cfads_stays_negative_and_missing_concept_has_no_number():
    negative = coverage_ratio(
        metric="dscr",
        facts=[_fact("c", "-8"), _fact("d", "4")],
        bindings=[_binding("cfads", "c"), _binding("debt_service", "d")],
        periods=[_period()],
        period_phase={},
        explicit_phases=False,
    )
    assert negative["rows"][0]["status"] == "computed"
    assert negative["rows"][0]["value"] == Decimal("-2.0000000000")
    missing = coverage_ratio(
        metric="dscr",
        facts=[_fact("c", "8")],
        bindings=[_binding("cfads", "c")],
        periods=[_period()],
        period_phase={},
        explicit_phases=False,
    )
    assert missing["rows"] == []
    assert missing["needs_input"] == [{"kind": "concept", "reason": "concept_unknown", "subject": "debt_service"}]


def test_zero_debt_is_outside_the_window_and_absent_concept_is_named():
    zero = coverage_ratio(
        metric="dscr",
        facts=[_fact("c", "8"), _fact("d", "0")],
        bindings=[_binding("cfads", "c"), _binding("debt_service", "d")],
        periods=[_period()],
        period_phase={},
        explicit_phases=False,
    )
    assert zero["rows"] == []
    absent = coverage_ratio(
        metric="dscr",
        facts=[_fact("c", "8")],
        bindings=[
            _binding("cfads", "c"),
            _binding("debt_service", "d", is_primary=False, status="unknown", source="confirmed"),
        ],
        periods=[_period()],
        period_phase={},
        explicit_phases=False,
    )
    assert absent["rows"] == []
    assert absent["needs_input"][0]["reason"] == "absent_in_book"


def test_ambiguous_pair_and_icr_numerator():
    ambiguous = coverage_ratio(
        metric="dscr",
        facts=[],
        bindings=[
            _binding("debt_service", "d1", status="ambiguous", is_primary=False),
            _binding("debt_service", "d2", status="ambiguous", is_primary=False),
            _binding("cfads", "c"),
        ],
        periods=[_period()],
        period_phase={},
        explicit_phases=False,
    )
    assert ambiguous["needs_input"][0]["reason"] == "ambiguous"
    icr = coverage_ratio(
        metric="icr",
        facts=[_fact("e", "10"), _fact("b", "6"), _fact("i", "0")],
        bindings=[_binding("ebitda", "e"), _binding("ebit", "b"), _binding("interest", "i")],
        periods=[_period()],
        period_phase={},
        explicit_phases=False,
    )
    assert icr["warnings"][0]["code"] == "icr_numerator"
    assert icr["rows"][0]["status"] == "missing_input"
    assert icr["rows"][0]["value"] is None


def test_ratio_mismatch_and_marker_mix_and_pair_status():
    bindings = [_binding("cfads", "c"), _binding("debt_service", "d"), _binding("dscr", "m")]
    far = AuditInput(
        rows=[{"row_key": "m", "binding_key": "m"}],
        periods=[_period()],
        facts=[_fact("c", "10"), _fact("d", "4"), _fact("m", "9")],
        bindings=bindings,
    )
    assert [item.code for item in RATIO_MISMATCH.check(far)] == ["ratio_mismatch"]
    close = AuditInput(
        rows=[{"row_key": "m", "binding_key": "m"}],
        periods=[_period()],
        facts=[_fact("c", "10"), _fact("d", "4"), _fact("m", "2.5")],
        bindings=bindings,
    )
    assert RATIO_MISMATCH.check(close) == []
    assert RATIO_MISMATCH.check(AuditInput()) == []
    assert MARKER_MIX.check(
        AuditInput(
            bindings=[{"is_primary": True}],
            periods=[_period("p", "actual"), _period("q", "plan")],
        )
    ) == []
    mixed = AuditInput(
        rows=[{"row_key": "s", "binding_key": "s"}],
        periods=[_period("p", "actual"), _period("q", "plan")],
        facts=[
            {**_fact("a", "1", "p"), "cell_id": "A"},
            {**_fact("b", "1", "q"), "cell_id": "B"},
        ],
        links=[{"row_key": "s", "ref_cell": "A"}, {"row_key": "s", "ref_cell": "B"}],
    )
    [mix] = MARKER_MIX.check(mixed)
    assert mix.params["markers"] == ["actual", "plan"]
    assert pair_status([("keep", 4.0)]) == ("keep", False)
    assert pair_status([("a", 4.0), ("b", 3.5)]) == (None, True)
    assert pair_status([("low", 2.0)]) == (None, True)


def test_dscr_findings_stay_quiet_when_only_icr_applies():
    """Привязанные cfads, debt_service и dscr не дают находок DSCR, если применима только ICR."""

    from datetime import date

    bindings = [_binding("cfads", "c"), _binding("debt_service", "d"), _binding("dscr", "m")]
    periods = []
    facts = []
    for name in ("p", "q", "r"):
        periods.append(
            {
                "axis_id": "Sheet!r1",
                "period_id": name,
                "period_key_base": name,
                "grain": "quarter",
                "period_start": date(2024, 1, 1),
                "period_end": date(2024, 1, 15),
            }
        )
        facts.extend([_fact("c", "10", name), _fact("d", "4", name), _fact("m", "9", name)])
    quiet = AuditInput(periods=periods, facts=facts, bindings=bindings, applicable_metrics=frozenset({"icr"}))
    assert dscr_rows(quiet) == []
    assert RATIO_MISMATCH.check(quiet) == []
    assert SCULPTING_DEVIATION.check(quiet) == []
    assert PERIOD_GRAIN_MISMATCH.check(quiet) == []
    live = AuditInput(periods=periods, facts=facts, bindings=bindings, applicable_metrics=frozenset({"dscr"}))
    assert [item.code for item in RATIO_MISMATCH.check(live)] == ["ratio_mismatch", "ratio_mismatch", "ratio_mismatch"]
    assert len(PERIOD_GRAIN_MISMATCH.check(live)) == 3


def test_dscr_cache_must_match_the_model_row():
    bindings = [_binding("cfads", "c"), _binding("debt_service", "d"), _binding("dscr", "m")]
    rows = [{"row_key": "m", "binding_key": "m"}]
    same = AuditInput(
        rows=rows,
        periods=[_period()],
        facts=[_fact("c", "10"), _fact("d", "4"), _fact("m", "2.5")],
        bindings=bindings,
    )
    assert RATIO_MISMATCH.check(same) == []
    drifted = AuditInput(
        rows=rows,
        periods=[_period()],
        facts=[_fact("c", "10"), _fact("d", "4"), _fact("m", "9")],
        bindings=bindings,
    )
    assert [item.params["model"] for item in RATIO_MISMATCH.check(drifted)] == ["9"]


def _unknown(row_key: str) -> dict:
    return {"row_key": row_key, "binding_key": row_key, "is_primary": False, "status": "unknown"}


def test_unmapped_walks_up_to_dscr_and_icr():
    deep = AuditInput(
        rows=[{"row_key": key, "binding_key": key} for key in ("u", "mid", "d", "m")],
        periods=[_period()],
        bindings=[
            _binding("dscr", "m"),
            _binding("debt_service", "d"),
            _unknown("u"),
            _binding("other", "mid"),
        ],
        facts=[
            {"cell_id": "U", "row_key": "u", "axis_id": "Sheet!r1", "period_id": "p"},
            {"cell_id": "M", "row_key": "mid", "axis_id": "Sheet!r1", "period_id": "p"},
            {"cell_id": "D", "row_key": "d", "axis_id": "Sheet!r1", "period_id": "p"},
        ],
        links=[
            {"row_key": "mid", "ref_cell": "U"},
            {"row_key": "d", "ref_cell": "M"},
            {"row_key": "m", "ref_cell": "D"},
        ],
    )
    [high] = UNMAPPED_IN_METRIC_CHAIN.check(deep)
    assert high.severity == "high"
    near = AuditInput(
        rows=[{"row_key": "u", "binding_key": "u"}, {"row_key": "m", "binding_key": "m"}],
        periods=[_period()],
        bindings=[_binding("dscr", "m"), _unknown("u")],
        facts=[{"cell_id": "U", "row_key": "u", "axis_id": "Sheet!r1", "period_id": "p"}],
        links=[{"row_key": "m", "ref_cell": "U"}],
    )
    [medium] = UNMAPPED_IN_METRIC_CHAIN.check(near)
    assert medium.severity == "medium"
    interest = AuditInput(
        rows=[{"row_key": key, "binding_key": key} for key in ("u", "i", "r")],
        periods=[_period()],
        bindings=[_binding("icr", "r"), _binding("interest", "i"), _unknown("u")],
        facts=[
            {"cell_id": "U", "row_key": "u", "axis_id": "Sheet!r1", "period_id": "p"},
            {"cell_id": "I", "row_key": "i", "axis_id": "Sheet!r1", "period_id": "p"},
        ],
        links=[{"row_key": "i", "ref_cell": "U"}, {"row_key": "r", "ref_cell": "I"}],
    )
    assert UNMAPPED_IN_METRIC_CHAIN.check(interest)[0].severity == "high"


def test_marked_period_stays_until_the_profile_picks_one():
    bindings = [_binding("cfads", "c"), _binding("debt_service", "d")]
    period = {**_period("2024@факт"), "period_key_base": "2024", "marker_class": "actual"}
    facts = [
        {**_fact("c", "10"), "period_id": "2024@факт"},
        {**_fact("d", "4"), "period_id": "2024@факт"},
    ]
    kept = coverage_ratio(
        metric="dscr",
        facts=facts,
        bindings=bindings,
        periods=[period],
        period_phase={("Sheet!r1", "2024@факт"): "operation"},
        explicit_phases=True,
    )
    assert kept["rows"][0]["value"] == Decimal("2.5000000000")
    dropped = coverage_ratio(
        metric="dscr",
        facts=facts,
        bindings=bindings,
        periods=[period],
        period_phase={("Sheet!r1", "2024@факт"): "operation"},
        explicit_phases=True,
        marker_class="plan",
    )
    assert dropped["rows"] == []


def test_construction_phase_is_not_a_dscr_mismatch():
    bindings = [_binding("cfads", "c"), _binding("debt_service", "d"), _binding("dscr", "m")]
    built = {**_period("q"), "phase": "construction"}
    data = AuditInput(
        rows=[{"row_key": "m", "binding_key": "m"}],
        periods=[built],
        facts=[_fact("c", "10", "q"), _fact("d", "4", "q"), _fact("m", "9", "q")],
        bindings=bindings,
    )
    assert RATIO_MISMATCH.check(data) == []


def test_two_formulas_on_one_row_are_not_one_mix():
    data = AuditInput(
        rows=[{"row_key": "s", "binding_key": "s"}],
        periods=[_period("p", "actual"), _period("q", "plan")],
        facts=[
            {**_fact("a", "1", "p"), "cell_id": "A"},
            {**_fact("b", "1", "q"), "cell_id": "B"},
        ],
        links=[
            {"row_key": "s", "cell": "S!C1", "ref_cell": "A"},
            {"row_key": "s", "cell": "S!D1", "ref_cell": "B"},
        ],
    )
    assert MARKER_MIX.check(data) == []
