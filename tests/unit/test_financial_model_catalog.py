"""Financial Model Catalog (фаза 3): записи показателей, версия в SMV, целостность."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from finance_analysis.application.analyses import RATIO_METRICS
from finance_analysis.application.financial_catalog import load_financial_catalog
from finance_analysis.application.model_types import load_model_types
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
        assert isinstance(item.inputs, frozenset)
        # base-only метрики наследуют входы базы; у всех публичных есть входы или base.
        assert item.inputs or item.base, metric_id
        assert item.model_types
        for use in item.model_types.values():
            assert use in {"required", "optional", "not_applicable"}


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
    import yaml

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
        assert item.inputs <= package.ids
        assert not (item.inputs & catalog.row_fallback_ids)
        for variant in item.variants.values():
            assert variant.inputs <= package.ids


def test_contract_schema_file_exists_and_matches_snapshot_shape():
    root = Path(__file__).resolve().parents[2]
    schema_path = root / "src/finance_analysis/domain/contracts/financial_model_catalog.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["required"] == ["version", "stamp", "indicators"]
    body = load_financial_catalog().as_dict()
    validate_indicator_records(list(body["indicators"].values()))
    assert set(body) >= {"version", "stamp", "indicators", "row_fallbacks"}


def test_dscr_variants_and_npv_unit():
    catalog = load_financial_catalog()
    dscr = catalog.indicators["dscr"]
    assert "pf" in dscr.variants
    assert "corporate_covenant" in dscr.variants
    assert dscr.unit == "ratio"
    assert dscr.variants["corporate_covenant"].window == "LTM"
    assert catalog.indicators["npv"].unit == "money"
    assert "interest_paid" in catalog.row_fallback_ids


def test_validate_indicator_records_rejects_fallback_shaped_gap():
    with pytest.raises(ValueError, match="inputs"):
        validate_indicator_records([{"id": "x", "unit": "ratio", "status": "active", "inputs": "ebitda"}])
