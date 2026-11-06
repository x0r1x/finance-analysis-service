"""Прогнозный тариф не сливается с договорным и не забирает цену продукта."""

from __future__ import annotations

import pytest

from finance_analysis.application.catalog import load_catalog
from finance_analysis.domain.glossary import GlossaryInvalid, build_package
from finance_analysis.domain.mapping import assign_rows

_DICTS = {"flows": {"inflow": ["приток"]}, "markers": {"actual": ["факт"]}}
_FORECAST = (
    "Прогнозный тариф",
    "ожидаемая цена реализации",
    "прогнозная цена электроэнергии",
    "Forecast energy tariff",
    "Merchant price forecast",
    "Electricity price forecast",
    "Electricity price forecast (real terms)",
    "Merchant price (real)",
    "Merchant price (nominal)",
)
_CONTRACTED = (
    "Contracted energy tariff",
    "PPA Power Price",
    "Тариф по договору на энергию",
)
# В книгах это договор или цена без признака прогноза. К прогнозу не привязывается.
_UNBOUND = (
    "PPA (pay-as-produced) price",
    "PPA price (real)",
    "PPA price (nominal)",
    "PPA price",
    "price",
    "tariff",
    "electricity price",
    "energy price",
    "цена",
    "тариф",
    "цена электроэнергии",
    "Mid case",
    "Low case",
    "Applied (real terms)",
    "Цена продукта 1",
    "Темп роста цены Продукта 1",
    "Средний прирост цен продаж",
    "Прирост цен на ОРЭ - 1 Ценовая зона",
)


def test_distinctive_forecast_labels_do_not_take_a_contract_or_a_product_price():
    package = load_catalog()
    for label in _FORECAST:
        hit = package.resolve(label)
        assert hit is not None and hit.concept == "forecast_energy_tariff", label
        assert package.ambiguous_hits(label) == ()
    for label in _CONTRACTED:
        hit = package.resolve(label)
        assert hit is not None and hit.concept == "energy_tariff", label
    for label in _UNBOUND:
        assert package.resolve(label) is None, label
        assert package.ambiguous_hits(label) == (), label


def test_shared_synonym_without_the_flag_is_rejected():
    with pytest.raises(GlossaryInvalid) as caught:
        _pair(ambiguous=False)
    assert "electricity price" in caught.value.labels


def test_ambiguous_label_keeps_both_candidates():
    package = _pair(ambiguous=True)
    assert package.resolve("electricity price") is None
    hits = package.ambiguous_hits("electricity price")
    assert {hit.concept for hit in hits} == {"energy_tariff", "forecast_energy_tariff"}
    row = {
        "kind": "fact",
        "label": "electricity price",
        "binding_key": "bk",
        "row_key": "rk",
        "unit": "price",
    }
    item = assign_rows([row], [], package)["bk"]
    assert item.status == "ambiguous" and item.concept is None and item.is_primary is False
    assert {candidate["concept"] for candidate in item.evidence["candidates"]} == {
        "energy_tariff",
        "forecast_energy_tariff",
    }
    contracted = {
        "kind": "fact",
        "label": "PPA Power Price",
        "binding_key": "ppa",
        "row_key": "ppa",
        "unit": "price",
    }
    bound = assign_rows([contracted], [], package)["ppa"]
    assert bound.status == "bound" and bound.concept == "energy_tariff"
    forecast = {
        "kind": "fact",
        "label": "Merchant price (nominal)",
        "binding_key": "fc",
        "row_key": "fc",
        "unit": "price",
    }
    got = assign_rows([forecast], [], package)["fc"]
    assert got.status == "bound" and got.concept == "forecast_energy_tariff"


def _pair(*, ambiguous: bool):
    shared: object = {"text": "electricity price", "ambiguous": True} if ambiguous else "electricity price"
    concepts = {
        "energy_tariff": {
            "semantic_role": "parameter",
            "dimension": "currency_per_energy",
            "temporal_nature": "rate",
            "pricing_basis": "energy",
        },
        "forecast_energy_tariff": {
            "semantic_role": "assumption",
            "dimension": "currency_per_energy",
            "temporal_nature": "rate",
            "pricing_basis": "energy",
        },
    }
    glossaries = {
        "energy_tariff": {
            "concept": "energy_tariff",
            "pref": {"en": "Contracted energy tariff", "ru": "Тариф по договору на энергию"},
            "alt": {"en": ["PPA Power Price", shared]},
        },
        "forecast_energy_tariff": {
            "concept": "forecast_energy_tariff",
            "pref": {"en": "Forecast energy tariff", "ru": "Прогнозный тариф"},
            "alt": {"en": ["Merchant price (nominal)", shared]},
        },
    }
    return build_package({"taxonomy": "core-1", "concepts": concepts}, glossaries, _DICTS)
