"""Старт API закрывает операции умершего процесса и не трогает очередь воркера."""

from __future__ import annotations

import pytest

from finance_analysis.application.operations import create_op
from finance_analysis.domain.book import Actor

pytestmark = pytest.mark.asyncio


async def test_startup_sweep_fails_orphans_and_keeps_worker_ops(local_service, redis_runtime):
    mine = await local_service.create_op("mapping.infer", "packt", Actor(user_id="alex"), {})
    gone = await create_op(
        local_service.store,
        "glossary.validate",
        None,
        Actor(user_id="alex"),
        {},
        owner="previous-process",
    )
    queued = await create_op(
        local_service.store,
        "glossary.validate",
        None,
        Actor(user_id="alex"),
        {"queue": "fas:glossary", "stage": "glossary.transition"},
        owner="worker",
    )
    beating = await create_op(
        local_service.store,
        "mapping.infer",
        "packt",
        Actor(user_id="alex"),
        {},
        owner="worker-process",
    )
    await redis_runtime.cache_set(f"fas:op:{beating['id']}:hb", b"1:1", 60)
    leased = await create_op(
        local_service.store,
        "analysis",
        None,
        Actor(user_id="alex"),
        {},
        owner="other-replica",
    )
    await redis_runtime.cache_set("fas:api:other-replica", b"1", 60)

    assert await local_service.sweep_orphans() == 1

    assert (await local_service.get_op(mine["id"]))["status"] == "running"
    assert (await local_service.get_op(queued["id"]))["status"] == "running"
    assert (await local_service.get_op(beating["id"]))["status"] == "running"
    assert (await local_service.get_op(leased["id"]))["status"] == "running"
    failed = await local_service.get_op(gone["id"])
    assert failed["status"] == "failed"
    assert failed["error"]["type"] == "urn:fas:problem:interrupted"
    assert failed["error"]["detail"] == "операция прервана перезапуском"
    assert failed["error"]["retryable"] is True
