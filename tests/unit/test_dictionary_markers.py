"""Маркеры периода и потоки — из dictionaries.yaml, не из Python-констант."""

from __future__ import annotations

from pathlib import Path

import yaml

from finance_analysis.application.catalog import load_catalog
from finance_analysis.domain import periods
from finance_analysis.domain.dictionaries import clear_dictionaries_cache, load_dictionaries, marker_token_sets
from finance_analysis.domain.periods import marker_class


def test_marker_sets_match_catalog_package():
    package = load_catalog()
    assert periods.MARKER_ACTUAL == frozenset(token.casefold() for token in package.markers["actual"])
    assert periods.MARKER_PLAN == frozenset(token.casefold() for token in package.markers["plan"])
    assert periods.MARKER_ESTIMATE == frozenset(token.casefold() for token in package.markers["estimate"])
    for klass, tokens in package.markers.items():
        for token in tokens:
            assert marker_class(token) == klass


def test_yaml_only_marker_is_recognized_without_code_constants(tmp_path: Path):
    """Новый токен в YAML распознаётся без правок frozenset в periods.py."""

    novel = "neon_actual_marker"
    # Старые хардкоды periods.py этот токен не содержали.
    assert novel not in {"факт", "actual", "a", "act", "ф"}
    path = tmp_path / "dictionaries.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "flows": {"inflow": ["приток"], "outflow": ["отток"]},
                "markers": {
                    "actual": ["факт", novel],
                    "plan": ["план"],
                    "estimate": ["e"],
                },
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    clear_dictionaries_cache()
    loaded = load_dictionaries(str(path))
    markers = loaded["markers"]
    assert isinstance(markers, dict)
    assert marker_class(novel, markers=markers) == "actual"
    assert marker_class("план", markers=markers) == "plan"
    assert novel.casefold() in marker_token_sets(markers)["actual"]
    clear_dictionaries_cache()


def test_default_marker_class_reads_repo_dictionaries_yaml():
    raw = load_dictionaries()
    markers = raw["markers"]
    assert isinstance(markers, dict)
    assert "прогноз" in markers["estimate"]
    assert marker_class("прогноз") == "estimate"
    assert marker_class("custom-unknown") == "other"
    assert marker_class(None) is None
