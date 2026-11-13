"""Financial Model Catalog (фаза 3): записи показателей, версия в SMV, целостность."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from finance_analysis.application.analyses import RATIO_METRICS
from finance_analysis.application.financial_catalog import load_financial_catalog
from finance_analysis.application.model_types import (
    load_metric_catalog,
    load_model_types,
    metrics_file,
)
from finance_analysis.domain.financial_catalog import (
    FinancialModelCatalog,
    Indicator,
    IndicatorFormula,
    IndicatorInputs,
    ModelTypeUse,
    catalog_version_for,
    validate_catalog_schema,
    validate_financial_catalog_integrity,
    validate_indicator_records,
)
from finance_analysis.domain.semantic_model import (
    live_components,
    semantic_model_version_for,
)
from finance_analysis.domain.validation.catalog_integrity import (
    CatalogIntegrityError,
    validate_catalog_integrity,
)
from finance_analysis.domain.validation.model_types import ModelTypeInvalid


def _write_coverage(tmp_path: Path, body: dict) -> Path:
    path = tmp_path / "coverage.yaml"
    path.write_text(yaml.safe_dump(body, allow_unicode=True), encoding="utf-8")
    return path


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


def test_load_path_runs_schema_and_cross_field_integrity():
    catalog = load_financial_catalog()
    validate_catalog_schema(catalog.as_dict())
    validate_financial_catalog_integrity(catalog)


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
    assert catalog.indicators["npv"].formula.as_dict()["rate"] == ["wacc", "discount_rate"]
    assert catalog.indicators["npv"].formula.terminal == "terminal_value"
    assert catalog.indicators["irr"].formula.terminal == "terminal_value"
    identity = catalog.indicators["fcf_identity"]
    assert identity.unit == "money"
    assert "vk477" in identity.variants
    assert identity.variants["fcff_after_interest"].formula.add_back == ("net_interest", "tax_rate")
    assert "interest_paid" not in catalog.row_fallback_ids
    assert "cash_covenant" in dscr.variants
    assert dscr.variants["cash_covenant"].window == "period"
    assert "ocf" in dscr.variants["cash_covenant"].inputs.concepts
    assert dscr.model_types["corporate"].variant == "corporate_covenant"
    assert dscr.model_types["project_finance"].variant == "pf"
    assert all(item.variant != "cash_covenant" for item in dscr.model_types.values())
    assert "ПБУ 23/2011" in (dscr.variants["cash_covenant"].definition or "")


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
    with pytest.raises(ModelTypeInvalid, match="status"):
        load_financial_catalog(_write_coverage(tmp_path, body))


def test_meta_rejects_invalid_window_type(tmp_path: Path):
    body = yaml.safe_load(metrics_file().read_text(encoding="utf-8"))
    body["metrics"]["net_debt_ebitda"]["window"] = ["LTM"]
    with pytest.raises(ModelTypeInvalid, match="window"):
        load_financial_catalog(_write_coverage(tmp_path, body))


def test_meta_rejects_non_string_definition(tmp_path: Path):
    body = yaml.safe_load(metrics_file().read_text(encoding="utf-8"))
    body["metrics"]["dscr"]["definition"] = 42
    with pytest.raises(ModelTypeInvalid, match="definition"):
        load_financial_catalog(_write_coverage(tmp_path, body))


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda m: m.__setitem__("denominator", 123), "denominator"),
        (lambda m: m.__setitem__("numerator", 123), "numerator"),
        (lambda m: m.__setitem__("denominator", [1, 2]), "denominator"),
        (lambda m: m.__setitem__("numerator", {"plus": [1]}), "plus"),
        (lambda m: m.__setitem__("rate", 123), "rate"),
        (lambda m: m.__setitem__("rate", ""), "rate"),
    ],
)
def test_formula_field_types_rejected_on_metric_load(tmp_path: Path, mutate, match: str):
    body = yaml.safe_load(metrics_file().read_text(encoding="utf-8"))
    metric = dict(body["metrics"]["dscr"])
    metric.pop("variants", None)
    mutate(metric)
    body["metrics"] = {"dscr": metric}
    with pytest.raises((ModelTypeInvalid, CatalogIntegrityError), match=match):
        load_metric_catalog(_write_coverage(tmp_path, body))


def test_invalid_base_type_rejected(tmp_path: Path):
    body = yaml.safe_load(metrics_file().read_text(encoding="utf-8"))
    body["metrics"] = {"broken": {"base": 123}}
    with pytest.raises((ModelTypeInvalid, CatalogIntegrityError), match="base"):
        load_metric_catalog(_write_coverage(tmp_path, body))


def test_empty_base_rejected(tmp_path: Path):
    body = yaml.safe_load(metrics_file().read_text(encoding="utf-8"))
    body["metrics"] = {"broken": {"base": ""}}
    with pytest.raises((ModelTypeInvalid, CatalogIntegrityError), match="base"):
        load_metric_catalog(_write_coverage(tmp_path, body))


def test_nested_variants_rejected(tmp_path: Path):
    body = yaml.safe_load(metrics_file().read_text(encoding="utf-8"))
    dscr = dict(body["metrics"]["dscr"])
    pf = dict(dscr["variants"]["pf"])
    pf["variants"] = {"nested": {"numerator": ["cfads"], "denominator": "debt_service"}}
    dscr["variants"] = {"pf": pf}
    body["metrics"] = {"dscr": dscr}
    with pytest.raises((ModelTypeInvalid, CatalogIntegrityError), match="вложенные variants"):
        load_metric_catalog(_write_coverage(tmp_path, body))


def test_coverage_shape_rejects_bad_denominator_type():
    from finance_analysis.application.model_types import load_coverage_document

    payload_doc = dict(load_coverage_document())
    metrics = dict(payload_doc["metrics"])
    dscr = dict(metrics["dscr"])
    dscr["denominator"] = 123
    metrics["dscr"] = dscr
    payload_doc["metrics"] = metrics
    from finance_analysis.application.catalog import load_catalog, load_dimensions
    from finance_analysis.application.model_types import (
        load_interest_order,
        load_row_fallbacks,
        model_types_dir,
    )

    package = load_catalog()
    inputs, variants, _composed, bases, _rates, expressions = load_metric_catalog()
    fallbacks = load_row_fallbacks()
    documents = {
        file.stem: yaml.safe_load(file.read_text(encoding="utf-8"))
        for file in sorted(model_types_dir().glob("*.yaml"))
        if not file.name.startswith("_")
    }
    with pytest.raises(CatalogIntegrityError, match="denominator"):
        validate_catalog_integrity(
            concepts=package.ids,
            concept_dimensions={name: item.dimension for name, item in package.concepts.items()},
            dimensions=load_dimensions(),
            model_documents=documents,
            metric_inputs=inputs,
            variant_inputs=variants,
            metric_expressions=expressions,
            metric_bases=bases,
            interest_order=load_interest_order(concepts=package.ids, fallbacks=fallbacks),
            row_fallbacks=fallbacks,
            coverage_document=payload_doc,
        )


def test_validate_indicator_records_rejects_flat_inputs():
    with pytest.raises(TypeError, match="inputs"):
        validate_indicator_records(
            [{"id": "x", "unit": "ratio", "status": "active", "inputs": ["ebitda"]}]
        )


def test_integrity_rejects_mismatched_id_and_missing_variant_ref():
    catalog = load_financial_catalog()
    dscr = catalog.indicators["dscr"]
    broken = Indicator(
        id="not_dscr",
        inputs=dscr.inputs,
        unit=dscr.unit,
        formula=dscr.formula,
        variants=dscr.variants,
        model_types=dscr.model_types,
        status=dscr.status,
        base=dscr.base,
    )
    indicators = {**catalog.indicators, "dscr": broken}
    bad = FinancialModelCatalog(
        indicators=indicators,
        version=catalog_version_for(indicators),
        stamp=catalog.stamp,
        row_fallback_ids=catalog.row_fallback_ids,
    )
    with pytest.raises(ValueError, match="id != ключ"):
        validate_financial_catalog_integrity(bad)

    ghost = Indicator(
        id="dscr",
        inputs=dscr.inputs,
        unit=dscr.unit,
        formula=dscr.formula,
        variants=dscr.variants,
        model_types={
            **dscr.model_types,
            "corporate": ModelTypeUse(use="optional", variant="missing_variant"),
        },
        status=dscr.status,
    )
    indicators2 = {**catalog.indicators, "dscr": ghost}
    bad2 = FinancialModelCatalog(
        indicators=indicators2,
        version=catalog_version_for(indicators2),
        stamp=catalog.stamp,
        row_fallback_ids=catalog.row_fallback_ids,
    )
    with pytest.raises(ValueError, match="нет в variants"):
        validate_financial_catalog_integrity(bad2)


def test_integrity_rejects_input_concepts_drift():
    from finance_analysis.domain.financial_catalog import _assert_input_concepts

    inputs = IndicatorInputs(all_of=frozenset({"interest"}), one_of=frozenset({"ebitda"}))
    with pytest.raises(ValueError, match="input_concepts"):
        _assert_input_concepts("icr", inputs, ["interest"])


def test_integrity_rejects_unknown_base():
    catalog = load_financial_catalog()
    adscr = catalog.indicators["adscr"]
    broken = Indicator(
        id="adscr",
        inputs=adscr.inputs,
        unit=adscr.unit,
        formula=IndicatorFormula(base="no_such_metric"),
        variants=adscr.variants,
        model_types=adscr.model_types,
        status=adscr.status,
        base="no_such_metric",
    )
    indicators = {**catalog.indicators, "adscr": broken}
    bad = FinancialModelCatalog(
        indicators=indicators,
        version=catalog_version_for(indicators),
        stamp=catalog.stamp,
        row_fallback_ids=catalog.row_fallback_ids,
    )
    with pytest.raises(ValueError, match="base"):
        validate_financial_catalog_integrity(bad)


@pytest.mark.parametrize(
    "extra",
    [
        {"numerator": ["project_fcf"], "denominator": "debt_outstanding"},
        {"numerator": ["project_fcf"]},
        {"denominator": "debt_outstanding"},
        {"rate": "discount_rate"},
    ],
)
def test_base_rejects_formula_overrides(tmp_path: Path, extra: dict):
    body = yaml.safe_load(metrics_file().read_text(encoding="utf-8"))
    body["metrics"] = {
        "dscr": {
            "numerator": ["cfads"],
            "denominator": "debt_service",
        },
        "broken": {"base": "dscr", **extra},
    }
    with pytest.raises((ModelTypeInvalid, CatalogIntegrityError), match="base"):
        load_metric_catalog(_write_coverage(tmp_path, body))


@pytest.mark.parametrize(
    "numerator",
    [
        {},
        {"plus": []},
        {"minus": []},
        {"plus": [], "minus": []},
    ],
)
def test_empty_plus_minus_sides_rejected(tmp_path: Path, numerator: dict):
    body = yaml.safe_load(metrics_file().read_text(encoding="utf-8"))
    body["metrics"] = {
        "broken": {
            "numerator": numerator,
            "denominator": "debt_service",
        }
    }
    with pytest.raises((ModelTypeInvalid, CatalogIntegrityError), match="пуст"):
        load_metric_catalog(_write_coverage(tmp_path, body))


def test_integrity_rejects_stale_version_after_indicator_mutation():
    catalog = load_financial_catalog()
    # Mutable dict of indicators: content changed, version left stale.
    mutated = dict(catalog.indicators)
    dscr = mutated["dscr"]
    mutated["dscr"] = Indicator(
        id="dscr",
        inputs=dscr.inputs,
        unit="money",
        formula=dscr.formula,
        variants=dscr.variants,
        model_types=dscr.model_types,
        status=dscr.status,
        definition="mutated",
    )
    stale = FinancialModelCatalog(
        indicators=mutated,
        version=catalog.version,
        stamp=catalog.stamp,
        row_fallback_ids=catalog.row_fallback_ids,
    )
    with pytest.raises(ValueError, match="не соответствует содержимому"):
        validate_financial_catalog_integrity(stale)
