"""Фаза 1: явная матрица тип×метрика и снимок matrix.json."""

from __future__ import annotations

import json
import shutil

import pytest
import yaml

from finance_analysis.application.analyses import RATIO_METRICS
from finance_analysis.application.model_types import (
    load_matrix_snapshot,
    load_model_types,
    matrix_file,
    model_types_dir,
)
from finance_analysis.domain.model_type import applicability
from finance_analysis.domain.validation.model_types import (
    ModelTypeInvalid,
    build_applicability_matrix,
    validate_model_types,
)

# Типы без показателей покрытия из текущего каталога: все cover/NPV = not_applicable.
# Полноценные типы моделей; будущие метрики не запрещены. Renewables / RE — DSCR optional.
_NO_COVER_METRICS = ("lbo_ma", "dcf_valuation", "bank_leasing")
_OPTIONAL_DSCR = frozenset({"dscr", "dscr_min", "dscr_avg"})
_DSCR_VARIANT_TYPES = ("renewables_dpm", "real_estate_income")


def _catalog():
    return load_model_types()


def test_repo_matrix_snapshot_matches_yaml_dump():
    catalog = _catalog()
    snapshot = load_matrix_snapshot()
    dump = build_applicability_matrix(
        catalog.documents,
        catalog.metric_inputs,
        default_use=catalog.default_use,
    )
    assert snapshot == dump
    assert sorted(snapshot) == sorted(RATIO_METRICS)
    assert set(next(iter(snapshot.values()))) == set(catalog.types)


def test_missing_explicit_use_fails_validation():
    catalog = _catalog()
    types = {key: dict(body) for key, body in catalog.documents.items()}
    pf = dict(types["project_finance"])
    metrics = dict(pf["metrics"])
    del metrics["net_debt_ebitda"]
    pf["metrics"] = metrics
    types["project_finance"] = pf
    with pytest.raises(ModelTypeInvalid, match="нет явного use"):
        validate_model_types(
            types,
            concepts=catalog.concepts,
            metric_inputs=catalog.metric_inputs,
            variant_inputs=catalog.variant_inputs,
        )


def test_matrix_mismatch_fails_check_config(tmp_path, monkeypatch):
    from finance_analysis.cli import _check_config

    folder = tmp_path / "model_types"
    shutil.copytree(model_types_dir(), folder)
    body = json.loads((folder / "matrix.json").read_text(encoding="utf-8"))
    body["dscr"]["project_finance"]["use"] = "optional"
    (folder / "matrix.json").write_text(
        json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "finance_analysis.application.model_types.model_types_dir", lambda: folder
    )
    with pytest.raises(SystemExit) as caught:
        _check_config()
    assert caught.value.code == 1


def test_star_alone_does_not_cover_known_metrics(tmp_path, monkeypatch):
    folder = tmp_path / "model_types"
    shutil.copytree(model_types_dir(), folder)
    other = yaml.safe_load((folder / "other.yaml").read_text(encoding="utf-8"))
    other["metrics"] = {"*": {"use": "optional"}}
    (folder / "other.yaml").write_text(
        yaml.safe_dump(other, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    # Снимок ещё отражает старые явные ячейки — но сначала падает явный use.
    monkeypatch.setattr(
        "finance_analysis.application.model_types.model_types_dir", lambda: folder
    )
    with pytest.raises(ModelTypeInvalid, match="нет явного use"):
        load_model_types()


def test_no_cover_metrics_and_dscr_optional_types_match_intended_cells():
    catalog = _catalog()
    for type_id in _NO_COVER_METRICS:
        for metric in RATIO_METRICS:
            assert applicability(catalog, (type_id,), metric) == "not_applicable", (
                type_id,
                metric,
            )
            assert catalog.types[type_id].metrics[metric] == "not_applicable"
            assert metric not in catalog.types[type_id].variants
    for type_id in _DSCR_VARIANT_TYPES:
        for metric in RATIO_METRICS:
            use = applicability(catalog, (type_id,), metric)
            if metric in _OPTIONAL_DSCR:
                assert use == "optional", (type_id, metric)
            else:
                assert use == "not_applicable", (type_id, metric)
        assert catalog.types[type_id].variants["dscr"] == "pf"


def test_matrix_file_path_is_under_model_types():
    assert matrix_file().name == "matrix.json"
    assert matrix_file().parent == model_types_dir()
