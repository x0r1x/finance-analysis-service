"""Фаза 2b на сервисе: модели в конвейере, examples/ и signals/, shadow-гейт, eval, сценарий S5 (§12)."""

from __future__ import annotations

import asyncio
import json
import time

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from finance_analysis.adapters.api.app import create_app
from finance_analysis.adapters.ml.http import HttpEmbed, HttpRerank
from finance_analysis.adapters.ml.resilience import (
    CircuitBreaker,
    Endpoint,
    RetryBudget,
)
from finance_analysis.adapters.storage.parquet_io import PyarrowParquet
from finance_analysis.adapters.storage.store import open_storage
from finance_analysis.adapters.vector.numpy_index import NumpyIndex
from finance_analysis.adapters.wren.query import WrenQuery
from finance_analysis.application.ports import Models
from finance_analysis.application.service import FasService
from finance_analysis.domain.book import Actor
from finance_analysis.domain.glossary_release import package_of
from tests.books import job_id
from tests.models import FakeClm, FakeEmbed, FakeRerank

pytestmark = pytest.mark.asyncio
RVI = job_id("rvi")
HEADERS = {"X-User-Id": "alex", "X-Client-Id": "desk"}
PATH = "Senior Debt › Debt Service Coverage Ratio (DSCR) › CFADS during debt term"


async def _service(settings, redis_runtime, builder, models: Models) -> FasService:
    store = await open_storage(settings)
    return FasService(
        settings, store, PyarrowParquet(), builder, WrenQuery(settings), redis_runtime, models=models, vector_index=NumpyIndex()
    )


async def test_models_add_candidates_and_decisions_feed_learning(settings, redis_runtime, builder):
    service = await _service(settings, redis_runtime, builder, Models(embed=FakeEmbed(), rerank=FakeRerank(), clm=FakeClm()))
    await service.perform_load(RVI, actor=Actor(), fence=1)
    await service.settle()
    head = (await service._read_head(RVI))[0]
    bindings = await service._dataset_rows(RVI, head, "bindings")
    rows = await service._dataset_rows(RVI, head, "dim_row")
    assert len(bindings) == sum(1 for row in rows if row["kind"] == "fact")
    with_candidates = [row for row in bindings if json.loads(row["evidence_json"]).get("candidates")]
    assert with_candidates, "у строк без точной метки есть кандидаты моделей"
    lexical = next(row for row in bindings if row["label_path_text"].endswith(" › CFADS"))
    assert json.loads(lexical["evidence_json"])["label"]["id"].startswith("cfads/")
    questions = await service.questions_view(RVI, Actor(), wait_sec=5)
    for item in questions["questions"]:
        if item["kind"] != "concept":
            continue
        assert item["subject"] in service.catalog.ids
        assert all("binding_key" in cand for cand in item["candidates"])

    target = next(row for row in rows if row["label"] == "Total debt service" and row["kind"] == "fact")
    posted = await service.submit_decisions(
        RVI, {"decisions": [{"kind": "concept.set", "target": target["binding_key"], "value": "debt_service"}]}, Actor(user_id="u1"), wait_sec=60
    )
    assert posted["results"][0]["status"] == "accepted", posted
    await service.settle()
    examples = await service.examples.active()
    assert [(row["binding_key"], row["concept"]) for row in examples] == [(target["binding_key"], "debt_service")]
    signals = await service.learning.signals.rows()
    assert any(row["kind"] in {"human.confirmed", "human.corrected"} and row["concept"] == "debt_service" for row in signals)
    unmapped = await service.learning.unmapped.rows()
    assert unmapped and all(row["job_id"] == RVI for row in unmapped)


async def test_shadow_gate_blocks_regression_over_http(settings, local_service, redis_runtime, task_workers):
    await local_service.glossary.bootstrap()
    await local_service.perform_load(RVI, actor=Actor(), fence=1)
    await local_service.settle()
    app = create_app(settings, service=local_service, support=redis_runtime)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fas") as client:
        state = (await client.get("/v1/glossary", headers=HEADERS)).json()
        # «Total debt service» — единственная основная строка debt_service. Снятие alt роняет покрытие.
        released = await client.post(
            "/v1/glossary/releases",
            headers={**HEADERS, "If-Match": state["etag"]},
            json={"ops": [{"op": "remove_label", "concept": "debt_service", "kind": "alt", "lang": "en", "text": "Total debt service"}]},
        )
        assert released.status_code == 200, released.text
        version, etag = released.json()["version"], released.json()["etag"]
        blocked = await client.post(
            "/v1/glossary/transitions", headers={**HEADERS, "If-Match": etag}, json={"version": version, "status": "active"}
        )
        assert blocked.status_code == 202, blocked.text
        failed = await local_service.wait_op(blocked.json()["id"], 120_000)
        assert failed["status"] == "failed", failed
        assert failed["error"]["code"] == "glossary_regression"
        assert failed["error"]["type"] == "urn:fas:problem:glossary_regression"
        assert f"coverage_down:{RVI}" in failed["error"]["shadow"]["reasons"]
        view = await client.get(f"/v1/glossary/releases/{version}", headers=HEADERS)
        assert view.json()["shadow"]["passed"] is False
        no_reason = await client.post(
            "/v1/glossary/transitions", headers={**HEADERS, "If-Match": etag}, json={"version": version, "status": "active", "force": True}
        )
        assert no_reason.status_code == 400
        forced = await client.post(
            "/v1/glossary/transitions",
            headers={**HEADERS, "If-Match": etag},
            json={"version": version, "status": "active", "force": True, "reason": "методолог: метка снята осознанно"},
        )
        assert forced.status_code == 202, forced.text
        done = await local_service.wait_op(forced.json()["id"], 120_000)
        assert done["status"] == "succeeded", done
        events = (await client.get("/v1/glossary/events", headers=HEADERS)).json()["events"]
        assert events[-1]["force"] is True and events[-1]["reason"]
        labels = (await client.get("/v1/glossary/labels", headers=HEADERS, params={"q": "денежный поток"})).json()["labels"]
        assert labels and all(item["provenance"]["origin"] == "base_git" for item in labels)


async def test_eval_and_pruned_concept_on_golden_book(settings, local_service, tmp_path):
    await local_service.perform_load(RVI, actor=Actor(), fence=1)
    folder = tmp_path / "eval" / "labels"
    folder.mkdir(parents=True)
    (folder / "rvi.json").write_text(
        json.dumps(
            {
                "job_id": RVI,
                "by_path": {f"{PATH} › CFADS": "cfads", f"{PATH} › Total debt service": "debt_service"},
                "critical_paths": [f"{PATH} › Total debt service"],
            }
        ),
        encoding="utf-8",
    )
    local_service.settings.fas_eval_dir = str(tmp_path / "eval")
    state = await local_service.glossary.bootstrap()
    document = await local_service.glossary.document(state["active"])
    report = await local_service.evaluator.run(package_of(document))
    summary = report["summary"]
    assert summary["books"] == 1 and summary["false_binding_rate"] == 0.0
    # «CFADS» — сильное совпадение (вся подпись). «Total debt service» — точная alt.
    assert summary["top1"]["cfads"] == 1.0
    assert summary["top1"]["debt_service"] == 1.0
    pruned = await local_service.evaluator.pruned(document, ["cfads"])
    assert pruned["cfads"] == {"rows": 1, "leaked": 0, "nil_recall": 1.0}


async def test_s5_slow_and_failing_model_servers_degrade(settings, redis_runtime, builder):
    """S5: embed отвечает дольше таймаута, rerank падает. Загрузка идёт, цепи размыкаются, latency ограничена."""

    calls = {"embed": 0, "rerank": 0}

    async def slow_embed(request):
        calls["embed"] += 1
        await asyncio.sleep(1.0)
        return httpx.Response(200, json={"data": []})

    def broken_rerank(request):
        calls["rerank"] += 1
        return httpx.Response(503)

    budget = RetryBudget(60)

    def endpoint(stage, handler, timeout):
        breaker = CircuitBreaker(stage, failures=2, window_sec=30, open_sec=30)
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return Endpoint(stage, "http://m", concurrency=2, timeout=timeout, breaker=breaker, retries=1, budget=budget, client=client)

    embed = HttpEmbed(endpoint("embed", slow_embed, 0.2), "e")
    rerank = HttpRerank(endpoint("rerank", broken_rerank, 0.2), "r", "cohere")
    service = await _service(settings, redis_runtime, builder, Models(embed=embed, rerank=rerank))
    started = time.monotonic()
    await service.perform_load(RVI, actor=Actor(), fence=1)
    elapsed = time.monotonic() - started
    await service.settle()
    head = (await service._read_head(RVI))[0]
    bindings = await service._dataset_rows(RVI, head, "bindings")
    degraded = {item["stage"] for row in bindings for item in json.loads(row["evidence_json"]).get("degraded") or []}
    assert {"embed", "rerank"} <= degraded
    assert service.model_states() == {"embed": "open", "rerank": "open", "clm": "absent", "llm": "absent"}
    assert calls["embed"] <= 2 and calls["rerank"] <= 4
    assert elapsed < 30
    ready = await service.ready()
    assert ready["status"] == "ok" and ready["models"]["embed"] == "open"


async def test_shadow_gate_blocks_metric_concept_moving_to_another_row(local_service):
    await local_service.perform_load(RVI, actor=Actor(), fence=1)
    await local_service.settle()
    state = await local_service.glossary.bootstrap()
    released = await local_service.glossary.release(
        [
            {"op": "remove_label", "concept": "debt_service", "kind": "alt", "lang": "en", "text": "Total debt service"},
            {"op": "add_label", "concept": "debt_service", "kind": "alt", "lang": "en", "text": "Total uses of funds"},
        ],
        f"h-{state['seq']}",
    )
    report = await local_service.evaluator.shadow(released["version"])
    assert report["passed"] is False
    assert f"primary_moved:{RVI}" in report["reasons"]
    moved = report["books"][0]["metric_concepts_moved"]
    assert moved[0]["concept"] == "debt_service" and moved[0]["path"].endswith("Total uses of funds")


async def test_blocked_proposal_stays_open(local_service):
    await local_service.glossary.bootstrap()
    await local_service.perform_load(RVI, actor=Actor(), fence=1)
    await local_service.settle()
    proposal = await local_service.glossary.add_proposal(
        {"concept": "debt_service", "kind": "alt", "lang": "en", "text": "Total uses of funds"}
    )
    decided = await local_service.glossary.decide_proposals([{"id": proposal["id"], "decision": "accept"}])
    assert decided["release"]["activated"] is False
    assert decided["shadow"]["passed"] is False
    assert decided["results"][0]["status"] == "open"
    again = await local_service.glossary.proposal(proposal["id"])
    assert again["status"] == "open" and again["blocked_release"] == decided["release"]["version"]
