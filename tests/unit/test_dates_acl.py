"""Даты, @marker и ACL builder."""

from __future__ import annotations

import json
from datetime import date

import pytest

from finance_analysis.adapters.builder.acl import parse_context, parse_graph, parse_summary
from finance_analysis.application.project import derive_rows, project
from finance_analysis.domain.errors import UnsupportedBuilderShape
from finance_analysis.domain.periods import marker_class, phase_from_flags, resolve_period_dates, split_period_key
from tests.books import (
    BUILDER_ROOT,
    PACKT_PERIOD,
    PACKT_PHASE_AXIS,
    PACKT_REVENUE_CELL,
    PACKT_REVENUE_ROW,
    PACKT_REVENUE_VALUE,
)
from tests.conftest import JOB


def test_marker_does_not_move_dates():
    base, marker = split_period_key("2025@факт")
    assert base == "2025"
    assert marker == "факт"
    assert marker_class(marker) == "actual"
    start, end, source = resolve_period_dates(base, calendar_year=2025, start_date=None, end_date=None, previous_end=None)
    assert (start, end, source) == (date(2025, 1, 1), date(2025, 12, 31), "key")
    anchor_start, anchor_end, anchor_source = resolve_period_dates(
        "Y1", calendar_year=2030, start_date=None, end_date=None, previous_end=None
    )
    assert anchor_source == "anchor"
    assert anchor_start == date(2030, 1, 1)
    assert anchor_end == date(2030, 12, 31)
    assert marker_class("план") == "plan"
    assert marker_class("прогноз") == "estimate"
    assert marker_class("custom") == "other"


def test_phase_flags_ignore_false_and_keep_string_values():
    assert phase_from_flags({"construction": True, "operation": False}) == "construction"
    assert phase_from_flags({"construction": False, "operation": True}) == "operation"
    assert phase_from_flags({"phase": "operation"}) == "operation"
    assert phase_from_flags({"beginning of construction": True}) is None


def test_design_summary_keeps_http_etag():
    parsed = parse_summary(
        {
            "content_sha256": "b" * 64,
            "context_schema_version": "1",
            "graph_schema_version": "1",
            "status": "succeeded",
        },
        etag="summary-2",
        job_id=JOB,
    )
    assert parsed.etag == "summary-2"
    assert parsed.context_schema_version == "1"


def test_acl_packt_and_missing_field():
    folder = BUILDER_ROOT / JOB
    meta = json.loads((folder / "meta.json").read_text())
    graph = json.loads((folder / "graph.json").read_text())
    parsed = parse_summary(meta, etag="ignored", job_id=JOB, graph_schema_version=graph["schema_version"])
    assert parsed.content_sha256 == meta["content_sha256"]
    assert parsed.context_schema_version == meta["schema_version"]
    assert parsed.graph_schema_version == "1.7.0"
    assert parsed.etag != "ignored"
    assert len(parsed.etag) == 64
    context = json.loads((folder / "context.json").read_text())
    snapshot = parse_graph(graph, parse_context(context))
    assert "Input Assumptions!r5" in snapshot.axes
    tables = project(snapshot, model_id=JOB, build="0123456789abcdef")
    facts = {(row["row_key"], row["period_id"]): row for row in tables["fact_observation"]}
    revenue = facts[(PACKT_REVENUE_ROW, PACKT_PERIOD)]
    assert revenue["cell_id"] == PACKT_REVENUE_CELL
    assert str(revenue["value_raw"]) == PACKT_REVENUE_VALUE
    assert any(row["axis_id"] == "Input Assumptions!r5" for row in tables["fact_observation"])
    derived = derive_rows(tables, state_seq=0, derive="d", versions={})
    phases = {(row["axis_id"], row["period_id"]): row["phase"] for row in derived["period_semantics"]}
    assert phases[(PACKT_PHASE_AXIS, "Y1")] == "construction"
    assert phases[(PACKT_PHASE_AXIS, PACKT_PERIOD)] == "operation"
    broken = {
        "axes": [
            {
                "id": "years",
                "sheet": "Model",
                "periods": [{"col": 8, "text": "2024", "index": 1}],
            }
        ],
        "blocks": [],
    }
    with pytest.raises(UnsupportedBuilderShape):
        parse_context(broken)


def test_dict_axes_still_parse_markers():
    context = {
        "axes": {
            "years": {
                "id": "years",
                "sheet": "Model",
                "periods": [
                    {"col": 8, "text": "2024", "period_key": "2024", "index": 1},
                    {"col": 9, "text": "2025 факт", "period_key": "2025@факт", "index": 2},
                ],
            }
        },
        "blocks": [
            {
                "block_id": "b",
                "sheet": "Model",
                "kind": "timeline",
                "rows": [
                    {
                        "row_key": "rev",
                        "sheet": "Model",
                        "row": 10,
                        "label": "Revenue",
                        "kind": "fact",
                        "series": [
                            {
                                "axis_id": "years",
                                "values": ["100.5", "210"],
                                "value_statuses": ["cached", "cached"],
                            }
                        ],
                    }
                ],
            }
        ],
    }
    tables = project(parse_context(context), model_id=JOB, build="0123456789abcdef")
    periods = {row["period_id"]: row for row in tables["dim_period"]}
    assert periods["2024"]["date_source"] == "key"
    assert periods["2024"]["period_start"] == date(2024, 1, 1)
    assert periods["2025@факт"]["period_marker"] == "факт"
    assert periods["2025@факт"]["marker_class"] == "actual"
    facts = {(row["row_key"], row["period_id"]): row for row in tables["fact_observation"]}
    assert facts[("rev", "2024")]["cell_id"] == "Model!H10"
    assert str(facts[("rev", "2024")]["value_raw"]) == "100.5"


def test_builder_dates_win():
    start, end, source = resolve_period_dates(
        "2024",
        calendar_year=2024,
        start_date=date(2024, 2, 1),
        end_date=date(2024, 2, 28),
        previous_end=None,
    )
    assert source == "builder"
    assert start == date(2024, 2, 1)
    assert end == date(2024, 2, 28)
