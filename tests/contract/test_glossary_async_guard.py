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


async def test_transition_refreshes_heartbeat_until_it_finishes(app, local_service, redis_runtime):
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
        posted = await client.post(
            "/v1/glossary/transitions",
            headers={**HEADERS, "If-Match": etag},
            json={"version": version, "status": "active"},
        )
        assert posted.status_code == 202, posted.text
        op_id = posted.json()["id"]
        key = f"fas:op:{op_id}:hb"
        await asyncio.wait_for(started.wait(), 5)
        first = await redis_runtime.redis.get(key)
        await asyncio.sleep(0.12)
        second = await redis_runtime.redis.get(key)
        assert first and second and first != second
        release.set()
        done = await local_service.wait_op(op_id, 30_000)
        assert done["status"] == "succeeded", done
        after = await client.get("/v1/glossary", headers=HEADERS)
        assert after.json()["active"] == version
        assert after.json()["seq"] != before["seq"]
        await _absent(redis_runtime.redis, key)


async def test_closed_operation_does_not_activate_the_release(app, local_service):
    async def gate(_version: str) -> dict:
        running = await local_service.list_ops(kind="glossary.validate", job_id=None, status="running")
        await local_service.finish_op(
            running[0]["id"],
            "failed",
            error={"code": "dependency_unavailable", "detail": "нет метки живости"},
        )
        return _PASSED

    local_service.glossary.gate = gate
    async with _client(app) as client:
        version, etag, before = await _release(client)
        posted = await client.post(
            "/v1/glossary/transitions",
            headers={**HEADERS, "If-Match": etag},
            json={"version": version, "status": "active"},
        )
        assert posted.status_code == 202, posted.text
        done = await local_service.wait_op(posted.json()["id"], 30_000)
        assert done["status"] == "failed", done
        assert done["error"]["code"] == "dependency_unavailable"
        after = await client.get("/v1/glossary", headers=HEADERS)
        assert after.json()["active"] == before["active"]
        assert after.json()["seq"] == before["seq"]
        assert after.json()["active"] != version


async def test_cancel_flag_alone_blocks_the_head_write(app, local_service, redis_runtime):
    async def gate(_version: str) -> dict:
        running = await local_service.list_ops(kind="glossary.validate", job_id=None, status="running")
        await redis_runtime.cache_set(f"fas:op:{running[0]['id']}:cancel", b"1", 60)
        return _PASSED

    local_service.glossary.gate = gate
    async with _client(app) as client:
        version, etag, before = await _release(client)
        posted = await client.post(
            "/v1/glossary/transitions",
            headers={**HEADERS, "If-Match": etag},
            json={"version": version, "status": "active"},
        )
        assert posted.status_code == 202, posted.text
        done = await local_service.wait_op(posted.json()["id"], 30_000)
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
        posted = await client.post(
            "/v1/glossary/transitions",
            headers={**HEADERS, "If-Match": etag},
            json={"version": version, "status": "canary"},
        )
        assert posted.status_code == 202, posted.text
        op_id = posted.json()["id"]
        await asyncio.wait_for(started.wait(), 5)
        cancelled = await client.post(f"/v1/operations/{op_id}:cancel", headers=HEADERS)
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "cancelled"
        release.set()
        done = await local_service.wait_op(op_id, 30_000)
        assert done["status"] == "cancelled", done
        after = await client.get("/v1/glossary", headers=HEADERS)
        assert after.json()["canary"] == before["canary"]
        assert after.json()["seq"] == before["seq"]
        assert after.json()["active"] != version


async def test_cancel_during_proposal_shadow_does_not_accept(app, local_service, redis_runtime):
    async def gate(_version: str) -> dict:
        running = await local_service.list_ops(kind="glossary.validate", job_id=None, status="running")
        await redis_runtime.cache_set(f"fas:op:{running[0]['id']}:cancel", b"1", 60)
        return _PASSED

    local_service.glossary.gate = gate
    async with _client(app) as client:
        before = await client.get("/v1/glossary", headers=HEADERS)
        made = await client.post(
            "/v1/glossary/proposals",
            headers=HEADERS,
            json={"concept": "cfads", "kind": "alt", "lang": "en", "text": "черновик отмены"},
        )
        assert made.status_code == 200, made.text
        proposal_id = made.json()["id"]
        posted = await client.post(
            "/v1/glossary/proposals:decide",
            headers=HEADERS,
            json={"decisions": [{"id": proposal_id, "decision": "accept"}]},
        )
        assert posted.status_code == 202, posted.text
        done = await local_service.wait_op(posted.json()["id"], 30_000)
        assert done["status"] == "cancelled", done
        after = await client.get("/v1/glossary", headers=HEADERS)
        assert after.json()["active"] == before.json()["active"]
        proposal = await client.get(f"/v1/glossary/proposals/{proposal_id}", headers=HEADERS)
        assert proposal.json()["status"] == "open"


async def test_require_match_does_not_wait_on_the_shadow_lock(local_service):
    await local_service.glossary.ensure()
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
        first = await client.post(
            "/v1/glossary/transitions",
            headers={**HEADERS, "If-Match": etag},
            json={"version": version, "status": "active"},
        )
        assert first.status_code == 202, first.text
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
        done = await local_service.wait_op(first.json()["id"], 30_000)
        assert done["status"] == "succeeded", done


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



