"""Вывод типа модели и применимость метрик (срез 1)."""

from __future__ import annotations

import pytest

from finance_analysis.domain.audit import AuditInput
from finance_analysis.domain.model_type import (
    applicability,
    contradicts_signals,
    effective,
    infer,
)
from finance_analysis.domain.validation.model_types import (
    ModelTypeInvalid,
    validate_model_types,
)
from finance_analysis.plugins.rules.coverage import MISSING_TOTAL_ROW


def _catalog():
    from finance_analysis.application.model_types import load_model_types

    return load_model_types()


def test_cfads_and_debt_service_are_project_finance():
    catalog = _catalog()
    got = infer(
        catalog,
        bound=frozenset({"cfads", "debt_service"}),
        sheets=frozenset({"Debt", "CFS"}),
        accept=0.6,
        gap=0.15,
    )
    assert got.confident is True
    assert got.primary == "project_finance"
    assert got.labels == ("project_finance",)
    assert got.scores["project_finance"] == 1.0
    assert got.scores["corporate"] == 0.0


def test_three_statements_are_corporate_and_dscr_does_not_apply():
    """Синтетическая corporate-книга: три формы отчётности, без строк клиента."""
    catalog = _catalog()
    got = infer(
        catalog,
        bound=frozenset(),
        sheets=frozenset({"ОПиУ", "Баланс", "ДДС"}),
        accept=0.6,
        gap=0.15,
    )
    assert got.confident is True
    assert got.primary == "corporate"
    assert applicability(catalog, got.labels, "dscr") == "not_applicable"
    assert applicability(catalog, got.labels, "llcr") == "not_applicable"
    assert applicability(catalog, got.labels, "icr") == "required"


def test_gap_below_threshold_asks_and_unions_candidates():
    catalog = _catalog()
    got = infer(
        catalog,
        bound=frozenset({"cfads", "debt_service"}),
        sheets=frozenset({"ОПиУ", "Баланс", "ДДС"}),
        accept=0.6,
        gap=0.15,
    )
    assert got.confident is False
    assert got.reason == "ambiguous"
    labels = tuple(item.type_id for item in got.candidates)
    assert set(labels) == {"project_finance", "corporate"}
    assert applicability(catalog, labels, "dscr") == "required"
    assert applicability(catalog, labels, "icr") == "required"


def test_nothing_fired_does_not_drop_a_metric():
    catalog = _catalog()
    got = infer(catalog, bound=frozenset(), sheets=frozenset({"Model"}), accept=0.6, gap=0.15)
    assert got.confident is False
    assert got.reason == "unknown"
    assert applicability(catalog, (), "dscr") == "required"
    assert applicability(catalog, (), "icr") == "required"


def test_book_fact_beats_profile_and_profile_beats_a_weak_guess():
    catalog = _catalog()
    weak = infer(catalog, bound=frozenset(), sheets=frozenset({"Model"}), accept=0.6, gap=0.15)
    profile = {"labels": ["corporate"], "primary": "corporate"}
    used = effective(weak, confirmed=None, profile_default=profile, profile_version="bank@p-1")
    assert used.source == "profile"
    assert used.primary == "corporate"
    confirmed = {"labels": ["project_finance"], "primary": "project_finance", "seq": 4}
    over = effective(weak, confirmed=confirmed, profile_default=profile, profile_version="bank@p-1")
    assert over.source == "confirmed"
    assert over.primary == "project_finance"
    assert over.seq == 4


def test_profile_conflict_asks_instead_of_applying_the_profile():
    catalog = _catalog()
    strong = infer(
        catalog,
        bound=frozenset({"cfads", "debt_service"}),
        sheets=frozenset({"Debt"}),
        accept=0.6,
        gap=0.15,
    )
    profile = {"labels": ["corporate"], "primary": "corporate"}
    used = effective(strong, confirmed=None, profile_default=profile, profile_version="bank@p-2")
    assert used.source == "unresolved"
    assert used.reason == "profile_conflict"
    assert contradicts_signals(strong.scores, "corporate") is True
    offered = {item.type_id: item.score for item in used.candidates}
    assert offered["project_finance"] == 1.0
    assert offered["corporate"] == 0.0


def test_corporate_book_does_not_raise_missing_total_row_for_cfads():
    data = AuditInput(
        bindings=[
            {"row_key": None, "effective_concept": "cfads", "status": "unknown", "source": "confirmed"},
        ],
        applicable_metrics=frozenset({"icr"}),
    )
    assert MISSING_TOTAL_ROW.check(data) == []


def test_flat_sheet_group_fails_check_config(tmp_path, monkeypatch):
    import shutil

    import yaml

    from finance_analysis.application.model_types import model_types_dir
    from finance_analysis.cli import _check_config

    catalog = _catalog()
    validate_model_types(catalog.documents, concepts=catalog.concepts, metric_inputs=catalog.metric_inputs)
    folder = tmp_path / "model_types"
    shutil.copytree(model_types_dir(), folder)
    body = yaml.safe_load((folder / "corporate.yaml").read_text(encoding="utf-8"))
    body["signals"][0]["groups"] = ["ОПиУ", "Баланс", "ДДС"]
    (folder / "corporate.yaml").write_text(yaml.safe_dump(body, allow_unicode=True, sort_keys=False), encoding="utf-8")
    monkeypatch.setattr("finance_analysis.application.model_types.model_types_dir", lambda: folder)
    with pytest.raises(SystemExit) as caught:
        _check_config()
    assert caught.value.code == 1


def test_validator_rejects_an_unknown_metric():
    catalog = _catalog()
    types = {key: dict(body) for key, body in catalog.documents.items()}
    corporate = dict(types["corporate"])
    corporate["metrics"] = {**corporate["metrics"], "nope": {"use": "required"}}
    types["corporate"] = corporate
    with pytest.raises(ModelTypeInvalid, match="nope"):
        validate_model_types(types, concepts=catalog.concepts, metric_inputs=catalog.metric_inputs)
