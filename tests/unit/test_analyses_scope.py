"""Срез `scope` аудита по периодам и маркерам (§3.2)."""

from __future__ import annotations

import pytest

from finance_analysis.application.analyses import _in_scope, _scope
from finance_analysis.application.rule_engine import load_rules, select_rules
from finance_analysis.domain.audit import AuditInput
from finance_analysis.domain.errors import InvalidArgument
from tests.unit.rule_inputs import PERIODS, fact, row


def test_scope_periods_and_markers():
    key = "S|70|S!r2"
    periods = [dict(item, period_index=index, marker_class="plan" if item["period_marker"] else None) for index, item in enumerate(PERIODS)]
    data = AuditInput(
        rows=[row(key)],
        periods=periods,
        facts=[fact(key, "S!C70", "2024", "1"), fact(key, "S!E70", "2026@план", "1")],
    )
    rule = select_rules(load_rules(), ["hardcoded_formula"])[0]
    early = rule.finding(data, locations=[data.placed("S!C70")], row_key=key, axis_id="S!r2", period_id="2024")
    planned = rule.finding(data, locations=[data.placed("S!E70")], row_key=key, axis_id="S!r2", period_id="2026@план")
    book = rule.finding(data)

    def kept(scope: dict) -> list:
        parsed = _scope({"scope": scope})
        return [item for item in (early, planned, book) if _in_scope(item, parsed, data, set())]

    assert kept({"period_from": "2025"}) == [planned, book]
    assert kept({"period_to": "2025"}) == [early, book]
    # Маркер совпадает и по тексту, и по классу.
    assert kept({"markers": ["план"]}) == kept({"markers": ["plan"]}) == [planned, book]
    assert kept({"period_from": "1999"}) == [book]
    with pytest.raises(InvalidArgument):
        _scope({"scope": {"markers": "план"}})
