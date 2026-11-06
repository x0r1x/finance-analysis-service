"""Единый контракт целостности каталогов (3.4 + 3.5)."""

from __future__ import annotations

import pytest
import yaml

from finance_analysis.application.catalog import load_catalog, load_dimensions
from finance_analysis.application.model_types import (
    load_coverage_document,
    load_interest_order,
    load_metric_catalog,
    load_model_types,
    load_row_fallbacks,
    metrics_file,
    model_types_dir,
)
from finance_analysis.domain.model_type import Composed, MetricInputs, RowFallback, Side
from finance_analysis.domain.validation.catalog_integrity import (
    CatalogIntegrityError,
    validate_catalog_integrity,
)
from finance_analysis.domain.validation.model_types import ModelTypeInvalid


def _repo_payload():
    package = load_catalog()
    inputs, variants, composed, bases, rates = load_metric_catalog()
    fallbacks = load_row_fallbacks()
    order = load_interest_order(concepts=package.ids, fallbacks=fallbacks)
    documents = {}
    for file in sorted(model_types_dir().glob("*.yaml")):
        if file.name.startswith("_"):
            continue
        documents[file.stem] = yaml.safe_load(file.read_text(encoding="utf-8"))
    return {
        "concepts": package.ids,
        "concept_dimensions": {name: item.dimension for name, item in package.concepts.items()},
        "dimensions": load_dimensions(),
        "model_documents": documents,
        "metric_inputs": inputs,
        "variant_inputs": variants,
        "composed": composed,
        "metric_bases": bases,
        "metric_rates": rates,
        "interest_order": order,
        "row_fallbacks": fallbacks,
        "coverage_keys": frozenset(load_coverage_document()),
    }


def test_repo_catalogs_pass_integrity_and_interest_paid_is_fallback():
    catalog = load_model_types()
    assert "interest_paid" not in catalog.concepts
    assert "interest_paid" in catalog.row_fallbacks
    assert catalog.row_fallbacks["interest_paid"].canonical == "interest"
    validate_catalog_integrity(**_repo_payload())


def test_interest_order_rejects_undeclared_phantom_id(tmp_path):
    body = yaml.safe_load(metrics_file().read_text(encoding="utf-8"))
    body["interest_order"]["icr"] = ["interest", "ghost_paid"]
    path = tmp_path / "coverage.yaml"
    path.write_text(yaml.safe_dump(body, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ModelTypeInvalid, match="ghost_paid"):
        load_interest_order(path, concepts=load_catalog().ids, fallbacks=load_row_fallbacks(path))


def test_row_fallback_must_not_shadow_a_concept():
    payload = _repo_payload()
    payload["row_fallbacks"] = {
        "interest": RowFallback("interest", "ebitda", "interest", "bad"),
    }
    with pytest.raises(CatalogIntegrityError, match="совпадает с concept_id"):
        validate_catalog_integrity(**payload)


def test_metric_input_cannot_be_only_a_fallback():
    payload = _repo_payload()
    payload["metric_inputs"] = {
        **payload["metric_inputs"],
        "icr": MetricInputs(frozenset({"interest_paid"}), frozenset({"ebitda"})),
    }
    with pytest.raises(CatalogIntegrityError, match="row_fallback"):
        validate_catalog_integrity(**payload)


def test_metric_base_cycle_is_rejected():
    payload = _repo_payload()
    payload["metric_bases"] = {"adscr": "dscr_min", "dscr_min": "adscr"}
    with pytest.raises(CatalogIntegrityError, match="цикл base"):
        validate_catalog_integrity(**payload)


def test_composed_side_rejects_incompatible_units():
    payload = _repo_payload()
    payload["composed"] = {
        **payload["composed"],
        "net_debt_ebitda": Composed(
            Side(("net_debt", "discount_rate"), ()),
            Side(("ebitda",), ()),
            "LTM",
        ),
    }
    with pytest.raises(CatalogIntegrityError, match="единицы несовместимы"):
        validate_catalog_integrity(**payload)


def test_composed_ratio_rejects_incompatible_sides():
    payload = _repo_payload()
    payload["composed"] = {
        **payload["composed"],
        "net_debt_ebitda": Composed(
            Side(("net_debt",), ()),
            Side(("discount_rate",), ()),
            "LTM",
        ),
    }
    with pytest.raises(CatalogIntegrityError, match="числителя и знаменателя"):
        validate_catalog_integrity(**payload)


def test_unknown_coverage_key_is_rejected():
    payload = _repo_payload()
    payload["coverage_keys"] = payload["coverage_keys"] | frozenset({"phantom_section"})
    with pytest.raises(CatalogIntegrityError, match="phantom_section"):
        validate_catalog_integrity(**payload)


def test_unused_row_fallback_is_rejected():
    payload = _repo_payload()
    payload["row_fallbacks"] = {
        **payload["row_fallbacks"],
        "extra_paid": RowFallback("extra_paid", "interest", "extra_paid", "unused"),
    }
    with pytest.raises(CatalogIntegrityError, match="не используется"):
        validate_catalog_integrity(**payload)


def test_check_config_reports_fallback_count():
    from finance_analysis.cli import _check_config

    # Smoke: real catalog loads through the CLI entry.
    _check_config()
