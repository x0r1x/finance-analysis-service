"""Обычный анализ пишет хвост в хранилище и указатель в DuckDB, не в result_data."""

from __future__ import annotations

import inspect
import json

import pytest

from finance_analysis.adapters.api.route import analyses as analyses_route
from finance_analysis.application.service import Accepted
from finance_analysis.domain.book import Actor
from finance_analysis.domain.metrics import coverage_ratio, dscr_pf
from tests.books import job_id

pytestmark = pytest.mark.asyncio
PACKT = job_id("packt")


async def test_ratios_analysis_writes_the_trace_outside_the_result(local_service):
    result = await local_service.analyses.run(
        PACKT, {"type": "ratios", "metrics": ["dscr"]}, Actor(), wait_sec=120
    )
    if isinstance(result, Accepted):
        operation = await local_service.wait_op(result.operation["id"], 120_000)
        assert operation["status"] == "succeeded", operation
        analysis_id = operation["result"]["analysis_id"]
    else:
        analysis_id = result["analysis_id"]
    body = await local_service.analyses.result(PACKT, analysis_id)
    assert "calculation_traces" not in body["result_data"]
    pointer = local_service.trace_pointer
    rows = pointer.list_analysis(analysis_id)
    assert rows
    assert rows[0]["state"] == "committed"
    payload = json.loads(await local_service.store.get(rows[0]["object_key"]))
    assert payload["trace"]["implementation"]
    assert payload["trace"]["calculation_stamp"]
    assert "evidence=False" in inspect.getsource(coverage_ratio)
    assert "evidence=False" in inspect.getsource(dscr_pf)
    assert "analyses.delete" in inspect.getsource(analyses_route.register)
    removed = await local_service.analyses.delete(PACKT, analysis_id)
    assert removed["traces_removed"] == len(rows)
    assert pointer.count(analysis_id) == 0
