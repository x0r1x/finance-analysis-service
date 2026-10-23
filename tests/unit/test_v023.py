"""Правки v0.23: summary, ключ сборки, флаги, guard, срез."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from finance_analysis.adapters.builder.acl import parse_context
from finance_analysis.adapters.builder.etag import strong_etag
from finance_analysis.adapters.builder.fixture import FixtureBuilder
from finance_analysis.adapters.builder.http import HttpBuilder
from finance_analysis.adapters.wren.query import build_mdl
from finance_analysis.application.project import project
from finance_analysis.application.semantic_guard import SemanticWriteGuard
from finance_analysis.application.service import _match_periods
from finance_analysis.domain.book import (
    Changed,
    NotModified,
    ReportNotReady,
    build_key_for,
)
from finance_analysis.domain.errors import UnsupportedBuilderShape
from finance_analysis.domain.validation.semantics import check_derived
from finance_analysis.settings import Settings
from tests.books import BUILDER_ROOT, job_id
from tests.conftest import JOB


def test_builder_package_does_not_name_the_sidecar():
    root = Path("src/finance_analysis/adapters/builder")
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py"))
    assert "meta.json" not in text


def test_build_key_uses_job_etag_and_projection():
    left = build_key_for("a" * 64, '"summary-2:one"', "1")
    assert left == build_key_for("a" * 64, '"summary-2:one"', "1")
    assert left != build_key_for("b" * 64, '"summary-2:one"', "1")
    assert left != build_key_for("a" * 64, '"summary-2:two"', "1")
    assert left != build_key_for("a" * 64, '"summary-2:one"', "2")
    assert len(left) == 16


def test_dim_period_schema_has_timeline_fields():
    path = Path("src/finance_analysis/adapters/storage/schemas/dim_period.json")
    names = [column["name"] for column in json.loads(path.read_text())["columns"]]
    assert "group_key" not in names
    assert names.index("timeline_id") < names.index("period_id")
    assert "axis_kind" in names
    assert "flags_source" in names


def test_ignored_fields_and_missing_index():
    context = {
        "axes": [
            {
                "id": "years",
                "sheet": "Model",
                "header_row": 3,
                "periods": [
                    {
                        "col": 4,
                        "text": "2024",
                        "period_key": "2024",
                        "index": 1,
                        "group_key": "hidden",
                    }
                ],
            }
        ],
        "blocks": [],
    }
    snapshot = parse_context(context)
    period = snapshot.axes["years"].periods[0]
    assert not hasattr(period, "group_key")
    assert not hasattr(snapshot.axes["years"], "header_row")
    broken = {
        "axes": [{"id": "years", "sheet": "Model", "periods": [{"col": 4, "period_key": "2024", "text": "2024"}]}],
        "blocks": [],
    }
    with pytest.raises(UnsupportedBuilderShape) as caught:
        parse_context(broken)
    assert any(field.endswith("index") for field in caught.value.extra["fields"])


def test_timeline_mismatch_does_not_copy_flags():
    context = {
        "axes": [
            {
                "id": "canon",
                "sheet": "A",
                "timeline_id": "canon",
                "periods": [
                    {"col": 4, "text": "Y1", "period_key": "Y1", "index": 1, "flags": {"operation": True}},
                ],
            },
            {
                "id": "other",
                "sheet": "B",
                "timeline_id": "canon",
                "periods": [
                    {"col": 9, "text": "Y2", "period_key": "Y2", "index": 1},
                ],
            },
        ],
        "blocks": [],
    }
    tables, warnings = project(parse_context(context), model_id=JOB, build="0123456789abcdef")
    other = next(row for row in tables["dim_period"] if row["axis_id"] == "other")
    assert json.loads(other["flags_json"]) == {}
    assert other["flags_source"] is None
    assert any(item["code"] == "timeline_mismatch" for item in warnings)


def test_period_templates_ignore_phase():
    rows = [
        {
            "axis_id": "a",
            "period_id": "2024",
            "period_key_base": "2024",
            "calendar_year": 2024,
            "period_marker": None,
            "period_start": None,
            "period_end": None,
            "phase": "operation",
        },
        {
            "axis_id": "a",
            "period_id": "2024@факт",
            "period_key_base": "2024",
            "calendar_year": 2024,
            "period_marker": "факт",
            "period_start": None,
            "period_end": None,
            "phase": None,
        },
        {
            "axis_id": "a",
            "period_id": "2032",
            "period_key_base": "2032",
            "calendar_year": 2032,
            "period_marker": None,
            "period_start": None,
            "period_end": None,
            "phase": None,
        },
    ]
    assert [item["period_id"] for item in _match_periods("2024", rows)] == ["2024", "2024@факт"]
    assert [item["period_id"] for item in _match_periods("факт 2024", rows)] == ["2024@факт"]
    assert [item["period_id"] for item in _match_periods("2030-2035", rows)] == ["2032"]
    assert _match_periods("первый операционный год", rows) == []


def test_concept_measure_keeps_only_primary_row():
    mdl = build_mdl(JOB, {name: f"/tmp/{JOB}/{name}.parquet" for name in (
        "fact_observation",
        "dim_row",
        "dim_period",
        "bindings",
        "row_semantics",
        "period_semantics",
    )})
    expression = mdl["cubes"][0]["dimensions"]
    concept = next(item for item in expression if item["name"] == "concept")
    measure = next(item for item in mdl["cubes"][0]["measures"] if item["name"] == "value_sum")
    assert concept["expression"] == "CASE WHEN is_primary THEN effective_concept END"
    assert measure["expression"] == "sum(CASE WHEN is_primary THEN normalized_value END)"
    import duckdb

    table = duckdb.sql(
        f"""
        SELECT {concept["expression"]} AS concept, {measure["expression"]} AS total
        FROM (VALUES ('revenue', true, 10), ('revenue', false, 99), ('other', false, 7))
             t(effective_concept, is_primary, normalized_value)
        GROUP BY 1
        """
    ).fetchall()
    grouped = {name: total for name, total in table if name is not None}
    assert grouped == {"revenue": 10}
    assert [total for name, total in table if name is None] == [None]


async def test_fixture_summary_etag_head_and_rebuild():
    builder = FixtureBuilder(BUILDER_ROOT)
    first = await builder.summary(JOB, None)
    assert builder.calls == [("GET", "/summary")]
    assert first.etag.startswith('"summary-2:')
    assert first.status == "succeeded"
    again = await builder.summary(JOB, first.etag)
    assert isinstance(again, NotModified)
    assert again.etag == first.etag
    assert builder.calls[-1] == ("GET", "/summary")
    head = await builder.head_summary(JOB, first.etag)
    assert isinstance(head, NotModified)
    assert head.etag == first.etag
    assert not hasattr(head, "warnings")
    builder.rebuilding.add(JOB)
    blocked = await builder.summary(JOB, None)
    assert isinstance(blocked, ReportNotReady)
    assert blocked.as_dict() == {"error": "report_not_ready"}
    blocked_head = await builder.head_summary(JOB, first.etag)
    assert isinstance(blocked_head, ReportNotReady)


def test_strong_etag_shape():
    tag = strong_etag(
        content_sha256="ab",
        context_mtime_ns=0,
        context_size=3,
        graph_mtime_ns=0,
        graph_size=4,
    )
    assert tag == '"summary-2:ab:0:3:0:4"'


async def test_http_summary_is_one_get():
    calls: list[tuple[str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        match = request.headers.get("if-none-match")
        calls.append((request.method, match))
        if request.method == "HEAD":
            return httpx.Response(304, headers={"etag": '"summary-2:abc"'})
        if match == '"summary-2:abc"':
            return httpx.Response(304, headers={"etag": '"summary-2:abc"'})
        return httpx.Response(
            200,
            headers={"etag": '"summary-2:abc"'},
            json={
                "status": "succeeded",
                "context_schema_version": "1.14.0",
                "graph_schema_version": "1.7.0",
                "warnings": [],
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    builder = HttpBuilder(Settings(BUILDER_BASE_URL="http://builder"), client=client)
    loaded = await builder.summary(JOB, None)
    assert [item[0] for item in calls] == ["GET"]
    assert loaded.etag == '"summary-2:abc"'
    cached = await builder.summary(JOB, loaded.etag)
    assert isinstance(cached, NotModified)
    assert calls[-1] == ("GET", '"summary-2:abc"')
    head = await builder.head_summary(JOB, loaded.etag)
    assert isinstance(head, NotModified)
    assert calls[-1][0] == "HEAD"


async def test_breaker_states_do_not_call_network():
    builder = HttpBuilder(Settings(BUILDER_BASE_URL="http://builder"))
    assert await builder.breaker_state() == "closed"
    builder._open_until = datetime.now(UTC) + timedelta(seconds=30)
    assert await builder.breaker_state() == "open"
    builder._open_until = datetime.now(UTC) - timedelta(seconds=1)
    assert await builder.breaker_state() == "half_open"
    builder._ok()
    assert await builder.breaker_state() == "closed"


async def test_running_status_is_not_a_cached_etag(settings, redis_runtime):
    from finance_analysis.adapters.storage.parquet_io import PyarrowParquet
    from finance_analysis.adapters.storage.store import open_storage
    from finance_analysis.adapters.wren.query import WrenQuery
    from finance_analysis.application.service import FasService
    from finance_analysis.domain.book import Actor

    store = await open_storage(settings)
    builder = FixtureBuilder(BUILDER_ROOT)
    service = FasService(settings, store, PyarrowParquet(), builder, WrenQuery(settings), redis_runtime)
    actor = Actor()
    head = await service.perform_load(JOB, actor=actor, fence=1)
    etag = (await service._manifest(JOB, head.build_key))["builder_ref"]["summary_etag"]
    builder.calls.clear()
    builder.status_override[JOB] = "running"
    view = await service.book_view(JOB, actor, wait_sec=30)
    assert view.body["loaded"] is True
    assert view.body["is_latest"] is None
    assert {"code": "freshness_unknown", "params": {}} in view.body["warnings"]
    assert view.body["build_key"] == head.build_key
    assert (await service._manifest(JOB, head.build_key))["builder_ref"]["summary_etag"] == etag
    assert builder.calls == [("GET", "/summary")]
    fresh = FixtureBuilder(BUILDER_ROOT)
    fresh.rebuilding.add(job_id("rvi"))
    other = FasService(settings, store, PyarrowParquet(), fresh, WrenQuery(settings), redis_runtime)
    blocked = await other.book_view(job_id("rvi"), actor, wait_sec=5)
    assert blocked.body["loaded"] is False
    assert blocked.body["is_latest"] is None
    assert {"code": "freshness_unknown", "params": {}} in blocked.body["warnings"]


async def test_guard_rejects_and_duplicates(tmp_path):
    from finance_analysis.adapters.storage.store import LocalStore
    from finance_analysis.domain.book import Actor

    store = LocalStore(tmp_path / "store")
    guard = SemanticWriteGuard(store, catalog=frozenset({"revenue"}), targets=frozenset({"row-1"}))
    unknown = await guard.append(
        JOB,
        target="row-1",
        event_type="concept.confirm",
        value="revenue",
        actor=Actor(),
        expected_seq=None,
        request_id="u",
        concept="revenue",
    )
    assert unknown.accepted is False
    assert unknown.code == "schema_invalid"
    outside = await guard.append(
        JOB,
        target="row-1",
        event_type="concept.set",
        value="other",
        actor=Actor(),
        expected_seq=None,
        request_id="c",
        concept="other",
    )
    assert outside.code == "concept_not_in_catalog"
    tables = {
        "bindings": [
            {"concept": "revenue", "effective_concept": "revenue", "is_primary": True, "row_key": "row-1"},
            {"concept": "revenue", "effective_concept": "revenue", "is_primary": True, "row_key": "row-2"},
        ]
    }
    primary = guard.review_derived(tables, row_keys=frozenset({"row-1", "row-2"}))
    assert primary.accepted is False
    assert primary.code == "concept_already_bound"
    remapped = check_derived(
        {
            "bindings": [
                {"concept": "a", "effective_concept": "b", "is_primary": True, "row_key": "row-1"},
                {"concept": "c", "effective_concept": "b", "is_primary": True, "row_key": "row-2"},
            ]
        },
        catalog=frozenset({"a", "b", "c"}),
        row_keys=frozenset({"row-1", "row-2"}),
    )
    assert remapped.code == "concept_already_bound"
    foreign = guard.review_derived(
        {"bindings": [{"concept": "other", "effective_concept": "other", "is_primary": False, "row_key": "row-1"}]},
        row_keys=frozenset({"row-1"}),
    )
    assert foreign.code == "concept_not_in_catalog"
    first = await guard.append(
        JOB,
        target="row-1",
        event_type="concept.set",
        value="revenue",
        actor=Actor(),
        expected_seq=None,
        request_id="once",
        concept="revenue",
    )
    assert first.accepted and not first.duplicate
    second = await guard.append(
        JOB,
        target="row-1",
        event_type="concept.set",
        value="revenue",
        actor=Actor(),
        expected_seq=None,
        request_id="twice",
        concept="revenue",
    )
    assert second.accepted and second.duplicate
    assert len(await guard.read_all(JOB)) == 1


def test_consistent_head_is_not_a_body():
    assert Changed("x").etag == "x"
