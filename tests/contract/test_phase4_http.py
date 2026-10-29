"""Фаза 4: отчёт, impact, полный прогон, сценарий, SSE."""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from finance_analysis.adapters.api.app import create_app
from finance_analysis.domain.book import Actor
from tests.books import job_id

pytestmark = pytest.mark.asyncio

RVI = job_id("rvi")
HEADERS = {"X-User-Id": "alex", "X-Client-Id": "desk"}


@pytest.fixture
def app(settings, local_service, redis_runtime):
    return create_app(settings, service=local_service, support=redis_runtime)


def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://fas", timeout=120)


def _sse(body: str) -> list[tuple[str, str]]:
    found = []
    for block in body.split("\n\n"):
        if not block.strip() or block.lstrip().startswith(":"):
            continue
        seq, kind = "", ""
        for line in block.splitlines():
            if line.startswith("id: "):
                seq = line[4:]
            elif line.startswith("event: "):
                kind = line[7:]
        if kind:
            found.append((seq, kind))
    return found


async def test_report_impact_full_scenario_and_sse(app, local_service, settings):
    async with _client(app) as client:
        denied = await client.get("/v1/capabilities", headers={**HEADERS, "Accept": "text/event-stream"})
        assert denied.status_code == 406, denied.text
        glossary = await client.get("/v1/glossary/events", headers={**HEADERS, "Accept": "text/event-stream"})
        assert glossary.status_code == 406, glossary.text

        audit = await client.post(f"/v1/books/{RVI}/analyses", headers=HEADERS, json={"type": "audit"})
        assert audit.status_code == 200, audit.text
        analysis_id = audit.json()["analysis_id"]
        assert isinstance(audit.json()["summary"]["text"], str)
        report = await client.get(
            f"/v1/books/{RVI}/analyses/{analysis_id}/report",
            headers={**HEADERS, "Accept": "text/markdown"},
            params={"format": "md"},
        )
        again = await client.get(
            f"/v1/books/{RVI}/analyses/{analysis_id}/report",
            headers=HEADERS,
            params={"format": "md"},
        )
        assert report.status_code == 200, report.text
        assert report.content == again.content
        assert analysis_id in report.text
        assert "builder_ref" in report.text
        assert audit.json()["versions"]["fas"] in report.text

        head = (await local_service._read_head(RVI))[0]
        periods = await local_service._dataset_rows(RVI, head, "dim_period")
        impact = await client.post(
            f"/v1/books/{RVI}/analyses",
            headers=HEADERS,
            json={"type": "impact", "target": "PF Model!M537", "depth": 2},
        )
        expect = 200 if len(periods) <= settings.sync_max_periods else 202
        assert impact.status_code == expect, impact.text
        if impact.status_code == 202:
            waited = await client.get(f"/v1/operations/{impact.json()['id']}", headers=HEADERS, params={"wait_ms": 30000})
            assert waited.json()["status"] == "succeeded", waited.text
            stored = await client.get(
                f"/v1/books/{RVI}/analyses/{waited.json()['result']['analysis_id']}",
                headers=HEADERS,
            )
            view = stored.json()
        else:
            view = impact.json()
        assert view["result_data"]["impact"]["origin"] == "PF Model!M537"
        assert view["result_data"]["impact"]["external"] == []
        assert any(item["code"] == "external_not_in_trace" for item in view["warnings"])
        missing_cell = await client.post(
            f"/v1/books/{RVI}/analyses",
            headers=HEADERS,
            json={"type": "impact", "target": "NotACell!A1"},
        )
        assert missing_cell.status_code == 404, missing_cell.text

        full = await client.post(f"/v1/books/{RVI}/analyses", headers=HEADERS, json={"type": "full", "metrics": ["dscr"]})
        assert full.status_code == 202, full.text
        op_id = full.json()["id"]
        done = await client.get(f"/v1/operations/{op_id}", headers=HEADERS, params={"wait_ms": 30000})
        assert done.json()["status"] == "succeeded", done.text
        assert done.json()["result"]["analysis_id"]
        assert done.json()["result"]["resource"].endswith(done.json()["result"]["analysis_id"])

        stream = await client.get(
            f"/v1/operations/{op_id}/events",
            headers={**HEADERS, "Accept": "text/event-stream"},
        )
        assert stream.status_code == 200, stream.text
        events = _sse(stream.text)
        assert any(kind == "progress" for _seq, kind in events)
        assert events[-1][1] == "done"
        resumed = await client.get(
            f"/v1/operations/{op_id}/events",
            headers={**HEADERS, "Accept": "text/event-stream", "Last-Event-ID": events[0][0]},
        )
        tail = _sse(resumed.text)
        assert tail
        assert all(int(seq) > int(events[0][0]) for seq, _kind in tail)
        assert tail[-1][1] == "done"

        missing = await client.post(
            f"/v1/books/{RVI}:compare",
            headers=HEADERS,
            json={"base": {"scenario": "нет такого"}, "other": {"scenario": "тоже нет"}},
        )
        assert missing.status_code == 400, missing.text
        mixed = await client.post(
            f"/v1/books/{RVI}:compare",
            headers=HEADERS,
            json={"base": {"scenario": "Live"}, "other": {"job_id": RVI}},
        )
        assert mixed.status_code == 400, mixed.text

        settings.sse_enabled = False
        try:
            off = await client.get(
                f"/v1/operations/{op_id}/events",
                headers={**HEADERS, "Accept": "text/event-stream"},
            )
            assert off.status_code == 404, off.text
            still = await client.get(f"/v1/operations/{op_id}", headers=HEADERS)
            assert still.status_code == 200, still.text
        finally:
            settings.sse_enabled = True


async def test_sse_reads_the_store_when_pubsub_is_quiet(app, local_service, redis_runtime, settings):
    settings.sse_heartbeat_sec = 1
    real = redis_runtime.messages
    entered = asyncio.Event()

    async def quiet(channel):
        if str(channel).startswith("fas:op:"):
            entered.set()
            while True:
                await asyncio.sleep(30)
                yield "no"
        async for item in real(channel):
            yield item

    redis_runtime.messages = quiet
    task: asyncio.Task | None = None
    try:
        op = await local_service.create_op("analysis", None, Actor(), {"type": "full"})
        async with _client(app) as client:
            task = asyncio.create_task(
                client.get(
                    f"/v1/operations/{op['id']}/events",
                    headers={**HEADERS, "Accept": "text/event-stream"},
                )
            )
            await asyncio.wait_for(entered.wait(), timeout=5)
            await local_service.finish_op(
                op["id"], "succeeded", result={"analysis_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV"}
            )
            response = await asyncio.wait_for(task, timeout=5)
        assert response.status_code == 200, response.text
        assert "event: done" in response.text
    finally:
        redis_runtime.messages = real
        if task is not None and not task.done():
            task.cancel()
