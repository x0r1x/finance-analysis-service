"""§5.4 и окно test_periods без толкования флагов."""

from __future__ import annotations

from decimal import Decimal

from finance_analysis.domain.coverage import (
    COVERAGE_TEST_PERIODS,
    TEST_PERIODS,
    is_coverage_test_period,
)
from finance_analysis.domain.operational_year import resolve_operational_year
from finance_analysis.domain.phases import check_phase_order, check_phase_value


def _period(axis: str, period_id: str, index: int, *, timeline: str | None = None, kind: str = "time") -> dict:
    return {
        "axis_id": axis,
        "timeline_id": timeline or axis,
        "axis_kind": kind,
        "period_id": period_id,
        "period_key_base": period_id,
        "period_index": index,
        "calendar_year": None,
    }


def test_default_coverage_window_is_nonzero_debt_service():
    assert TEST_PERIODS == "nonzero_debt_service"
    assert COVERAGE_TEST_PERIODS == {
        "dscr": "nonzero_debt_service",
        "llcr": "nonzero_debt_service",
        "adscr": "nonzero_debt_service",
    }
    assert is_coverage_test_period(debt_service_nonzero=False, phase=None, explicit_phases=False) is False
    assert is_coverage_test_period(debt_service_nonzero=True, phase=None, explicit_phases=False) is True
    assert (
        is_coverage_test_period(debt_service_nonzero=True, phase="construction", explicit_phases=True)
        is False
    )
    assert is_coverage_test_period(debt_service_nonzero=True, phase="operation", explicit_phases=True) is True


def test_phase_dictionary_has_no_flag_synonyms():
    assert check_phase_value("operation").accepted
    assert check_phase_value("construction").accepted
    assert check_phase_value("эксплуатация").accepted is False
    assert check_phase_value("TBA").accepted is False
    order = check_phase_order([(1, "operation"), (2, "construction")])
    assert order.accepted is False
    assert check_phase_order([(1, "construction"), (4, "operation")]).accepted


def test_unbound_debt_service_needs_input_and_ignores_flags():
    periods = [
        _period("TBA!r2", "Y1", 1),
        _period("TBA!r2", "Y5", 5),
        _period("Debt!r3", "Y5", 5, timeline="TBA!r2"),
    ]
    resolved = resolve_operational_year(periods, [], [], [])
    assert resolved["periods"] == []
    assert resolved["needs_input"] == [
        {"kind": "concept", "reason": "concept_unknown", "subject": "debt_service"}
    ]
    assert all(item["kind"] != "phase" for item in resolved["needs_input"])


def test_nonzero_debt_service_picks_first_timeline_period():
    periods = [
        _period("TBA!r2", "Y4", 4),
        _period("TBA!r2", "Y5", 5),
        _period("Debt!r3", "Y4", 4, timeline="TBA!r2"),
        _period("Debt!r3", "Y5", 5, timeline="TBA!r2"),
    ]
    bindings = [
        {
            "row_key": "debt",
            "effective_concept": "debt_service",
            "is_primary": True,
            "status": "bound",
        }
    ]
    facts = [
        {"row_key": "debt", "axis_id": "Debt!r3", "period_id": "Y4", "value_dec": Decimal(0)},
        {"row_key": "debt", "axis_id": "Debt!r3", "period_id": "Y5", "value_dec": Decimal(-1)},
    ]
    resolved = resolve_operational_year(periods, [], bindings, facts)
    assert resolved["basis"] == "nonzero_debt_service"
    assert resolved["needs_input"] == []
    assert resolved["periods"][0]["axis_id"] == "TBA!r2"
    assert resolved["periods"][0]["period_id"] == "Y5"
    assert resolved["periods"][0]["reason"] == "no_calendar_anchor"


def test_phase_set_wins_over_debt_service():
    periods = [_period("TBA!r2", "Y1", 1), _period("TBA!r2", "Y5", 5)]
    semantics = [
        {"axis_id": "TBA!r2", "period_id": "Y1", "phase": "construction"},
        {"axis_id": "TBA!r2", "period_id": "Y5", "phase": "operation"},
    ]
    events = [
        {"type": "phase.set", "target": "TBA!r2+Y1", "value": "construction", "seq": 1},
        {"type": "phase.set", "target": "TBA!r2+Y5", "value": "operation", "seq": 2},
    ]
    resolved = resolve_operational_year(periods, semantics, [], [], events=events)
    assert resolved["basis"] == "phase_decision"
    assert resolved["periods"][0]["period_id"] == "Y5"
    assert resolved["needs_input"] == []
