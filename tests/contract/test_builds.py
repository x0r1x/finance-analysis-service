"""История сборок читается только из `_builds/`."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from finance_analysis.adapters.api.app import create_app
from finance_analysis.domain.book import Actor
from tests.conftest import JOB

pytestmark = pytest.mark.asyncio


async def test_build_history_lists_only_the_index(settings, local_service, redis_runtime):
    actor = Actor(user_id="reader", client_id="desk")
    head = await local_service.perform_load(JOB, actor=actor, fence=1)
    seen: list[str] = []
    original = local_service.store.list

    async def tracking(prefix):
        seen.append(prefix)
        async for item in original(prefix):
            yield item

    local_service.store.list = tracking
    app = create_app(settings, service=local_service, support=redis_runtime)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fas") as client:
        listing = await client.get(f"/v1/books/{JOB}/builds")
        history = list(seen)
        seen.clear()
        one = await client.get(f"/v1/books/{JOB}/builds/{head.build_key}")
    assert listing.status_code == 200
    body = listing.json()
    assert body["items"]
    assert body["items"][0]["build_key"] == head.build_key
    assert body["items"][0]["current"] is True
    assert body["next_page_token"] is None
    assert history == [f"books/{JOB}/_builds/"]
    assert one.status_code == 200
    detail = one.json()
    assert detail["index"]["build_key"] == head.build_key
    assert detail["manifest"]["build_key"] == head.build_key
    assert detail["derived"]
    assert f"books/{JOB}" not in seen
    assert f"books/{JOB}/" not in seen
