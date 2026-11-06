"""Financial Model Catalog (фаза 3): записи показателей, версия в SMV, целостность."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from finance_analysis.application.analyses import RATIO_METRICS
from finance_analysis.application.financial_catalog import load_financial_catalog
from finance_analysis.application.model_types import load_model_types, metrics_file
from finance_analysis.domain.financial_catalog import (
    catalog_version_for,
    validate_indicator_records,
)
from finance_analysis.domain.semantic_model import (
    live_components,
    semantic_model_version_for,
)
from finance_analysis.domain.validation.catalog_integrity import (
    validate_catalog_integrity,
)
from finance_analysis.domain.validation.model_types import ModelTypeInvalid

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "src/finance_analysis/domain/contracts/financial_model_catalog.json"
)


def _schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def test_repo_catalog_covers_public_metrics_with_inputs_and_units():
    catalog = load_financial_catalog()
    assert catalog.version
    assert catalog.stamp
    assert len(catalog.version) == 16
    for metric_id in RATIO_METRICS:
        item = catalog.get(metric_id)
        assert item is not None, metric_id
        assert item.id == metric_id
        assert item.unit
        assert item.status == "active"
        assert item.inputs.concepts or item.base, metric_id
        assert item.formula.as_dict() or item.base, metric_id
        assert item.model_types
        for use in item.model_types.values():
            assert use.use in {"required", "optional", "not_applicable"}


def test_catalog_version_stable_and_in_smv_metrics_component():
    catalog = load_financial_catalog()
    again = load_financial_catalog()
    assert catalog.version == again.version
    assert catalog.version == catalog_version_for(catalog.indicators)
    components = live_components(
        "none",
        model_types_version=load_model_types().version,
        metrics_version=catalog.version,
        rules_versions={"missing_total_row": "1"},
    )
    assert components["metrics"] == {"version": catalog.version, "stamp": catalog.stamp}
    assert semantic_model_version_for(components) == semantic_model_version_for(dict(components))


def test_metric_inputs_subset_of_taxonomy_concepts():
    from finance_analysis.application.catalog import load_catalog, load_dimensions
    from finance_analysis.application.model_types import (
        load_coverage_document,
        load_interest_order,
        load_metric_catalog,
        load_row_fallbacks,
        model_types_dir,
    )

    package = load_catalog()
    inputs, variants, _composed, bases, _rates, expressions = load_metric_catalog()
    fallbacks = load_row_fallbacks()
    order = load_interest_order(concepts=package.ids, fallbacks=fallbacks)
    documents = {}
    for file in sorted(model_types_dir().glob("*.yaml")):
        if file.name.startswith("_"):
            continue
        documents[file.stem] = yaml.safe_load(file.read_text(encoding="utf-8"))
    validate_catalog_integrity(
        concepts=package.ids,
        concept_dimensions={name: item.dimension for name, item in package.concepts.items()},
        dimensions=load_dimensions(),
        model_documents=documents,
        metric_inputs=inputs,
        variant_inputs=variants,
        metric_expressions=expressions,
        metric_bases=bases,
        interest_order=order,
        row_fallbacks=fallbacks,
        coverage_document=load_coverage_document(),
    )
    catalog = load_financial_catalog()
    for item in catalog.indicators.values():
        assert item.inputs.concepts <= package.ids
        assert not (item.inputs.concepts & catalog.row_fallback_ids)
        for variant in item.variants.values():
            assert variant.inputs.concepts <= package.ids


def test_catalog_as_dict_validates_against_json_schema():
    body = load_financial_catalog().as_dict()
    Draft202012Validator.check_schema(_schema())
    Draft202012Validator(_schema()).validate(body)


def test_dscr_preserves_model_type_variant_and_formula():
    catalog = load_financial_catalog()
    dscr = catalog.indicators["dscr"]
    assert "pf" in dscr.variants
    assert "corporate_covenant" in dscr.variants
    assert dscr.unit == "ratio"
    assert dscr.variants["corporate_covenant"].window == "LTM"
    corporate = dscr.model_types["corporate"]
    assert corporate.use == "optional"
    assert corporate.variant == "corporate_covenant"
    pf = dscr.model_types["project_finance"]
    assert pf.use == "required"
    assert pf.variant == "pf"
    formula = dscr.variants["corporate_covenant"].formula.as_dict()
    assert formula["numerator"] == {"plus": ["ebitda"], "minus": ["cash_taxes", "capex"]}
    assert formula["denominator"] == {"plus": ["interest", "principal"], "minus": []}
    base_formula = dscr.formula.as_dict()
    assert base_formula["numerator"]["plus"] == ["cfads"]
    assert base_formula["denominator"]["plus"] == ["debt_service"]
    assert catalog.indicators["npv"].unit == "money"
    assert catalog.indicators["npv"].formula.rate == "discount_rate"
    assert "interest_paid" in catalog.row_fallback_ids


def test_inputs_preserve_all_of_and_one_of():
    catalog = load_financial_catalog()
    icr = catalog.indicators["icr"]
    assert icr.inputs.one_of == frozenset({"ebitda", "ebit"})
    assert "interest" in icr.inputs.all_of
    assert set(icr.as_dict()["input_concepts"]) == set(icr.inputs.concepts)
    assert icr.formula.one_of == frozenset({"ebitda", "ebit"})
    assert icr.formula.denominator is not None
    assert icr.formula.denominator.plus == ("interest",)


def test_meta_rejects_non_string_status(tmp_path: Path):
    body = yaml.safe_load(metrics_file().read_text(encoding="utf-8"))
    body["metrics"]["dscr"]["status"] = 123
    path = tmp_path / "coverage.yaml"
    path.write_text(yaml.safe_dump(body, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ModelTypeInvalid, match="status"):
        load_financial_catalog(path)


def test_meta_rejects_invalid_window_type(tmp_path: Path):
    body = yaml.safe_load(metrics_file().read_text(encoding="utf-8"))
    body["metrics"]["net_debt_ebitda"]["window"] = ["LTM"]
    path = tmp_path / "coverage.yaml"
    path.write_text(yaml.safe_dump(body, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ModelTypeInvalid, match="window"):
        load_financial_catalog(path)


def test_meta_rejects_non_string_definition(tmp_path: Path):
    body = yaml.safe_load(metrics_file().read_text(encoding="utf-8"))
    body["metrics"]["dscr"]["definition"] = 42
    path = tmp_path / "coverage.yaml"
    path.write_text(yaml.safe_dump(body, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ModelTypeInvalid, match="definition"):
        load_financial_catalog(path)


def test_validate_indicator_records_rejects_flat_inputs():
    with pytest.raises(TypeError, match="inputs"):
        validate_indicator_records(
            [{"id": "x", "unit": "ratio", "status": "active", "inputs": ["ebitda"]}]
        )
