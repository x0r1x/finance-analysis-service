"""Каждая fact-строка ровно в одном статусе (§5.10.1)."""

import json

from finance_analysis.adapters.builder.acl import parse_context, parse_graph
from finance_analysis.application.catalog import load_catalog, load_git_document
from finance_analysis.application.project import derive_rows, project
from finance_analysis.domain.glossary_release import apply_ops, package_of
from finance_analysis.domain.mapping import assign_rows
from tests.books import BUILDER_ROOT, job_id

_STATUSES = {"bound", "bound_with_warning", "ambiguous", "unknown", "not_applicable", "ignored"}


def _at(tables: dict, bindings: list[dict], sheet: str, row_num: int) -> dict:
    source = next(row for row in tables["dim_row"] if row["sheet"] == sheet and row["row_num"] == row_num)
    return next(row for row in bindings if row["binding_key"] == source["binding_key"])


def _tables(alias: str) -> dict:
    job = job_id(alias)
    folder = BUILDER_ROOT / job
    graph = json.loads((folder / "graph.json").read_text())
    context = json.loads((folder / "context.json").read_text())
    tables, _warnings = project(parse_graph(graph, parse_context(context)), model_id=job, build="b")
    return tables


def test_packt_and_rvi_partition_fact_rows():
    catalog = load_catalog()
    for alias in ("packt", "rvi"):
        tables = _tables(alias)
        derived = derive_rows(
            tables,
            state_seq=0,
            derive="d",
            versions={"glossary": "none"},
            glossary=catalog,
            facts=tables["fact_observation"],
        )
        facts = [row for row in tables["dim_row"] if row["kind"] == "fact"]
        bindings = derived["bindings"]
        assert len(bindings) == len(facts)
        assert {row["status"] for row in bindings} <= _STATUSES
        owners: dict[str, int] = {}
        for row in bindings:
            if row["is_primary"] and row["concept"]:
                owners[row["concept"]] = owners.get(row["concept"], 0) + 1
        assert all(count == 1 for count in owners.values())
        labels = {row["binding_key"]: row["label"] for row in tables["dim_row"]}
        if alias == "packt":
            debt = next(row for row in bindings if labels[row["binding_key"]] == "Debt service")
            assert debt["status"] == "bound" and debt["source"] == "inferred"
            cfads = _at(tables, bindings, "CFS", 14)
            assert cfads["concept"] == "cfads" and cfads["status"] == "bound" and cfads["is_primary"]
        else:
            service = _at(tables, bindings, "PF Model", 534)
            assert service["concept"] == "debt_service" and service["status"] == "bound" and service["is_primary"]
            # §5.5: одна строка на понятие. Хвостовая аббревиатура (CFADS) склеивает две строки.
            for number in (239, 532):
                row = _at(tables, bindings, "PF Model", number)
                assert row["concept"] == "cfads" and row["status"] == "ambiguous" and row["is_primary"] is False
        assert all(row["phase"] is None for row in derived["period_semantics"])


def test_two_labels_are_ambiguous_and_confirmed_wins():
    catalog = load_catalog()
    rows = [
        {"kind": "fact", "binding_key": "a", "label": "EBITDA", "sign": None},
        {"kind": "fact", "binding_key": "b", "label": "EBITDA", "sign": None},
    ]
    both = assign_rows(rows, [], catalog)
    assert both["a"].status == "ambiguous" and both["a"].is_primary is False
    assert both["b"].is_primary is False
    events = [{"seq": 1, "type": "concept.set", "target": "a", "binding_key": "a", "value": "ebitda"}]
    mixed = assign_rows(rows, events, catalog)
    assert mixed["a"].is_primary is True and mixed["a"].source == "confirmed"
    assert mixed["b"].is_primary is False and mixed["b"].status == "bound"


def test_removed_label_drops_inferred_and_keeps_confirmed():
    document = load_git_document()
    full = package_of(document)
    stripped = package_of(
        apply_ops(
            document,
            [{"op": "remove_label", "concept": "cfads", "kind": "alt", "lang": "en", "text": "CFADS"}],
        )
    )
    rows = [
        {"kind": "fact", "binding_key": "cf", "label": "CFADS", "sign": "inflow"},
        {"kind": "fact", "binding_key": "ds", "label": "Total debt service", "sign": "outflow"},
    ]
    events = [{"seq": 1, "type": "concept.set", "target": "ds", "binding_key": "ds", "value": "debt_service"}]
    before = assign_rows(rows, events, full)
    after = assign_rows(rows, events, stripped)
    assert before["cf"].status == "bound" and before["cf"].source == "inferred"
    assert after["cf"].status == "unknown"
    assert after["ds"].concept == "debt_service" and after["ds"].source == "confirmed"
