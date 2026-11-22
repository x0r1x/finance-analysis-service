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


def test_pattern_break_on_unbound_row_and_opening_is_quiet():
    key = "S|12|S!r2"
    facts = [fact(key, "S!C12", "2024", "1"), fact(key, "S!D12", "2025", "1"), fact(key, "S!E12", "2026@план", "1")]
    broken = AuditInput(
        rows=[row(key)],
        periods=PERIODS,
        facts=facts,
        links=link("S!C12", "C11+1", key, "2024") + link("S!D12", "D11+2", key, "2025") + link("S!E12", "E11+3", key, "2026@план"),
    )
    [found] = check("formula_pattern_break", broken)
    assert found.params["patterns"][0]["id"] == "A"
    assert {item.cell_id for item in found.locations} == {"S!C12", "S!D12", "S!E12"}
    assert check("formula_segment", broken) == []
    opening = AuditInput(
        rows=[row(key)],
        periods=PERIODS,
        facts=facts,
        links=link("S!C12", "B12", key, "2024") + link("S!D12", "D11+1", key, "2025") + link("S!E12", "E11+1", key, "2026@план"),
    )
    assert check("formula_pattern_break", opening) == []
    assert check("formula_segment", opening) == []


def test_two_axes_of_one_row_are_not_a_false_break():
    # Год и квартал — две оси одного ряда. Смешение даёт ложный segment.
    key = "S|10|S!r2"
    year, quarter = "S!r8", "S!r2"
    facts = [
        fact(key, "S!C10", "2024", "1", axis=quarter),
        fact(key, "S!D10", "2025", "1", axis=quarter),
        fact(key, "S!E10", "2026@план", "1", axis=quarter),
        fact(key, "S!U10", "2024", "1", axis=year),
        fact(key, "S!V10", "2025", "1", axis=year),
        fact(key, "S!W10", "2026@план", "1", axis=year),
    ]
    data = AuditInput(
        rows=[row(key)],
        periods=[*PERIODS, {"axis_id": year, "period_id": "2024", "period_key_base": "2024", "period_marker": None}],
        facts=facts,
        links=link("S!C10", "SUM(C10:F10)", key, "2024")
        + link("S!D10", "SUM(D10:G10)", key, "2025")
        + link("S!E10", "SUM(E10:H10)", key, "2026@план")
        + link("S!U10", "C10+D10", key, "2024")
        + link("S!V10", "D10+E10", key, "2025")
        + link("S!W10", "E10+F10", key, "2026@план"),
    )
    from finance_analysis.domain.formula_shape import row_shapes

    shapes = row_shapes(data)
    assert len(shapes) == 2
    assert {shape.axis_id: shape.kind for shape in shapes} == {year: "uniform", quarter: "uniform"}
    assert check("formula_pattern_break", data) == []
    assert check("formula_segment", data) == []


def test_break_stays_on_its_axis():
    key = "S|10|S!r2"
    year, quarter = "S!r8", "S!r2"
    facts = [
        fact(key, "S!C10", "2024", "1", axis=quarter),
        fact(key, "S!D10", "2025", "1", axis=quarter),
        fact(key, "S!E10", "2026@план", "1", axis=quarter),
        fact(key, "S!U10", "2024", "1", axis=year),
        fact(key, "S!V10", "2025", "1", axis=year),
        fact(key, "S!W10", "2026@план", "1", axis=year),
    ]
    data = AuditInput(
        rows=[row(key)],
        periods=[*PERIODS, {"axis_id": year, "period_id": "2024", "period_key_base": "2024", "period_marker": None}],
        facts=facts,
        links=link("S!C10", "B10+1", key, "2024")
        + link("S!D10", "C10+1", key, "2025")
        + link("S!E10", "D10+1", key, "2026@план")
        + link("S!U10", "C10+1", key, "2024")
        + link("S!V10", "C10+2", key, "2025")
        + link("S!W10", "C10+3", key, "2026@план"),
    )
    [found] = check("formula_pattern_break", data)
    assert {item.cell_id for item in found.locations} == {"S!U10", "S!V10", "S!W10"}
    assert {item.axis_id for item in found.locations} == {year}
    assert found.fingerprint == fingerprint("formula_pattern_break", "bk-S-10", "", "", "1")
    assert check("formula_segment", data) == []


def test_row_total_off_the_period_axis_is_not_a_pattern_break():
    key = "S|16|S!r2"
    period, total = "S!r2", "S!r9"
    facts = [
        fact(key, "S!C16", "2024", "1", axis=period),
        fact(key, "S!E16", "2026@план", "1", axis=period),
        fact(key, "S!D16", "2025", "2", axis=total),
    ]
    data = AuditInput(
        rows=[row(key)],
        periods=[*PERIODS, {"axis_id": total, "period_id": "2025", "period_key_base": "2025", "period_marker": None}],
        facts=facts,
        links=link("S!C16", "B16+1", key, "2024")
        + link("S!E16", "D16+1", key, "2026@план")
        + link("S!D16", "SUM(C16:E16)", key, "2025"),
    )
    assert check("formula_pattern_break", data) == []


def test_zero_addend_skips_if_and_a_partial_range():
    host, other = "S|15|S!r2", "S|1|S!r2"
    facts = [
        fact(host, "S!D15", "2025", "10"),
        fact(host, "S!E15", "2025", "0"),
        fact(host, "S!F15", "2025", "0"),
        fact(host, "S!G15", "2025", "1"),
        fact(other, "S!A1", "2024", "0"),
        fact(other, "S!B1", "2024", "0"),
        fact(other, "S!C1", "2024", "0"),
        fact(other, "S!C2", "2024", "10"),
        fact(other, "S!C3", "2024", "0"),
        fact(other, "S!C5", "2024", "0"),
        fact(other, "S!C6", "2024", None, "empty"),
        fact(other, "S!C7", "2024", "0"),
    ]
    data = AuditInput(
        rows=[row(host), row(other)],
        periods=PERIODS,
        facts=facts,
        links=link("S!D15", "IF(A1=0,SUM(C1:C2),0)", host, "2025")
        + link("S!E15", "SUM(C3:C4)", host, "2025")
        + link("S!F15", "SUM(C5:C6)", host, "2025")
        + link("S!G15", "G14+C7", host, "2025"),
    )
    found = check("zero_addend", data)
    cells = {item.cell_id for mark in found for item in mark.locations}
    assert "S!D15" not in cells
    assert "S!E15" not in cells
    assert cells == {"S!F15", "S!G15"}


def test_two_segments_are_info_not_a_break():
    key = "S|13|S!r2"
    facts = [fact(key, f"S!{col}13", period, "1") for col, period in (("C", "2024"), ("D", "2025"), ("E", "2026@план"))]
    data = AuditInput(
        rows=[row(key)],
        periods=PERIODS,
        facts=facts,
        links=link("S!C13", "C12+1", key, "2024") + link("S!D13", "D12+1", key, "2025") + link("S!E13", "E12+5", key, "2026@план"),
    )
    assert check("formula_pattern_break", data) == []
    [found] = check("formula_segment", data)
    assert found.severity == "info"
    assert [item["id"] for item in found.params["patterns"]] == ["A", "B"]


def test_cross_period_prior_column_and_zero_addend():
    key = "S|14|S!r2"
    other = "S|2|S!r2"
    facts = [
        fact(key, "S!C14", "2024", "1"),
        fact(key, "S!D14", "2025", "1"),
        fact(other, "S!D2", "2025", "0", axis="S!r2"),
    ]
    data = AuditInput(
        rows=[row(key), row(other)],
        periods=PERIODS,
        facts=facts,
        links=link("S!D14", "D13+D2", key, "2025", refs=("S!D13", "S!D2"), formula_class="cross_period")
        + link("S!C14", "B14", key, "2024", refs=("S!B14",), formula_class="rollforward"),
    )
    [cross] = check("cross_period_ref", data)
    assert cross.locations[0].cell_id == "S!D14"
    [prior] = check("prior_column", data)
    assert prior.severity == "info" and prior.locations[0].cell_id == "S!C14"
    [zero] = check("zero_addend", data)
    assert zero.locations[0].cell_id == "S!D14"


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


def test_golden_formula_patterns_on_packt_and_rvi():
    # Ложные разрывы шаблона: Packt молчит, у RVI четыре ряда из одной ячейки на шаблон.
    assert golden_count("packt", "formula_pattern_break") == 0
    assert golden_count("rvi", "formula_pattern_break") == 4
    assert golden_count("packt", "formula_segment") == 0
    assert golden_count("rvi", "formula_segment") == 0
    assert golden_count("packt", "cross_period_ref") == 2
    assert golden_count("rvi", "cross_period_ref") == 10
    assert golden_count("packt", "prior_column") == 5
    assert golden_count("rvi", "prior_column") == 10
    # Ноль слагаемого больше не берёт частичный диапазон и IF. Packt 49→42, RVI 125→110:
    # ушедшие ряды — SUM, где известен не весь диапазон, либо IF, который старый разбор читал как ссылку.
    assert golden_count("packt", "zero_addend") == 42
    assert golden_count("rvi", "zero_addend") == 110


def test_golden_offset_indirect_used():
    assert golden_count("rvi", "offset_indirect_used") > 0
    assert golden_count("packt", "offset_indirect_used") == 0
