"""Фаза 3b: снимок ремапа, откат inferred и GET /v1/glossary/stats."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from finance_analysis.adapters.api.app import create_app
from finance_analysis.application.catalog import load_catalog
from finance_analysis.application.metrics import GLOSSARY_REVIEW_OPEN
from finance_analysis.domain.book import Actor
from finance_analysis.domain.errors import GlossaryRegression
from tests.books import job_id
from tests.conftest import JOB

pytestmark = pytest.mark.asyncio
HEADERS = {"X-User-Id": "alex", "X-Client-Id": "desk"}
RVI = job_id("rvi")


@pytest.fixture
def app(settings, local_service, redis_runtime):
    return create_app(settings, service=local_service, support=redis_runtime)


async def test_glossary_stats_on_signals(app, local_service):
    catalog = load_catalog()
    rows = {"k": {"binding_key": "k", "row_key": "k", "label": "Lender cash", "label_path_text": "Lender cash"}}
    record = {"seq": 1, "type": "concept.confirmed", "binding_key": "k", "value": "cfads", "actor": {"user_id": "u1"}}
    await local_service.learning.record_decisions(
        "job", [record], rows=rows, bindings={}, events=[record], profile="acme", glossary_version="g", package=catalog
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fas") as client:
        bad = await client.get("/v1/glossary/stats", headers=HEADERS, params={"from": "yesterday"})
        assert bad.status_code == 400
        ok = await client.get("/v1/glossary/stats", headers=HEADERS, params={"profile_id": "acme"})
        assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["auto"]["rollback_rate"] is None
    assert body["review"]["open"] >= 1
    assert "unknown_by_month" in body and "lf_accuracy" in body
    assert GLOSSARY_REVIEW_OPEN._value.get() >= 1


async def test_remap_batch_snapshot_and_rollback_restores_inferred(local_service):
    # Книга пинит глоссарий при загрузке. Голова должна уже существовать, иначе pin остаётся none.
    await local_service.glossary.ensure()
    await local_service.perform_load(JOB, actor=Actor(), fence=1)
    await local_service.perform_load(RVI, actor=Actor(), fence=1)
    state = await local_service.glossary.ensure()
    before = state["active"]
    released = await local_service.glossary.release(
        [{"op": "add_label", "concept": "cfads", "kind": "alt", "lang": "en", "text": "zz canary token"}],
        f"h-{state['seq']}",
    )
    await local_service.glossary.transition(released["version"], "active", released["etag"])
    moved = await local_service.remap_glossary(limit=1)
    first, second = sorted((JOB, RVI))
    assert moved["jobs"] == [first] and second in moved["remaining"]
    stayed = (await local_service._read_head(second))[0]
    shifted = (await local_service._read_head(first))[0]
    assert stayed.versions["glossary"] == before
    assert shifted.versions["glossary"] == released["version"]
    view = await local_service.describe(second, stayed, fresh=False)
    assert view.body["versions"]["glossary"] == before

    head = (await local_service._read_head(RVI))[0]
    rows = await local_service._dataset_rows(RVI, head, "dim_row")
    cfads = next(row for row in rows if row["label"] == "CFADS" and row["kind"] == "fact")
    debt = next(row for row in rows if row["label"] == "Total debt service" and row["kind"] == "fact")
    posted = await local_service.submit_decisions(
        RVI,
        {"decisions": [{"kind": "concept.set", "target": debt["binding_key"], "value": "debt_service", "expected_seq": None}]},
        Actor(),
        wait_sec=60,
    )
    assert posted["results"][0]["status"] == "accepted", posted
    state = await local_service.glossary.ensure()
    removed = await local_service.glossary.release(
        [{"op": "remove_label", "concept": "cfads", "kind": "alt", "lang": "en", "text": "CFADS"}],
        f"h-{state['seq']}",
    )
    with pytest.raises(GlossaryRegression):
        await local_service.glossary.transition(removed["version"], "active", removed["etag"])
    await local_service.glossary.transition(
        removed["version"], "active", removed["etag"], force=True, reason="тест отката метки"
    )
    await local_service.remap_glossary()
    fresh = (await local_service._read_head(RVI))[0]
    bindings = await local_service._dataset_rows(RVI, fresh, "bindings")
    dropped = next(row for row in bindings if row["binding_key"] == cfads["binding_key"])
    kept = next(row for row in bindings if row["binding_key"] == debt["binding_key"])
    assert dropped["status"] == "unknown"
    assert kept["source"] == "confirmed" and kept["effective_concept"] == "debt_service"

    await local_service.glossary.rollback(f"h-{(await local_service.glossary.ensure())['seq']}")
    await local_service.remap_glossary()
    restored_head = (await local_service._read_head(RVI))[0]
    restored = await local_service._dataset_rows(RVI, restored_head, "bindings")
    back = next(row for row in restored if row["binding_key"] == cfads["binding_key"])
    still = next(row for row in restored if row["binding_key"] == debt["binding_key"])
    # Стадия 6 поднимает лексическую строку до verified, когда cfads, debt_service и dscr сходятся.
    assert back["status"] == "bound" and back["effective_concept"] == "cfads" and back["source"] in {"inferred", "verified"}
    assert still["source"] == "confirmed" and still["effective_concept"] == "debt_service"
