"""SMV рядом с derive_key в книге и run.parquet."""

from __future__ import annotations

import json

import pyarrow.parquet as pq
import pytest

from finance_analysis.application.service import Accepted
from finance_analysis.domain.book import Actor
from finance_analysis.domain.semantic_model import HEAD_KEY, semantic_model_key
from tests.conftest import JOB

pytestmark = pytest.mark.asyncio


async def test_book_and_run_expose_smv_beside_derive_key(local_service):
    actor = Actor()
    head = await local_service.perform_load(JOB, actor=actor, fence=1)
    assert head.derive_key
    assert head.versions.get("semantic_model")
    assert head.versions["semantic_model"] != head.derive_key

    view = await local_service.describe(JOB, head, fresh=False)
    body = view.body
    assert body["derive_key"] == head.derive_key
    assert body["semantic_model_version"] == head.versions["semantic_model"]
    assert body["versions"]["semantic_model"] == body["semantic_model_version"]
    assert body["semantic_model_source"] == "stored"

    manifest = json.loads(await local_service.store.get(semantic_model_key(body["semantic_model_version"])))
    assert manifest["version"] == body["semantic_model_version"]

    # Анализ до ensure глоссария: pin книги не должен смениться от глобальной публикации.
    result = await local_service.analyses.run(
        JOB, {"type": "ratios", "metrics": ["dscr"]}, actor, wait_sec=120
    )
    if isinstance(result, Accepted):
        operation = await local_service.wait_op(result.operation["id"], 120_000)
        assert operation["status"] == "succeeded", operation
        analysis_id = operation["result"]["analysis_id"]
        marker = json.loads(
            await local_service.store.get(f"books/{JOB}/{head.build_key}/results/{analysis_id}/result.json")
        )
        envelope = marker["result"]
    else:
        envelope = result
        analysis_id = envelope["analysis_id"]

    assert envelope["versions"]["derive_key"]
    assert envelope["versions"]["semantic_model"]
    assert envelope["versions"].get("book_semantic_model") == head.versions["semantic_model"]
    run_key = f"books/{JOB}/{head.build_key}/results/{analysis_id}/run.parquet"
    table = pq.read_table(local_service.store.physical(run_key))
    names = table.column_names
    # Same run table as derive_key ("beside" semantically); append-only P6 → SMV last.
    assert "derive_key" in names
    assert "semantic_model_version" in names
    assert names[-1] == "semantic_model_version"
    assert names.index("semantic_model_version") > names.index("derive_key")
    smv = table.column("semantic_model_version")[0].as_py()
    derive = table.column("derive_key")[0].as_py()
    assert smv == envelope["versions"]["semantic_model"]
    assert derive == envelope["versions"]["derive_key"]
    assert smv != derive

    # Глобальный _head — только после публикации активного глоссария (не от load книги).
    gloss = await local_service.glossary.bootstrap()
    await local_service.publish_semantic_model(gloss["active"])
    pointer = json.loads(await local_service.store.get(HEAD_KEY))
    assert pointer["glossary"] == gloss["active"]
    assert pointer["glossary_seq"] == gloss["seq"]
    assert pointer["active"]
    # Исторический glossary книги не откатывает указатель (active-glossary / seq guard).
    await local_service.publish_semantic_model(head.versions.get("glossary"))
    again = json.loads(await local_service.store.get(HEAD_KEY))
    assert again["active"] == pointer["active"]
    assert again["glossary_seq"] == pointer["glossary_seq"]
