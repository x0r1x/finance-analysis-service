"""Bulkhead, circuit breaker, бюджет повторов и дедлайн на сервер модели (§4.13.4)."""

from __future__ import annotations

import asyncio
import random
import time
from collections import deque

import httpx
from prometheus_client import Counter, Gauge, Histogram

from finance_analysis.domain.deadline import Deadline
from finance_analysis.domain.errors import ModelDegraded

MODEL_CALLS = Counter("fas_model_calls_total", "Вызовы серверов моделей", ["server", "outcome"])
MODEL_SECONDS = Histogram("fas_model_seconds", "Латентность серверов моделей", ["server"])
BREAKER_STATE = Gauge("fas_model_breaker_open", "Цепь сервера модели открыта (1) или нет (0)", ["server"])
RETRY_TOKENS = Gauge("fas_model_retry_budget", "Остаток бюджета повторов процесса")


class CircuitBreaker:
    """N ошибок или таймаутов за окно → open на open_sec, затем один пробный вызов (half-open)."""

    def __init__(self, name: str, *, failures: int, window_sec: float, open_sec: float, clock=time.monotonic) -> None:
        self.name = name
        self._limit = max(failures, 1)
        self._window = window_sec
        self._open_sec = open_sec
        self._clock = clock
        self._errors: deque[float] = deque()
        self._open_until: float | None = None
        self._probe = False

    def state(self) -> str:
        if self._open_until is None:
            return "closed"
        if self._clock() < self._open_until:
            return "open"
        return "half_open"

    def allow(self) -> bool:
        state = self.state()
        if state == "closed":
            return True
        if state == "open" or self._probe:
            return False
        self._probe = True
        return True

    def success(self) -> None:
        self._errors.clear()
        self._open_until = None
        self._probe = False
        BREAKER_STATE.labels(self.name).set(0)

    def failure(self) -> None:
        now = self._clock()
        if self.state() == "half_open":
            self._trip(now)
            return
        self._errors.append(now)
        while self._errors and now - self._errors[0] > self._window:
            self._errors.popleft()
        if len(self._errors) >= self._limit:
            self._trip(now)

    def release_probe(self) -> None:
        self._probe = False

    def _trip(self, now: float) -> None:
        self._open_until = now + self._open_sec
        self._probe = False
        self._errors.clear()
        BREAKER_STATE.labels(self.name).set(1)


class RetryBudget:
    """Token bucket на процесс: RETRY_BUDGET_PER_MIN повторов в минуту на все серверы."""

    def __init__(self, per_minute: int, *, clock=time.monotonic) -> None:
        self._capacity = float(max(per_minute, 0))
        self._tokens = self._capacity
        self._rate = self._capacity / 60.0
        self._clock = clock
        self._at = clock()

    def take(self) -> bool:
        now = self._clock()
        self._tokens = min(self._capacity, self._tokens + (now - self._at) * self._rate)
        self._at = now
        if self._tokens < 1:
            RETRY_TOKENS.set(self._tokens)
            return False
        self._tokens -= 1
        RETRY_TOKENS.set(self._tokens)
        return True


class Endpoint:
    """Свой httpx.AsyncClient и семафор на сервер: медленный LLM не съедает соединения embed."""

    def __init__(
        self,
        stage: str,
        base_url: str,
        *,
        concurrency: int,
        timeout: float,
        breaker: CircuitBreaker,
        retries: int,
        budget: RetryBudget | None,
        headers: dict | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.stage = stage
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.breaker = breaker
        self._retries = retries
        self._budget = budget
        self._headers = headers or {}
        self._semaphore = asyncio.Semaphore(concurrency)
        self._client = client or httpx.AsyncClient(
            limits=httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency),
            timeout=httpx.Timeout(timeout, connect=min(timeout, 2.0)),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def post(self, path: str, payload: dict, *, deadline: Deadline) -> dict:
        if deadline.budget(self.timeout) is None:
            MODEL_CALLS.labels(self.stage, "deadline").inc()
            raise ModelDegraded(self.stage, "deadline")
        if not self.breaker.allow():
            MODEL_CALLS.labels(self.stage, "circuit_open").inc()
            raise ModelDegraded(self.stage, "circuit_open")
        try:
            wait = deadline.budget(self.timeout)
            if wait is None:
                raise ModelDegraded(self.stage, "deadline")
            try:
                await asyncio.wait_for(self._semaphore.acquire(), timeout=wait)
            except TimeoutError:
                MODEL_CALLS.labels(self.stage, "bulkhead").inc()
                raise ModelDegraded(self.stage, "bulkhead") from None
            try:
                return await self._attempts(path, payload, deadline)
            finally:
                self._semaphore.release()
        finally:
            self.breaker.release_probe()

    async def _attempts(self, path: str, payload: dict, deadline: Deadline) -> dict:
        attempt = 0
        while True:
            budget = deadline.budget(self.timeout)
            if budget is None:
                MODEL_CALLS.labels(self.stage, "deadline").inc()
                raise ModelDegraded(self.stage, "deadline")
            started = time.monotonic()
            reason = None
            try:
                # Таймауты httpx — на фазу (connect/read), а нужен общий предел вызова: wait_for.
                response = await asyncio.wait_for(
                    self._client.post(f"{self.base_url}{path}", json=payload, headers=self._headers, timeout=budget),
                    timeout=budget,
                )
            except (httpx.TimeoutException, TimeoutError):
                reason = "timeout"
            except httpx.HTTPError:
                reason = "error"
            else:
                MODEL_SECONDS.labels(self.stage).observe(time.monotonic() - started)
                if response.status_code >= 500:
                    reason = f"http_{response.status_code}"
                elif response.status_code >= 400:
                    # Ответ сервера по существу: цепь не размыкаем, стадию пропускаем.
                    self.breaker.success()
                    MODEL_CALLS.labels(self.stage, "rejected").inc()
                    raise ModelDegraded(self.stage, f"http_{response.status_code}")
                else:
                    try:
                        body = response.json()
                    except ValueError:
                        self.breaker.success()
                        MODEL_CALLS.labels(self.stage, "schema").inc()
                        raise ModelDegraded(self.stage, "schema") from None
                    self.breaker.success()
                    MODEL_CALLS.labels(self.stage, "ok").inc()
                    return body
            self.breaker.failure()
            MODEL_CALLS.labels(self.stage, reason).inc()
            if attempt >= self._retries or self.breaker.state() != "closed":
                raise ModelDegraded(self.stage, reason)
            if self._budget is None or not self._budget.take():
                raise ModelDegraded(self.stage, f"{reason}_no_retry_budget")
            attempt += 1
            delay = random.random() * min(1.0, 0.05 * (2**attempt))
            if deadline.budget(self.timeout) is None or deadline.remaining() <= delay:
                raise ModelDegraded(self.stage, "deadline")
            await asyncio.sleep(delay)
