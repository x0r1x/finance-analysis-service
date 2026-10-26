"""Правила по проверочным строкам (`plugins/rules/checks.py`, §6.1)."""

from __future__ import annotations

from finance_analysis.domain.audit import AuditInput
from tests.unit.rule_inputs import PERIODS, check, fact, golden_count, row


def test_check_failure_is_nonzero_on_check_row():
    flag = "S|20|S!r2"
    comparison = "S|21|S!r2"
    data = AuditInput(
        rows=[
            row(flag, check_row=True, formula="=IF(R[-1]C[0]<>0,1,0)"),
            row(comparison, check_row=True, formula="=R[-9]C[0]-R[-3]C[0]<0.01"),
            row("S|22|S!r2", check_row=True, has_formula=False, formula=None),
        ],
        periods=PERIODS,
        facts=[
            fact(flag, "S!C20", "2024", "0", "zero_explicit"),
            fact(flag, "S!D20", "2025", "1"),
            fact(comparison, "S!C21", "2024", "1"),
            fact(comparison, "S!D21", "2025", "0", "zero_explicit"),
            fact("S|22|S!r2", "S!C22", "2024", "1"),
        ],
    )
    found = {item.locations[0].cell_id: item for item in check("check_failure", data)}
    # §6.1: сбой — ненулевое значение, как бы проверка ни была записана.
    assert set(found) == {"S!D20", "S!C21"}
    assert found["S!D20"].severity == "critical"
    assert found["S!C21"].params == {"nonzero_cells": 1, "label": "row 21"}


def test_no_master_check():
    assert check("no_master_check", AuditInput(rows=[row("S|1|S!r2")]))[0].severity == "info"
    assert check("no_master_check", AuditInput(rows=[row("S|1|S!r2", check_row=True)])) == []


def test_golden_check_failure():
    # Проверки Packt записаны сравнением (`=A-B<0.01`, TRUE = 1): по §6.1 это ненулевое значение.
    assert golden_count("packt", "check_failure") == 2
    assert golden_count("rvi", "check_failure") == 0


def test_golden_no_master_check():
    assert golden_count("packt", "no_master_check") == golden_count("rvi", "no_master_check") == 0
