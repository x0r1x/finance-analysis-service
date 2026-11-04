"""Фоновый переход глоссария не расходится с проверкой зависших операций."""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from finance_analysis.adapters.api.app import create_app

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
