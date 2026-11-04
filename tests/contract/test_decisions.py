"""Журнал: один пакет — одна свёртка, чужое понятие требует supersedes."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from finance_analysis.adapters.api.app import create_app
from finance_analysis.application.service import Accepted
from finance_analysis.domain.book import Actor
from tests.conftest import JOB

pytestmark = pytest.mark.asyncio
HEADERS = {"X-User-Id": "alex", "X-Client-Id": "desk"}


@pytest.fixture
def app(settings, local_service, redis_runtime):
    return create_app(settings, service=local_service, support=redis_runtime)


def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://fas")


async def test_mapping_infer_refolds(app, local_service, task_workers):
    await local_service.perform_load(JOB, actor=Actor(), fence=1)
    async with _client(app) as client:
        started = await client.post(f"/v1/books/{JOB}/mapping:infer", headers=HEADERS)
    assert started.status_code == 202, started.text
    assert started.json()["payload"]["queue"] == "fas:interactive"
    assert started.json()["payload"]["stage"] == "mapping.infer"
    done = await local_service.wait_op(started.json()["id"], 60_000)
    assert done["status"] == "succeeded", done
    assert done["result"]["derive_key"]
    assert done["result"]["build_key"]


async def test_packt_semantics_mapping_and_one_fold(app, local_service, task_workers):
    async with _client(app) as client:
        semantics = await client.get(f"/v1/books/{JOB}/semantics", headers=HEADERS)
        assert semantics.status_code == 200, semantics.text
        assert any(row["excluded"] and row["exclusion_reason"] == "check_row" for row in semantics.json()["rows"])
        assert all(row["phase"] is None for row in semantics.json()["periods"])
        mapping = await client.get(f"/v1/books/{JOB}/mapping", headers=HEADERS)
        assert mapping.status_code == 200, mapping.text
        assert sum(mapping.json()["counts"].values()) == len(mapping.json()["rows"])
        book = await client.get(f"/v1/books/{JOB}", headers=HEADERS)
        assert "row_coverage" in book.json()
        assert "covered" in book.json()["critical_path"]
        questions = await client.get(f"/v1/books/{JOB}/questions", headers=HEADERS)
        assert questions.status_code == 200
        for item in questions.json()["questions"]:
            assert len(item["question_id"]) == 40
            if item["kind"] == "concept":
                assert all("binding_key" in cand for cand in item["candidates"])
        inferred = await client.post(f"/v1/books/{JOB}/mapping:infer", headers=HEADERS)
        assert inferred.status_code == 202
        assert inferred.json()["kind"] == "mapping.infer"

    head = (await local_service._read_head(JOB))[0]
    old_derive = head.derive_key
    before = local_service.fold_runs
    rows = await local_service._dataset_rows(JOB, head, "dim_row")
    debt = next(row for row in rows if row["label"] == "Debt service" and row["kind"] == "fact")
    ebitda = next(row for row in rows if row["label"] == "EBITDA" and row["kind"] == "fact")
    posted = await local_service.submit_decisions(
        JOB,
        {
            "decisions": [
                {"kind": "sign.set", "target": debt["binding_key"], "value": "outflow", "expected_seq": None},
                {"kind": "unit.set", "target": debt["binding_key"], "value": "money", "expected_seq": None},
            ]
        },
        Actor(),
        wait_sec=60,
    )
    assert [item["status"] for item in posted["results"]] == ["accepted", "accepted"]
    assert local_service.fold_runs == before + 1
    view = await local_service.book_view(JOB, Actor(), wait_sec=30, min_state_seq=posted["pending_state_seq"])
    assert view.body["derive_key"] != old_derive
    waiting = await local_service.book_view(JOB, Actor(), wait_sec=30, min_state_seq=posted["pending_state_seq"] + 1)
    assert isinstance(waiting, Accepted)

    taken = await local_service.submit_decisions(
        JOB,
        {"decisions": [{"kind": "concept.set", "target": debt["binding_key"], "value": "debt_service", "expected_seq": None}]},
        Actor(),
        wait_sec=30,
    )
    assert taken["results"][0]["status"] == "accepted"
    clash = await local_service.submit_decisions(
        JOB,
        {"decisions": [{"kind": "concept.set", "target": ebitda["binding_key"], "value": "debt_service", "expected_seq": None}]},
        Actor(),
        wait_sec=30,
    )
    assert clash["results"][0]["status"] == "rejected"
    assert clash["results"][0]["errors"][0]["code"] == "supersede_required"
    blank = await local_service.submit_decisions(
        JOB,
        {
            "decisions": [
                {
                    "kind": "concept.set",
                    "target": ebitda["binding_key"],
                    "value": "debt_service",
                    "expected_seq": None,
                    "supersedes": {"seq": None},
                }
            ]
        },
        Actor(),
        wait_sec=30,
    )
    assert blank["results"][0]["status"] == "rejected"
    assert blank["results"][0]["errors"][0]["code"] == "supersede_required"
    inferred = {
        "source": "inferred",
        "binding_key": ebitda["binding_key"],
        "derive_key": head.derive_key,
    }
    kept = await local_service.submit_decisions(
        JOB,
        {
            "decisions": [
                {
                    "kind": "concept.set",
                    "target": ebitda["binding_key"],
                    "value": "ebitda",
                    "expected_seq": None,
                    "supersedes": inferred,
                }
            ]
        },
        Actor(),
        wait_sec=30,
    )
    assert kept["results"][0]["status"] == "accepted"
    events = await local_service.guard.read_all(JOB)
    assert any(event.get("type") == "concept.set" and event.get("supersedes") == inferred for event in events)
    assert any(
        event.get("type") == "concept.set" and event.get("target") == debt["binding_key"] and event.get("value") == "debt_service"
        for event in events
    )

    async with _client(app) as client:
        stale = await client.post(
            f"/v1/books/{JOB}/decisions",
            headers={**HEADERS, "If-Match": "s-999"},
            json={"decisions": [{"kind": "sign.set", "target": debt["binding_key"], "value": "inflow"}]},
        )
        assert stale.status_code == 412
        assert stale.json()["etag"] == f"s-{stale.json()['state_seq']}"
        listed = await client.get(f"/v1/books/{JOB}/decisions", headers=HEADERS)
        assert listed.status_code == 200
        assert any(item.get("type") == "concept.set" for item in listed.json()["items"])
