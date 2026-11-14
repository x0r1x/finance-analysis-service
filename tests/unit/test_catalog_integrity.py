"""Единый контракт целостности каталогов (3.4 + 3.5, review PR #54)."""

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
from finance_analysis.domain.model_type import (
    MetricExpression,
    MetricInputs,
    RowFallback,
)
from finance_analysis.domain.validation.catalog_integrity import (
    CatalogIntegrityError,
    validate_catalog_integrity,
)
from finance_analysis.domain.validation.model_types import ModelTypeInvalid


def _repo_payload():
    package = load_catalog()
    inputs, variants, composed, bases, rates, expressions = load_metric_catalog()
    del composed, rates
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
        "metric_expressions": expressions,
        "metric_bases": bases,
        "interest_order": order,
        "row_fallbacks": fallbacks,
        "coverage_document": load_coverage_document(),
    }


def test_repo_catalogs_pass_and_matching_fields_are_declarative():
    catalog = load_model_types()
    assert "interest_paid" in catalog.concepts
    assert "interest_paid" not in catalog.row_fallbacks
    # Порядок ICR на main: сначала начисление, затем уплаченные проценты.
    assert catalog.interest_order["icr"] == ("interest", "interest_paid")
    validate_catalog_integrity(**_repo_payload())


def test_interest_order_rejects_undeclared_phantom_id(tmp_path):
    body = yaml.safe_load(metrics_file().read_text(encoding="utf-8"))
    body["interest_order"]["icr"] = ["interest", "ghost_paid"]
    path = tmp_path / "coverage.yaml"
    path.write_text(yaml.safe_dump(body, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ModelTypeInvalid, match="ghost_paid"):
        load_interest_order(path, concepts=load_catalog().ids, fallbacks=load_row_fallbacks(path))


def test_interest_order_rejects_non_interest_concept():
    payload = _repo_payload()
    payload["interest_order"] = {**payload["interest_order"], "icr": ("ebitda", "interest_paid")}
    with pytest.raises(CatalogIntegrityError, match="не interest"):
        validate_catalog_integrity(**payload)


def test_interest_order_rejects_unknown_slot_and_duplicates():
    payload = _repo_payload()
    payload["interest_order"] = {**payload["interest_order"], "net_debt_ebitda": ("interest",)}
    with pytest.raises(CatalogIntegrityError, match="неизвестные слоты"):
        validate_catalog_integrity(**payload)
    payload = _repo_payload()
    payload["interest_order"] = {**payload["interest_order"], "icr": ("interest", "interest")}
    with pytest.raises(CatalogIntegrityError, match="повторы"):
        validate_catalog_integrity(**payload)


def test_row_fallback_must_not_shadow_a_concept():
    payload = _repo_payload()
    payload["row_fallbacks"] = {
        "interest": RowFallback("interest", "ebitda", "interest", "interest_basis_paid"),
    }
    with pytest.raises(CatalogIntegrityError, match="совпадает с concept_id"):
        validate_catalog_integrity(**payload)


def test_unknown_matching_rule_is_rejected():
    payload = _repo_payload()
    payload["row_fallbacks"] = {
        "extra_paid": RowFallback("extra_paid", "interest", "extra_paid", "not_a_rule"),
    }
    with pytest.raises(CatalogIntegrityError, match="неизвестный matching.rule"):
        validate_catalog_integrity(**payload)


def test_metric_input_cannot_be_only_a_fallback():
    payload = _repo_payload()
    payload["row_fallbacks"] = {
        "extra_paid": RowFallback("extra_paid", "interest", "extra_paid", "interest_basis_paid"),
    }
    payload["metric_inputs"] = {
        **payload["metric_inputs"],
        "icr": MetricInputs(frozenset({"extra_paid"}), frozenset({"ebitda"})),
    }
    with pytest.raises(CatalogIntegrityError, match="row_fallback"):
        validate_catalog_integrity(**payload)


def test_metric_dependency_cycle_including_variant_is_rejected():
    payload = _repo_payload()
    payload["metric_bases"] = {**payload["metric_bases"], "adscr": "dscr_min", "dscr_min": "adscr"}
    with pytest.raises(CatalogIntegrityError, match="цикл зависимостей"):
        validate_catalog_integrity(**payload)
    payload = _repo_payload()
    payload["metric_bases"] = {
        **payload["metric_bases"],
        "dscr.pf": "dscr.corporate_covenant",
        "dscr.corporate_covenant": "dscr.pf",
    }
    with pytest.raises(CatalogIntegrityError, match="цикл зависимостей"):
        validate_catalog_integrity(**payload)


def test_plain_formula_units_cover_dscr_and_reject_bad_pair():
    payload = _repo_payload()
    validate_catalog_integrity(**payload)
    expressions = dict(payload["metric_expressions"])
    expressions["dscr"] = MetricExpression(
        numerator_plus=("cfads",),
        denominator_plus=("discount_rate",),
    )
    payload["metric_expressions"] = expressions
    with pytest.raises(CatalogIntegrityError, match="единицы"):
        validate_catalog_integrity(**payload)


def test_composed_side_rejects_incompatible_units():
    payload = _repo_payload()
    expressions = dict(payload["metric_expressions"])
    expressions["net_debt_ebitda"] = MetricExpression(
        numerator_plus=("net_debt", "discount_rate"),
        denominator_plus=("ebitda",),
    )
    payload["metric_expressions"] = expressions
    with pytest.raises(CatalogIntegrityError, match="единицы несовместимы"):
        validate_catalog_integrity(**payload)


def test_nested_unknown_keys_are_rejected():
    payload = _repo_payload()
    document = dict(payload["coverage_document"])
    metrics = dict(document["metrics"])
    dscr = dict(metrics["dscr"])
    dscr["surprise"] = True
    metrics["dscr"] = dscr
    document["metrics"] = metrics
    payload["coverage_document"] = document
    with pytest.raises(CatalogIntegrityError, match="surprise"):
        validate_catalog_integrity(**payload)


def test_unused_row_fallback_is_rejected():
    payload = _repo_payload()
    payload["row_fallbacks"] = {
        **payload["row_fallbacks"],
        "extra_paid": RowFallback("extra_paid", "interest", "extra_paid", "interest_basis_paid"),
    }
    with pytest.raises(CatalogIntegrityError, match="не используется"):
        validate_catalog_integrity(**payload)


def test_check_config_reports_fallback_count():
    from finance_analysis.cli import _check_config

    _check_config()
