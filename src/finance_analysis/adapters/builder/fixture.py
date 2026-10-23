"""Книга из каталога фикстур. Эмулирует HTTP `/summary`.

Если рядом с публикацией лежит `summary.json`, это тело ответа.
Иначе тело собирается из версий схем `context.json` и `graph.json`.

`GET /summary` отдаёт форму `summary-2` и strong ETag. `If-None-Match` при
`status=succeeded` и том же ETag — `304` без тела. `HEAD` тоже без тела.
Режим пересборки — `409 {"error": "report_not_ready"}`. Статус, отличный от
`succeeded`, при том же ETag отвечает `200`: ETag этот статус не кодирует.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import anyio

from finance_analysis.adapters.builder.acl import (
    parse_context,
    parse_links,
    parse_summary,
)
from finance_analysis.adapters.builder.etag import strong_etag
from finance_analysis.domain.book import (
    Changed,
    GraphLink,
    NotModified,
    ReportNotReady,
    Summary,
    WorkbookSnapshot,
)
from finance_analysis.domain.errors import NotFound, UnsupportedBuilderShape


class FixtureBuilder:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.calls: list[tuple[str, str]] = []
        self.rebuilding: set[str] = set()
        self.status_override: dict[str, str] = {}
        self.warnings_override: dict[str, list[str]] = {}
        self.head_misses: dict[str, int] = {}
        self.foreign_graph_reads: dict[str, int] = {}
        self.foreign_graph_from: dict[str, str] = {}
        self._forced_breaker = "closed"

    async def breaker_state(self) -> str:
        return self._forced_breaker

    def _dir(self, job_id: str) -> Path:
        path = self.root / job_id
        if not path.is_dir():
            raise NotFound("книга builder не найдена")
        return path

    async def _bytes(self, path: Path) -> bytes:
        if not await anyio.to_thread.run_sync(path.is_file):
            raise NotFound("в книге нет файла публикации")
        return await anyio.to_thread.run_sync(path.read_bytes)

    async def _publication(self, job_id: str) -> tuple[dict, str]:
        folder = self._dir(job_id)
        context_raw = await self._bytes(folder / "context.json")
        graph_raw = await self._bytes(folder / "graph.json")
        context = await anyio.to_thread.run_sync(json.loads, context_raw)
        graph = await anyio.to_thread.run_sync(json.loads, graph_raw)
        context_version = context.get("schema_version")
        graph_version = graph.get("schema_version")
        missing = []
        if context_version in (None, ""):
            missing.append("context.json.schema_version")
        if graph_version in (None, ""):
            missing.append("graph.json.schema_version")
        if missing:
            raise UnsupportedBuilderShape("в публикации не хватает версии схемы", extra={"fields": missing})
        digest = hashlib.sha256(context_raw + b"\n" + graph_raw).hexdigest()
        tag = strong_etag(
            content_sha256=digest,
            context_mtime_ns=0,
            context_size=len(context_raw),
            graph_mtime_ns=0,
            graph_size=len(graph_raw),
        )
        summary_path = folder / "summary.json"
        if await anyio.to_thread.run_sync(summary_path.is_file):
            raw = await self._bytes(summary_path)
            body = await anyio.to_thread.run_sync(json.loads, raw)
            if not isinstance(body, dict):
                raise UnsupportedBuilderShape("summary не объект", extra={"fields": ["summary"]})
            body = dict(body)
        else:
            body = {
                "context_schema_version": str(context_version),
                "graph_schema_version": str(graph_version),
                "warnings": [],
            }
        body["status"] = self.status_override.get(job_id, body.get("status", "succeeded"))
        if job_id in self.warnings_override:
            body["warnings"] = list(self.warnings_override[job_id])
        return body, tag

    async def summary(self, job_id: str, etag: str | None) -> Summary | NotModified | ReportNotReady:
        self.calls.append(("GET", "/summary"))
        if job_id in self.rebuilding:
            return ReportNotReady()
        body, tag = await self._publication(job_id)
        parsed = parse_summary(body, etag=tag, job_id=job_id)
        if etag and etag == tag and parsed.status == "succeeded":
            return NotModified(tag)
        return parsed

    async def head_summary(self, job_id: str, etag: str) -> NotModified | Changed | ReportNotReady:
        self.calls.append(("HEAD", "/summary"))
        if job_id in self.rebuilding:
            return ReportNotReady()
        misses = self.head_misses.get(job_id, 0)
        if misses > 0:
            self.head_misses[job_id] = misses - 1
            return Changed(f"{etag}:moved")
        _body, tag = await self._publication(job_id)
        if etag == tag:
            return NotModified(tag)
        return Changed(tag)

    async def context(self, job_id: str) -> WorkbookSnapshot | ReportNotReady:
        self.calls.append(("GET", "/context.json"))
        if job_id in self.rebuilding:
            return ReportNotReady()
        raw = await self._bytes(self._dir(job_id) / "context.json")
        payload = await anyio.to_thread.run_sync(json.loads, raw)
        return await anyio.to_thread.run_sync(parse_context, payload)

    async def graph(self, job_id: str) -> tuple[GraphLink, ...] | ReportNotReady:
        self.calls.append(("GET", "/graph.json"))
        if job_id in self.rebuilding:
            return ReportNotReady()
        source = job_id
        left = self.foreign_graph_reads.get(job_id, 0)
        if left > 0:
            source = self.foreign_graph_from[job_id]
            self.foreign_graph_reads[job_id] = left - 1
        raw = await self._bytes(self._dir(source) / "graph.json")
        payload = await anyio.to_thread.run_sync(json.loads, raw)
        return await anyio.to_thread.run_sync(parse_links, payload)

    async def aclose(self) -> None:
        return None
