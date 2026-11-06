"""Маркеры периода и потоки — из dictionaries.yaml, не из Python-констант."""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest
import yaml

from finance_analysis.adapters.builder.acl import parse_context
from finance_analysis.application.catalog import load_catalog
from finance_analysis.application.project import project
from finance_analysis.domain import periods
from finance_analysis.domain.book import FAS_PROJECTION_VERSION
from finance_analysis.domain.derive_fingerprint import (
    CONFIG_SOURCES,
    PACKAGE_SOURCES,
    configs_root,
    derive_fingerprint,
)
from finance_analysis.domain.dictionaries import (
    clear_dictionaries_cache,
    load_dictionaries,
    marker_token_sets,
)
from finance_analysis.domain.glossary import GlossaryInvalid, parse_dictionary_groups
from finance_analysis.domain.periods import marker_class, split_period_key
from tests.conftest import JOB


def _write_dicts(path: Path, *, markers: dict, flows: dict | None = None) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "flows": flows or {"inflow": ["приток"], "outflow": ["отток"]},
                "markers": markers,
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )


def test_marker_sets_match_catalog_package():
    package = load_catalog()
    assert periods.MARKER_ACTUAL == frozenset(token.casefold() for token in package.markers["actual"])
    assert periods.MARKER_PLAN == frozenset(token.casefold() for token in package.markers["plan"])
    assert periods.MARKER_ESTIMATE == frozenset(token.casefold() for token in package.markers["estimate"])
    for klass, tokens in package.markers.items():
        for token in tokens:
            assert marker_class(token) == klass


def test_yaml_only_marker_via_default_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Новый токен только в temp YAML → marker_class(token) без markers=."""

    novel = "neon_actual_marker"
    assert novel not in {"факт", "actual", "a", "act", "ф"}
    path = tmp_path / "dictionaries.yaml"
    _write_dicts(
        path,
        markers={"actual": ["факт", novel], "plan": ["план"], "estimate": ["e"]},
    )
    monkeypatch.setattr("finance_analysis.domain.dictionaries.dictionaries_file", lambda: path)
    clear_dictionaries_cache()
    assert marker_class(novel) == "actual"
    assert novel.casefold() in periods.MARKER_ACTUAL
    assert marker_class("план") == "plan"
    clear_dictionaries_cache()


def test_default_marker_class_reads_repo_dictionaries_yaml():
    raw = load_dictionaries()
    markers = raw["markers"]
    assert "прогноз" in markers["estimate"]
    assert marker_class("прогноз") == "estimate"
    assert marker_class("custom-unknown") == "other"
    assert marker_class(None) is None


def test_yaml_change_recognized_after_cache_invalidation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "dictionaries.yaml"
    _write_dicts(path, markers={"actual": ["факт"], "plan": ["план"], "estimate": ["e"]})
    monkeypatch.setattr("finance_analysis.domain.dictionaries.dictionaries_file", lambda: path)
    clear_dictionaries_cache()
    assert marker_class("late_token") == "other"

    _write_dicts(
        path,
        markers={"actual": ["факт", "late_token"], "plan": ["план"], "estimate": ["e"]},
    )
    assert marker_class("late_token") == "other"
    clear_dictionaries_cache()
    assert marker_class("late_token") == "actual"
    clear_dictionaries_cache()


def test_alt_catalog_markers_require_explicit_markers_arg(tmp_path: Path):
    """Alt-каталог не подменяет default marker_class; нужен markers=package.markers."""

    shutil.copytree(configs_root() / "configs", tmp_path / "configs")
    dict_path = tmp_path / "configs" / "glossary" / "dictionaries.yaml"
    body = yaml.safe_load(dict_path.read_text(encoding="utf-8"))
    novel = "alt_catalog_only_marker"
    body["markers"]["actual"].append(novel)
    dict_path.write_text(yaml.safe_dump(body, allow_unicode=True), encoding="utf-8")

    clear_dictionaries_cache()
    package = load_catalog(tmp_path / "configs" / "concepts" / "core.yaml")
    assert novel in package.markers["actual"]
    assert marker_class(novel) == "other"
    assert marker_class(novel, markers=package.markers) == "actual"
    clear_dictionaries_cache()


def test_invalid_dictionary_entries_raise_without_silent_drop(tmp_path: Path):
    with pytest.raises(GlossaryInvalid) as bad_int:
        parse_dictionary_groups({"actual": ["факт", 123], "plan": ["план"], "estimate": ["e"]}, "markers")
    assert "actual" in bad_int.value.labels

    with pytest.raises(GlossaryInvalid) as bad_empty:
        parse_dictionary_groups({"actual": ["факт", ""], "plan": ["план"], "estimate": ["e"]}, "markers")
    assert "actual" in bad_empty.value.labels

    with pytest.raises(GlossaryInvalid) as bad_null:
        parse_dictionary_groups({"actual": ["факт", None], "plan": ["план"], "estimate": ["e"]}, "markers")
    assert "actual" in bad_null.value.labels

    with pytest.raises(GlossaryInvalid) as missing:
        parse_dictionary_groups({"plan": ["план"], "estimate": ["e"]}, "markers")
    assert "actual" in missing.value.labels

    with pytest.raises(GlossaryInvalid) as blank:
        parse_dictionary_groups({"actual": ["  "], "plan": ["план"], "estimate": ["e"]}, "markers")
    assert "actual" in blank.value.labels

    with pytest.raises(GlossaryInvalid) as dup:
        parse_dictionary_groups(
            {"actual": ["факт"], "plan": ["Факт"], "estimate": ["e"]},
            "markers",
        )
    assert "Факт" in dup.value.labels or "факт" in dup.value.labels

    path = tmp_path / "dictionaries.yaml"
    _write_dicts(
        path,
        markers={"actual": ["факт", None], "plan": ["план"], "estimate": ["e"]},
    )
    clear_dictionaries_cache()
    with pytest.raises(GlossaryInvalid):
        load_dictionaries(str(path))
    clear_dictionaries_cache()


def test_spaced_yaml_token_matches_stripped_marker():
    markers = parse_dictionary_groups(
        {"actual": [" факт"], "plan": ["план"], "estimate": ["e"]},
        "markers",
    )
    assert markers["actual"] == ("факт",)
    assert marker_class("факт", markers=markers) == "actual"
    assert marker_class(" факт", markers=markers) == "actual"


def test_missing_marker_class_raises():
    with pytest.raises(GlossaryInvalid) as caught:
        marker_token_sets({"plan": ["план"], "estimate": ["e"]})
    assert "actual" in caught.value.labels


def test_dictionaries_yaml_in_derive_fingerprint_and_projection_stamp():
    assert "configs/glossary/dictionaries.yaml" in CONFIG_SOURCES
    assert "domain/dictionaries.py" in PACKAGE_SOURCES
    assert FAS_PROJECTION_VERSION.startswith("3:")
    assert len(FAS_PROJECTION_VERSION) > 4
    assert derive_fingerprint() == derive_fingerprint()


def test_period_keys_classify_through_project_path():
    """Реальные period_key проходят split + project → dim_period.marker_class."""

    for key, expected in (
        ("2026Q1@actual", "actual"),
        ("2026Q1@plan", "plan"),
        ("2026Q1@forecast", "estimate"),
    ):
        base, marker = split_period_key(key)
        assert base == "2026Q1"
        assert marker_class(marker) == expected

    context = {
        "axes": {
            "years": {
                "id": "years",
                "sheet": "Model",
                "periods": [
                    {"col": 8, "text": "2026Q1 actual", "period_key": "2026Q1@actual", "index": 1},
                    {"col": 9, "text": "2026Q1 plan", "period_key": "2026Q1@plan", "index": 2},
                    {"col": 10, "text": "2026Q1 forecast", "period_key": "2026Q1@forecast", "index": 3},
                ],
            }
        },
        "blocks": [
            {
                "block_id": "b",
                "sheet": "Model",
                "kind": "timeline",
                "rows": [
                    {
                        "row_key": "rev",
                        "sheet": "Model",
                        "row": 10,
                        "label": "Revenue",
                        "kind": "fact",
                        "series": [
                            {
                                "axis_id": "years",
                                "values": ["1", "2", "3"],
                                "value_statuses": ["cached", "cached", "cached"],
                            }
                        ],
                    }
                ],
            }
        ],
    }
    tables, _warnings = project(parse_context(context), model_id=JOB, build="0123456789abcdef")
    by_id = {row["period_id"]: row for row in tables["dim_period"]}
    assert by_id["2026Q1@actual"]["marker_class"] == "actual"
    assert by_id["2026Q1@plan"]["marker_class"] == "plan"
    assert by_id["2026Q1@forecast"]["marker_class"] == "estimate"
    assert by_id["2026Q1@actual"]["period_start"] == date(2026, 1, 1)
    assert by_id["2026Q1@actual"]["period_end"] == date(2026, 3, 31)
