"""Клиенты моделей: диалекты, строгая валидация, bulkhead, circuit breaker, дедлайн, бюджет повторов (§4.13.4, §10.3)."""

import asyncio
import json

import httpx
import pytest

from finance_analysis.adapters.ml.http import HttpClm, HttpEmbed, HttpRerank
from finance_analysis.adapters.ml.resilience import (
    CircuitBreaker,
    Endpoint,
    RetryBudget,
)
from finance_analysis.domain.deadline import Deadline
from finance_analysis.domain.errors import ModelDegraded


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _endpoint(handler, *, retries=0, budget=None, clock=None, concurrency=4, timeout=2.0, failures=3) -> Endpoint:
    breaker = CircuitBreaker("m", failures=failures, window_sec=30, open_sec=30, clock=clock or Clock())
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return Endpoint("m", "http://model", concurrency=concurrency, timeout=timeout, breaker=breaker, retries=retries, budget=budget, client=client)


async def test_rerank_dialects_normalize_to_index_score():
    def cohere(request):
        assert request.url.path == "/v1/rerank"
        return httpx.Response(200, json={"results": [{"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.2}]})

    def tei(request):
        assert request.url.path == "/rerank"
        assert json.loads(request.content)["texts"] == ["a", "b"]
        return httpx.Response(200, json=[{"index": 0, "score": 0.1}, {"index": 1, "score": 0.7}])

    deadline = Deadline.after_ms(1000)
    assert await HttpRerank(_endpoint(cohere), "r", "cohere").rerank("q", ["a", "b"], deadline=deadline, top_n=5) == [(1, 0.9), (0, 0.2)]
    assert await HttpRerank(_endpoint(tei), "r", "tei").rerank("q", ["a", "b"], deadline=deadline, top_n=1) == [(1, 0.7)]


async def test_embed_and_clm_reject_off_schema_answers():
    embed = HttpEmbed(_endpoint(lambda r: httpx.Response(200, json={"data": [{"index": 0, "embedding": "x"}]})), "e")
    with pytest.raises(ModelDegraded) as caught:
        await embed.embed(["a"], deadline=Deadline.after_ms(1000))
    assert caught.value.reason == "schema"

    question = {"concept": {"type": "choice", "criteria": {"cfads": "", "none": ""}}}
    clm = HttpClm(_endpoint(lambda r: httpx.Response(200, json={"answers": {"concept": {"choice": "ebitda", "probabilities": {}}}})), "c")
    with pytest.raises(ModelDegraded):
        await clm.choose("s", question, deadline=Deadline.after_ms(1000))
    good = HttpClm(
        _endpoint(lambda r: httpx.Response(200, json={"questions": {"concept": {"choice": "cfads", "probabilities": {"cfads": 0.7, "none": 0.3}}}})),
        "c",
    )
    assert (await good.choose("s", question, deadline=Deadline.after_ms(1000)))["concept"]["choice"] == "cfads"


async def test_breaker_opens_then_half_open_probe_closes():
    clock = Clock()
    state = {"fail": True, "calls": 0}

    def handler(request):
        state["calls"] += 1
        return httpx.Response(503) if state["fail"] else httpx.Response(200, json={"ok": 1})

    endpoint = _endpoint(handler, clock=clock)
    for _ in range(3):
        with pytest.raises(ModelDegraded):
            await endpoint.post("/x", {}, deadline=Deadline.after_ms(1000))
    assert endpoint.breaker.state() == "open"
    with pytest.raises(ModelDegraded) as caught:
        await endpoint.post("/x", {}, deadline=Deadline.after_ms(1000))
    assert caught.value.reason == "circuit_open" and state["calls"] == 3
    clock.now = 31
    assert endpoint.breaker.state() == "half_open"
    state["fail"] = False
    assert await endpoint.post("/x", {}, deadline=Deadline.after_ms(1000)) == {"ok": 1}
    assert endpoint.breaker.state() == "closed"


async def test_retries_spend_budget_and_4xx_does_not_trip():
    calls = {"n": 0}

    def flaky(request):
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] == 1 else httpx.Response(200, json={"ok": 1})

    budget = RetryBudget(1)
    assert await _endpoint(flaky, retries=2, budget=budget, failures=5).post("/x", {}, deadline=Deadline.after_ms(2000)) == {"ok": 1}
    calls["n"] = 0
    with pytest.raises(ModelDegraded) as caught:
        await _endpoint(flaky, retries=2, budget=budget, failures=5).post("/x", {}, deadline=Deadline.after_ms(2000))
    assert caught.value.reason.endswith("no_retry_budget")

    endpoint = _endpoint(lambda r: httpx.Response(422), failures=1)
    with pytest.raises(ModelDegraded):
        await endpoint.post("/x", {}, deadline=Deadline.after_ms(1000))
    assert endpoint.breaker.state() == "closed"


async def test_deadline_skips_stage_and_bulkhead_bounds_wait():
    endpoint = _endpoint(lambda r: httpx.Response(200, json={}))
    with pytest.raises(ModelDegraded) as caught:
        await endpoint.post("/x", {}, deadline=Deadline.after_ms(10))
    assert caught.value.reason == "deadline"

    release = asyncio.Event()

    async def slow(request):
        await release.wait()
        return httpx.Response(200, json={})

    gated = _endpoint(slow, concurrency=1)
    first = asyncio.create_task(gated.post("/x", {}, deadline=Deadline.after_ms(5000)))
    await asyncio.sleep(0.01)
    with pytest.raises(ModelDegraded) as caught:
        await gated.post("/x", {}, deadline=Deadline.after_ms(200))
    assert caught.value.reason in {"bulkhead", "deadline"}
    release.set()
    assert await first == {}
