"""Маппинг finding_kind: default + override; по одному правилу на каждый kind."""

from __future__ import annotations

from finance_analysis.domain.audit import AuditInput, promote_needs_findings
from finance_analysis.plugins.rules.checks import NO_MASTER_CHECK
from finance_analysis.plugins.rules.formulas import (
    HARDCODED_FORMULA,
    LITERAL_IN_FORMULA,
    MISSING_CACHED_VALUE,
)
from finance_analysis.plugins.rules.ratios import ICR_REFERENCE
from tests.unit.rule_inputs import PERIODS, check, fact, link, row


def test_error_kind_from_logic_rule():
    key = "S|10|S!r2"
    data = AuditInput(
        rows=[row(key)],
        periods=PERIODS,
        facts=[fact(key, "S!C10", "2024", "5"), fact(key, "S!D10", "2025", "6")],
        links=link("S!D10", "C10+1", key, "2025"),
    )
    [found] = check("hardcoded_formula", data)
    assert found.finding_kind == "error"
    assert found.error_class == HARDCODED_FORMULA.error_class
    assert found.severity == HARDCODED_FORMULA.severity


def test_warning_kind_from_qualitative_rule():
    key = "S|11|S!r2"
    data = AuditInput(
        rows=[row(key)],
        periods=PERIODS,
        facts=[fact(key, "S!C11", "2024", "1")],
        links=link("S!C11", "A1*1.1", key, "2024"),
    )
    [found] = check("literal_in_formula", data)
    assert found.finding_kind == "warning"
    assert found.error_class == LITERAL_IN_FORMULA.error_class


def test_methodology_kind_from_practice_override():
    [found] = check("no_master_check", AuditInput(rows=[row("S|1|S!r2")]))
    assert found.finding_kind == "methodology"
    assert found.severity == NO_MASTER_CHECK.severity
    assert found.error_class == NO_MASTER_CHECK.error_class


def test_insufficient_data_kind_from_omission_rule():
    [found] = check(
        "missing_cached_value",
        AuditInput(rows=[row("S|1|S!r2")], periods=PERIODS, counters={"missing_cached_values": 2}),
    )
    assert found.finding_kind == "insufficient_data"
    assert found.error_class == MISSING_CACHED_VALUE.error_class


def test_ambiguity_kind_from_promote_and_icr_default():
    promoted = promote_needs_findings([{"kind": "concept", "reason": "ambiguous", "subject": "cfads"}])
    assert promoted[0].finding_kind == "ambiguity"
    assert promoted[0].code == "binding_ambiguity"
    # Правило само по умолчанию не ambiguity (quantitative/low → warning);
    # call-site finding_kind="ambiguity" в ratios.py ортогонален severity.
    assert ICR_REFERENCE.resolved_kind() == "warning"
    assert ICR_REFERENCE.severity == "low"
