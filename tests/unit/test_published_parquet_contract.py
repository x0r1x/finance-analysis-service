"""Фаза 5 метаслоя: Published Parquet / DataMesh contract."""

from __future__ import annotations

import hashlib
import re
import tomllib
from datetime import UTC, datetime
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from finance_analysis.adapters.storage.parquet_io import write_table
from finance_analysis.domain.published_parquet import (
    PublishedParquetError,
    assert_columns_append_only,
    assert_published_contract,
    check_additive_evolution,
    check_index_matches_schemas,
    check_no_forbidden_writers,
    check_p5_required_keys,
    contract_label,
    contract_version,
    is_committed_readable,
    load_dataset_schema,
    load_published_contract,
    parse_marker_files,
    refuse_list_before_marker,
    verify_committed_files,
)

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src" / "finance_analysis"
_BUILD = "0123456789abcdef"


def test_contract_version_and_label():
    assert contract_version() == "1.0"
    assert contract_label() == "published_parquet@1.0"
    body = load_published_contract()
    assert "4.11" in body["aligns_with"]["design_sections"]
    assert "4.12" in body["aligns_with"]["design_sections"]
    assert "list_before_marker" in body["non_guarantees"]
    assert "iceberg_writers" in body["non_guarantees"]


def test_read_only_via_valid_marker():
    assert not is_committed_readable(None)
    assert not is_committed_readable({"fas_schema_version": "1.1"})
    # empty meta — не commit (P7)
    assert not is_committed_readable(
        {"files": {"a/01ARZ3NDEKTSV4RRFFQ69G5FAV/projection/fact_observation.parquet": {}}}
    )
    marker = {
        "fas_schema_version": "1.1",
        "files": {
            "a/01ARZ3NDEKTSV4RRFFQ69G5FAV/projection/fact_observation.parquet": {
                "sha256": "a" * 64,
                "rows": 3,
                "schema": "fact_observation@1.0",
            }
        },
    }
    files = parse_marker_files(marker)
    assert list(files) == ["a/01ARZ3NDEKTSV4RRFFQ69G5FAV/projection/fact_observation.parquet"]
    assert is_committed_readable(marker)


def test_parse_marker_requires_sha256_rows_schema():
    with pytest.raises(PublishedParquetError, match="нет полей"):
        parse_marker_files(
            {"files": {"projection/fact_observation.parquet": {"sha256": "a" * 64}}}
        )
    with pytest.raises(PublishedParquetError, match="sha256"):
        parse_marker_files(
            {
                "files": {
                    "projection/fact_observation.parquet": {
                        "sha256": "not-hex",
                        "rows": 1,
                        "schema": "fact_observation@1.0",
                    }
                }
            }
        )
    with pytest.raises(PublishedParquetError, match=r"\.\."):
        parse_marker_files(
            {
                "files": {
                    "../escape.parquet": {
                        "sha256": "a" * 64,
                        "rows": 0,
                        "schema": "fact_observation@1.0",
                    }
                }
            }
        )


def test_list_before_marker_refused():
    listed = [
        "a/01ARZ3NDEKTSV4RRFFQ69G5FAV/projection/fact_observation.parquet",
        "a/01ARZ3NDEKTSV4RRFFQ69G5FAV/projection/orphan.parquet",
    ]
    assert refuse_list_before_marker(marker=None, listed_keys=listed) == tuple(sorted(listed))
    marker = {
        "files": {
            "a/01ARZ3NDEKTSV4RRFFQ69G5FAV/projection/fact_observation.parquet": {
                "sha256": "b" * 64,
                "rows": 1,
                "schema": "fact_observation@1.0",
            }
        }
    }
    extras = refuse_list_before_marker(marker=marker, listed_keys=listed)
    assert extras == ("a/01ARZ3NDEKTSV4RRFFQ69G5FAV/projection/orphan.parquet",)


def _run_row() -> dict:
    return {
        "analysis_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "model_id": "job",
        "build_key": _BUILD,
        "state_seq": 1,
        "analysis_type": "audit",
        "status": "ok",
        "glossary_version": "g1",
        "taxonomy_version": "t1",
        "calibrator_version": None,
        "rules_version": None,
        "metrics_version": None,
        "profile_id": None,
        "profile_version": None,
        "derive_key": "fedcba9876543210",
        "fas_version": "0.23.0",
        "created_at_utc": datetime.now(UTC),
        "finished_at_utc": datetime.now(UTC),
        "semantic_model_version": "0123456789abcdef",
    }


def test_verify_committed_files_checks_digest_and_footer():
    payload, rows = write_table("run", [_run_row()], build_key=_BUILD)
    rel = "results/01ARZ3NDEKTSV4RRFFQ69G5FAV/run.parquet"
    marker = {
        "files": {
            rel: {
                "sha256": hashlib.sha256(payload).hexdigest(),
                "rows": rows,
                "schema": "run@1.1",
            }
        }
    }
    assert verify_committed_files(marker, {rel: payload}, allowed_prefixes=("results/",)) == []
    bad = verify_committed_files(marker, {rel: b"not-parquet"}, allowed_prefixes=("results/",))
    assert any("sha256" in item or "parquet" in item for item in bad)
    outside = verify_committed_files(marker, {rel: payload}, allowed_prefixes=("projection/",))
    assert any("allowed_prefixes" in item for item in outside)


def test_index_matches_schemas_p5_and_append_only():
    assert check_p5_required_keys() == []
    errors = check_index_matches_schemas()
    assert errors == [], errors
    assert_published_contract()


def test_schema_file_names_fails_on_non_object_json(tmp_path, monkeypatch):
    """Битый корень схемы (не object) — fail-closed, не silent skip."""

    from finance_analysis.domain import published_parquet as mod

    schemas = tmp_path / "schemas"
    schemas.mkdir()
    (schemas / "broken.json").write_text("[1, 2]", encoding="utf-8")
    monkeypatch.setattr(mod, "_SCHEMAS_DIR", schemas)
    with pytest.raises(PublishedParquetError, match="broken.json"):
        mod.schema_file_names()


def test_schema_file_names_skips_api_json_schema(tmp_path, monkeypatch):
    from finance_analysis.domain import published_parquet as mod

    schemas = tmp_path / "schemas"
    schemas.mkdir()
    (schemas / "book_rows.json").write_text(
        '{"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "array"}',
        encoding="utf-8",
    )
    (schemas / "dim_row.json").write_text(
        '{"dataset": "dim_row", "version": "1.0", "columns": []}',
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "_SCHEMAS_DIR", schemas)
    assert mod.schema_file_names() == frozenset({"dim_row"})


def test_bindings_index_requires_glossary_version():
    bindings = next(item for item in load_published_contract()["datasets"] if item["name"] == "bindings")
    assert "glossary_version" in bindings["required_keys"]
    doc = load_dataset_schema("bindings")
    assert any(col["name"] == "glossary_version" for col in doc["columns"])


def test_additive_evolution_requires_nullable_and_append_only():
    base = {
        "dataset": "demo",
        "version": "1.1",
        "columns": [
            {
                "name": "model_id",
                "type": "string",
                "nullable": False,
                "unit": "",
                "description": "",
                "since": "1.0",
            },
            {
                "name": "extra",
                "type": "string",
                "nullable": True,
                "unit": "",
                "description": "",
                "since": "1.1",
            },
        ],
    }
    assert check_additive_evolution(base) == []
    assert_columns_append_only(base)

    bad = {
        **base,
        "columns": [
            base["columns"][0],
            {**base["columns"][1], "nullable": False},
        ],
    }
    errors = check_additive_evolution(bad)
    assert any("nullable" in item for item in errors)

    reordered = {
        "dataset": "demo",
        "version": "1.1",
        "columns": [base["columns"][1], base["columns"][0]],
    }
    with pytest.raises(PublishedParquetError, match="монотонен|append"):
        assert_columns_append_only(reordered)
    assert check_additive_evolution(reordered)


def test_run_schema_smv_is_append_only_at_end():
    doc = load_dataset_schema("run")
    names = [column["name"] for column in doc["columns"]]
    assert names[-1] == "semantic_model_version"
    smv = next(col for col in doc["columns"] if col["name"] == "semantic_model_version")
    assert smv["since"] == "1.1"
    assert smv["nullable"] is True
    assert_columns_append_only(doc)
    assert check_additive_evolution(doc) == []


def test_written_run_parquet_matches_schema_and_footer():
    payload, count = write_table("run", [_run_row()], build_key=_BUILD)
    assert count == 1
    doc = load_dataset_schema("run")
    pf = pq.ParquetFile(__import__("io").BytesIO(payload))
    assert [field.name for field in pf.schema_arrow] == [c["name"] for c in doc["columns"]]
    assert pf.schema_arrow.names[-1] == "semantic_model_version"
    meta = pf.schema_arrow.metadata or {}
    assert meta[b"fas.schema"] == f"run@{doc['version']}".encode()
    assert meta[b"fas.build_key"] == _BUILD.encode()
    assert meta[b"fas.writer"].startswith(b"fas ")
    assert pf.metadata.num_row_groups == 1
    assert pf.metadata.row_group(0).column(0).compression == "ZSTD"
    table = pq.read_table(__import__("io").BytesIO(payload))
    assert table.column("semantic_model_version")[0].as_py() == "0123456789abcdef"


def test_no_iceberg_hive_writer_dependencies():
    pyproject = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    deps = list(pyproject["project"]["dependencies"])
    for extra in pyproject["project"].get("optional-dependencies", {}).values():
        deps.extend(extra)
    names = []
    for item in deps:
        name = item.split(">", 1)[0].split("=", 1)[0].split("<", 1)[0].split("[", 1)[0].strip().lower()
        names.append(name)
    errors = check_no_forbidden_writers(dependency_names=names)
    assert errors == [], errors

    pattern = re.compile(
        r"\b(pyiceberg|deltalake|LakePublisherPort|HiveCatalog|hive_metastore)\b"
    )
    hits = []
    for path in _SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            hits.append(str(path.relative_to(_ROOT)))
    assert hits == [], hits
