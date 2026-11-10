"""SemanticModelVersion: воспроизводимость, lifecycle ensure/publish, анализ vs книга."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pyarrow.parquet as pq
import pytest

from finance_analysis.adapters.storage.parquet_io import PyarrowParquet, load_schema
from finance_analysis.adapters.storage.store import LocalStore
from finance_analysis.application.analyses import Target
from finance_analysis.application.model_types import load_model_types
from finance_analysis.application.rule_engine import load_rules
from finance_analysis.application.service import FasService
from finance_analysis.domain.book import FAS_SCHEMA_VERSION, Head, derive_key_for
from finance_analysis.domain.errors import AlreadyExists
from finance_analysis.domain.semantic_model import (
    HEAD_KEY,
    live_components,
    rules_stamp,
    semantic_model_components,
    semantic_model_key,
    semantic_model_version_for,
    should_advance_head,
    stamp_path,
    validate_manifest,
)
from finance_analysis.plugins.rules import RULES


class _GlossaryPeek:
    def __init__(self, active: str = "g-1", seq: int = 1) -> None:
        self.active = active
        self.seq = seq

    async def peek(self):
        return {"active": self.active, "seq": self.seq}

    def activate(self, version: str) -> None:
        self.seq += 1
        self.active = version


def _components(**overrides) -> dict:
    base = semantic_model_components(
        glossary_version="g-1",
        taxonomy_id="core-1",
        taxonomy_stamp="aaaaaaaaaaaaaaaa",
        metrics_version="1111111111111111",
        metrics_stamp="bbbbbbbbbbbbbbbb",
        model_types_version="cccccccccccccccc",
        dimensions_id="dimensions-1",
        dimensions_stamp="dddddddddddddddd",
        rules_stamp_value="eeeeeeeeeeeeeeee",
        schema_version="1.1",
    )
    base.update(overrides)
    return base


def _service(store, *, glossary: str = "g-1", glossary_seq: int = 1) -> SimpleNamespace:
    from finance_analysis.application.financial_catalog import load_financial_catalog

    rules = {code: rule.version for code, rule in load_rules().items()}
    gloss = _GlossaryPeek(glossary, glossary_seq)
    model_types = load_model_types()
    service = SimpleNamespace(
        store=store,
        model_types=model_types,
        financial_catalog=load_financial_catalog(model_types=model_types),
        _rules_versions=rules,
        glossary=gloss,
    )
    service.ensure_semantic_model = FasService.ensure_semantic_model.__get__(service, SimpleNamespace)
    service.publish_semantic_model_head = FasService.publish_semantic_model_head.__get__(
        service, SimpleNamespace
    )
    service.publish_semantic_model = FasService.publish_semantic_model.__get__(service, SimpleNamespace)
    service.recover_semantic_model = FasService.recover_semantic_model.__get__(service, SimpleNamespace)
    return service


def test_same_inputs_same_semantic_model_version():
    left = semantic_model_version_for(_components())
    right = semantic_model_version_for(_components())
    assert left == right
    assert len(left) == 16


def test_glossary_change_bumps_smv_not_via_derive_inputs_alone():
    left = semantic_model_version_for(_components(glossary="g-1"))
    right = semantic_model_version_for(_components(glossary="g-2"))
    assert left != right


def test_metrics_stamp_change_bumps_smv():
    left = semantic_model_version_for(
        _components(metrics={"version": "1111111111111111", "stamp": "bbbbbbbbbbbbbbbb"})
    )
    right = semantic_model_version_for(
        _components(metrics={"version": "1111111111111111", "stamp": "ffffffffffffffff"})
    )
    assert left != right


def test_metrics_catalog_version_change_bumps_smv():
    left = semantic_model_version_for(
        _components(metrics={"version": "1111111111111111", "stamp": "bbbbbbbbbbbbbbbb"})
    )
    right = semantic_model_version_for(
        _components(metrics={"version": "2222222222222222", "stamp": "bbbbbbbbbbbbbbbb"})
    )
    assert left != right


def test_rules_version_change_bumps_smv():
    left = rules_stamp({"missing_total_row": "1"})
    right = rules_stamp({"missing_total_row": "2"})
    assert left != right
    assert semantic_model_version_for(_components(rules=left[:16])) != semantic_model_version_for(
        _components(rules=right[:16])
    )


def test_builtin_rules_declare_nonempty_versions():
    assert RULES
    for rule in RULES:
        assert isinstance(rule.version, str) and rule.version.strip(), rule.code


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
    first = live_components(
        "none", model_types_version="mt", metrics_version="catalog1", rules_versions=rules
    )
    second = live_components(
        "none", model_types_version="mt", metrics_version="catalog1", rules_versions=rules
    )
    assert first == second
    assert first["schema"] == FAS_SCHEMA_VERSION
    assert first["metrics"]["version"] == "catalog1"
    assert first["metrics"]["stamp"]
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


def test_should_advance_head_rejects_older_glossary_seq():
    current = {"active": "bbbbbbbbbbbbbbbb", "glossary": "g-2", "glossary_seq": 5, "seq": 2}
    assert should_advance_head(current, glossary="g-1", glossary_seq=4, version="aaaaaaaaaaaaaaaa") is False
    assert should_advance_head(current, glossary="g-2", glossary_seq=5, version="bbbbbbbbbbbbbbbb") is False
    assert should_advance_head(current, glossary="g-3", glossary_seq=6, version="cccccccccccccccc") is True


def test_validate_manifest_requires_hash_match_and_components():
    components = _components()
    version = semantic_model_version_for(components)
    body = {
        "version": version,
        "components": components,
        "fas_version": "0.23.0",
        "created_at_utc": "2026-11-06T00:00:00Z",
    }
    assert validate_manifest(body)["version"] == version
    with pytest.raises(ValueError, match="hash"):
        validate_manifest({**body, "version": "0123456789abcdef"})
    broken = dict(components)
    broken["glossary"] = ""
    with pytest.raises(ValueError, match="пуст"):
        validate_manifest({**body, "version": semantic_model_version_for(broken), "components": broken})


def test_run_schema_adds_smv_append_only_at_end():
    doc = load_schema("run")
    names = [column["name"] for column in doc["columns"]]
    assert doc["version"] == "1.1"
    # P6 / Phase 5: additive column at end (not inserted before fas_version).
    assert names[-1] == "semantic_model_version"
    assert "derive_key" in names
    assert next(column for column in doc["columns"] if column["name"] == "semantic_model_version")["since"] == "1.1"


@pytest.mark.asyncio
async def test_ensure_does_not_write_global_head(tmp_path: Path):
    store = LocalStore(tmp_path / "store")
    service = _service(store)
    version = await FasService.ensure_semantic_model(service, "g-old")
    assert await store.stat(HEAD_KEY) is None
    manifest = json.loads(await store.get(semantic_model_key(version)))
    assert validate_manifest(manifest)["components"]["glossary"] == "g-old"
    again = await FasService.ensure_semantic_model(service, "g-old")
    assert again == version


@pytest.mark.asyncio
async def test_historical_ensure_does_not_roll_back_head(tmp_path: Path):
    store = LocalStore(tmp_path / "store")
    service = _service(store, glossary="g-2", glossary_seq=2)
    current = await FasService.publish_semantic_model(service, "g-2")
    pointer = json.loads(await store.get(HEAD_KEY))
    assert pointer["active"] == current
    assert pointer["glossary"] == "g-2"
    assert pointer["glossary_seq"] == 2
    historical = await FasService.ensure_semantic_model(service, "g-1")
    assert historical != current
    assert json.loads(await store.get(HEAD_KEY))["active"] == current
    stale = await FasService.publish_semantic_model(service, "g-1")
    assert stale == historical
    assert json.loads(await store.get(HEAD_KEY))["active"] == current
    assert validate_manifest(json.loads(await store.get(semantic_model_key(historical))))


@pytest.mark.asyncio
async def test_publish_head_cas_is_idempotent_and_advances_on_activation(tmp_path: Path):
    store = LocalStore(tmp_path / "store")
    service = _service(store, glossary="g-1", glossary_seq=1)
    first = await FasService.publish_semantic_model(service, "g-1")
    head = json.loads(await store.get(HEAD_KEY))
    assert head["active"] == first
    assert head["seq"] == 1
    assert head["glossary_seq"] == 1
    same = await FasService.publish_semantic_model_head(
        service, first, glossary="g-1", glossary_seq=1
    )
    assert same["active"] == first
    assert same["seq"] == 1
    service.glossary.activate("g-2")
    second = await FasService.publish_semantic_model(service, "g-2")
    assert second != first
    head = json.loads(await store.get(HEAD_KEY))
    assert head["active"] == second
    assert head["glossary"] == "g-2"
    assert head["glossary_seq"] == 2
    assert head["seq"] == 2


@pytest.mark.asyncio
async def test_stale_delayed_publish_cannot_overwrite_newer_head(tmp_path: Path):
    store = LocalStore(tmp_path / "store")
    service = _service(store, glossary="g-1", glossary_seq=1)
    old_smv = await FasService.ensure_semantic_model(service, "g-1")
    # Процесс B активировал g-2 и опубликовал указатель.
    service.glossary.activate("g-2")
    new_smv = await FasService.publish_semantic_model(service, "g-2")
    assert json.loads(await store.get(HEAD_KEY))["active"] == new_smv
    # Отложенный process A с g-1 / seq=1 не должен победить CAS.
    assert should_advance_head(
        json.loads(await store.get(HEAD_KEY)),
        glossary="g-1",
        glossary_seq=1,
        version=old_smv,
    ) is False
    rejected = await FasService.publish_semantic_model_head(
        service, old_smv, glossary="g-1", glossary_seq=1
    )
    assert rejected is None
    assert json.loads(await store.get(HEAD_KEY))["active"] == new_smv
    assert json.loads(await store.get(HEAD_KEY))["glossary_seq"] == 2


@pytest.mark.asyncio
async def test_recover_semantic_model_republishes_active(tmp_path: Path):
    from finance_analysis.application.glossary_store import GlossaryStore

    store = LocalStore(tmp_path / "store")
    service = _service(store, glossary="g-3", glossary_seq=3)

    async def _publish(version: str) -> str:
        return await FasService.publish_semantic_model(service, version)

    service.glossary.on_publish = _publish
    service.glossary.recover_semantic_model = GlossaryStore.recover_semantic_model.__get__(
        service.glossary, _GlossaryPeek
    )
    version = await FasService.recover_semantic_model(service)
    assert version
    pointer = json.loads(await store.get(HEAD_KEY))
    assert pointer["glossary"] == "g-3"
    assert pointer["glossary_seq"] == 3
    assert pointer["active"] == version


@pytest.mark.asyncio
async def test_describe_marks_estimated_smv_for_old_books(tmp_path: Path):
    store = LocalStore(tmp_path / "store")
    service = _service(store)
    estimated = await FasService.ensure_semantic_model(service, "g-legacy")

    async def _list(_prefix: str):
        if False:
            yield None

    async def _manifest(_job, _build):
        return {"builder_ref": {}, "warnings": []}

    async def _coverage(_job, _head):
        return {
            "row_coverage": {},
            "critical_path": {"covered": 1.0},
            "critical_unknown": 0,
        }

    service.store.list = _list
    service._manifest = _manifest
    service._coverage_public = _coverage
    service.describe = FasService.describe.__get__(service, SimpleNamespace)
    head = Head(
        build_key="0123456789abcdef",
        state_seq=0,
        derive_key="fedcba9876543210",
        versions={"glossary": "g-legacy", "profile": "p-0"},
    )
    view = await FasService.describe(service, "a" * 64, head, fresh=False)
    assert view.body["semantic_model_source"] == "estimated"
    assert view.body["semantic_model_version"] == estimated
    assert view.body["versions"]["semantic_model_estimated"] is True
    assert any(item.get("code") == "semantic_model_estimated" for item in view.body["warnings"])

    pinned = Head(
        build_key="0123456789abcdef",
        state_seq=0,
        derive_key="fedcba9876543210",
        versions={"glossary": "g-legacy", "semantic_model": estimated, "profile": "p-0"},
    )
    stored = await FasService.describe(service, "a" * 64, pinned, fresh=False)
    assert stored.body["semantic_model_source"] == "stored"
    assert "semantic_model_estimated" not in stored.body["versions"]


@pytest.mark.asyncio
async def test_analysis_uses_live_smv_while_book_pin_stays(tmp_path: Path):
    store = LocalStore(tmp_path / "store")
    service = _service(store)
    book_smv = await FasService.ensure_semantic_model(service, "g-1")
    # Имитация смены metrics после материализации: подменяем stamp через _rules_versions bump.
    service._rules_versions = {**service._rules_versions, "missing_total_row": "99-test"}
    live = await FasService.ensure_semantic_model(service, "g-1")
    assert live != book_smv
    head = Head(
        build_key="0123456789abcdef",
        state_seq=0,
        derive_key="fedcba9876543210",
        versions={"glossary": "g-1", "semantic_model": book_smv, "profile": "p-0"},
    )
    target = Target(
        head=head,
        build=head.build_key,
        manifest={},
        fresh=False,
        analysis_semantic_model=live,
    )
    versions = target.versions_with_smv(derive_key=head.derive_key)
    assert versions["semantic_model"] == live
    assert versions["book_semantic_model"] == book_smv
    assert head.versions["semantic_model"] == book_smv


@pytest.mark.asyncio
async def test_old_manifest_immutable_after_config_change(tmp_path: Path):
    store = LocalStore(tmp_path / "store")
    service = _service(store)
    old = await FasService.ensure_semantic_model(service, "g-1")
    raw = await store.get(semantic_model_key(old))
    service._rules_versions = {**service._rules_versions, "missing_total_row": "changed"}
    new = await FasService.ensure_semantic_model(service, "g-1")
    assert new != old
    assert await store.get(semantic_model_key(old)) == raw
    with pytest.raises(AlreadyExists):
        await store.put_if_absent(semantic_model_key(old), b"tamper")


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
    assert names[-1] == "semantic_model_version"
    assert "derive_key" in names
    assert table.column("semantic_model_version")[0].as_py() == "0123456789abcdef"
    assert table.column("derive_key")[0].as_py() == "fedcba9876543210"


@pytest.mark.asyncio
async def test_glossary_notify_survives_smv_publish_failure(tmp_path: Path):
    from finance_analysis.application.glossary_store import GlossaryStore

    store = LocalStore(tmp_path / "store")

    async def boom(_version: str):
        raise RuntimeError("object store down")

    glossary = GlossaryStore(store)
    glossary.on_publish = boom
    await glossary._notify("g-1")  # не поднимает — глоссарий уже активирован
