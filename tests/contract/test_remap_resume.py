"""Хвост пересчёта глоссария не закрывается успехом, пока книги ещё остались."""

from __future__ import annotations

import asyncio

import pytest

from finance_analysis.adapters.queue.tasks import _SERVICE_STAGES
from finance_analysis.domain.book import Actor

pytestmark = pytest.mark.asyncio


def _install(local_service, fake) -> None:
    local_service.remap_glossary = fake
    local_service.settings.remap_batch_books = 1
    local_service.settings.remap_books_per_min = 6000


async def _wait_calls(calls: list, predicate, timeout: float = 2) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError(calls)


async def test_remap_stays_running_with_heartbeat_until_the_tail_is_done(local_service):
    gate = asyncio.Event()
    calls: list[tuple] = []

    async def fake(*, limit=None, cursor=None):
        calls.append((limit, cursor))
        if limit is None:
            return {"jobs": ["job-a", "job-b", "job-c"], "remaining": [], "glossary": "g1", "cursor": "job-c"}
        if cursor is None:
            return {"jobs": ["job-a"], "remaining": ["job-b", "job-c"], "glossary": "g1", "cursor": "job-a"}
        if cursor == "job-a":
            await gate.wait()
            return {"jobs": ["job-b"], "remaining": ["job-c"], "glossary": "g1", "cursor": "job-b"}
        return {"jobs": ["job-c"], "remaining": [], "glossary": "g1", "cursor": "job-c"}

    _install(local_service, fake)
    started = await local_service.begin_remap()
    op_id = started["operation"]
    await _wait_calls(calls, lambda: (1, "job-a") in calls)

    current = await local_service.get_op(op_id)
    assert current["status"] == "running"
    assert current["payload"]["stage"] == "glossary.remap"
    assert current["payload"]["stage_args"]["cursor"] == "job-a"
    assert current["payload"]["queue"] == "fas:glossary"
    assert await local_service.support.cache_get(f"fas:op:{op_id}:hb")
    assert _SERVICE_STAGES["glossary.remap"] == "perform_glossary_remap"

    gate.set()
    done = await local_service.wait_op(op_id, 5000)
    assert done["status"] == "succeeded", done
    assert any(limit is None for limit, _cursor in calls)
    assert (1, "job-b") in calls


async def test_remap_requeue_resumes_from_the_payload_cursor(local_service):
    gate = asyncio.Event()
    calls: list[tuple] = []

    async def fake(*, limit=None, cursor=None):
        calls.append((limit, cursor))
        if limit is None:
            return {"jobs": ["job-b"], "remaining": [], "glossary": "g1", "cursor": "job-b"}
        if cursor == "job-a":
            await gate.wait()
            return {"jobs": ["job-b"], "remaining": [], "glossary": "g1", "cursor": "job-b"}
        raise AssertionError(f"пересчёт начался не с курсора: {limit} {cursor}")

    _install(local_service, fake)
    op = await local_service.create_op(
        "glossary.remap",
        None,
        Actor(user_id="system"),
        {"stage": "glossary.remap", "stage_args": {"cursor": "job-a"}, "queue": "fas:glossary"},
    )
    task = asyncio.create_task(local_service.perform_glossary_remap(op_id=op["id"]))
    await _wait_calls(calls, lambda: calls == [(1, "job-a")])
    assert (await local_service.get_op(op["id"]))["status"] == "running"
    assert await local_service.support.cache_get(f"fas:op:{op['id']}:hb")
    gate.set()
    result = await task
    assert result["remaining"] == []
    assert (await local_service.get_op(op["id"]))["status"] == "running"
    assert any(limit is None for limit, _cursor in calls)
