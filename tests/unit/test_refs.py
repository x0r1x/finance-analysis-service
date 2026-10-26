"""Правила по ссылкам (`plugins/rules/refs.py`, §6.1)."""

from __future__ import annotations

import pytest

from finance_analysis.domain.audit import AuditInput
from tests.unit.rule_inputs import PERIODS, check, fact, golden_count, link, row


def test_unresolved_ref_from_counter():
    [found] = check("unresolved_ref", AuditInput(counters={"unresolved": {"count": 40, "ids": ["S!C1"]}}))
    assert found.params["count"] == 40
    assert [item.cell_id for item in found.locations] == ["S!C1"]
    assert found.truncated
    # Без счётчиков R1 (старая сборка) правило молчит.
    assert check("unresolved_ref", AuditInput()) == []


def test_dangling_classes_alone_are_blank_cells_not_findings():
    # builder: dangling_classes — ссылки на настоящие пустые ячейки, вне dangling.count.
    blank = {"dangling": {"count": 0, "ids": []}, "dangling_classes": {"empty_ref": 445, "empty_range_member": 190}}
    assert check("dangling_ref", AuditInput(counters=blank)) == []
    broken = {"dangling": {"count": 2, "ids": ["S!C1"]}, "dangling_classes": {"empty_ref": 4}}
    [found] = check("dangling_ref", AuditInput(counters=broken))
    assert found.params == {"count": 2, "dangling_classes": {"empty_ref": 4}}
    assert found.truncated


def test_external_ref_reads_graph_refs_and_counter():
    key = "S|50|S!r2"
    data = AuditInput(
        rows=[row(key)],
        periods=PERIODS,
        facts=[fact(key, "S!C50", "2024", "1"), fact(key, "S!D50", "2025", "1")],
        links=link("S!C50", "[1]Rates!B2*2", key, "2024", refs=("[1]Rates!B2",))
        + link("S!D50", "[Prices.xlsx]Sheet1!A1:A3", key, "2025", refs=("[Prices.xlsx]Sheet1!A1:A3", "S!A1")),
        counters={"external": {"count": 4, "ids": ["S!C50", "S!D50", "T!A1"]}},
    )
    graph, rest = check("external_ref", data)
    assert [item.cell_id for item in graph.locations] == ["S!C50", "S!D50"]
    assert graph.params["refs"] == ["[1]Rates!B2", "[Prices.xlsx]Sheet1!A1:A3"]
    assert graph.binding_key == "bk-S-50"
    assert rest.params == {"count": 4, "located": 2, "unlocated": 2}
    assert [item.cell_id for item in rest.locations] == ["T!A1"] and rest.truncated
    data.counters["external"]["count"] = 2
    assert len(check("external_ref", data)) == 1


def test_external_ref_counter_without_graph_refs():
    [found] = check("external_ref", AuditInput(counters={"external": {"count": 1, "ids": ["S!C2"]}}))
    assert found.params == {"count": 1, "located": 0, "unlocated": 1}
    assert [item.cell_id for item in found.locations] == ["S!C2"]


@pytest.mark.parametrize("code", ["dangling_ref", "unresolved_ref", "external_ref"])
def test_golden_books_have_no_broken_refs(code):
    assert golden_count("packt", code) == golden_count("rvi", code) == 0
