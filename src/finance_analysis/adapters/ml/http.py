"""HTTP-адаптеры моделей (§10.3): embed, rerank (cohere|tei), CLM systemone, LLM chat."""

from __future__ import annotations

import math

from finance_analysis.adapters.ml.resilience import (
    CircuitBreaker,
    Endpoint,
    RetryBudget,
)
from finance_analysis.application.ports import Models
from finance_analysis.domain.deadline import Deadline
from finance_analysis.domain.errors import ModelDegraded
from finance_analysis.settings import Settings


class HttpEmbed:
    """OpenAI-совместимый POST /v1/embeddings."""

    def __init__(self, endpoint: Endpoint, model: str) -> None:
        self.endpoint = endpoint
        self.model = model

    async def embed(self, texts: list[str], *, deadline: Deadline) -> list[list[float]]:
        if not texts:
            return []
        body = await self.endpoint.post("/v1/embeddings", {"model": self.model, "input": texts}, deadline=deadline)
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list) or len(data) != len(texts):
            raise ModelDegraded("embed", "schema")
        ordered = sorted(data, key=lambda item: int(item.get("index", 0)) if isinstance(item, dict) else 0)
        vectors = []
        for item in ordered:
            vector = item.get("embedding") if isinstance(item, dict) else None
            if not isinstance(vector, list) or not vector or not all(isinstance(x, int | float) for x in vector):
                raise ModelDegraded("embed", "schema")
            vectors.append([float(x) for x in vector])
        return vectors


class HttpRerank:
    """Два диалекта: cohere (Cohere v2 / Jina / vLLM) и tei (HF TEI). Ответ → [(index, score)]."""

    def __init__(self, endpoint: Endpoint, model: str, dialect: str) -> None:
        self.endpoint = endpoint
        self.model = model
        self.dialect = dialect

    async def rerank(self, query: str, documents: list[str], *, deadline: Deadline, top_n: int) -> list[tuple[int, float]]:
        if not documents:
            return []
        if self.dialect == "tei":
            body = await self.endpoint.post("/rerank", {"query": query, "texts": documents, "raw_scores": False}, deadline=deadline)
            rows = body if isinstance(body, list) else None
            score_key = "score"
        else:
            payload = {"model": self.model, "query": query, "documents": documents, "top_n": min(top_n, len(documents))}
            body = await self.endpoint.post("/v1/rerank", payload, deadline=deadline)
            rows = body.get("results") if isinstance(body, dict) else None
            score_key = "relevance_score"
        if not isinstance(rows, list):
            raise ModelDegraded("rerank", "schema")
        out = []
        for item in rows:
            if not isinstance(item, dict):
                raise ModelDegraded("rerank", "schema")
            index, score = item.get("index"), item.get(score_key)
            if not isinstance(index, int) or not 0 <= index < len(documents) or not isinstance(score, int | float):
                raise ModelDegraded("rerank", "schema")
            if not math.isfinite(float(score)):
                raise ModelDegraded("rerank", "schema")
            out.append((index, float(score)))
        out.sort(key=lambda pair: -pair[1])
        return out[:top_n]


class HttpClm:
    """CLM-01 systemone: {model, state, questions} → {questions|answers: {name: {choice, probabilities}}}."""

    def __init__(self, endpoint: Endpoint, model: str) -> None:
        self.endpoint = endpoint
        self.model = model

    async def choose(self, state: str, questions: dict, *, deadline: Deadline) -> dict[str, dict]:
        body = await self.endpoint.post("", {"model": self.model, "state": state, "questions": questions}, deadline=deadline)
        answers = body.get("questions") or body.get("answers") if isinstance(body, dict) else None
        if not isinstance(answers, dict):
            raise ModelDegraded("clm", "schema")
        out = {}
        for name, question in questions.items():
            answer = answers.get(name)
            criteria = question.get("criteria") or {}
            if not isinstance(answer, dict):
                raise ModelDegraded("clm", "schema")
            choice = answer.get("choice")
            probabilities = answer.get("probabilities") or {}
            if choice not in criteria or not isinstance(probabilities, dict):
                raise ModelDegraded("clm", "schema")
            clean = {}
            for key, value in probabilities.items():
                if key not in criteria or not isinstance(value, int | float) or not 0 <= float(value) <= 1:
                    raise ModelDegraded("clm", "schema")
                clean[key] = float(value)
            out[name] = {"choice": choice, "probabilities": clean}
        return out


class HttpLlm:
    """OpenAI-совместимый POST /v1/chat/completions. Только текст, числа LLM не выдаёт."""

    def __init__(self, endpoint: Endpoint, model: str) -> None:
        self.endpoint = endpoint
        self.model = model

    async def complete(self, messages: list[dict], *, deadline: Deadline, max_tokens: int = 800) -> str:
        payload = {"model": self.model, "messages": messages, "max_tokens": max_tokens, "temperature": 0}
        body = await self.endpoint.post("/v1/chat/completions", payload, deadline=deadline)
        try:
            text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise ModelDegraded("llm", "schema") from None
        if not isinstance(text, str):
            raise ModelDegraded("llm", "schema")
        return text


def build_models(settings: Settings) -> Models:
    """Повторы — только embed и rerank (идемпотентны); LLM и CLM внутри запроса не повторяются."""

    budget = RetryBudget(settings.retry_budget_per_min)

    def endpoint(stage: str, url: str, concurrency: int, timeout: float, retries: int, headers=None) -> Endpoint:
        breaker = CircuitBreaker(stage, failures=settings.cb_failures, window_sec=settings.cb_window_sec, open_sec=settings.cb_open_sec)
        return Endpoint(stage, url, concurrency=concurrency, timeout=timeout, breaker=breaker, retries=retries, budget=budget, headers=headers)

    models = Models()
    if settings.embed_base_url and settings.embed_model:
        models.embed = HttpEmbed(
            endpoint("embed", settings.embed_base_url, settings.embed_max_concurrency, settings.embed_timeout_sec, settings.retry_max),
            settings.embed_model,
        )
    if settings.rerank_base_url and settings.rerank_model:
        models.rerank = HttpRerank(
            endpoint("rerank", settings.rerank_base_url, settings.rerank_max_concurrency, settings.rerank_timeout_sec, settings.retry_max),
            settings.rerank_model,
            settings.rerank_dialect,
        )
    if settings.clm_base_url and settings.clm_model:
        headers = {"Authorization": f"Bearer {settings.clm_api_key}"} if settings.clm_api_key else None
        models.clm = HttpClm(
            endpoint("clm", settings.clm_base_url, settings.clm_max_concurrency, settings.clm_timeout_sec, 0, headers),
            settings.clm_model,
        )
    if settings.llm_base_url and settings.llm_model:
        headers = {"Authorization": f"Bearer {settings.llm_api_key}"} if settings.llm_api_key else None
        models.llm = HttpLlm(
            endpoint("llm", settings.llm_base_url, settings.llm_max_concurrency, settings.llm_timeout_sec, 0, headers),
            settings.llm_model,
        )
    return models


def breaker_states(models: Models) -> dict[str, str]:
    out = {}
    for name in ("embed", "rerank", "clm", "llm"):
        client = getattr(models, name)
        endpoint = getattr(client, "endpoint", None)
        out[name] = "absent" if endpoint is None else endpoint.breaker.state()
    return out


async def close_models(models: Models) -> None:
    for name in ("embed", "rerank", "clm", "llm"):
        endpoint = getattr(getattr(models, name), "endpoint", None)
        if endpoint is not None:
            await endpoint.aclose()
