"""Крупные локальные книги builder. Без переменных окружения тест пропускается.

Каталог не коммитится. Пример раскладки — `tests/fixtures/local-builder/{job_id}/`
(см. `.gitignore` и `tests/fixtures/builder/README.md`).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from finance_analysis.adapters.builder.acl import consistency_token
from finance_analysis.adapters.builder.fixture import FixtureBuilder
from finance_analysis.adapters.storage.parquet_io import PyarrowParquet
from finance_analysis.adapters.storage.store import open_storage
from finance_analysis.adapters.wren.query import WrenQuery
from finance_analysis.application.keys import build_index_key
from finance_analysis.application.service import FasService
from finance_analysis.domain.book import Actor

pytestmark = pytest.mark.asyncio

_REASON = (
    "локальные книги не заданы: нужны FAS_LOCAL_BUILDER_JOBS_DIR и FAS_LOCAL_BUILDER_JOBS"
)


def _configured() -> bool:
    return bool(os.environ.get("FAS_LOCAL_BUILDER_JOBS_DIR") and os.environ.get("FAS_LOCAL_BUILDER_JOBS"))


def _jobs() -> tuple[Path, list[str]]:
    root = Path(os.environ["FAS_LOCAL_BUILDER_JOBS_DIR"])
    ids = [item.strip() for item in os.environ["FAS_LOCAL_BUILDER_JOBS"].split(",") if item.strip()]
    return root, ids


async def _assert_job(service: FasService, job_id: str, root: Path) -> None:
    folder = root / job_id
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    graph = json.loads((folder / "graph.json").read_text(encoding="utf-8"))
    head = await service.perform_load(job_id, actor=Actor(), fence=1)
    manifest = await service._manifest(job_id, head.build_key)
    ref = manifest["builder_ref"]
    assert ref["builder_status"] in {"succeeded", "degraded"}
    assert ref["content_sha256"] == meta["content_sha256"]
    assert meta.get("generation") not in (None, "")
    assert ref["summary_etag"] == consistency_token(
        status=meta["status"],
        generation=meta["generation"],
        content_sha256=meta["content_sha256"],
        stages=meta["stages"],
    )
    assert ref["context_schema_version"] == str(meta["schema_version"])
    assert ref["graph_schema_version"] == str(graph["schema_version"])
    index = json.loads(await service.store.get(build_index_key(job_id, head.build_key)))
    assert index["stats"]["rows"] > 0
    assert index["stats"]["observations"] > 0


@pytest.mark.skipif(not _configured(), reason=_REASON)
async def test_local_builder_jobs_on_local_storage(settings, redis_runtime):
    root, ids = _jobs()
    store = await open_storage(settings)
    service = FasService(
        settings,
        store,
        PyarrowParquet(),
        FixtureBuilder(root),
        WrenQuery(settings),
        redis_runtime,
    )
    for job in ids:
        await _assert_job(service, job, root)


@pytest.mark.skipif(not _configured(), reason=_REASON)
async def test_local_builder_jobs_on_minio(tmp_path, minio_endpoint, redis_runtime):
    from tests.conftest import s3_settings

    root, ids = _jobs()
    settings = s3_settings(tmp_path, minio_endpoint)
    settings = settings.model_copy(update={"fas_s3_prefix": f"localjobs{tmp_path.name}"})
    store = await open_storage(settings)
    service = FasService(
        settings,
        store,
        PyarrowParquet(),
        FixtureBuilder(root),
        WrenQuery(settings),
        redis_runtime,
    )
    for job in ids:
        await _assert_job(service, job, root)
    await store.delete_prefix("")
