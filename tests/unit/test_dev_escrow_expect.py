"""Схема без эскроу не становится development_escrow. Файлы чужой модели не читаются."""

from __future__ import annotations

import pytest

from finance_analysis.application.model_types import load_model_types
from finance_analysis.domain.model_type import infer
from tests.dev_escrow_expect import assert_variant

_SHEETS = frozenset({"DCF", "VAT estimates", "unit costs", "Land valuation"})


def _infer(bound: frozenset[str]):
    return infer(load_model_types(), bound=bound, sheets=_SHEETS, accept=0.6, gap=0.15)


def test_escrowed_funds_rate_alone_is_development_escrow():
    got = _infer(frozenset({"escrowed_funds_rate"}))
    assert_variant(
        got,
        {"scheme": "escrow", "expect": {"kind": "type", "primary": "development_escrow"}},
        accept=0.6,
    )
    assert got.scores["corporate"] == 0.0
    assert got.scores["project_finance"] == 0.0


def test_balance_alone_still_scores_one():
    got = _infer(frozenset({"escrow_balance"}))
    assert got.scores["development_escrow"] == 1.0
    assert got.primary == "development_escrow"


def test_ddy_without_an_escrow_marker_is_a_question():
    got = _infer(frozenset())
    assert_variant(got, {"scheme": "ddy", "expect": {"kind": "question", "reason": "unknown"}}, accept=0.6)
    assert got.scores["corporate"] == 0.0
    assert got.scores["project_finance"] == 0.0


def test_ddy_yaml_cannot_ask_for_the_escrow_type():
    got = _infer(frozenset())
    with pytest.raises(AssertionError):
        assert_variant(
            got,
            {"scheme": "ddy", "expect": {"kind": "type", "primary": "development_escrow"}},
            accept=0.6,
        )


def test_escrow_candidate_is_enough_when_the_type_only_leads():
    got = _infer(frozenset({"escrowed_funds_rate", "cfads", "debt_service"}))
    assert got.confident is True and got.primary == "development_escrow"
    assert_variant(got, {"scheme": "escrow", "expect": {"kind": "candidate"}}, accept=0.6)
