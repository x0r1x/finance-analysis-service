"""Маршруты фазы 0, квоты, дедлайн, отмена, actor."""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from finance_analysis.adapters.api.app import create_app
from finance_analysis.domain.errors import InvalidArgument
from tests.books import (
    PACKT_PERIOD,
    PACKT_REVENUE_CELL,
    PACKT_REVENUE_ROW,
    PACKT_REVENUE_VALUE,
    PACKT_TRAFFIC_DIFF,
    PACKT_TRAFFIC_HV_ROW,
    PACKT_TRAFFIC_PC_ROW,
    job_id,
)
from tests.conftest import JOB

pytestmark = pytest.mark.asyncio


@pytest.fixture
def app(settings, local_service, redis_runtime):
    return create_app(settings, service=local_service, support=redis_runtime)


async def test_capabilities_health_metrics(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fas") as client:
        live = await client.get("/health/live")
        ready = await client.get("/health/ready")
        caps = await client.get("/v1/capabilities")
        metrics = await client.get("/metrics")
    assert live.status_code == 200
    assert ready.status_code == 200
    assert ready.json()["storage"]["conditional_writes"] == "flock"
    assert ready.json()["builder"] == "closed"
    assert caps.json()["storage"]["backend"] == "local"
    assert caps.json()["metrics"] == ["dscr", "icr", "adscr", "dscr_min", "dscr_avg", "llcr", "plcr"]
    assert any(tool["name"] == "get_series" for tool in caps.json()["tools"])
    assert b"fas_http_requests_total" in metrics.content or metrics.status_code == 200


async def test_series_and_expression_match_excel_cache(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fas") as client:
        headers = {"X-User-Id": "alex", "X-Client-Id": "desk"}
        loaded = await client.post(f"/v1/books/{JOB}:load", headers=headers)
        assert loaded.status_code == 200, loaded.text
        assert loaded.json()["job_id"] == JOB
        assert all(item["code"] != "builder_warning" for item in loaded.json()["warnings"])
        series = await client.post(
            f"/v1/books/{JOB}/series",
            headers=headers,
            json={"row_keys": [PACKT_REVENUE_ROW], "periods": [PACKT_PERIOD]},
        )
        assert series.status_code == 200, series.text
        rows = series.json()["result_data"]["series"]
        assert rows[0]["value"] == PACKT_REVENUE_VALUE
        assert rows[0]["cell_id"] == PACKT_REVENUE_CELL
        expression = await client.post(
            f"/v1/books/{JOB}/expression",
            headers=headers,
            json={
                "expression": "a - b",
                "bindings": {
                    "a": {"row_key": PACKT_TRAFFIC_PC_ROW, "period_id": PACKT_PERIOD},
                    "b": {"row_key": PACKT_TRAFFIC_HV_ROW, "period_id": PACKT_PERIOD},
                },
            },
        )
        assert expression.status_code == 200, expression.text
        assert expression.json()["result_data"]["expression"]["result"] == PACKT_TRAFFIC_DIFF
        resolved = await client.post(
            f"/v1/books/{JOB}/periods:resolve",
            headers=headers,
            json={"text": "первый операционный год"},
        )
        assert resolved.status_code == 200, resolved.text
        resolved_body = resolved.json()
        assert resolved_body["needs_input"] == []
        assert resolved_body["periods"][0]["period_id"] == "Y5"
        assert resolved_body["periods"][0]["basis"] == "nonzero_debt_service"
        assert resolved_body["periods"][0]["reason"] == "no_calendar_anchor"
        assert all(item["kind"] != "phase" for item in resolved_body["needs_input"])
        sliced = await client.post(
            f"/v1/books/{JOB}/slice",
            headers=headers,
            json={"measures": ["value_sum"], "dimensions": ["row_key"]},
        )
        assert sliced.status_code == 200, sliced.text
        bad = await client.get("/v1/books/" + ("g" * 64))
        assert bad.status_code == 400
        assert bad.json()["code"] == "invalid_id"
        bare = await client.post("/v1/books/" + JOB + "/series", json={})
        assert bare.status_code == 400


async def test_rvi_loads_from_summary_not_sidecar(app):
    rvi = job_id("rvi")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fas") as client:
        headers = {"X-User-Id": "alex", "X-Client-Id": "desk"}
        loaded = await client.post(f"/v1/books/{rvi}:load", headers=headers)
        assert loaded.status_code == 200, loaded.text
        body = loaded.json()
        assert set(body["builder_ref"]) == {
            "job_id",
            "summary_etag",
            "context_schema_version",
            "graph_schema_version",
        }
        assert body["builder_ref"]["summary_etag"].startswith('"summary-2:')
        assert body["is_latest"] is True
        assert all(item["code"] != "builder_degraded" for item in body["warnings"])
        cached = [item for item in body["warnings"] if item["code"] == "builder_warning"]
        assert cached
        assert "missing cached values" in cached[0]["params"]["message"]
        year = await client.post(f"/v1/books/{rvi}/periods:resolve", headers=headers, json={"text": "2024"})
        assert year.status_code == 200, year.text
        assert year.json()["periods"]
        marked = await client.post(
            f"/v1/books/{rvi}/periods:resolve",
            headers=headers,
            json={"text": "факт 2024"},
        )
        assert marked.status_code == 200, marked.text
        span = await client.post(
            f"/v1/books/{rvi}/periods:resolve",
            headers=headers,
            json={"text": "2030-2035"},
        )
        assert span.status_code == 200, span.text
        assert span.json()["periods"]


async def test_idempotency_and_actor(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fas") as client:
        headers = {"X-User-Id": "alex", "X-Client-Id": "desk", "Idempotency-Key": "k1"}
        first = await client.post(f"/v1/books/{JOB}:load", headers=headers)
        second = await client.post(f"/v1/books/{JOB}:load", headers=headers)
        assert first.status_code == second.status_code == 200
        assert first.json()["build_key"] == second.json()["build_key"]
        clash = await client.post(f"/v1/books/{JOB}:load", headers={**headers, "Idempotency-Key": "k1"}, content=b"{}")
        assert clash.status_code == 422
        assert app.fastapi.state.inflight == 0
        retry_headers = {"X-User-Id": "alex", "X-Client-Id": "desk", "Idempotency-Key": "broken"}
        bad = await client.post(
            f"/v1/books/{JOB}/series",
            headers={**retry_headers, "Content-Type": "application/json"},
            content=b"{",
        )
        assert bad.status_code == 400
        assert app.fastapi.state.inflight == 0
        again = await client.post(
            f"/v1/books/{JOB}/series",
            headers=retry_headers,
            json={"row_keys": [PACKT_REVENUE_ROW], "periods": [PACKT_PERIOD]},
        )
        assert again.status_code == 200
        assert app.fastapi.state.inflight == 0


async def test_rate_limit_429(settings, local_service, redis_runtime):
    settings.rate_user_rps = 1
    settings.rate_user_burst = 1
    app = create_app(settings, service=local_service, support=redis_runtime)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fas") as client:
        headers = {"X-User-Id": "quota-user", "X-Client-Id": "desk"}
        responses = []
        for _ in range(4):
            responses.append(await client.get("/v1/capabilities", headers=headers))
    limited = next(item for item in responses if item.status_code == 429)
    assert limited.headers["retry-after"]
    assert limited.json()["code"] == "rate_limited"


async def test_deadline_504_and_load_202(settings, local_service, redis_runtime):
    settings.sync_deadline_ms = 50

    async def slow_summary(job_id, etag):
        await asyncio.sleep(0.4)
        return await type(local_service.builder).summary(local_service.builder, job_id, etag)

    local_service.builder.summary = slow_summary
    app = create_app(settings, service=local_service, support=redis_runtime)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fas") as client:
        book = await client.get(f"/v1/books/{JOB}")
        assert book.status_code == 504
        assert book.headers["retry-after"]
        assert book.json()["code"] == "deadline_exceeded"
        accepted = await client.post(f"/v1/books/{JOB}:load", headers={"Prefer": "respond-async"})
        assert accepted.status_code == 202, accepted.text
        assert accepted.headers["operation-location"].startswith("/v1/operations/")
        op_id = accepted.json()["id"]
        waited = await client.get(f"/v1/operations/{op_id}", params={"wait_ms": 2000})
        assert waited.status_code == 200
        assert waited.json()["status"] in {"succeeded", "running", "failed"}


async def test_disconnect_cancels_handler(settings, local_service, redis_runtime):
    started = asyncio.Event()
    cancelled = asyncio.Event()
    original = local_service.builder.summary

    async def wrapped(job_id, etag):
        started.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return await original(job_id, etag)

    local_service.builder.summary = wrapped
    app = create_app(settings, service=local_service, support=redis_runtime)
    incoming: asyncio.Queue = asyncio.Queue()

    async def receive():
        return await incoming.get()

    async def send(message):
        return None

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": f"/v1/books/{JOB}",
        "raw_path": f"/v1/books/{JOB}".encode(),
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1234),
        "server": ("test", 80),
    }
    await incoming.put({"type": "http.request", "body": b"", "more_body": False})
    task = asyncio.create_task(app(scope, receive, send))
    await asyncio.wait_for(started.wait(), timeout=2)
    await incoming.put({"type": "http.disconnect"})
    await asyncio.wait_for(cancelled.wait(), timeout=2)
    await asyncio.wait_for(task, timeout=2)


async def test_query_without_book_is_not_planned(local_service):
    with pytest.raises(InvalidArgument):
        await local_service.query.sql(JOB, "SELECT 1", pin=None)


async def test_redis_lock_excludes(redis_runtime):
    async with redis_runtime.lock("book:demo", 500) as first:
        with pytest.raises(TimeoutError):
            async with redis_runtime.lock("book:demo", 100):
                pass
        assert first.fence >= 1
    async with redis_runtime.lock("book:demo", 500) as second:
        assert second.fence == first.fence + 1
