"""Поддельные серверы моделей для тестов фазы 2b: детерминированные, без сети."""

from __future__ import annotations

import asyncio
import hashlib
import math
import re

from finance_analysis.domain.errors import ModelDegraded

_WORD = re.compile(r"[a-zа-яё0-9]+", re.IGNORECASE)
DIM = 64


def text_vector(text: str) -> list[float]:
    """Мешок слов с хешированием: близкие тексты дают близкие векторы."""

    vector = [0.0] * DIM
    for word in _WORD.findall(text.lower()):
        digest = int(hashlib.sha1(word.encode()).hexdigest(), 16)
        vector[digest % DIM] += 1.0
    norm = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [x / norm for x in vector]


class FakeEmbed:
    model = "fake-embed"

    def __init__(self, *, fail: bool = False, delay: float = 0.0) -> None:
        self.fail = fail
        self.delay = delay
        self.calls = 0

    async def embed(self, texts, *, deadline):
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise ModelDegraded("embed", "timeout")
        return [text_vector(text) for text in texts]


class FakeRerank:
    model = "fake-rerank"

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    async def rerank(self, query, documents, *, deadline, top_n):
        self.calls += 1
        if self.fail:
            raise ModelDegraded("rerank", "circuit_open")
        q = text_vector(query)
        scored = [(index, sum(a * b for a, b in zip(q, text_vector(doc), strict=True))) for index, doc in enumerate(documents)]
        scored.sort(key=lambda pair: -pair[1])
        return scored[:top_n]


class FakeClm:
    model = "fake-clm"

    def __init__(self, choice: str | None = None, *, fail: bool = False) -> None:
        self.choice = choice
        self.fail = fail
        self.calls = 0

    async def choose(self, state, questions, *, deadline):
        self.calls += 1
        if self.fail:
            raise ModelDegraded("clm", "timeout")
        out = {}
        for name, question in questions.items():
            criteria = list(question["criteria"])
            choice = self.choice if self.choice in criteria else criteria[0]
            rest = (1 - 0.8) / max(len(criteria) - 1, 1)
            out[name] = {"choice": choice, "probabilities": {key: 0.8 if key == choice else rest for key in criteria}}
        return out


class FakeLlm:
    model = "fake-llm"

    async def complete(self, messages, *, deadline, max_tokens=800):
        return '{"pref": {"ru": "Комиссия агента", "en": "Agency fee"}, "definition": "", "broader": "debt_service", "unit": "money", "expected_sign": "outflow"}'


class FakeBudget:
    def __init__(self) -> None:
        self.used: dict[str, int] = {}

    async def take(self, key, limit, ttl):
        self.used[key] = self.used.get(key, 0) + 1
        return self.used[key] <= limit
