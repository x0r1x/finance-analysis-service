"""Прогнозный тариф не сливается с договорным и не забирает цену продукта."""

from __future__ import annotations

import pytest

from finance_analysis.application.catalog import load_catalog, load_git_document
from finance_analysis.application.learning import label_is_known
from finance_analysis.domain.glossary import GlossaryInvalid, build_package
from finance_analysis.domain.glossary_release import apply_ops, label_diff, package_of
from finance_analysis.domain.mapping import assign_rows, label_id

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


def test_real_and_nominal_merchant_prices_keep_their_own_surface():
    package = load_catalog()
    rows = [
        _fact("real", "Merchant price (real)"),
        _fact("nominal", "Merchant price (nominal)"),
    ]
    assigned = assign_rows(rows, [], package)
    for key, label in (("real", "Merchant price (real)"), ("nominal", "Merchant price (nominal)")):
        item = assigned[key]
        assert item.concept == "forecast_energy_tariff"
        assert item.status == "ambiguous" and item.is_primary is False
        assert item.matched_label == label
        assert item.evidence["label"]["text"] == label
        assert item.evidence["label"]["id"] == label_id("forecast_energy_tariff", "alt", label)
    alone = assign_rows([rows[1]], [], package)["nominal"]
    assert alone.status == "bound" and alone.matched_label == "Merchant price (nominal)"


def test_ambiguous_label_stays_known_through_resolve_and_release():
    document = _release_document()
    package = package_of(document)
    assert package.resolve("electricity price") is None
    assert label_is_known(package, "electricity price")
    assert not label_is_known(package, "нет такой цены")
    added = apply_ops(
        document,
        [
            {
                "op": "add_label",
                "concept": "forecast_energy_tariff",
                "kind": "alt",
                "lang": "en",
                "text": "electricity price",
            }
        ],
    )
    assert label_diff(document, added) == []
    alts = added["glossaries"]["forecast_energy_tariff"]["alt"]["en"]
    assert {"text": "electricity price", "ambiguous": True} in alts
    assert "electricity price" not in alts
    removed = apply_ops(
        document,
        [
            {
                "op": "remove_label",
                "concept": "forecast_energy_tariff",
                "kind": "alt",
                "lang": "en",
                "text": "electricity price",
            }
        ],
    )
    gone = label_diff(document, removed)
    assert gone == [
        {
            "concept": "forecast_energy_tariff",
            "kind": "alt",
            "lang": "en",
            "text": "electricity price",
            "change": "remove",
        }
    ]
    assert package_of(removed).resolve("electricity price").concept == "energy_tariff"


async def test_glossary_resolve_lists_ambiguous_candidates_and_skips_the_model(tmp_path):
    from copy import deepcopy

    from finance_analysis.adapters.storage.store import LocalStore
    from finance_analysis.application.glossary_store import GlossaryStore

    gloss = GlossaryStore(LocalStore(tmp_path))
    head = await gloss.ensure()
    document = deepcopy(load_git_document())
    phrase = "shared electricity price"
    for concept in ("energy_tariff", "forecast_energy_tariff"):
        document["glossaries"][concept]["alt"]["en"].append({"text": phrase, "ambiguous": True})
    saved = await gloss.release([], f"h-{head['seq']}", document=document)
    seen: list[str] = []

    async def rank(row, package, version):
        seen.append(row["label"])

    result = await gloss.resolve({"label": phrase, "version": saved["version"]}, rank=rank)
    body = result["results"][0]
    assert seen == []
    assert body["match"] is None
    assert {item["concept"] for item in body["candidates"]} == {"energy_tariff", "forecast_energy_tariff"}
    assert all(item["text"] == phrase for item in body["candidates"])
    missed = await gloss.resolve({"label": "нет такой цены", "version": saved["version"]}, rank=rank)
    assert seen == ["нет такой цены"]
    assert missed["results"][0]["candidates"] == []


def _fact(key: str, label: str) -> dict:
    return {"kind": "fact", "label": label, "binding_key": key, "row_key": key, "unit": "EUR/MWh"}


def _release_document() -> dict:
    shared = {"text": "electricity price", "ambiguous": True}
    return {
        "taxonomy": "core-1",
        "concepts": {
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
        },
        "glossaries": {
            "energy_tariff": {
                "concept": "energy_tariff",
                "pref": {"en": "Contracted energy tariff", "ru": "Тариф по договору на энергию"},
                "alt": {"en": ["PPA Power Price", shared]},
            },
            "forecast_energy_tariff": {
                "concept": "forecast_energy_tariff",
                "pref": {"en": "Forecast energy tariff", "ru": "Прогнозный тариф"},
                "alt": {"en": ["Merchant price (nominal)", dict(shared)]},
            },
        },
        "dictionaries": _DICTS,
    }


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
