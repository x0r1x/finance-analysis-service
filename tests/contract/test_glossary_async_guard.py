"""Фоновый переход глоссария не расходится с проверкой зависших операций."""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from finance_analysis.adapters.api.app import create_app
from finance_analysis.domain.book import Actor
from finance_analysis.domain.errors import PreconditionFailed

pytestmark = pytest.mark.asyncio
HEADERS = {"X-User-Id": "alex", "X-Client-Id": "desk"}
_PREF = {"op": "set_pref", "concept": "cfads", "kind": "pref", "lang": "en", "text": "Flow for debt"}
_PASSED = {"passed": True, "reasons": [], "eval": {}, "books": [], "path": "test"}


@pytest.fixture
def app(settings, local_service, redis_runtime):
    return create_app(settings, service=local_service, support=redis_runtime)


def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://fas")


async def _release(client: AsyncClient) -> tuple[str, str, dict]:
    boot = await client.post("/v1/glossary/bootstrap", headers=HEADERS, json={})
    assert boot.status_code == 200, boot.text
    state = await client.get("/v1/glossary", headers=HEADERS)
    assert state.status_code == 200, state.text
    made = await client.post(
        "/v1/glossary/releases",
        headers={**HEADERS, "If-Match": state.headers["etag"]},
        json={"ops": [_PREF]},
    )
    assert made.status_code == 200, made.text
    fresh = await client.get("/v1/glossary", headers=HEADERS)
    return made.json()["version"], made.headers["etag"], fresh.json()


async def _absent(redis, key: str) -> None:
    for _ in range(50):
        if await redis.get(key) is None:
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"ключ {key} не удалён")


async def _validate_op(local_service) -> dict:
    return await local_service.create_op(
        "glossary.validate",
        None,
        Actor(),
        {"stage": "glossary.transition"},
    )


async def test_transition_refreshes_heartbeat_until_it_finishes(app, local_service, redis_runtime):
    from types import SimpleNamespace

    from finance_analysis.adapters.queue.tasks import _beat

    local_service.settings.op_heartbeat_sec = 0.05
    started = asyncio.Event()
    release = asyncio.Event()

    async def gate(_version: str) -> dict:
        started.set()
        await release.wait()
        return _PASSED

    local_service.glossary.gate = gate
    async with _client(app) as client:
        version, etag, before = await _release(client)
        op = await _validate_op(local_service)
        key = f"fas:op:{op['id']}:hb"
        stop = asyncio.Event()
        beater = asyncio.create_task(
            _beat(SimpleNamespace(settings=local_service.settings, redis=redis_runtime.redis), op["id"], 1, stop)
        )
        task = asyncio.create_task(
            local_service.perform_glossary_transition(
                version, "active", etag, force=False, reason=None, op_id=op["id"]
            )
        )
        try:
            await asyncio.wait_for(started.wait(), 5)
            first = await redis_runtime.redis.get(key)
            await asyncio.sleep(0.12)
            second = await redis_runtime.redis.get(key)
            assert first and second and first != second
            release.set()
            result = await task
            assert result["status"] == "active"
            done = await local_service.finish_op(op["id"], "succeeded", result=result)
            assert done["status"] == "succeeded", done
            after = await client.get("/v1/glossary", headers=HEADERS)
            assert after.json()["active"] == version
            assert after.json()["seq"] != before["seq"]
        finally:
            release.set()
            stop.set()
            beater.cancel()
            await asyncio.gather(beater, task, return_exceptions=True)
            await redis_runtime.redis.delete(key)
        await _absent(redis_runtime.redis, key)


async def test_closed_operation_does_not_activate_the_release(app, local_service):
    op = await _validate_op(local_service)

    async def gate(_version: str) -> dict:
        await local_service.finish_op(
            op["id"],
            "failed",
            error={"code": "dependency_unavailable", "detail": "нет метки живости"},
        )
        return _PASSED

    local_service.glossary.gate = gate
    async with _client(app) as client:
        version, etag, before = await _release(client)
        result = await local_service.perform_glossary_transition(
            version, "active", etag, force=False, reason=None, op_id=op["id"]
        )
        assert result == {"skipped": True}
        done = await local_service.get_op(op["id"])
        assert done["status"] == "failed", done
        assert done["error"]["code"] == "dependency_unavailable"
        after = await client.get("/v1/glossary", headers=HEADERS)
        assert after.json()["active"] == before["active"]
        assert after.json()["seq"] == before["seq"]
        assert after.json()["active"] != version


async def test_cancel_flag_alone_blocks_the_head_write(app, local_service, redis_runtime):
    op = await _validate_op(local_service)

    async def gate(_version: str) -> dict:
        await redis_runtime.cache_set(f"fas:op:{op['id']}:cancel", b"1", 60)
        return _PASSED

    local_service.glossary.gate = gate
    async with _client(app) as client:
        version, etag, before = await _release(client)
        result = await local_service.perform_glossary_transition(
            version, "active", etag, force=False, reason=None, op_id=op["id"]
        )
        assert result == {"skipped": True}
        done = await local_service.get_op(op["id"])
        assert done["status"] == "cancelled", done
        after = await client.get("/v1/glossary", headers=HEADERS)
        assert after.json()["active"] == before["active"]
        assert after.json()["seq"] == before["seq"]


async def test_http_cancel_during_shadow_does_not_activate(app, local_service):
    started = asyncio.Event()
    release = asyncio.Event()

    async def gate(_version: str) -> dict:
        started.set()
        await release.wait()
        return _PASSED

    local_service.glossary.gate = gate
    async with _client(app) as client:
        version, etag, before = await _release(client)
        op = await _validate_op(local_service)
        task = asyncio.create_task(
            local_service.perform_glossary_transition(
                version, "canary", etag, force=False, reason=None, op_id=op["id"]
            )
        )
        try:
            await asyncio.wait_for(started.wait(), 5)
            cancelled = await client.post(f"/v1/operations/{op['id']}:cancel", headers=HEADERS)
            assert cancelled.status_code == 200, cancelled.text
            assert cancelled.json()["status"] == "cancelled"
            release.set()
            result = await task
            assert result == {"skipped": True}
            done = await local_service.get_op(op["id"])
            assert done["status"] == "cancelled", done
            after = await client.get("/v1/glossary", headers=HEADERS)
            assert after.json()["canary"] == before["canary"]
            assert after.json()["seq"] == before["seq"]
            assert after.json()["active"] != version
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)


async def test_cancel_during_proposal_shadow_does_not_accept(app, local_service, redis_runtime):
    op = await _validate_op(local_service)

    async def gate(_version: str) -> dict:
        await redis_runtime.cache_set(f"fas:op:{op['id']}:cancel", b"1", 60)
        return _PASSED

    local_service.glossary.gate = gate
    async with _client(app) as client:
        boot = await client.post("/v1/glossary/bootstrap", headers=HEADERS, json={})
        assert boot.status_code == 200, boot.text
        before = await client.get("/v1/glossary", headers=HEADERS)
        made = await client.post(
            "/v1/glossary/proposals",
            headers=HEADERS,
            json={"concept": "cfads", "kind": "alt", "lang": "en", "text": "черновик отмены"},
        )
        assert made.status_code == 200, made.text
        proposal_id = made.json()["id"]
        result = await local_service.perform_proposal_decision(
            [{"id": proposal_id, "decision": "accept"}],
            op_id=op["id"],
        )
        assert result == {"skipped": True}
        done = await local_service.get_op(op["id"])
        assert done["status"] == "cancelled", done
        after = await client.get("/v1/glossary", headers=HEADERS)
        assert after.json()["active"] == before.json()["active"]
        proposal = await client.get(f"/v1/glossary/proposals/{proposal_id}", headers=HEADERS)
        assert proposal.json()["status"] == "open"


async def test_require_match_does_not_wait_on_the_shadow_lock(local_service):
    await local_service.glossary.bootstrap()
    hold = asyncio.Event()
    acquired = asyncio.Event()

    async def occupy() -> None:
        async with local_service.glossary._lock:
            acquired.set()
            await hold.wait()

    task = asyncio.create_task(occupy())
    await asyncio.wait_for(acquired.wait(), 5)
    started = asyncio.get_running_loop().time()
    with pytest.raises(PreconditionFailed):
        await local_service.glossary.require_match("h-999")
    assert asyncio.get_running_loop().time() - started < 0.5
    hold.set()
    await task


async def test_second_transition_is_glossary_busy(app, local_service):
    started = asyncio.Event()
    release = asyncio.Event()

    async def gate(_version: str) -> dict:
        started.set()
        await release.wait()
        return _PASSED

    local_service.glossary.gate = gate
    async with _client(app) as client:
        version, etag, _before = await _release(client)
        op = await _validate_op(local_service)
        task = asyncio.create_task(
            local_service.perform_glossary_transition(
                version, "active", etag, force=False, reason=None, op_id=op["id"]
            )
        )
        try:
            await asyncio.wait_for(started.wait(), 5)
            began = asyncio.get_running_loop().time()
            second = await client.post(
                "/v1/glossary/transitions",
                headers={**HEADERS, "If-Match": "h-999"},
                json={"version": version, "status": "active"},
            )
            elapsed = asyncio.get_running_loop().time() - began
            assert elapsed < 1
            assert second.status_code == 409, second.text
            assert second.json()["code"] == "glossary_busy"
            release.set()
            result = await task
            assert result["status"] == "active"
            done = await local_service.finish_op(op["id"], "succeeded", result=result)
            assert done["status"] == "succeeded", done
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)


async def test_running_remap_rejects_a_transition(app, local_service):
    async with _client(app) as client:
        version, etag, _before = await _release(client)
        await local_service.create_op("glossary.remap", None, Actor(), {})
        began = asyncio.get_running_loop().time()
        posted = await client.post(
            "/v1/glossary/transitions",
            headers={**HEADERS, "If-Match": etag},
            json={"version": version, "status": "active"},
        )
        assert asyncio.get_running_loop().time() - began < 1
        assert posted.status_code == 409, posted.text
        assert posted.json()["code"] == "glossary_busy"


async def test_replayed_transition_succeeds_when_the_head_is_already_there(app, local_service):
    async with _client(app) as client:
        version, etag, _before = await _release(client)
        first = await local_service.perform_glossary_transition(
            version, "active", etag, force=False, reason=None
        )
        assert first["status"] == "active"
        settled = await client.get("/v1/glossary", headers=HEADERS)
        replay = await local_service.perform_glossary_transition(
            version, "active", etag, force=False, reason=None
        )
        assert replay["status"] == "active"
        assert replay["state"]["active"] == version
        again = await client.get("/v1/glossary", headers=HEADERS)
        assert again.json()["seq"] == settled.json()["seq"]
        assert again.headers["etag"] == settled.headers["etag"]
        with pytest.raises(PreconditionFailed):
            await local_service.perform_glossary_transition(
                version, "canary", etag, force=False, reason=None
            )


async def test_bad_status_is_409_and_force_without_reason_is_400(app):
    async with _client(app) as client:
        bad = await client.post(
            "/v1/glossary/transitions",
            headers=HEADERS,
            json={"version": "g-missing", "status": "retired"},
        )
        assert bad.status_code == 409, bad.text
        assert bad.json()["code"] == "invalid_transition"
        forced = await client.post(
            "/v1/glossary/transitions",
            headers=HEADERS,
            json={"version": "g-missing", "status": "active", "force": True},
        )
        assert forced.status_code == 400, forced.text
        assert forced.json()["code"] == "invalid_argument"



