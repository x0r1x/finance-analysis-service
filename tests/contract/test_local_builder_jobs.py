"""Крупные локальные книги builder. Без переменных окружения тест пропускается.

Каталог не коммитится. Пример раскладки — `tests/fixtures/local-builder/{job_id}/`
(см. `.gitignore` и `tests/fixtures/builder/README.md`).
Проверяются только инварианты загрузки, без ожидаемых значений конкретной книги.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

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


async def _assert_job(service: FasService, job_id: str) -> None:
    actor = Actor()
    head = await service.perform_load(job_id, actor=actor, fence=1)
    manifest = await service._manifest(job_id, head.build_key)
    ref = manifest["builder_ref"]
    assert ref["job_id"] == job_id
    assert ref["summary_etag"].startswith('"summary-2:')
    assert "content_sha256" not in ref
    assert "builder_status" not in ref
    assert "builder_files" not in manifest
    assert all(item.get("code") != "timeline_mismatch" for item in manifest.get("warnings") or [])
    index = json_loads(await service.store.get(build_index_key(job_id, head.build_key)))
    assert index["stats"]["rows"] > 0
    assert index["stats"]["observations"] > 0
    resolved = await service.resolve_periods(
        job_id,
        {"text": "первый операционный год"},
        actor,
        wait_sec=service.settings.load_sync_sec,
    )
    assert resolved["periods"] == []
    assert resolved["needs_input"] == [
        {"kind": "concept", "reason": "concept_unknown", "subject": "debt_service"}
    ]
    assert all(item["kind"] != "phase" for item in resolved["needs_input"])


def json_loads(raw: bytes):
    import json

    return json.loads(raw)


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
        await _assert_job(service, job)


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
        await _assert_job(service, job)
    await store.delete_prefix("")
