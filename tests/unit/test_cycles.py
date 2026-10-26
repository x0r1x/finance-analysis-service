"""Правила по циклам (`plugins/rules/cycles.py`, §6.1)."""

from __future__ import annotations

import pytest

from finance_analysis.domain.audit import AuditInput
from tests.unit.rule_inputs import PERIODS, check, golden_count, link, row

CYCLES = [{"id": "c1", "class": "unexpected", "members": 2}, {"id": "c2", "class": "iterative_ok", "members": 3}]


def test_unexpected_cycle_only_for_unexpected_class():
    [found] = check("unexpected_cycle", AuditInput(counters={"cycles": CYCLES}))
    assert found.params == {"cycle_id": "c1", "members": 2, "located": False}


def test_unexpected_cycle_locates_members_in_graph():
    key = "S|60|S!r2"
    links = (
        link("S!C60", "D60+1", key, "2024", refs=("S!D60",))
        + link("S!D60", "C60*0.5", key, "2025", refs=("S!C60",))
        + link("S!E60", "E60", key, "2026@план", refs=("S!E60",))
    )
    data = AuditInput(
        rows=[row(key)],
        periods=PERIODS,
        links=links,
        counters={
            "iterate": False,
            "cycles": [{"id": "c1", "class": "unexpected", "members": 2}, {"id": "c2", "class": "unexpected", "members": 3}],
        },
    )
    assert data.cycles == [("S!E60",), ("S!C60", "S!D60")]
    first, second = check("unexpected_cycle", data)
    assert [item.cell_id for item in first.locations] == ["S!C60", "S!D60"]
    assert first.params["located"] is True
    assert second.locations == () and second.params["located"] is False


def test_iterative_rules():
    off = AuditInput(counters={"iterate": False, "cycles": CYCLES})
    assert check("iterative_cycle_without_iterate", off)[0].params == {"cycles": 2, "iterate": False}
    assert check("iterative_calc_enabled", off) == []
    on = AuditInput(counters={"iterate": True, "cycles": CYCLES})
    assert check("iterative_calc_enabled", on)[0].severity == "medium"
    assert check("iterative_cycle_without_iterate", on) == []
    assert check("iterative_cycle_without_iterate", AuditInput(counters={"iterate": False, "cycles": []})) == []


@pytest.mark.parametrize("code", ["unexpected_cycle", "iterative_calc_enabled", "iterative_cycle_without_iterate"])
def test_golden_books_have_no_cycles(code):
    assert golden_count("packt", code) == golden_count("rvi", code) == 0
