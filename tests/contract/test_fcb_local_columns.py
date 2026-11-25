from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal

import pytest

from finance_analysis.adapters.builder.acl import parse_context
from finance_analysis.adapters.builder.fixture import FixtureBuilder
from finance_analysis.application import service as service_module
from finance_analysis.application.project import derive_rows, project
from finance_analysis.domain.book import FAS_PROJECTION_VERSION, Actor
from finance_analysis.domain.errors import UnsupportedBuilderShape
from finance_analysis.domain.operational_year import resolve_operational_year
from tests.conftest import JOB


def _block(kind, sheet, axis_id, columns, *, block_id=None):
    block_id = block_id or axis_id
    values = [value for _, _, _, value, _ in columns]
    statuses = [status for _, _, _, _, status in columns]
    return {
        "block_id": block_id,
        "sheet": sheet,
        "kind": kind,
        "axis_ids": [axis_id] if kind == "timeline" else [],
        "periods": []
        if kind == "timeline"
        else [
            {"col": col, "period_key": key, "text": text}
            for col, key, text, _, _ in columns
        ],
        "rows": [
            {
                "row_key": f"{sheet}|3|{block_id}",
                "sheet": sheet,
                "row": 3,
                "kind": "fact",
                "label": "Facility",
                "label_path": ["Financing"],
                "series": [
                    {"axis_id": axis_id, "values": values, "value_statuses": statuses}
                ],
            }
        ],
    }


def _context(schema_version, *, mixed):
    blocks = [
        _block(
            "params",
            "Inputs",
            "Inputs!r1",
            [(2, "2024", "Budget scenario", "11", "cached")],
        ),
        _block(
            "key_value",
            "Sources & Uses",
            "Sources & Uses!c3",
            [
                (3, "c3", "$mm", "125.5", "cached"),
                (4, "c4", "x EBITDA", "0", "zero_explicit"),
            ],
        ),
        _block(
            "matrix",
            "Sensitivity",
            "Sensitivity!c3",
            [
                (2, "c2", "Low", None, "empty"),
                (3, "c3", "Base", "10", "cached"),
                (5, "c5", "High", "12", "cached"),
            ],
        ),
    ]
    axes = []
    if mixed:
        columns = [
            (2, "2023", "2023", "5", "cached"),
            (3, "2024", "2024", "6", "cached"),
        ]
        axis_id = "Cash Flow!r1"
        axes.append(
            {
                "id": axis_id,
                "timeline_id": axis_id,
                "sheet": "Cash Flow",
                "grain": "year",
                "periods": [
                    {"col": col, "period_key": key, "text": text, "index": index}
                    for index, (col, key, text, _, _) in enumerate(columns)
                ],
            }
        )
        blocks.append(
            _block("timeline", "Cash Flow", axis_id, columns, block_id="Cash Flow!r2")
        )
    return {"schema_version": schema_version, "axes": axes, "blocks": blocks}


@pytest.mark.parametrize("schema_version", ["1.14.0", "1.15.0"])
@pytest.mark.parametrize("mixed", [False, True])
def test_local_column_facts_preserve_their_cells_outside_the_calendar(
    schema_version, mixed
):
    payload = _context(schema_version, mixed=mixed)
    tables, _ = project(parse_context(payload), model_id=JOB, build="build")
    assert {row["block_kind"] for row in tables["dim_row"]} == {
        block["kind"] for block in payload["blocks"]
    }
    periods = tables["dim_period"]
    local_periods = [row for row in periods if row["axis_kind"] == "params"]
    assert [(row["period_id"], row["header_text"]) for row in local_periods] == [
        ("2024", "Budget scenario"),
        ("c3", "$mm"),
        ("c4", "x EBITDA"),
        ("c2", "Low"),
        ("c3", "Base"),
        ("c5", "High"),
    ]
    assert all(
        row["period_start"] is None
        and row["period_end"] is None
        and row["timeline_id"] is None
        for row in local_periods
    )
    facts = tables["fact_observation"]
    assert [
        (row["cell_id"], row["value_dec"], row["value_status"])
        for row in facts
        if row["axis_kind"] == "params"
    ] == [
        ("Inputs!B3", Decimal(11), "cached"),
        ("Sources & Uses!C3", Decimal("125.5"), "cached"),
        ("Sources & Uses!D3", Decimal(0), "zero_explicit"),
        ("Sensitivity!B3", None, "empty"),
        ("Sensitivity!C3", Decimal(10), "cached"),
        ("Sensitivity!E3", Decimal(12), "cached"),
    ]
    events = [
        {
            "seq": 1,
            "type": "phase.set",
            "target": "Sources & Uses!c3+c3",
            "value": "operation",
        }
    ]
    if mixed:
        events.append(
            {
                "seq": 2,
                "type": "phase.set",
                "target": "Cash Flow!r1+2024",
                "value": "operation",
            }
        )
    derived = derive_rows(
        tables, state_seq=len(events), derive="d", versions={}, events=events
    )
    semantics = derived["period_semantics"]
    assert [
        (row["axis_id"], row["period_id"]) for row in semantics if row["phase"]
    ] == ([("Cash Flow!r1", "2024")] if mixed else [])
    operation = resolve_operational_year(periods, semantics, [], facts)
    assert [period["period_id"] for period in operation["periods"]] == (
        ["2024"] if mixed else []
    )
    assert bool(operation["needs_input"]) is not mixed


@pytest.mark.parametrize(
    ("fields", "missing"),
    [
        ({}, "axes"),
        ({"axes": None}, "axes"),
        ({"axes": "malformed"}, "axes"),
        ({"axes": [7]}, "axes[0]"),
    ],
)
def test_missing_or_invalid_axes_are_diagnosed(fields, missing):
    with pytest.raises(UnsupportedBuilderShape) as raised:
        parse_context({"blocks": [], **fields})
    assert raised.value.extra["fields"] == [missing]


def test_unknown_block_kind_is_diagnosed():
    payload = _context("1.15.0", mixed=True)
    payload["blocks"][1]["kind"] = "future_kind"
    with pytest.raises(UnsupportedBuilderShape) as raised:
        parse_context(payload)
    assert raised.value.extra["fields"] == ["blocks[1].kind"]


async def test_projection_refresh_preserves_bindings_and_resolves_only_calendar_periods(
    local_service, tmp_path, monkeypatch
):
    book = tmp_path / JOB
    book.mkdir()
    (book / "context.json").write_text(
        json.dumps(_context("1.14.0", mixed=True)), encoding="utf-8"
    )
    (book / "graph.json").write_text(
        '{"schema_version":"1.7.0","links":[]}', encoding="utf-8"
    )
    builder = FixtureBuilder(tmp_path)
    local_service.builder = builder

    read_context = builder.context

    async def legacy_context(job_id):
        snapshot = await read_context(job_id)
        axes = {
            axis_id: replace(axis, axis_kind="time")
            if axis_id in {"Sources & Uses!c3", "Sensitivity!c3"}
            else axis
            for axis_id, axis in snapshot.axes.items()
        }
        return replace(snapshot, axes=axes)

    with monkeypatch.context() as legacy:
        legacy.setattr(builder, "context", legacy_context)
        legacy.setattr(service_module, "FAS_PROJECTION_VERSION", "3:previous")
        old = await local_service.perform_load(JOB, actor=Actor(), fence=1)
    legacy_periods = await local_service._dataset_rows(JOB, old, "dim_period")
    assert any(
        row["axis_id"] == "Sources & Uses!c3" and row["axis_kind"] == "time"
        for row in legacy_periods
    )

    resolved = await local_service.resolve_periods(
        JOB, {"text": "2024"}, Actor(), wait_sec=60
    )
    assert [(row["axis_id"], row["period_id"]) for row in resolved["periods"]] == [
        ("Cash Flow!r1", "2024")
    ]
    new, _ = await local_service._read_head(JOB)
    assert resolved["build_key"] == new.build_key != old.build_key
    old_manifest = await local_service._manifest(JOB, old.build_key)
    new_manifest = await local_service._manifest(JOB, new.build_key)
    assert new_manifest["builder_ref"] == old_manifest["builder_ref"]
    assert new_manifest["fas_projection_version"] == FAS_PROJECTION_VERSION
    left = await local_service._dataset_rows(JOB, old, "dim_row")
    right = await local_service._dataset_rows(JOB, new, "dim_row")
    assert {row["row_key"]: row["binding_key"] for row in left} == {
        row["row_key"]: row["binding_key"] for row in right
    }

    decisions = await local_service.submit_decisions(
        JOB,
        {
            "decisions": [
                {
                    "kind": "phase.set",
                    "target": "Sources & Uses!c3+c3",
                    "value": "operation",
                },
                {"kind": "actuals_end.set", "value": "c3"},
            ]
        },
        Actor(),
        wait_sec=60,
    )
    assert [item["status"] for item in decisions["results"]] == ["rejected", "rejected"]


async def test_outline_hidden_fact_stays_in_analysis_after_storage(local_service, tmp_path):
    payload = _context("1.15.0", mixed=True)
    folded, manual, legacy = (block["rows"][0] for block in payload["blocks"][:3])
    for row in (folded, manual, legacy):
        row["hidden"] = True
    folded["hidden_by_outline"] = True
    manual["hidden_by_outline"] = False
    book = tmp_path / JOB
    book.mkdir()
    (book / "context.json").write_text(json.dumps(payload), encoding="utf-8")
    (book / "graph.json").write_text('{"schema_version":"1.7.0","links":[]}', encoding="utf-8")
    local_service.builder = FixtureBuilder(tmp_path)

    head = await local_service.perform_load(JOB, actor=Actor(), fence=1)
    stored = {row["row_key"]: row for row in await local_service._dataset_rows(JOB, head, "dim_row")}
    semantics = {row["row_key"]: row for row in await local_service._dataset_rows(JOB, head, "row_semantics")}
    for source, marker in ((folded, True), (manual, False), (legacy, None)):
        key = source["row_key"]
        assert stored[key]["hidden"] is True
        assert stored[key]["hidden_by_outline"] is marker
        assert semantics[key]["excluded"] is (marker is not True)
        assert semantics[key]["exclusion_reason"] == (None if marker else "hidden")
