"""Фаза 4 без живой книги: отчёт, пояснение, impact, сценарий, два job_id."""

from __future__ import annotations

import pytest

from finance_analysis.adapters.storage.store import LocalStore
from finance_analysis.application.analyses import AuditInput, Target, _origins
from finance_analysis.application.compare import (
    Comparisons,
    _input_deltas,
    _input_index,
    match_periods,
)
from finance_analysis.application.explain import narrate
from finance_analysis.application.impact import impact_view
from finance_analysis.application.operations import create_op, read_op
from finance_analysis.application.report import (
    choose_format,
    render_json,
    render_markdown,
)
from finance_analysis.application.service import FasService
from finance_analysis.domain.book import Actor, Head
from finance_analysis.domain.errors import NotAcceptable, NotFound


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
    [row] = _input_deltas(_input_index(facts, live), _input_index(facts, fact))
    assert row["period_key_base"] == "2024"
    assert row["base"] == "10"
    assert row["other"] == "4"
    assert row["delta_abs"] == "-6"


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
