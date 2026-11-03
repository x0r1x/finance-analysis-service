"""Живой finance-context. Книги читаются из корпуса билдера, в репозиторий не копируются."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from pathlib import Path

import httpx
import pytest

from finance_analysis.adapters.builder.http import HttpBuilder
from finance_analysis.adapters.storage.parquet_io import PyarrowParquet
from finance_analysis.adapters.storage.store import open_storage
from finance_analysis.adapters.wren.query import WrenQuery
from finance_analysis.application.keys import build_index_key
from finance_analysis.application.service import FasService
from finance_analysis.domain.book import Actor
from tests.books import PACKT_PERIOD, PACKT_REVENUE_ROW, PACKT_REVENUE_VALUE

DEFAULT_CORPUS = (
    Path(__file__).resolve().parents[2].parent / "finance-context-builder" / "resources" / "corpus"
)


def corpus_dir() -> Path:
    raw = os.environ.get("FAS_IT_CORPUS")
    return Path(raw) if raw else DEFAULT_CORPUS


def _lock_path() -> Path:
    return corpus_dir().parent / "corpus.lock.json"


def _lock() -> dict:
    return json.loads(_lock_path().read_text(encoding="utf-8"))


def _books() -> list[Path]:
    root = corpus_dir()
    if not root.is_dir() or not _lock_path().is_file():
        return []
    skip = {book["filename"] for book in _lock()["books"] if book.get("available") is False}
    return sorted(
        path
        for path in root.iterdir()
        if path.is_file() and path.suffix.lower() in {".xlsx", ".xls"} and path.name not in skip
    )


def _ids(path: Path | None) -> str:
    return "missing" if path is None else path.name


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not os.environ.get("BUILDER_BASE_URL"), reason="нужен BUILDER_BASE_URL"),
    pytest.mark.skipif(not corpus_dir().is_dir(), reason=f"нет корпуса {corpus_dir()}"),
]


def _check_hash(path: Path) -> None:
    for book in _lock()["books"]:
        if book.get("filename") != path.name or not book.get("sha256"):
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == book["sha256"], digest
        return


async def _wait_job(client: httpx.AsyncClient, base: str, job_id: str, timeout: int) -> None:
    deadline = time.time() + timeout
    status = ""
    body: dict = {}
    while time.time() < deadline:
        response = await client.get(f"{base}/v1/context-jobs/{job_id}")
        response.raise_for_status()
        body = response.json()
        status = str(body.get("status") or "")
        if status == "succeeded":
            return
        if status in {"failed", "cancelled"}:
            raise AssertionError(body)
        await asyncio.sleep(2)
    raise AssertionError(f"{job_id} still {status}")


@pytest.mark.parametrize("book", _books() or [None], ids=_ids)
async def test_corpus_book_loads(book: Path | None, tmp_path, settings, redis_runtime) -> None:
    if book is None:
        pytest.skip(f"нет xlsx/xls в {corpus_dir()}")
    _check_hash(book)
    base = os.environ["BUILDER_BASE_URL"].rstrip("/")
    timeout = 600 if book.suffix.lower() == ".xls" else 300
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0)) as client:
        with book.open("rb") as handle:
            response = await client.post(
                f"{base}/v1/context-jobs",
                files={"file": (book.name, handle, "application/octet-stream")},
            )
        assert response.status_code == 202, response.text
        job_id = response.json()["job_id"]
        await _wait_job(client, base, job_id, timeout)
    tuned = settings.model_copy(update={"builder_base_url": base, "load_sync_sec": float(timeout)})
    store = await open_storage(tuned)
    service = FasService(
        tuned,
        store,
        PyarrowParquet(),
        HttpBuilder(tuned),
        WrenQuery(tuned),
        redis_runtime,
    )
    actor = Actor(user_id="alex", client_id="desk")
    head = await service.perform_load(job_id, actor=actor, fence=1)
    manifest = await service._manifest(job_id, head.build_key)
    assert manifest["builder_ref"]["job_id"] == job_id
    index = json.loads(await service.store.get(build_index_key(job_id, head.build_key)))
    assert index["stats"]["rows"] > 0
    if book.name == "packt-project-finance.xlsx":
        series = await service.series(
            job_id,
            {"row_keys": [PACKT_REVENUE_ROW], "periods": [PACKT_PERIOD]},
            actor,
            wait_sec=30,
        )
        assert series["result_data"]["series"][0]["value"] == PACKT_REVENUE_VALUE
