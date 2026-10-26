"""Правила по формулам (`plugins/rules/formulas.py`, §6.1)."""

from __future__ import annotations

from finance_analysis.domain.audit import AuditInput, fingerprint
from tests.unit.rule_inputs import PERIODS, check, fact, golden, golden_count, link, row


def test_hardcoded_formula_flags_constant_in_formula_row():
    key = "S|10|S!r2"
    data = AuditInput(
        rows=[row(key)],
        periods=PERIODS,
        facts=[fact(key, "S!C10", "2024", "5"), fact(key, "S!D10", "2025", "6"), fact(key, "S!E10", "2026@план", "7")],
        links=link("S!D10", "C10+1", key, "2025") + link("S!E10", "D10+1", key, "2026@план"),
    )
    found = check("hardcoded_formula", data)
    assert [item.locations[0].cell_id for item in found] == ["S!C10"]
    assert found[0].binding_key == "bk-S-10"
    assert found[0].fingerprint == fingerprint("hardcoded_formula", "bk-S-10", "2024", "", "0")
    assert found[0].params["formula_class"] == "same_period"
    # Без formula_class на оси строка — не строка формул.
    assert check("hardcoded_formula", AuditInput(rows=data.rows, periods=PERIODS, facts=data.facts)) == []
    # Ячейка из formula_exceptions — формула другого шаблона, не константа.
    excepted = AuditInput(rows=[row(key, formula_exceptions=["S!C10"])], periods=PERIODS, facts=data.facts, links=data.links)
    assert check("hardcoded_formula", excepted) == []


def test_hardcoded_counts_uncached_formulas():
    key = "S|41|S!r2"
    facts = [fact(key, f"S!{col}41", period, None, "empty") for col, period in (("C", "2024"), ("D", "2025"))]
    facts.append(fact(key, "S!E41", "2026@план", "5"))
    links = link("S!C41", "B41+1", key, "2024") + link("S!D41", "C41+1", key, "2025")
    [found] = check("hardcoded_formula", AuditInput(rows=[row(key)], periods=PERIODS, facts=facts, links=links))
    assert found.locations[0].cell_id == "S!E41"


def test_literal_severity_rises_when_literal_changes_along_row():
    key = "S|11|S!r2"
    facts = [fact(key, "S!C11", "2024", "1"), fact(key, "S!D11", "2025", "1")]
    same = AuditInput(rows=[row(key)], periods=PERIODS, facts=facts, links=link("S!C11", "A1*1.1", key, "2024") + link("S!D11", "B1*1.1", key, "2025"))
    varied = AuditInput(rows=[row(key)], periods=PERIODS, facts=facts, links=link("S!C11", "A1*1.1", key, "2024") + link("S!D11", "B1*1.2", key, "2025"))
    [low] = check("literal_in_formula", same)
    [medium] = check("literal_in_formula", varied)
    assert (low.severity, low.params["literals"]) == ("low", ["1.1"])
    assert (medium.severity, medium.params["literals"]) == ("medium", ["1.1", "1.2"])
    assert low.fingerprint == medium.fingerprint


def test_formula_inconsistent_uses_builder_exceptions():
    key = "S|12|S!r2"
    data = AuditInput(
        rows=[row(key, formula_exceptions=["S!D12"], formula_exceptions_truncated=True)],
        periods=PERIODS,
        facts=[fact(key, "S!C12", "2024", "1"), fact(key, "S!D12", "2025", "2")],
    )
    [found] = check("formula_inconsistent_in_row", data)
    assert [item.cell_id for item in found.locations] == ["S!D12"]
    assert found.truncated is True


def test_missing_cached_value_counter_only():
    # Счётчик R1 есть, а ячеек без кэша в проекции нет — одна находка книги с truncated.
    [missing] = check("missing_cached_value", AuditInput(rows=[row("S|1|S!r2")], periods=PERIODS, counters={"missing_cached_values": 3}))
    assert missing.params == {"count": 3, "located": 0, "unlocated": 3} and missing.truncated
    assert check("missing_cached_value", AuditInput()) == []


def test_missing_cached_value_keeps_counter_remainder():
    key = "S|40|S!r2"
    data = AuditInput(
        rows=[row(key)],
        periods=PERIODS,
        facts=[fact(key, "S!C40", "2024", None, "empty")],
        links=link("S!C40", "A1+B1", key, "2024"),
        counters={"missing_cached_values": 20},
    )
    found = check("missing_cached_value", data)
    assert [item.locations[0].cell_id if item.locations else None for item in found] == ["S!C40", None]
    assert found[1].params == {"count": 20, "located": 1, "unlocated": 19}
    assert found[1].truncated
    data.counters["missing_cached_values"] = 1
    assert len(check("missing_cached_value", data)) == 1


def test_text_rules_group_by_row_and_axis():
    key = "S|30|S!r2"
    data = AuditInput(
        rows=[row(key)],
        periods=PERIODS,
        facts=[fact(key, "S!C30", "2024", "1"), fact(key, "S!D30", "2025", "1")],
        links=link("S!C30", "OFFSET(A1,0,1)+NPV(r,B1:B3)+IF(a,IF(b,1,2),3)", key, "2024")
        + link("S!D30", "INDIRECT(\"A1\")", key, "2025")
        + link("X!Z9", "NPV(r,A1:A3)", None, None),
    )
    [offset] = check("offset_indirect_used", data)
    assert offset.params == {"functions": ["INDIRECT", "OFFSET"], "cells": 2}
    npv = check("excel_npv_used", data)
    # Ячейка вне строк книги — своя находка с отпечатком по ячейке.
    assert len(npv) == 2 and {item.binding_key for item in npv} == {"bk-S-30", None}
    assert check("nested_if", data)[0].params["depth"] == 2
    long = AuditInput(rows=[row(key)], periods=PERIODS, facts=data.facts, links=link("S!C30", "+".join(["A1"] * 13), key, "2024"))
    assert check("long_formula", long)[0].params["operands"] == 13


def test_golden_missing_cached_value():
    # В RVI 20 формул без кэша — ровно как в счётчике R1, остатка нет.
    assert golden_count("rvi", "missing_cached_value") == golden("rvi").counters["missing_cached_values"] == 20
    assert golden_count("packt", "missing_cached_value") == 0


def test_golden_formula_inconsistent_in_row():
    assert golden_count("rvi", "formula_inconsistent_in_row") == 13


def test_golden_offset_indirect_used():
    assert golden_count("rvi", "offset_indirect_used") > 0
    assert golden_count("packt", "offset_indirect_used") == 0
