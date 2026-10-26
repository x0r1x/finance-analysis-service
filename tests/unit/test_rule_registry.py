"""Реестр правил фазы 1 (§6.1, §8 Strategy + Registry)."""

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


def test_registry_covers_phase1_table():
    registry = load_rules()
    assert PHASE1 <= set(registry)
    for rule in registry.values():
        assert rule.severity in {"info", "low", "medium", "high", "critical"}
        assert rule.error_class in {"mechanical", "logic", "omission", "quantitative", "qualitative"}
        assert rule.requires <= {"rows", "periods", "facts", "links", "counters"}
    with pytest.raises(InvalidArgument):
        select_rules(registry, ["no_such_rule"])
    assert "links" not in requirements(select_rules(registry, ["no_master_check"]))
    assert {"links", "counters"} <= requirements(select_rules(registry, ["missing_cached_value"]))
