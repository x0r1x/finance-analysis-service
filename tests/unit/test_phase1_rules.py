"""Правила фазы 1, разбор формул и отпечаток находки (§6.1)."""

from __future__ import annotations

import json
from collections import Counter
from decimal import Decimal

import pytest

from finance_analysis.adapters.builder.acl import (
    parse_context,
    parse_links,
    parse_summary,
)
from finance_analysis.application.project import project
from finance_analysis.application.rule_engine import (
    load_rules,
    requirements,
    run_rules,
    select_rules,
)
from finance_analysis.domain.audit import AuditInput, axis_ordinals, fingerprint
from finance_analysis.domain.book import with_links
from finance_analysis.domain.errors import InvalidArgument
from finance_analysis.domain.formulas import analyze
from tests.books import BUILDER_ROOT, job_id

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


def _row(row_key: str, **extra) -> dict:
    sheet, row_num, _block = row_key.split("|")
    return {
        "row_key": row_key,
        "binding_key": f"bk-{sheet}-{row_num}",
        "sheet": sheet,
        "label": extra.pop("label", f"row {row_num}"),
        "has_formula": extra.pop("has_formula", True),
        "formula": extra.pop("formula", "=R[0]C[-1]+1"),
        "check_row": extra.pop("check_row", False),
        "formula_exceptions": extra.pop("formula_exceptions", []),
        **extra,
    }


def _fact(row_key: str, cell: str, period: str, value: str | None, status: str = "cached", axis: str = "S!r2") -> dict:
    return {
        "row_key": row_key,
        "cell_id": cell,
        "axis_id": axis,
        "period_id": period,
        "value_raw": value,
        "value_dec": None if value is None else Decimal(value),
        "normalized_value": None if value is None else Decimal(value),
        "value_status": status,
    }


def _link(cell: str, formula: str, row_key: str | None, period: str | None, refs: tuple[str, ...] = ("S!A1",)) -> list[dict]:
    return [
        {"cell": cell, "formula": formula, "formula_class": "same_period", "ref_cell": ref, "row_key": row_key, "period_id": period}
        for ref in refs
    ] or [{"cell": cell, "formula": formula, "formula_class": None, "ref_cell": None, "row_key": row_key, "period_id": period}]


PERIODS = [
    {"axis_id": "S!r2", "period_id": "2024", "period_key_base": "2024", "period_marker": None},
    {"axis_id": "S!r2", "period_id": "2025", "period_key_base": "2025", "period_marker": None},
    {"axis_id": "S!r2", "period_id": "2026@план", "period_key_base": "2026", "period_marker": "план"},
]


def _check(code: str, data: AuditInput):
    return select_rules(load_rules(), [code])[0].check(data)


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


def test_formula_facts():
    facts = analyze("=IF(A1>0,IF(B$2<5%,0.07*'Year 2024'!C3,SUM(D1:D9)),\"x 99\")*12")
    assert facts.if_depth == 2
    assert facts.functions == {"IF", "SUM"}
    # 12 и 0 универсальны, 99 в строке и 2024 в имени листа — не литералы.
    assert sorted(facts.literals, key=Decimal) == ["0.05", "0.07"]
    assert analyze("=Z172*(1+AA165)").literals == ()
    assert analyze("=NPV(Rate,B1:B9)").functions == {"NPV"}
    assert analyze("=XNPV(Rate,B1:B9,C1:C9)").functions == {"XNPV"}
    assert analyze("=A:A+3:3").operands == 2


def test_fingerprint_and_axis_ordinal():
    left = fingerprint("hardcoded_formula", "bk", "2024", "", "0")
    assert left == fingerprint("hardcoded_formula", "bk", "2024", "", "0")
    assert left != fingerprint("hardcoded_formula", "bk", "2024", "план", "0")
    assert len(left) == 40
    # Вставка строки сдвигает номер шапки, но не порядок осей листа.
    before = axis_ordinals(["PF!r7", "PF!r185", "PF!r11", "TBA!r2"])
    after = axis_ordinals(["PF!r8", "PF!r186", "PF!r12", "TBA!r3"])
    assert before == {"PF!r7": 0, "PF!r11": 1, "PF!r185": 2, "TBA!r2": 0}
    assert [after[key] for key in ("PF!r8", "PF!r12", "PF!r186", "TBA!r3")] == [0, 1, 2, 0]


def test_hardcoded_formula_flags_constant_in_formula_row():
    key = "S|10|S!r2"
    data = AuditInput(
        rows=[_row(key)],
        periods=PERIODS,
        facts=[_fact(key, "S!C10", "2024", "5"), _fact(key, "S!D10", "2025", "6"), _fact(key, "S!E10", "2026@план", "7")],
        links=_link("S!D10", "C10+1", key, "2025") + _link("S!E10", "D10+1", key, "2026@план"),
    )
    found = _check("hardcoded_formula", data)
    assert [item.locations[0].cell_id for item in found] == ["S!C10"]
    assert found[0].binding_key == "bk-S-10"
    assert found[0].fingerprint == fingerprint("hardcoded_formula", "bk-S-10", "2024", "", "0")
    assert found[0].params["formula_class"] == "same_period"
    # Без formula_class на оси строка — не строка формул.
    assert _check("hardcoded_formula", AuditInput(rows=data.rows, periods=PERIODS, facts=data.facts)) == []
    # Ячейка из formula_exceptions — формула другого шаблона, не константа.
    excepted = AuditInput(rows=[_row(key, formula_exceptions=["S!C10"])], periods=PERIODS, facts=data.facts, links=data.links)
    assert _check("hardcoded_formula", excepted) == []


def test_literal_severity_rises_when_literal_changes_along_row():
    key = "S|11|S!r2"
    facts = [_fact(key, "S!C11", "2024", "1"), _fact(key, "S!D11", "2025", "1")]
    same = AuditInput(rows=[_row(key)], periods=PERIODS, facts=facts, links=_link("S!C11", "A1*1.1", key, "2024") + _link("S!D11", "B1*1.1", key, "2025"))
    varied = AuditInput(rows=[_row(key)], periods=PERIODS, facts=facts, links=_link("S!C11", "A1*1.1", key, "2024") + _link("S!D11", "B1*1.2", key, "2025"))
    [low] = _check("literal_in_formula", same)
    [medium] = _check("literal_in_formula", varied)
    assert (low.severity, low.params["literals"]) == ("low", ["1.1"])
    assert (medium.severity, medium.params["literals"]) == ("medium", ["1.1", "1.2"])
    assert low.fingerprint == medium.fingerprint


def test_formula_inconsistent_uses_builder_exceptions():
    key = "S|12|S!r2"
    data = AuditInput(
        rows=[_row(key, formula_exceptions=["S!D12"], formula_exceptions_truncated=True)],
        periods=PERIODS,
        facts=[_fact(key, "S!C12", "2024", "1"), _fact(key, "S!D12", "2025", "2")],
    )
    [found] = _check("formula_inconsistent_in_row", data)
    assert [item.cell_id for item in found.locations] == ["S!D12"]
    assert found.truncated is True


def test_counter_rules():
    counters = {
        "iterate": False,
        "missing_cached_values": 3,
        "unresolved": {"count": 40, "ids": ["S!C1"]},
        "external": {"count": 1, "ids": ["S!C2"]},
        "dangling": {"count": 0, "ids": []},
        "dangling_classes": {"empty_ref": 4},
        "cycles": [{"id": "c1", "class": "unexpected", "members": 2}, {"id": "c2", "class": "iterative_ok", "members": 3}],
    }
    data = AuditInput(rows=[_row("S|1|S!r2", check_row=True)], periods=PERIODS, counters=counters)
    codes = Counter(item.code for item in run_rules(list(load_rules().values()), data))
    assert codes["unresolved_ref"] == 1
    assert codes["external_ref"] == 1
    assert codes["dangling_ref"] == 0
    assert codes["unexpected_cycle"] == 1
    assert codes["iterative_cycle_without_iterate"] == 1
    assert codes["iterative_calc_enabled"] == 0
    assert codes["no_master_check"] == 0
    # Счётчик есть, а ячеек без кэша в проекции нет — одна находка книги с truncated.
    [missing] = _check("missing_cached_value", data)
    assert missing.params == {"count": 3, "located": 0, "unlocated": 3} and missing.truncated
    [unresolved] = _check("unresolved_ref", data)
    assert unresolved.truncated and unresolved.params["count"] == 40
    assert _check("iterative_calc_enabled", AuditInput(counters={"iterate": True}))
    # Без счётчиков R1 (старая сборка) правила по ним молчат.
    assert _check("unresolved_ref", AuditInput()) == []


def test_missing_cached_value_keeps_counter_remainder():
    key = "S|40|S!r2"
    data = AuditInput(
        rows=[_row(key)],
        periods=PERIODS,
        facts=[_fact(key, "S!C40", "2024", None, "empty")],
        links=_link("S!C40", "A1+B1", key, "2024"),
        counters={"missing_cached_values": 20},
    )
    found = _check("missing_cached_value", data)
    assert [item.locations[0].cell_id if item.locations else None for item in found] == ["S!C40", None]
    assert found[1].params == {"count": 20, "located": 1, "unlocated": 19}
    assert found[1].truncated
    data.counters["missing_cached_values"] = 1
    assert len(_check("missing_cached_value", data)) == 1


def test_hardcoded_counts_uncached_formulas():
    key = "S|41|S!r2"
    facts = [_fact(key, f"S!{col}41", period, None, "empty") for col, period in (("C", "2024"), ("D", "2025"))]
    facts.append(_fact(key, "S!E41", "2026@план", "5"))
    links = _link("S!C41", "B41+1", key, "2024") + _link("S!D41", "C41+1", key, "2025")
    [found] = _check("hardcoded_formula", AuditInput(rows=[_row(key)], periods=PERIODS, facts=facts, links=links))
    assert found.locations[0].cell_id == "S!E41"


def test_dangling_classes_alone_are_blank_cells_not_findings():
    # builder: dangling_classes — ссылки на настоящие пустые ячейки, вне dangling.count.
    blank = {"dangling": {"count": 0, "ids": []}, "dangling_classes": {"empty_ref": 445, "empty_range_member": 190}}
    assert _check("dangling_ref", AuditInput(counters=blank)) == []
    broken = {"dangling": {"count": 2, "ids": ["S!C1"]}, "dangling_classes": {"empty_ref": 4}}
    [found] = _check("dangling_ref", AuditInput(counters=broken))
    assert found.params == {"count": 2, "dangling_classes": {"empty_ref": 4}}
    assert found.truncated


def test_check_failure_is_nonzero_on_check_row():
    flag = "S|20|S!r2"
    comparison = "S|21|S!r2"
    data = AuditInput(
        rows=[
            _row(flag, check_row=True, formula="=IF(R[-1]C[0]<>0,1,0)"),
            _row(comparison, check_row=True, formula="=R[-9]C[0]-R[-3]C[0]<0.01"),
            _row("S|22|S!r2", check_row=True, has_formula=False, formula=None),
        ],
        periods=PERIODS,
        facts=[
            _fact(flag, "S!C20", "2024", "0", "zero_explicit"),
            _fact(flag, "S!D20", "2025", "1"),
            _fact(comparison, "S!C21", "2024", "1"),
            _fact(comparison, "S!D21", "2025", "0", "zero_explicit"),
            _fact("S|22|S!r2", "S!C22", "2024", "1"),
        ],
    )
    found = {item.locations[0].cell_id: item for item in _check("check_failure", data)}
    # §6.1: сбой — ненулевое значение, как бы проверка ни была записана.
    assert set(found) == {"S!D20", "S!C21"}
    assert found["S!D20"].severity == "critical"
    assert found["S!C21"].params == {"nonzero_cells": 1, "label": "row 21"}
    assert _check("no_master_check", AuditInput(rows=[_row("S|1|S!r2")]))[0].severity == "info"


def test_external_ref_reads_graph_refs_and_counter():
    key = "S|50|S!r2"
    data = AuditInput(
        rows=[_row(key)],
        periods=PERIODS,
        facts=[_fact(key, "S!C50", "2024", "1"), _fact(key, "S!D50", "2025", "1")],
        links=_link("S!C50", "[1]Rates!B2*2", key, "2024", refs=("[1]Rates!B2",))
        + _link("S!D50", "[Prices.xlsx]Sheet1!A1:A3", key, "2025", refs=("[Prices.xlsx]Sheet1!A1:A3", "S!A1")),
        counters={"external": {"count": 4, "ids": ["S!C50", "S!D50", "T!A1"]}},
    )
    graph, rest = _check("external_ref", data)
    assert [item.cell_id for item in graph.locations] == ["S!C50", "S!D50"]
    assert graph.params["refs"] == ["[1]Rates!B2", "[Prices.xlsx]Sheet1!A1:A3"]
    assert graph.binding_key == "bk-S-50"
    assert rest.params == {"count": 4, "located": 2, "unlocated": 2}
    assert [item.cell_id for item in rest.locations] == ["T!A1"] and rest.truncated
    data.counters["external"]["count"] = 2
    assert len(_check("external_ref", data)) == 1


def test_unexpected_cycle_locates_members_in_graph():
    key = "S|60|S!r2"
    links = (
        _link("S!C60", "D60+1", key, "2024", refs=("S!D60",))
        + _link("S!D60", "C60*0.5", key, "2025", refs=("S!C60",))
        + _link("S!E60", "E60", key, "2026@план", refs=("S!E60",))
    )
    data = AuditInput(
        rows=[_row(key)],
        periods=PERIODS,
        links=links,
        counters={
            "iterate": False,
            "cycles": [{"id": "c1", "class": "unexpected", "members": 2}, {"id": "c2", "class": "unexpected", "members": 3}],
        },
    )
    assert data.cycles == [("S!E60",), ("S!C60", "S!D60")]
    first, second = _check("unexpected_cycle", data)
    assert [item.cell_id for item in first.locations] == ["S!C60", "S!D60"]
    assert first.params["located"] is True
    assert second.locations == () and second.params["located"] is False


def test_text_rules_group_by_row_and_axis():
    key = "S|30|S!r2"
    data = AuditInput(
        rows=[_row(key)],
        periods=PERIODS,
        facts=[_fact(key, "S!C30", "2024", "1"), _fact(key, "S!D30", "2025", "1")],
        links=_link("S!C30", "OFFSET(A1,0,1)+NPV(r,B1:B3)+IF(a,IF(b,1,2),3)", key, "2024")
        + _link("S!D30", "INDIRECT(\"A1\")", key, "2025")
        + _link("X!Z9", "NPV(r,A1:A3)", None, None),
    )
    [offset] = _check("offset_indirect_used", data)
    assert offset.params == {"functions": ["INDIRECT", "OFFSET"], "cells": 2}
    npv = _check("excel_npv_used", data)
    # Ячейка вне строк книги — своя находка с отпечатком по ячейке.
    assert len(npv) == 2 and {item.binding_key for item in npv} == {"bk-S-30", None}
    assert _check("nested_if", data)[0].params["depth"] == 2
    long = AuditInput(rows=[_row(key)], periods=PERIODS, facts=data.facts, links=_link("S!C30", "+".join(["A1"] * 13), key, "2024"))
    assert _check("long_formula", long)[0].params["operands"] == 13


def _golden(alias: str) -> AuditInput:
    job = job_id(alias)
    folder = BUILDER_ROOT / job
    snapshot = with_links(
        parse_context(json.loads((folder / "context.json").read_text())),
        parse_links(json.loads((folder / "graph.json").read_text())),
    )
    summary = parse_summary(json.loads((folder / "summary.json").read_text()), etag='"summary-2:x"')
    tables, _warnings = project(snapshot, model_id=job, build="0123456789abcdef")
    rows = [dict(row, formula_exceptions=json.loads(row["formula_exceptions_json"])) for row in tables["dim_row"]]
    return AuditInput(
        rows=rows,
        periods=tables["dim_period"],
        facts=tables["fact_observation"],
        links=tables["graph_links"],
        counters=summary.counters,
    )


def test_golden_books_audit():
    rules = list(load_rules().values())
    packt = Counter(item.code for item in run_rules(rules, _golden("packt")))
    rvi_data = _golden("rvi")
    rvi = Counter(item.code for item in run_rules(rules, rvi_data))
    # Проверки обеих книг сходятся; в RVI 20 формул без кэша — как в счётчике R1.
    # Проверки Packt записаны сравнением (`=A-B<0.01`, TRUE = 1): по §6.1 это ненулевое значение.
    assert packt["check_failure"] == 2
    assert rvi["check_failure"] == 0
    assert packt["no_master_check"] == rvi["no_master_check"] == 0
    assert rvi["missing_cached_value"] == rvi_data.counters["missing_cached_values"] == 20
    assert rvi["offset_indirect_used"] > 0
    assert rvi["formula_inconsistent_in_row"] == 13
    assert packt["iterative_calc_enabled"] == rvi["iterative_calc_enabled"] == 0


def test_summary_counters_and_exceptions_reach_projection():
    data = _golden("rvi")
    assert data.counters["iterate"] is False
    assert data.counters["dangling_classes"] == {"empty_ref": 445, "empty_range_member": 190}
    assert data.counters["cycles"] == []
    rows = {row["row_key"]: row for row in data.rows}
    assert rows["PF Model|13|PF Model!r11"]["formula_exceptions"] == ["PF Model!G13"]
    assert rows["PF Model|13|PF Model!r11"]["formula_exceptions_truncated"] is False


def test_scope_periods_and_markers():
    from finance_analysis.application.analyses import _in_scope, _scope

    key = "S|70|S!r2"
    periods = [dict(item, period_index=index, marker_class="plan" if item["period_marker"] else None) for index, item in enumerate(PERIODS)]
    data = AuditInput(
        rows=[_row(key)],
        periods=periods,
        facts=[_fact(key, "S!C70", "2024", "1"), _fact(key, "S!E70", "2026@план", "1")],
    )
    rule = select_rules(load_rules(), ["hardcoded_formula"])[0]
    early = rule.finding(data, locations=[data.placed("S!C70")], row_key=key, axis_id="S!r2", period_id="2024")
    planned = rule.finding(data, locations=[data.placed("S!E70")], row_key=key, axis_id="S!r2", period_id="2026@план")
    book = rule.finding(data)

    def kept(scope: dict) -> list:
        parsed = _scope({"scope": scope})
        return [item for item in (early, planned, book) if _in_scope(item, parsed, data, set())]

    assert kept({"period_from": "2025"}) == [planned, book]
    assert kept({"period_to": "2025"}) == [early, book]
    # Маркер совпадает и по тексту, и по классу.
    assert kept({"markers": ["план"]}) == kept({"markers": ["plan"]}) == [planned, book]
    assert kept({"period_from": "1999"}) == [book]
    with pytest.raises(InvalidArgument):
        _scope({"scope": {"markers": "план"}})


async def test_http_trace_reads_r5():
    import httpx

    from finance_analysis.adapters.builder.http import HttpBuilder
    from finance_analysis.domain.book import ReportNotReady
    from finance_analysis.settings import Settings

    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        if request.url.params["from"] == "PF Model!M537":
            return httpx.Response(409, json={"error": "report_not_ready", "detail": "rebuild"})
        return httpx.Response(
            200,
            json={
                "origin": "PF Model!AA172",
                "direction": "precedents",
                "depth": 2,
                "stopped": None,
                "nodes": [{"node_id": "PF Model!AA172", "depth": 0, "formula_template": "x"}],
                "edges": [{"source": "PF Model!AA172", "target": "PF Model!Z172", "kind": "ref"}],
            },
        )

    builder = HttpBuilder(Settings(BUILDER_BASE_URL="http://builder"), client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    job = job_id("rvi")
    found = await builder.trace(job, "PF Model!AA172", direction="precedents", depth=2)
    assert seen[0].path == f"/v1/context-jobs/{job}/graph/trace"
    assert dict(seen[0].params) == {"from": "PF Model!AA172", "direction": "precedents", "depth": "2"}
    assert found["edges"][0]["target"] == "PF Model!Z172"
    assert "formula_template" not in found["nodes"][0]
    assert isinstance(await builder.trace(job, "PF Model!M537", direction="precedents", depth=2), ReportNotReady)
