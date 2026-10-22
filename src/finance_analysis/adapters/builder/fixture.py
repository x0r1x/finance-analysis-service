"""Книга из каталога фикстур builder для стенда и тестов.

Каталог — `meta.json` + `context.json` + `graph.json` (реальный дамп).
`summary.json` оставлен для проектной формы из §2.
"""

from __future__ import annotations

import json
from pathlib import Path

from finance_analysis.adapters.builder.acl import (
    is_meta_payload,
    parse_context,
    parse_graph,
    parse_summary,
)
from finance_analysis.domain.book import NotModified
from finance_analysis.domain.errors import NotFound


class FixtureBuilder:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._etag: dict[str, str] = {}
        self._generation_delta: dict[str, int] = {}
        self._graph_versions: dict[str, str | None] = {}
        self.flips_left: dict[str, int] = {}

    def _dir(self, job_id: str) -> Path:
        path = self.root / job_id
        if not path.is_dir():
            raise NotFound("книга builder не найдена")
        return path

    def _read(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def _document(self, job_id: str) -> dict:
        folder = self._dir(job_id)
        meta = folder / "meta.json"
        if meta.is_file():
            payload = self._read(meta)
            delta = self._generation_delta.get(job_id, 0)
            if delta:
                payload = dict(payload)
                payload["generation"] = int(payload.get("generation") or 0) + delta
            return payload
        summary = folder / "summary.json"
        if summary.is_file():
            return self._read(summary)
        raise NotFound("в книге нет meta.json")

    def _graph_version(self, job_id: str) -> str | None:
        if job_id in self._graph_versions:
            return self._graph_versions[job_id]
        path = self._dir(job_id) / "graph.json"
        version = None
        if path.is_file():
            raw = self._read(path).get("schema_version")
            version = None if raw in (None, "") else str(raw)
        self._graph_versions[job_id] = version
        return version

    async def summary(self, job_id: str, etag: str | None):
        payload = self._document(job_id)
        if is_meta_payload(payload):
            parsed = parse_summary(
                payload,
                etag="",
                job_id=job_id,
                graph_schema_version=self._graph_version(job_id),
            )
        else:
            current = self._etag.get(job_id) or str(payload.get("etag") or "sum-1")
            self._etag[job_id] = current
            body = {key: value for key, value in payload.items() if key != "etag"}
            parsed = parse_summary(body, etag=current, job_id=job_id)
        if etag and etag == parsed.etag:
            return NotModified(etag)
        return parsed

    async def context(self, job_id: str):
        folder = self._dir(job_id)
        if self.flips_left.get(job_id, 0) > 0:
            self.flips_left[job_id] -= 1
            if (folder / "meta.json").is_file():
                self._generation_delta[job_id] = self._generation_delta.get(job_id, 0) + 1
            else:
                current = self._etag.get(job_id, "sum-1")
                self._etag[job_id] = current + "-next"
        raw = (folder / "context.json").read_bytes()
        snapshot = parse_context(json.loads(raw))
        graph_path = folder / "graph.json"
        if graph_path.is_file():
            snapshot = parse_graph(json.loads(graph_path.read_text(encoding="utf-8")), snapshot)
        context_etag = "ctx-1"
        return snapshot, context_etag, raw.hex()[:64]

    async def healthy(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None
