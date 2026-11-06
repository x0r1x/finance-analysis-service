"""SemanticModelVersion: воспроизводимость и отличие от derive_key."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pyarrow.parquet as pq
import pytest

from finance_analysis.adapters.storage.parquet_io import PyarrowParquet, load_schema
from finance_analysis.adapters.storage.store import LocalStore
from finance_analysis.application.model_types import load_model_types
from finance_analysis.application.rule_engine import load_rules
from finance_analysis.application.service import FasService
from finance_analysis.domain.book import FAS_SCHEMA_VERSION, Head, derive_key_for
from finance_analysis.domain.semantic_model import (
    HEAD_KEY,
    live_components,
    rules_stamp,
    semantic_model_components,
    semantic_model_key,
    semantic_model_version_for,
    stamp_path,
)


def _components(**overrides) -> dict:
    base = semantic_model_components(
        glossary_version="g-1",
        taxonomy_id="core-1",
        taxonomy_stamp="aaaaaaaaaaaaaaaa",
        metrics_stamp="bbbbbbbbbbbbbbbb",
        model_types_version="cccccccccccccccc",
        dimensions_id="dimensions-1",
        dimensions_stamp="dddddddddddddddd",
        rules_stamp_value="eeeeeeeeeeeeeeee",
        schema_version="1.1",
    )
    base.update(overrides)
    return base


def test_same_inputs_same_semantic_model_version():
    left = semantic_model_version_for(_components())
    right = semantic_model_version_for(_components())
    assert left == right
    assert len(left) == 16


def test_glossary_change_bumps_smv_not_via_derive_inputs_alone():
    left = semantic_model_version_for(_components(glossary="g-1"))
    right = semantic_model_version_for(_components(glossary="g-2"))
    assert left != right


def test_state_seq_changes_derive_key_not_smv():
    components = _components()
    smv = semantic_model_version_for(components)
    shared = {
        "glossary_version": "g-1",
        "taxonomy_version": "core-1",
        "calibrator_version": "none",
        "embed_model": "",
        "rerank_model": "",
        "clm_model": "",
        "profile_version": "p-0",
        "fas_derive_version": "1",
        "model_types_version": "cccccccccccccccc",
        "model_type_seq": 0,
        "sheet_roles_version": "none",
    }
    assert derive_key_for(state_seq=0, **shared) != derive_key_for(state_seq=1, **shared)
    assert semantic_model_version_for(components) == smv


def test_live_components_stable_and_include_schema():
    rules = {"missing_total_row": "1"}
    first = live_components("none", model_types_version="mt", rules_versions=rules)
    second = live_components("none", model_types_version="mt", rules_versions=rules)
    assert first == second
    assert first["schema"] == FAS_SCHEMA_VERSION
    assert semantic_model_version_for(first) == semantic_model_version_for(second)


def test_stamp_ignores_line_endings(tmp_path: Path):
    path = tmp_path / "configs" / "metrics"
    path.mkdir(parents=True)
    file = path / "coverage.yaml"
    file.write_bytes(b"metrics:\r\n  dscr: {}\r\n")
    crlf = stamp_path(tmp_path, "configs/metrics")
    file.write_bytes(b"metrics:\n  dscr: {}\n")
    assert stamp_path(tmp_path, "configs/metrics") == crlf


def test_rules_stamp_order_independent():
    assert rules_stamp({"a": "1", "b": "2"}) == rules_stamp({"b": "2", "a": "1"})
    assert rules_stamp({"a": "1"}) != rules_stamp({"a": "2"})


def test_run_schema_adds_smv_beside_derive_key():
    doc = load_schema("run")
    names = [column["name"] for column in doc["columns"]]
    assert doc["version"] == "1.1"
    assert names.index("semantic_model_version") == names.index("derive_key") + 1
    assert next(column for column in doc["columns"] if column["name"] == "semantic_model_version")["since"] == "1.1"


@pytest.mark.asyncio
async def test_ensure_semantic_model_persists_manifest(tmp_path: Path):
    store = LocalStore(tmp_path / "store")
    rules = {code: rule.version for code, rule in load_rules().items()}
    model_types = load_model_types()
    service = SimpleNamespace(store=store, model_types=model_types, _rules_versions=rules)
    version = await FasService.ensure_semantic_model(service, "g-test")
    again = await FasService.ensure_semantic_model(service, "g-test")
    assert version == again
    assert len(version) == 16
    manifest = json.loads(await store.get(semantic_model_key(version)))
    assert manifest["version"] == version
    assert manifest["components"]["glossary"] == "g-test"
    pointer = json.loads(await store.get(HEAD_KEY))
    assert pointer["active"] == version

    # Книжный ответ держит SMV рядом с derive_key (как describe).
    head = Head(
        build_key="0123456789abcdef",
        state_seq=0,
        derive_key="fedcba9876543210",
        versions={"glossary": "g-test", "semantic_model": version, "profile": "p-0"},
    )
    book = {
        "derive_key": head.derive_key,
        "semantic_model_version": head.versions.get("semantic_model"),
        "versions": head.versions,
    }
    assert book["semantic_model_version"] == version
    assert book["semantic_model_version"] != book["derive_key"]
    assert book["versions"]["semantic_model"] == book["semantic_model_version"]


@pytest.mark.asyncio
async def test_run_parquet_writes_smv_beside_derive_key(tmp_path: Path):
    parquet = PyarrowParquet()
    row = {
        "analysis_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "model_id": "a" * 64,
        "build_key": "0123456789abcdef",
        "state_seq": 1,
        "analysis_type": "ratios",
        "status": "succeeded",
        "glossary_version": "g-1",
        "taxonomy_version": "core-1",
        "calibrator_version": "none",
        "rules_version": "{}",
        "metrics_version": "ratios",
        "profile_id": "p-0",
        "profile_version": "p-0",
        "derive_key": "fedcba9876543210",
        "semantic_model_version": "0123456789abcdef",
        "fas_version": "0.23.0",
        "created_at_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        "finished_at_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    }
    payload, count = await parquet.write("run", [row], build_key="0123456789abcdef")
    assert count == 1
    path = tmp_path / "run.parquet"
    path.write_bytes(payload)
    table = pq.read_table(path)
    names = table.column_names
    assert names.index("semantic_model_version") == names.index("derive_key") + 1
    assert table.column("semantic_model_version")[0].as_py() == "0123456789abcdef"
    assert table.column("derive_key")[0].as_py() == "fedcba9876543210"
