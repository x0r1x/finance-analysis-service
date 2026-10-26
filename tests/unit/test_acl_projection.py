"""Входы фазы 1 из builder: счётчики R1, formula_exceptions и trace R5 (§2.1, ACL, проекция)."""

from __future__ import annotations

import httpx

from finance_analysis.adapters.builder.http import HttpBuilder
from finance_analysis.domain.book import ReportNotReady
from finance_analysis.settings import Settings
from tests.books import job_id
from tests.unit.rule_inputs import golden


def test_summary_counters_and_exceptions_reach_projection():
    data = golden("rvi")
    assert data.counters["iterate"] is False
    assert data.counters["dangling_classes"] == {"empty_ref": 445, "empty_range_member": 190}
    assert data.counters["cycles"] == []
    rows = {item["row_key"]: item for item in data.rows}
    assert rows["PF Model|13|PF Model!r11"]["formula_exceptions"] == ["PF Model!G13"]
    assert rows["PF Model|13|PF Model!r11"]["formula_exceptions_truncated"] is False


async def test_http_trace_reads_r5():
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
