"""Проверка зависших операций не считает пустой повтор успехом."""

from __future__ import annotations

import json
import time

import pytest

from finance_analysis.adapters.queue import runtime as runtime_mod
from finance_analysis.adapters.queue.runtime import WorkerRuntime
from finance_analysis.adapters.queue.tasks import _stage, reconcile_operations
from finance_analysis.application import keys
from finance_analysis.application.operations import create_op
from finance_analysis.domain.book import Actor

pytestmark = pytest.mark.asyncio


class _Broker:
    def __init__(self) -> None:
        self.payloads: list[dict] = []

    def find_task(self, _name: str):
        return self

    def kicker(self):
        return self

    def with_labels(self, **_kwargs):
        return self

    async def kiq(self, payload: dict) -> None:
        self.payloads.append(payload)


async def _backdate(local_service, op_id: str) -> None:
    key = keys.operation_key(op_id)
    body = json.loads(await local_service.store.get(key))
    body["created_at"] = "2020-01-01T00:00:00Z"
    await local_service.store.put(key, json.dumps(body).encode())


async def test_expired_lease_fails_a_stageless_load_and_a_stage_resumes(local_service, redis_runtime):
    stuck = await create_op(
        local_service.store,
        "book.load",
        "packt",
        Actor(user_id="alex"),
        {},
        owner="previous-process",
    )
    await _backdate(local_service, stuck["id"])
    await redis_runtime.cache_set("fas:api:previous-process", b"1", 60)
    assert await local_service.sweep_orphans() == 0
    assert (await local_service.get_op(stuck["id"]))["status"] == "running"

    broker = _Broker()
    runtime_mod.RUNTIME = WorkerRuntime(
        settings=local_service.settings,
        redis=redis_runtime.redis,
        store=local_service.store,
        schedule=None,
        broker=broker,
        locks=redis_runtime,
    )
    try:
        left = await reconcile_operations()
        assert left == {"resent": 0, "closed": 0}
        assert (await local_service.get_op(stuck["id"]))["status"] == "running"
        assert broker.payloads == []

        await redis_runtime.cache_delete("fas:api:previous-process")
        closed = await reconcile_operations()
        assert closed == {"resent": 0, "closed": 1}
        failed = await local_service.get_op(stuck["id"])
        assert failed["status"] == "failed"
        assert failed["error"]["code"] == "interrupted"
        assert failed["error"]["type"] == "urn:fas:problem:interrupted"
        assert broker.payloads == []

        missing = await _stage(None, {"op_id": stuck["id"]}, 1)
        assert missing["ok"] is False
        assert missing["status"] == "failed"
        assert missing["error"]["code"] == "interrupted"

        replay = await create_op(
            local_service.store,
            "book.load",
            "packt",
            Actor(user_id="alex"),
            {"stage": "marker", "idempotent": True, "queue": "fas:interactive"},
            owner="previous-process",
        )
        await _backdate(local_service, replay["id"])
        resent = await reconcile_operations()
        assert resent == {"resent": 1, "closed": 0}
        assert broker.payloads[0]["op_id"] == replay["id"]
        assert broker.payloads[0]["stage"] == "marker"
        assert (await local_service.get_op(replay["id"]))["status"] == "running"
        await redis_runtime.cache_set(f"fas:op:{replay['id']}:hb", f"1:{time.time()}".encode(), 60)

        plain = await create_op(
            local_service.store,
            "analysis",
            None,
            Actor(user_id="alex"),
            {"stage": "sleep"},
            owner="previous-process",
        )
        await _backdate(local_service, plain["id"])
        other = await reconcile_operations()
        assert other == {"resent": 0, "closed": 1}
        stalled = await local_service.get_op(plain["id"])
        assert stalled["status"] == "failed"
        assert stalled["error"]["code"] == "dependency_unavailable"
    finally:
        runtime_mod.RUNTIME = None
