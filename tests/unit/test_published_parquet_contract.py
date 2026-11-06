"""Фаза 5 метаслоя: Published Parquet / DataMesh contract."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from finance_analysis.domain.published_parquet import (
    PublishedParquetError,
    assert_columns_append_only,
    assert_published_contract,
    check_additive_evolution,
    check_index_matches_schemas,
    check_no_forbidden_writers,
    contract_label,
    contract_version,
    is_committed_readable,
    load_published_contract,
    marker_files,
    refuse_list_before_marker,
)

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src" / "finance_analysis"


def test_contract_version_and_label():
    assert contract_version() == "1.0"
    assert contract_label() == "published_parquet@1.0"
    body = load_published_contract()
    assert "4.11" in body["aligns_with"]["design_sections"]
    assert "4.12" in body["aligns_with"]["design_sections"]
    assert "list_before_marker" in body["non_guarantees"]
    assert "iceberg_writers" in body["non_guarantees"]


def test_read_only_via_marker():
    assert marker_files(None) == {}
    assert not is_committed_readable(None)
    assert not is_committed_readable({"fas_schema_version": "1.1"})
    marker = {
        "fas_schema_version": "1.1",
        "files": {
            "a/01ARZ3NDEKTSV4RRFFQ69G5FAV/projection/fact_observation.parquet": {
                "sha256": "abc",
                "rows": 3,
                "schema": "fact_observation@1.0",
            }
        },
    }
    files = marker_files(marker)
    assert list(files) == ["a/01ARZ3NDEKTSV4RRFFQ69G5FAV/projection/fact_observation.parquet"]
    assert is_committed_readable(marker)


def test_list_before_marker_refused():
    listed = [
        "a/01ARZ3NDEKTSV4RRFFQ69G5FAV/projection/fact_observation.parquet",
        "a/01ARZ3NDEKTSV4RRFFQ69G5FAV/projection/orphan.parquet",
    ]
    assert refuse_list_before_marker(marker=None, listed_keys=listed) == tuple(sorted(listed))
    marker = {
        "files": {
            "a/01ARZ3NDEKTSV4RRFFQ69G5FAV/projection/fact_observation.parquet": {
                "sha256": "x",
                "rows": 1,
                "schema": "fact_observation@1.0",
            }
        }
    }
    extras = refuse_list_before_marker(marker=marker, listed_keys=listed)
    assert extras == ("a/01ARZ3NDEKTSV4RRFFQ69G5FAV/projection/orphan.parquet",)


def test_index_matches_schemas_and_additive_rules():
    errors = check_index_matches_schemas()
    assert errors == [], errors
    assert_published_contract()


def test_additive_evolution_requires_nullable_new_columns():
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
        "columns": [
            base["columns"][1],
            base["columns"][0],
        ],
    }
    with pytest.raises(PublishedParquetError, match="монотонен|append"):
        assert_columns_append_only(reordered)


def test_run_schema_additive_column_is_nullable():
    from finance_analysis.domain.published_parquet import load_dataset_schema

    doc = load_dataset_schema("run")
    smv = next(col for col in doc["columns"] if col["name"] == "semantic_model_version")
    assert smv["since"] == "1.1"
    assert smv["nullable"] is True
    assert check_additive_evolution(doc) == []


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

    # Импорты/символы писателей: ищем целые токены, не поясняющие docstring'и.
    import re

    pattern = re.compile(
        r"\b(pyiceberg|deltalake|LakePublisherPort|HiveCatalog|hive_metastore)\b"
    )
    hits = []
    for path in _SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            hits.append(str(path.relative_to(_ROOT)))
    assert hits == [], hits
