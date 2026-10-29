"""Фаза 4 без живой книги: отчёт, пояснение, impact, сценарий, два job_id."""

from __future__ import annotations

import pytest

from finance_analysis.adapters.storage.store import LocalStore
from finance_analysis.application.analyses import (
    Analyses,
    AuditInput,
    Target,
    _full_metrics,
    _origins,
    _prepare_analysis_body,
)
from finance_analysis.application.compare import (
    Comparisons,
    _input_deltas,
    _input_index,
    _scenario_inputs,
    match_periods,
)
from finance_analysis.application.explain import narrate
from finance_analysis.application.impact import impact_view
from finance_analysis.application.operations import append_event, create_op, read_op
from finance_analysis.application.report import (
    choose_format,
    render_json,
    render_markdown,
)
from finance_analysis.application.service import FasService
from finance_analysis.domain.book import Actor, Head
from finance_analysis.domain.errors import InvalidArgument, NotAcceptable, NotFound


def test_report_bytes_stay_put():
    result = {
        "analysis_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "status": "succeeded",
        "builder_ref": {"job_id": "book", "summary_etag": "abc"},
        "versions": {"fas": "0", "glossary": "g-0001"},
        "summary": {"text": "готово"},
        "result_data": {"ratios": [], "findings": [], "impact": None},
    }
    assert render_markdown(result) == render_markdown(result)
    assert "builder_ref" in render_markdown(result)
    assert render_json(result) == render_json(dict(reversed(list(result.items()))))


def test_choose_format_prefers_query():
    assert choose_format("md", "application/json", ("json", "md")) == "md"
    assert choose_format(None, "text/markdown", ("json", "md")) == "md"
    with pytest.raises(NotAcceptable):
        choose_format("xlsx", "*/*", ("json", "md"))


@pytest.mark.asyncio
async def test_narrate_keeps_template_when_the_model_invents_a_digit():
    items = [{"id": "summary", "code": "impact_completed", "params": {"drivers": 10}, "title": None}]
    plain = await narrate(None, items, None)
    assert plain["summary"] == "impact_completed: drivers=10"

    class Stub:
        def __init__(self, text: str) -> None:
            self.text = text
            self.calls = 0

        async def complete(self, messages, deadline, max_tokens=800):
            self.calls += 1
            assert "10" not in messages[0]["content"]
            return self.text

    digit = Stub('{"summary": "нашёл 10 драйверов"}')
    assert (await narrate(digit, items, None))["summary"] == plain["summary"]
    named = Stub('{"summary": "найдено {drivers} драйверов"}')
    assert (await narrate(named, items, None))["summary"] == "найдено 10 драйверов"
    assert digit.calls == 1 and named.calls == 1

    class Down:
        async def complete(self, messages, deadline, max_tokens=800):
            raise RuntimeError("нет модели")

    assert (await narrate(Down(), items, None))["summary"] == plain["summary"]
    missing = Stub('{"summary": "{drivers.missing}"}')
    assert (await narrate(missing, items, None))["summary"] == plain["summary"]
    hidden = Stub('{"summary": "{drivers.__class__.__name__}"}')
    assert (await narrate(hidden, items, None))["summary"] == plain["summary"]


def test_impact_uses_cached_values_and_does_not_invent_external():
    chain = {
        "source": "builder",
        "direction": "precedents",
        "depth": 2,
        "items": [
            {
                "origin": "S!A1",
                "nodes": [
                    {"node_id": "S!A1", "depth": 0, "formula": "=B1"},
                    {"node_id": "S!B1", "depth": 1, "formula": "1", "cached_value": "5", "row_key": "row"},
                ],
                "edges": [{"source": "S!A1", "target": "S!B1"}],
            }
        ],
    }
    bare = impact_view(chain, {}, [], "S!A1")
    assert bare["drivers"] == [
        {"node_id": "S!B1", "row_key": "row", "formula": "1", "cached_value": "5", "depth": 1}
    ]
    assert bare["external"] == []
    assert bare["warnings"] == [{"code": "external_not_in_trace", "params": {}}]

    linked = {
        "source": "graph_links",
        "direction": "precedents",
        "depth": 1,
        "items": [{"cell_id": "S!A1", "precedents": [{"cell_id": "S!B1", "value": "9", "row_key": "row"}]}],
    }
    fallback = impact_view(linked, {}, [{"fingerprint": "fp", "locations": [{"cell_id": "S!B1"}]}], "row")
    assert fallback["drivers"][0]["cached_value"] == "9"
    assert fallback["findings"] == ["fp"]
    assert fallback["warnings"] == [{"code": "external_not_in_trace", "params": {}}]

    marked = {
        "source": "builder",
        "direction": "precedents",
        "depth": 1,
        "items": [{"edges": [{"kind": "external_workbook", "source": "S!A1", "target": "Other!A1"}]}],
    }
    external = impact_view(marked, {}, [], "S!A1")
    assert external["external"][0]["kind"] == "external_workbook"
    assert external["warnings"] == []

    class Link:
        refs = ("[Other]Sheet!A1",)
        formula = None
        formula_class = None

    quoted = {
        "source": "builder",
        "items": [
            {
                "origin": "S!A1",
                "nodes": [{"node_id": "S!B1", "depth": 1, "formula": "=1"}],
                "edges": [{"kind": "ref", "source": "S!A1", "target": "S!B1"}],
            }
        ],
    }
    named = impact_view(quoted, {"S!A1": Link()}, [], "S!A1", {"S!B1": {"value_raw": "5"}})
    assert named["drivers"][0]["cached_value"] == "5"
    assert named["external"] == [{"cell_id": "S!A1", "ref": "[Other]Sheet!A1"}]
    assert named["warnings"] == []
    unclassified = impact_view(quoted, {}, [], "S!A1")
    assert unclassified["external"] == []
    assert unclassified["warnings"] == [{"code": "external_not_in_trace", "params": {}}]


def test_scenario_deltas_are_inputs_only():
    periods = [
        {"header_text": "Live", "period_marker": "fact", "marker_class": "fact", "axis_id": "a", "period_id": "p1"},
        {"header_text": "Case 1", "axis_id": "b", "period_id": "p2", "axis_kind": "params"},
    ]
    assert match_periods(periods, "case 1")[0]["period_id"] == "p2"
    assert match_periods(periods, "FACT")[0]["period_id"] == "p1"
    facts = [
        {"axis_id": "a", "period_id": "p1", "row_key": "row", "value": "4"},
        {"axis_id": "b", "period_id": "p2", "row_key": "row", "value": "10"},
    ]
    deltas = _input_deltas(_input_index(facts, match_periods(periods, "Live")), _input_index(facts, match_periods(periods, "Case 1")))
    assert deltas
    assert all("metric" not in row for row in deltas)
    assert {"row_key", "base", "other", "delta_abs", "delta_pct"} <= set(deltas[0])


def test_scenario_case_lines_up_on_the_same_period():
    live = [{"header_text": "Live", "axis_kind": "params", "axis_id": "p", "period_id": "c1", "period_key_base": "2024"}]
    fact = [{"period_marker": "fact", "axis_id": "t", "period_id": "2024", "period_key_base": "2024"}]
    facts = [
        {"axis_id": "p", "period_id": "c1", "row_key": "row", "value": "10"},
        {"axis_id": "t", "period_id": "2024", "row_key": "row", "value": "4"},
    ]
    [row] = _scenario_inputs(facts, [], live, fact)
    assert row["period_key_base"] == "2024"
    assert row["base"] == "10"
    assert row["other"] == "4"
    assert row["delta_abs"] == "-6"


def test_case_columns_pair_on_the_row_and_skip_formulas():
    left = [{"header_text": "Case 1", "axis_kind": "params", "axis_id": "p", "period_id": "case-1", "period_key_base": "case-1"}]
    right = [{"header_text": "Case 2", "axis_kind": "params", "axis_id": "p", "period_id": "case-2", "period_key_base": "case-2"}]
    facts = [
        {"axis_id": "p", "period_id": "case-1", "row_key": "gen", "value": "50"},
        {"axis_id": "p", "period_id": "case-2", "row_key": "gen", "value": "75"},
        {"axis_id": "p", "period_id": "case-1", "row_key": "npv", "value": "10"},
        {"axis_id": "p", "period_id": "case-2", "row_key": "npv", "value": "4"},
    ]
    rows = [{"row_key": "gen"}, {"row_key": "npv", "formula": "=1"}]
    [row] = _scenario_inputs(facts, rows, left, right)
    assert row["row_key"] == "gen"
    assert row["base"] == "50"
    assert row["other"] == "75"
    assert row["delta_abs"] == "25"


def test_full_rejects_an_empty_metrics_list():
    assert _full_metrics({}) == ["dscr"]
    with pytest.raises(InvalidArgument):
        _full_metrics({"metrics": []})
    with pytest.raises(InvalidArgument):
        _full_metrics({"metrics": None})


def test_prepare_drops_null_fields_and_a_blank_target():
    body = _prepare_analysis_body(
        {
            "type": "full",
            "metrics": None,
            "rules": None,
            "render": None,
            "build_key": None,
            "scope": None,
            "target": {"cell_id": None, "row_key": "", "concept": None},
        }
    )
    assert body == {"type": "full"}
    assert _full_metrics(body) == ["dscr"]


class _Stop(Exception):
    pass


class _Ensures:
    settings = type("Settings", (), {"load_sync_sec": 1})()

    async def ensure(self, *args, **kwargs):
        raise _Stop


@pytest.mark.asyncio
async def test_include_and_blank_target_follow_the_handler():
    analyses = Analyses(_Ensures())
    blank = {"cell_id": None, "row_key": None, "concept": None}
    with pytest.raises(InvalidArgument):
        await analyses.run("job", {"type": "audit", "include": []}, Actor(), wait_sec=1)
    with pytest.raises(InvalidArgument):
        await analyses.run("job", {"type": "impact", "target": blank}, Actor(), wait_sec=1)
    with pytest.raises(_Stop):
        await analyses.run("job", {"type": "audit", "target": dict(blank)}, Actor(), wait_sec=1)
    with pytest.raises(_Stop):
        await analyses.run("job", {"type": "full", "metrics": None, "target": dict(blank)}, Actor(), wait_sec=1)


def test_unknown_cell_is_not_an_empty_impact():
    data = AuditInput(
        facts=[{"row_key": "row", "cell_id": "S!A1"}],
        links=[{"cell": "S!B1", "row_key": "row"}],
    )
    assert _origins(data, {"cell_id": "S!A1"}) == ["S!A1"]
    assert _origins(data, {"cell_id": "S!B1"}) == ["S!B1"]
    with pytest.raises(NotFound):
        _origins(data, {"cell_id": "NotACell!A1"})


@pytest.mark.asyncio
async def test_progress_after_cancel_does_not_reopen_the_operation(redis_runtime, tmp_path):
    store = LocalStore(tmp_path / "ops")
    operation = await create_op(store, "analysis", None, Actor(), {"type": "full"})
    svc = type("Svc", (), {"store": store, "support": redis_runtime})()

    async def get_op(op_id):
        return await read_op(store, op_id)

    svc.get_op = get_op
    svc.finish_op = lambda op_id, status, **fields: FasService.finish_op(svc, op_id, status, **fields)
    await FasService.progress_op(svc, operation["id"], "loading")
    await FasService.cancel_op(svc, operation["id"], Actor())
    await FasService.progress_op(svc, operation["id"], "evaluating")
    await FasService.finish_op(svc, operation["id"], "succeeded", result={"analysis_id": "x"})

    async def stale_running(op_id):
        body = await read_op(store, op_id)
        return {**body, "status": "running"}

    svc.get_op = stale_running
    await FasService.progress_op(svc, operation["id"], "rendering")
    assert (await read_op(store, operation["id"]))["status"] == "cancelled"


@pytest.mark.asyncio
async def test_later_success_does_not_replace_cancel(redis_runtime, tmp_path):
    store = LocalStore(tmp_path / "ops")
    operation = await create_op(store, "analysis", None, Actor(), {"type": "full"})
    await append_event(store, operation["id"], {"status": "cancelled", "result": {"actor": "a"}})
    await append_event(store, operation["id"], {"status": "succeeded", "result": {"analysis_id": "x"}})
    body = await read_op(store, operation["id"])
    assert body["status"] == "cancelled"
    assert body["result"] == {"actor": "a"}

    fresh = await create_op(store, "analysis", None, Actor(), {"type": "full"})
    await redis_runtime.cache_set(f"fas:op:{fresh['id']}:cancel", b"1", 60)
    svc = type("Svc", (), {"store": store, "support": redis_runtime})()

    async def get_op(op_id):
        return await read_op(store, op_id)

    svc.get_op = get_op
    await FasService.finish_op(svc, fresh["id"], "succeeded", result={"analysis_id": "x"})
    assert (await read_op(store, fresh["id"]))["status"] == "running"


@pytest.mark.asyncio
async def test_full_does_not_save_after_cancel():
    saved: list[str] = []

    class Support:
        async def cache_get(self, key):
            return b"1"

    class Svc:
        support = Support()
        finished: tuple | None = None

        async def get_op(self, op_id):
            return {"status": "running"}

        async def finish_op(self, op_id, status, **fields):
            self.finished = (op_id, status)

        async def progress_op(self, op_id, stage):
            saved.append(stage)

    svc = Svc()
    analyses = Analyses(svc)

    async def unused(*args, **kwargs):
        saved.append("work")

    analyses._input = unused
    analyses._save_tables = unused
    await analyses._execute_full("job", None, "analysis", ["dscr"], None, {}, Actor(), "op")
    assert saved == []
    assert svc.finished == ("op", "cancelled")


@pytest.mark.asyncio
async def test_two_books_do_not_share_one_query():
    seen: list[tuple] = []

    class Analyses:
        async def compute_metrics(self, job, target, metrics):
            seen.append(("metrics", job))
            return {"rows": [], "periods": [], "facts": [], "bindings": [], "needs_input": [], "warnings": []}

    class Query:
        def __init__(self) -> None:
            self.calls: list = []

        async def sql(self, *args, **kwargs):
            self.calls.append(args)
            raise AssertionError(args)

    class Service:
        def __init__(self) -> None:
            self.query = Query()

        async def _dataset_rows(self, job, head, name):
            seen.append(("rows", job, name))
            return []

    analyses = Analyses()
    analyses.service = Service()
    left = Target(Head("b1", 1, "d", {}), "b1", {}, False, "d")
    right = Target(Head("b2", 1, "d", {}), "b2", {}, False, "d")
    result = await Comparisons(analyses)._compare("job-a", left, "job-b", right, ["dscr"], None)
    assert seen == [("metrics", "job-a"), ("metrics", "job-b"), ("rows", "job-a", "dim_row"), ("rows", "job-b", "dim_row")]
    assert result["other_job_id"] == "job-b"
    assert result["metrics"] == []
    assert analyses.service.query.calls == []
