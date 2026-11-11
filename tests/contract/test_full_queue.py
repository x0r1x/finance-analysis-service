"""`type: full` ставит задачу в Taskiq, а не в in-process spawn."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from finance_analysis.adapters.api.app import create_app
from tests.books import job_id

pytestmark = pytest.mark.asyncio

RVI = job_id("rvi")
HEADERS = {"X-User-Id": "alex", "X-Client-Id": "desk"}


@pytest.fixture
def app(settings, local_service, redis_runtime):
    return create_app(settings, service=local_service, support=redis_runtime)


def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://fas", timeout=120)


async def test_full_submits_to_interactive_queue(app, local_service, task_workers):
    async with _client(app) as client:
        posted = await client.post(
            f"/v1/books/{RVI}/analyses",
            headers=HEADERS,
            json={"type": "full", "metrics": ["dscr"]},
        )
    assert posted.status_code == 202, posted.text
    operation = posted.json()
    assert operation["kind"] == "analysis"
    assert operation["payload"]["queue"] == "fas:interactive"
    assert operation["payload"]["stage"] == "analysis.full"
    assert operation["payload"]["type"] == "full"
    assert operation["payload"]["analysis_id"]
    assert operation["payload"]["stage_args"]["job_id"] == RVI
    assert operation["payload"]["stage_args"]["metrics"] == ["dscr"]
    assert posted.headers["operation-location"] == f"/v1/operations/{operation['id']}"

    done = await local_service.wait_op(operation["id"], 120_000)
    assert done["status"] == "succeeded", done
    assert done["result"]["analysis_id"] == operation["payload"]["analysis_id"]
    assert done["result"]["resource"].endswith(done["result"]["analysis_id"])
