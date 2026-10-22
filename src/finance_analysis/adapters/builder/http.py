"""HTTP-клиент builder. Только httpx.AsyncClient."""

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone

import httpx

from finance_analysis.adapters.builder.acl import parse_context, parse_graph, parse_summary
from finance_analysis.domain.book import NotModified, Summary, WorkbookSnapshot
from finance_analysis.domain.errors import DependencyUnavailable
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

    def _breaker_open(self) -> bool:
        if self._open_until is None:
            return False
        if datetime.now(timezone.utc) >= self._open_until:
            self._open_until = None
            return False
        return True

    def _ok(self) -> None:
        self._failures = 0
        self._open_until = None

    def _fail(self) -> None:
        self._failures += 1
        if self._failures >= self._settings.cb_failures:
            self._open_until = datetime.now(timezone.utc).replace(microsecond=0)
            # CB_OPEN_SEC
            from datetime import timedelta

            self._open_until = datetime.now(timezone.utc) + timedelta(seconds=self._settings.cb_open_sec)

    async def _request(self, method: str, path: str, *, headers: dict | None = None) -> httpx.Response:
        if not self._base:
            raise DependencyUnavailable("BUILDER_BASE_URL не задан")
        if self._breaker_open():
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

    async def summary(self, job_id: str, etag: str | None) -> Summary | NotModified:
        headers = {"If-None-Match": etag} if etag else None
        head = await self._request("HEAD", f"/v1/context-jobs/{job_id}/summary", headers=headers)
        if head.status_code == 304:
            return NotModified(etag or "")
        current = head.headers.get("etag")
        response = await self._request("GET", f"/v1/context-jobs/{job_id}/summary", headers=headers)
        if response.status_code == 304:
            return NotModified(etag or "")
        response.raise_for_status()
        payload = response.json()
        tag = response.headers.get("etag") or current or ""
        return parse_summary(payload, etag=tag, job_id=job_id)

    async def context(self, job_id: str) -> tuple[WorkbookSnapshot, str | None, str]:
        response = await self._request("GET", f"/v1/context-jobs/{job_id}/context.json")
        response.raise_for_status()
        snapshot = parse_context(response.json())
        graph_response = await self._request("GET", f"/v1/context-jobs/{job_id}/graph.json")
        if graph_response.status_code != 404:
            graph_response.raise_for_status()
            snapshot = parse_graph(graph_response.json(), snapshot)
        return snapshot, response.headers.get("etag"), hashlib_sha(response.content)

    async def graph(self, job_id: str) -> tuple[WorkbookSnapshot | None, str | None]:
        response = await self._request("GET", f"/v1/context-jobs/{job_id}/graph.json")
        if response.status_code == 404:
            return None, None
        response.raise_for_status()
        snapshot = parse_graph(response.json(), parse_context({"axes": {"_": {"id": "_", "sheet": "_", "periods": []}}, "blocks": []}))
        return snapshot, response.headers.get("etag")

    async def healthy(self) -> bool:
        if not self._base or self._breaker_open():
            return False
        try:
            client = await self._http()
            response = await client.get(f"{self._base}/health", timeout=2.0)
            return response.status_code < 500
        except httpx.HTTPError:
            return False

    async def aclose(self) -> None:
        if self._owns and self._client is not None:
            await self._client.aclose()


def hashlib_sha(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()
