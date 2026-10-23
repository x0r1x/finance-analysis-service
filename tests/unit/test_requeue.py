"""fas ops requeue: запись fas:dlq снова попадает в очередь (§4.13.5)."""

from __future__ import annotations

import json

from finance_analysis.adapters.queue.names import DLQ
from finance_analysis.adapters.queue.requeue import requeue_dlq
from finance_analysis.adapters.storage.store import LocalStore
from finance_analysis.application.operations import append_event, create_op, read_op
from finance_analysis.domain.book import Actor


async def test_requeue_resets_attempt_and_removes_dlq_entry(redis_runtime, tmp_path):
    store = LocalStore(tmp_path / "ops")
    operation = await create_op(store, "analysis", None, Actor(), {"stage": "sleep"})
    await append_event(store, operation["id"], {"status": "failed", "error": {"code": "poison_task"}})
    payload = {"op_id": operation["id"], "queue": "fas:interactive", "stage": "sleep"}
    await redis_runtime.redis.set(f"fas:op:{operation['id']}:attempt", "4")
    await redis_runtime.redis.xadd(
        DLQ,
        {"op_id": operation["id"], "reason": "poison_task", "payload": json.dumps(payload)},
    )
    kicked: list[dict] = []

    async def kick(body: dict) -> None:
        kicked.append(body)

    report = await requeue_dlq(redis_runtime.redis, store, kick)
    assert report["requeued"] == 1
    assert kicked == [payload]
    assert await redis_runtime.redis.xlen(DLQ) == 0
    assert await redis_runtime.redis.get(f"fas:op:{operation['id']}:attempt") is None
    current = await read_op(store, operation["id"])
    assert current["status"] == "running"


async def test_requeue_one_entry_leaves_the_rest(redis_runtime, tmp_path):
    store = LocalStore(tmp_path / "ops")
    first = await redis_runtime.redis.xadd(DLQ, {"op_id": "a", "reason": "x", "payload": "{}"})
    await redis_runtime.redis.xadd(DLQ, {"op_id": "b", "reason": "y", "payload": "{}"})
    message_id = first.decode() if isinstance(first, bytes) else str(first)
    kicked: list[dict] = []

    async def kick(body: dict) -> None:
        kicked.append(body)

    report = await requeue_dlq(redis_runtime.redis, store, kick, entry_id=message_id)
    assert report["requeued"] == 1
    assert await redis_runtime.redis.xlen(DLQ) == 1
    assert kicked == [{}]
