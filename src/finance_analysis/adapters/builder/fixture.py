"""Книга из каталога golden-файлов для стенда и тестов."""

from __future__ import annotations

import json
from pathlib import Path

from finance_analysis.adapters.builder.acl import parse_context, parse_graph, parse_summary
from finance_analysis.domain.book import NotModified
from finance_analysis.domain.errors import NotFound


class FixtureBuilder:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._etag: dict[str, str] = {}
        self.flips_left: dict[str, int] = {}

    def _dir(self, job_id: str) -> Path:
        path = self.root / job_id
        if not path.is_dir():
            raise NotFound("книга builder не найдена")
        return path

    def _summary_payload(self, job_id: str) -> tuple[dict, str]:
        path = self._dir(job_id) / "summary.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        etag = self._etag.get(job_id) or str(payload.get("etag") or "sum-1")
        self._etag[job_id] = etag
        return payload, etag

    async def summary(self, job_id: str, etag: str | None):
        payload, current = self._summary_payload(job_id)
        if etag and etag == current:
            return NotModified(etag)
        body = {key: value for key, value in payload.items() if key != "etag"}
        return parse_summary(body, etag=current, job_id=job_id)

    async def context(self, job_id: str):
        folder = self._dir(job_id)
        if self.flips_left.get(job_id, 0) > 0:
            self.flips_left[job_id] -= 1
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
