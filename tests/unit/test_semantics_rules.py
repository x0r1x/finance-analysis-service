"""Знак, исключение и маркер. Фазу периода эти правила не ставят."""

from finance_analysis.domain.periods import marker_class
from finance_analysis.domain.semantics import exclusion


def test_check_row_is_excluded_and_plan_marker_is_plan():
    excluded, reason = exclusion({"kind": "flag", "hidden": False, "check_row": True}, empty_series=False)
    assert excluded is True
    assert reason == "check_row"
    assert marker_class("план") == "plan"
    assert marker_class("свой маркер") == "other"


def test_flag_kind_does_not_invent_a_phase():
    excluded, reason = exclusion({"kind": "flag", "hidden": False, "check_row": False}, empty_series=False)
    assert (excluded, reason) == (True, "flag")
    assert marker_class(None) is None


def test_collapsed_outline_does_not_exclude_a_fact_with_values():
    fact = {"kind": "fact", "hidden": True}
    assert exclusion(fact, empty_series=False) == (True, "hidden")
    collapsed = {**fact, "hidden_by_outline": True}
    assert exclusion(collapsed, empty_series=False) == (False, None)
    assert exclusion(collapsed, empty_series=True) == (True, "empty_series")
    assert exclusion({**collapsed, "check_row": True}, empty_series=False) == (True, "check_row")
