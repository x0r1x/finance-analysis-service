"""Реестр правил фаз 1–3 (§6.1, §8 Strategy + Registry)."""

from __future__ import annotations

import pytest

from finance_analysis.application.rule_engine import (
    load_rules,
    requirements,
    select_rules,
)
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
    with pytest.raises(InvalidArgument):
        select_rules(registry, ["no_such_rule"])
    assert "links" not in requirements(select_rules(registry, ["no_master_check"]))
    assert {"links", "counters"} <= requirements(select_rules(registry, ["missing_cached_value"]))
