"""Подтверждение переживает вставку строки и смену метки (§12 п. 6)."""

from __future__ import annotations

import shutil

import pytest

from finance_analysis.adapters.builder.fixture import FixtureBuilder
from finance_analysis.adapters.storage.parquet_io import PyarrowParquet
from finance_analysis.adapters.storage.store import open_storage
from finance_analysis.adapters.wren.query import WrenQuery
from finance_analysis.application.service import FasService
from finance_analysis.domain.book import Actor
from tests.books import BUILDER_ROOT, job_id
from tests.conftest import JOB
from tests.contract.test_analyses import _insert_row_on_every_sheet

pytestmark = pytest.mark.asyncio
RVI = job_id("rvi")


async def test_header_insert_keeps_concept_set(tmp_path, settings, redis_runtime):
    root = tmp_path / "builder"
    shutil.copytree(BUILDER_ROOT / JOB, root / JOB)
    store = await open_storage(settings)
    service = FasService(settings, store, PyarrowParquet(), FixtureBuilder(root), WrenQuery(settings), redis_runtime)
    head = await service.perform_load(JOB, actor=Actor(), fence=1)
    rows = await service._dataset_rows(JOB, head, "dim_row")
    debt = next(row for row in rows if row["label"] == "Debt service" and row["kind"] == "fact")
    posted = await service.submit_decisions(
        JOB,
        {"decisions": [{"kind": "concept.set", "target": debt["binding_key"], "value": "debt_service", "expected_seq": None}]},
        Actor(),
        wait_sec=60,
    )
    assert posted["results"][0]["status"] == "accepted", posted
    _insert_row_on_every_sheet(root / JOB)
    rebuilt = await service.perform_load(JOB, actor=Actor(), fence=2)
    assert rebuilt.build_key != head.build_key
    bindings = await service._dataset_rows(JOB, rebuilt, "bindings")
    found = next(row for row in bindings if row["binding_key"] == debt["binding_key"])
    assert found["source"] == "confirmed"
    assert found["effective_concept"] == "debt_service"


async def test_label_removal_drops_only_inferred(local_service):
    await local_service.perform_load(RVI, actor=Actor(), fence=1)
    head = (await local_service._read_head(RVI))[0]
    rows = await local_service._dataset_rows(RVI, head, "dim_row")
    cfads = next(row for row in rows if row["label"] == "CFADS" and row["kind"] == "fact")
    debt = next(row for row in rows if row["label"] == "Total debt service" and row["kind"] == "fact")
    posted = await local_service.submit_decisions(
        RVI,
        {"decisions": [{"kind": "concept.set", "target": debt["binding_key"], "value": "debt_service", "expected_seq": None}]},
        Actor(),
        wait_sec=60,
    )
    assert posted["results"][0]["status"] == "accepted", posted
    state = await local_service.glossary.ensure()
    released = await local_service.glossary.release(
        [{"op": "remove_label", "concept": "cfads", "kind": "alt", "lang": "en", "text": "CFADS"}],
        f"h-{state['seq']}",
    )
    # cfads на книге неоднозначен, основной строки нет: снятие alt не роняет покрытие и не блокирует релиз.
    await local_service.glossary.transition(released["version"], "active", released["etag"])
    await local_service.remap_glossary()
    fresh = (await local_service._read_head(RVI))[0]
    bindings = await local_service._dataset_rows(RVI, fresh, "bindings")
    dropped = next(row for row in bindings if row["binding_key"] == cfads["binding_key"])
    kept = next(row for row in bindings if row["binding_key"] == debt["binding_key"])
    assert dropped["status"] == "unknown"
    assert kept["source"] == "confirmed" and kept["effective_concept"] == "debt_service"
