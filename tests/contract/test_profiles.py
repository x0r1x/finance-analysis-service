"""Профиль: конвенция знака и класс маркера. Ставки в теле нет."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from finance_analysis.adapters.api.app import create_app
from finance_analysis.domain.book import Actor
from tests.conftest import JOB

pytestmark = pytest.mark.asyncio
HEADERS = {"X-User-Id": "alex", "X-Client-Id": "desk"}


@pytest.fixture
def app(settings, local_service, redis_runtime):
    return create_app(settings, service=local_service, support=redis_runtime)


def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://fas")


async def test_profile_etag_and_derive_key(app, local_service):
    async with _client(app) as client:
        extra = await client.put(
            "/v1/profiles/bank",
            headers={**HEADERS, "If-None-Match": "*"},
            json={"sign_convention": "outflow_negative", "rate": "0.08"},
        )
        assert extra.status_code == 400
        assert extra.json()["fields"] == ["rate"]
        created = await client.put(
            "/v1/profiles/bank",
            headers={**HEADERS, "If-None-Match": "*"},
            json={"sign_convention": "outflow_positive", "marker_class": "actual"},
        )
        assert created.status_code == 200, created.text
        assert created.headers["etag"] == "p-1"
        listed = await client.get("/v1/profiles", headers=HEADERS)
        assert listed.status_code == 200, listed.text
        assert {"id": "bank", "etag": "p-1"} in listed.json()["profiles"]
        missing = await client.put(
            "/v1/profiles/bank",
            headers=HEADERS,
            json={"marker_class": "plan"},
        )
        assert missing.status_code == 428
        wrong = await client.put(
            "/v1/profiles/bank",
            headers={**HEADERS, "If-Match": "p-9"},
            json={"marker_class": "plan"},
        )
        assert wrong.status_code == 412
        assert wrong.json()["etag"] == "p-1"

    await local_service.perform_load(JOB, actor=Actor(), fence=1)
    head = (await local_service._read_head(JOB))[0]
    posted = await local_service.submit_decisions(
        JOB,
        {"decisions": [{"kind": "profile.set", "target": "book", "value": "bank", "expected_seq": None}]},
        Actor(),
        wait_sec=60,
    )
    assert posted["results"][0]["status"] == "accepted", posted
    fresh = (await local_service._read_head(JOB))[0]
    assert fresh.derive_key != head.derive_key
    assert fresh.versions["profile"] == "bank@p-1"


async def test_profile_rejects_a_covenant_concept_outside_the_contract(app):
    foreign = {
        "numerator": {"plus": ["revenue"]},
        "denominator": {"plus": ["interest"]},
        "window": "LTM",
    }
    allowed = {
        "numerator": {"plus": ["ebitda"], "minus": ["cash_taxes"]},
        "denominator": {"plus": ["interest", "principal"]},
        "window": "LTM",
        "basis_ref": "кредитный договор, п. 4.2",
    }
    async with _client(app) as client:
        denied = await client.put(
            "/v1/profiles/covenant",
            headers={**HEADERS, "If-None-Match": "*"},
            json={"dscr_definition": foreign},
        )
        assert denied.status_code == 400, denied.text
        assert denied.json()["code"] == "invalid_argument"
        assert "необъявленные профильные входы: revenue" in denied.json()["detail"]
        missing = await client.get("/v1/profiles/covenant", headers=HEADERS)
        assert missing.status_code == 404

        created = await client.put(
            "/v1/profiles/covenant",
            headers={**HEADERS, "If-None-Match": "*"},
            json={"dscr_definition": allowed},
        )
        assert created.status_code == 200, created.text
        saved = await client.get("/v1/profiles/covenant", headers=HEADERS)
        assert saved.status_code == 200, saved.text
        assert saved.json()["body"]["dscr_definition"] == allowed

        replaced = await client.put(
            "/v1/profiles/covenant",
            headers={**HEADERS, "If-Match": created.headers["etag"]},
            json={"dscr_definition": foreign},
        )
        assert replaced.status_code == 400, replaced.text
        kept = await client.get("/v1/profiles/covenant", headers=HEADERS)
        assert kept.json()["body"]["dscr_definition"] == allowed


async def test_profile_put_requires_admin_token_when_configured(app, settings):
    settings.fas_admin_token = "secret"
    async with _client(app) as client:
        denied = await client.put(
            "/v1/profiles/bank",
            headers={**HEADERS, "If-None-Match": "*"},
            json={"sign_convention": "outflow_positive", "marker_class": "actual"},
        )
        assert denied.status_code == 403
        assert denied.json()["code"] == "admin_token_required"
        created = await client.put(
            "/v1/profiles/bank",
            headers={**HEADERS, "If-None-Match": "*", "X-Admin-Token": "secret"},
            json={"sign_convention": "outflow_positive", "marker_class": "actual"},
        )
        assert created.status_code == 200, created.text
