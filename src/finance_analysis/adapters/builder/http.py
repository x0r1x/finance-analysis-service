"""HTTP-клиент builder. Только httpx.AsyncClient."""

from __future__ import annotations

import asyncio
import hashlib
import random
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx

from finance_analysis.adapters.builder.acl import (
    parse_context,
    parse_links,
    parse_summary,
    parse_trace,
)
from finance_analysis.domain.book import (
    Changed,
    GraphLink,
    NotModified,
    ReportNotReady,
    Summary,
    WorkbookSnapshot,
)
from finance_analysis.domain.errors import DependencyUnavailable, NotFound
from finance_analysis.settings import Settings


class HttpBuilder:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._base = (settings.builder_base_url or "").rstrip("/")
        self._client = client
        self._owns = client is None
        self._failures = 0
        self._open_until: datetime | None = None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=2.0))
        return self._client

    async def breaker_state(self) -> str:
        """closed, пока не было отказа. open — окно активно. half_open — окно вышло, успеха ещё нет."""

        if self._open_until is None:
            return "closed"
        if datetime.now(UTC) < self._open_until:
            return "open"
        return "half_open"

    def _ok(self) -> None:
        self._failures = 0
        self._open_until = None

    def _fail(self) -> None:
        self._failures += 1
        if self._failures >= self._settings.cb_failures:
            self._open_until = datetime.now(UTC) + timedelta(seconds=self._settings.cb_open_sec)

    async def _request(self, method: str, path: str, *, headers: dict | None = None) -> httpx.Response:
        if not self._base:
            raise DependencyUnavailable("BUILDER_BASE_URL не задан")
        if await self.breaker_state() == "open":
            raise DependencyUnavailable("circuit breaker builder открыт")
        client = await self._http()
        last: Exception | None = None
        for attempt in range(self._settings.retry_max + 1):
            try:
                response = await client.request(method, f"{self._base}{path}", headers=headers)
            except httpx.HTTPError as exc:
                last = exc
                self._fail()
                await asyncio.sleep(random.random() * 0.05 * (2**attempt))
                continue
            if response.status_code >= 500:
                self._fail()
                last = DependencyUnavailable(f"builder {response.status_code}")
                await asyncio.sleep(random.random() * 0.05 * (2**attempt))
                continue
            self._ok()
            return response
        raise DependencyUnavailable(f"builder недоступен: {last}")

    def _path(self, job_id: str, suffix: str) -> str:
        return f"/v1/context-jobs/{job_id}/{suffix}"

    async def summary(self, job_id: str, etag: str | None) -> Summary | NotModified | ReportNotReady:
        headers = {"If-None-Match": etag} if etag else None
        response = await self._request("GET", self._path(job_id, "summary"), headers=headers)
        return self._summary_response(response, fallback=etag)

    async def head_summary(self, job_id: str, etag: str) -> NotModified | Changed | ReportNotReady:
        response = await self._request(
            "HEAD",
            self._path(job_id, "summary"),
            headers={"If-None-Match": etag},
        )
        if response.status_code == 304:
            return NotModified(response.headers.get("etag") or etag)
        if response.status_code == 409 and _is_not_ready(response):
            return ReportNotReady()
        if response.status_code == 404:
            raise NotFound("книга builder не найдена")
        response.raise_for_status()
        return Changed(response.headers.get("etag") or "")

    def _summary_response(self, response: httpx.Response, *, fallback: str | None) -> Summary | NotModified | ReportNotReady:
        if response.status_code == 304:
            return NotModified(response.headers.get("etag") or fallback or "")
        if response.status_code == 409 and _is_not_ready(response):
            return ReportNotReady()
        if response.status_code == 404:
            raise NotFound("книга builder не найдена")
        response.raise_for_status()
        return parse_summary(response.json(), etag=response.headers.get("etag") or fallback or "")

    async def context(self, job_id: str) -> WorkbookSnapshot | ReportNotReady:
        response = await self._request("GET", self._path(job_id, "context.json"))
        if response.status_code == 409 and _is_not_ready(response):
            return ReportNotReady()
        if response.status_code == 404:
            raise NotFound("книга builder не найдена")
        response.raise_for_status()
        return parse_context(response.json())

    async def graph(self, job_id: str) -> tuple[GraphLink, ...] | ReportNotReady:
        response = await self._request("GET", self._path(job_id, "graph.json"))
        if response.status_code == 409 and _is_not_ready(response):
            return ReportNotReady()
        if response.status_code == 404:
            return ()
        response.raise_for_status()
        return parse_links(response.json())

    async def trace(self, job_id: str, origin: str, *, direction: str, depth: int) -> dict | ReportNotReady:
        query = urlencode({"from": origin, "direction": direction, "depth": depth})
        response = await self._request("GET", self._path(job_id, f"graph/trace?{query}"))
        if response.status_code == 409 and _is_not_ready(response):
            return ReportNotReady()
        if response.status_code == 404:
            raise NotFound("книга или ячейка builder не найдена")
        response.raise_for_status()
        return parse_trace(response.json())

    async def aclose(self) -> None:
        if self._owns and self._client is not None:
            await self._client.aclose()


def _is_not_ready(response: httpx.Response) -> bool:
    if not response.content:
        return True
    try:
        payload = response.json()
    except ValueError:
        return False
    return isinstance(payload, dict) and payload.get("error") == "report_not_ready"


def hashlib_sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
