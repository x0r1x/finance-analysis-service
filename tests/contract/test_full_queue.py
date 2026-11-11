"""`type: full` ставит задачу в Taskiq, а не в in-process spawn."""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from finance_analysis.adapters.api.app import create_app
from finance_analysis.adapters.queue.jobs import TaskiqJobs
from finance_analysis.adapters.queue.names import INTERACTIVE
from finance_analysis.application import keys
from finance_analysis.domain.book import Actor
from tests.books import job_id
from tests.chaos.harness import WorkerProc
from tests.conftest import BUILDER_ROOT

pytestmark = pytest.mark.asyncio

RVI = job_id("rvi")
HEADERS = {"X-User-Id": "alex", "X-Client-Id": "desk"}


@pytest.fixture
def app(settings, local_service, redis_runtime):
    return create_app(settings, service=local_service, support=redis_runtime)


def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://fas", timeout=120)


async def test_full_submits_to_interactive_queue(app, local_service, task_workers):
    await local_service.perform_load(RVI, actor=Actor(), fence=1)
    head, _token = await local_service._read_head(RVI)
    assert head is not None
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
    args = operation["payload"]["stage_args"]
    assert args["job_id"] == RVI
    assert args["metrics"] == ["dscr"]
    assert args["build_key"] == head.build_key
    assert args["state_seq"] == head.state_seq
    assert args["derive_key"] == head.derive_key
    assert args["analysis_semantic_model"]
    assert posted.headers["operation-location"] == f"/v1/operations/{operation['id']}"

    done = await local_service.wait_op(operation["id"], 120_000)
    assert done["status"] == "succeeded", done
    assert done["result"]["analysis_id"] == operation["payload"]["analysis_id"]
    assert done["result"]["resource"].endswith(done["result"]["analysis_id"])


async def test_full_worker_uses_enqueue_snapshot_not_live_head(app, local_service, settings, tmp_path):
    """После постановки голова книги может уйти вперёд; worker считает по pins."""

    jobs = await TaskiqJobs.open(settings)
    await jobs.startup()
    local_service.jobs = jobs
    worker = None
    try:
        await local_service.perform_load(RVI, actor=Actor(), fence=1)
        head, token = await local_service._read_head(RVI)
        assert head is not None and token
        async with _client(app) as client:
            posted = await client.post(
                f"/v1/books/{RVI}/analyses",
                headers=HEADERS,
                json={"type": "full", "metrics": ["dscr"]},
            )
        assert posted.status_code == 202, posted.text
        operation = posted.json()
        args = operation["payload"]["stage_args"]
        assert args["build_key"] == head.build_key
        assert args["state_seq"] == head.state_seq
        assert args["derive_key"] == head.derive_key
        assert args["analysis_semantic_model"]

        advanced = {
            **head.as_dict(),
            "state_seq": head.state_seq + 999,
            "derive_key": "advanced-derive-not-used-by-full",
        }
        await local_service.store.put_if_match(keys.head_key(RVI), json.dumps(advanced).encode(), token)
        live, _ = await local_service._read_head(RVI)
        assert live is not None
        assert live.state_seq == head.state_seq + 999
        assert live.derive_key == "advanced-derive-not-used-by-full"

        worker = WorkerProc(
            settings,
            tmp_path,
            "interactive-snapshot",
            queue=INTERACTIVE,
            extra={"FAS_FIXTURE_DIR": str(BUILDER_ROOT)},
        )
        worker.wait_ready(40)

        done = await local_service.wait_op(operation["id"], 120_000)
        assert done["status"] == "succeeded", done
        stored = await local_service.analyses.result(RVI, args["analysis_id"])
        assert stored["build_key"] == head.build_key
        assert stored["versions"]["state_seq"] == head.state_seq
        assert stored["versions"]["derive_key"] == head.derive_key
        assert stored["versions"]["state_seq"] != live.state_seq
        assert stored["is_latest"] is False
    finally:
        if worker is not None:
            worker.stop()
        local_service.jobs = None
        await jobs.shutdown()
