"""Предложение человека становится релизом. Повторное решение — 409."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from finance_analysis.adapters.api.app import create_app

pytestmark = pytest.mark.asyncio
HEADERS = {"X-User-Id": "alex", "X-Client-Id": "desk"}


@pytest.fixture
def app(settings, local_service, redis_runtime):
    return create_app(settings, service=local_service, support=redis_runtime)


def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://fas")


async def test_accept_edits_text_and_reject_writes_no_release(app, local_service):
    async with _client(app) as client:
        made = await client.post(
            "/v1/glossary/proposals",
            headers=HEADERS,
            json={"concept": "cfads", "kind": "alt", "lang": "en", "text": "черновик"},
        )
        assert made.status_code == 200, made.text
        proposal_id = made.json()["id"]
        listed = await client.get("/v1/glossary/proposals", headers=HEADERS)
        assert any(item["id"] == proposal_id for item in listed.json()["proposals"])
        one = await client.get(f"/v1/glossary/proposals/{proposal_id}", headers=HEADERS)
        assert one.json()["status"] == "open"
        accepted = await client.post(
            "/v1/glossary/proposals:decide",
            headers=HEADERS,
            json={"decisions": [{"id": proposal_id, "decision": "accept", "text": "принятая метка"}]},
        )
        assert accepted.status_code == 202, accepted.text
        done = await local_service.wait_op(accepted.json()["id"], 120_000)
        assert done["status"] == "succeeded", done
        assert done["result"]["release"]["status"] == "active"
        content = await client.get("/v1/glossary/content", headers=HEADERS)
        assert "принятая метка" in content.text
        again = await client.post(
            "/v1/glossary/proposals:decide",
            headers=HEADERS,
            json={"decisions": [{"id": proposal_id, "decision": "reject"}]},
        )
        assert again.status_code == 409
        assert again.json()["code"] == "proposal_decided"

        other = await client.post(
            "/v1/glossary/proposals",
            headers=HEADERS,
            json={"concept": "cfads", "kind": "alt", "lang": "en", "text": "не брать"},
        )
        state = await client.get("/v1/glossary", headers=HEADERS)
        rejected = await client.post(
            "/v1/glossary/proposals:decide",
            headers=HEADERS,
            json={"decisions": [{"id": other.json()["id"], "decision": "reject"}]},
        )
        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["release"] is None
        after = await client.get("/v1/glossary", headers=HEADERS)
        assert after.json()["seq"] == state.json()["seq"]
