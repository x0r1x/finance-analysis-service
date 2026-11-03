"""К3: неуверенный лидер с именем corporate не считается попаданием."""

from __future__ import annotations

import pytest

from finance_analysis.application.model_types import load_model_types
from finance_analysis.domain.model_type import infer
from tests.k3_expect import assert_confident_primary

_STATEMENTS = frozenset({"ОПиУ", "Баланс", "ДДС"})


def test_an_unresolved_corporate_leader_is_not_a_pass():
    got = infer(
        load_model_types(),
        bound=frozenset({"cfads", "debt_service"}),
        sheets=_STATEMENTS,
        accept=0.6,
        gap=0.15,
    )
    assert got.primary == "corporate"
    assert got.confident is False
    assert got.labels == ()
    with pytest.raises(AssertionError):
        assert_confident_primary(got, "corporate")


def test_three_statements_pass_only_as_confident_corporate():
    got = infer(load_model_types(), bound=frozenset(), sheets=_STATEMENTS, accept=0.6, gap=0.15)
    assert_confident_primary(got, "corporate")
    with pytest.raises(AssertionError):
        assert_confident_primary(got, "project_finance")
