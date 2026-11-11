"""Реестр правил фаз 1–3 (§6.1, §8 Strategy + Registry)."""

from __future__ import annotations

import pytest

from finance_analysis.application.rule_engine import (
    load_rules,
    requirements,
    select_rules,
)
from finance_analysis.domain.audit import FINDING_KINDS, default_finding_kind
from finance_analysis.domain.errors import InvalidArgument

# Правила фазы 1 по таблице §6.1.
PHASE1 = {
    "hardcoded_formula",
    "literal_in_formula",
    "formula_inconsistent_in_row",
    "dangling_ref",
    "unresolved_ref",
    "external_ref",
    "unexpected_cycle",
    "iterative_calc_enabled",
    "iterative_cycle_without_iterate",
    "check_failure",
    "no_master_check",
    "missing_cached_value",
    "offset_indirect_used",
    "excel_npv_used",
    "nested_if",
    "long_formula",
}
# Правила фазы 2 по таблице §6.1 и правила фазы 3, которые поставляет фаза 3 (§12).
PHASE2 = {
    "daisy_chain",
    "partial_range_reference",
    "row_total_in_logic",
    "hidden_used_in_calc",
    "duplicate_label",
    "missing_unit",
    "hardcoded_value_in_formula_row",
    "dimension_mismatch",
    "pricing_basis_mismatch",
    "scale_mismatch",
    "unit_mismatch",
    "period_gap",
    "rollforward_break",
    "sign_anomaly",
    "sign_convention_mixed",
    "cross_sheet_inconsistency",
    "formula_class_mismatch",
}
PHASE3 = {"sculpting_deviation", "period_grain_mismatch", "missing_total_row"}


def test_registry_covers_phase1_table():
    registry = load_rules()
    assert PHASE1 | PHASE2 | PHASE3 <= set(registry)
    assert all(registry[code].phase == 2 for code in PHASE2)
    assert all(registry[code].phase == 3 for code in PHASE3)
    for rule in registry.values():
        assert rule.severity in {"info", "low", "medium", "high", "critical"}
        assert rule.error_class in {"mechanical", "logic", "omission", "quantitative", "qualitative"}
        assert rule.requires <= {"rows", "periods", "facts", "links", "counters", "semantics"}
        kind = rule.resolved_kind()
        assert kind in FINDING_KINDS
        if rule.finding_kind is None:
            assert kind == default_finding_kind(rule.error_class, rule.severity)
        else:
            assert kind == rule.finding_kind
        described = rule.describe()
        assert described["finding_kind"] == kind
        assert described["severity"] == rule.severity
        assert described["error_class"] == rule.error_class
    # Явные override: methodology / (ambiguity задаётся на call-site).
    assert registry["no_master_check"].resolved_kind() == "methodology"
    assert registry["period_grain_mismatch"].resolved_kind() == "methodology"
    assert registry["missing_total_row"].resolved_kind() == "insufficient_data"
    assert registry["hardcoded_formula"].resolved_kind() == "error"
    assert registry["literal_in_formula"].resolved_kind() == "warning"
    # Omission invariant: default insufficient_data unless Rule.finding_kind override.
    for rule in registry.values():
        if rule.error_class != "omission":
            continue
        if rule.finding_kind is None:
            assert rule.resolved_kind() == "insufficient_data", rule.code
        else:
            assert rule.finding_kind in FINDING_KINDS, rule.code
    with pytest.raises(InvalidArgument):
        select_rules(registry, ["no_such_rule"])
    assert "links" not in requirements(select_rules(registry, ["no_master_check"]))
    assert {"links", "counters"} <= requirements(select_rules(registry, ["missing_cached_value"]))
