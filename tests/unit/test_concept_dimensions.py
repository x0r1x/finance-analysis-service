"""Оси понятия, алиасы kind/unit и совместимость размерностей."""

from __future__ import annotations

from decimal import Decimal

import pytest

from finance_analysis.application.catalog import load_catalog, load_dimensions
from finance_analysis.domain.audit import AuditInput
from finance_analysis.domain.dimensions import parse_catalog
from finance_analysis.domain.glossary import GlossaryInvalid, build_package
from finance_analysis.domain.measure import dependency_measure, stamp_facts
from tests.unit.rule_inputs import PERIODS, check, fact, link, row

A = "S|5|S!r2"
B = "S|6|S!r2"
C = "S|7|S!r2"
_DICTS = {"flows": {"inflow": ["приток"]}, "markers": {"actual": ["факт"], "plan": ["план"], "estimate": ["e"]}}


def _glossary(name: str = "cfads") -> dict:
    return {name: {"concept": name, "pref": {"ru": "Имя", "en": "Name"}}}


def _package(body: dict, name: str = "cfads"):
    return build_package({"taxonomy": "core-1", "concepts": {name: body}}, _glossary(name), _DICTS)


def test_catalog_migrates_energy_payback_and_keeps_coarse_aliases():
    package = load_catalog()
    generation = package.concepts["energy_generation"]
    assert (generation.semantic_role, generation.dimension, generation.temporal_nature) == ("measure", "energy", "flow")
    assert generation.kind == "measure"
    assert generation.unit == "energy"
    assert generation.form == "amount"
    assert generation.effective_aggregation == "sum"
    capacity = package.concepts["installed_capacity"]
    assert (capacity.dimension, capacity.temporal_nature, capacity.effective_aggregation) == ("power", "stock", "last")
    payback = package.concepts["payback"]
    assert (payback.dimension, payback.temporal_nature, payback.kind, payback.unit) == (
        "duration",
        "point_in_time",
        "measure",
        "duration",
    )
    assert payback.effective_aggregation == "last"
    tariff = package.concepts["energy_tariff"]
    assert (tariff.semantic_role, tariff.dimension, tariff.kind, tariff.unit, tariff.pricing_basis) == (
        "parameter",
        "currency_per_energy",
        "parameter",
        "currency_per_energy",
        "energy",
    )
    assert tariff.billing_period is None
    assert tariff.object_aggregation is None
    capacity_tariff = package.concepts["capacity_tariff"]
    assert (capacity_tariff.semantic_role, capacity_tariff.dimension, capacity_tariff.pricing_basis, capacity_tariff.billing_period) == (
        "parameter",
        "currency_per_power_time",
        "capacity",
        "year",
    )
    for name in ("discount_rate", "wacc", "cap_rate", "vacancy", "capacity_factor", "degradation"):
        assert package.concepts[name].semantic_role == "assumption", name
        assert package.concepts[name].effective_aggregation == "none"
    for name in ("dscr_lockup", "dscr_default", "target_dscr"):
        assert package.concepts[name].semantic_role == "parameter", name
    catalog = load_dimensions()
    assert catalog.pricing_basis["currency_per_energy"] == "energy"
    assert catalog.pricing_basis["currency_per_power_time"] == "capacity"
    assert catalog.unit_currency["RUB/MWh"] == "RUB"
    assert catalog.unit_billing_period["RUB/MW/year"] == "year"
    assert catalog.unit_billing_period["RUB/MW/month"] == "month"
    assert tariff.effective_aggregation == "none"
    forecast = package.concepts["forecast_energy_tariff"]
    assert (
        forecast.semantic_role,
        forecast.dimension,
        forecast.temporal_nature,
        forecast.pricing_basis,
        forecast.effective_aggregation,
        forecast.kind,
    ) == ("assumption", "currency_per_energy", "rate", "energy", "none", "parameter")
    assert forecast.aggregation is None
    assert forecast.related_to == ("energy_tariff",)
    assert tariff.related_to == ("forecast_energy_tariff",)
    assert forecast.id != tariff.id
    rate = package.concepts["discount_rate"]
    assert rate.semantic_role == "assumption"
    assert rate.kind == "parameter"
    assert rate.unit == "ratio"
    assert rate.form == "ratio"
    assert rate.validation_range == ("0", "0.30")
    assert package.concepts["dscr"].kind == "ratio"
    assert package.concepts["debt_outstanding"].expected_sign is None
    assert package.concepts["debt_outstanding"].temporal_nature == "stock"
    assert package.concepts["vacancy"].validation_range == ("0", "1")
    assert catalog.units["MWh"] == "energy"
    assert catalog.units["years"] == "duration"
    assert catalog.units["RUB/MWh"] == "currency_per_energy"
    assert catalog.same("currency_per_energy", "currency_per_power_time")
    assert len(package.concepts) == 72
    assert all(item.object_aggregation is None and item.weight is None for item in package.concepts.values())


def test_old_kind_and_unit_map_to_axes_and_conflicts_fail():
    stock = _package({"kind": "measure", "unit": "money", "expected_sign": "stock"}).concepts["cfads"]
    assert stock.temporal_nature == "stock"
    assert stock.expected_sign is None
    assert stock.kind == "measure"
    assert stock.unit == "money"
    assert stock.sign_conflict("inflow") is True
    assert stock.sign_conflict("stock") is False
    ratio = _package({"kind": "ratio", "unit": "ratio"}).concepts["cfads"]
    assert (ratio.semantic_role, ratio.dimension, ratio.temporal_nature, ratio.kind, ratio.unit) == (
        "measure",
        "ratio",
        "rate",
        "ratio",
        "ratio",
    )
    assert ratio.effective_aggregation == "none"
    assumption = _package(
        {"kind": "parameter", "unit": "ratio", "semantic_role": "assumption", "dimension": "ratio"}
    ).concepts["cfads"]
    assert assumption.semantic_role == "assumption"
    assert assumption.kind == "parameter"
    with pytest.raises(GlossaryInvalid):
        _package({"kind": "ratio", "semantic_role": "parameter", "dimension": "ratio"})
    with pytest.raises(GlossaryInvalid):
        _package({"kind": "measure", "unit": "count", "dimension": "duration", "temporal_nature": "point_in_time"})
    with pytest.raises(GlossaryInvalid):
        _package({"semantic_role": "measure", "dimension": "money", "temporal_nature": "stock", "expected_sign": "inflow"})


def test_dimension_algebra_covers_ratio_energy_and_tariff():
    catalog = parse_catalog(
        {
            "dimensions": {
                "money": {"base": True, "units": ["RUB"]},
                "power": {"base": True, "units": ["MW"]},
                "duration": {"base": True, "units": ["year"]},
                "ratio": {"dimensionless": True, "units": ["1", "%"]},
                "energy": {"exponents": {"power": 1, "duration": 1}, "units": ["MWh"]},
                "currency_per_energy": {
                    "exponents": {"money": 1, "power": -1, "duration": -1},
                    "units": ["RUB/MWh"],
                },
            }
        }
    )
    assert catalog.combine("add", "money", "money") == {"money": 1}
    assert catalog.combine("add", "money", "energy") is None
    assert catalog.combine("ratio", "money", "money") == {}
    assert catalog.matches("ratio", catalog.combine("ratio", "money", "money"))
    assert catalog.combine("ratio", "energy", "power") == {"duration": 1}
    assert catalog.matches("duration", catalog.combine("ratio", "energy", "power"))
    assert not catalog.matches("ratio", catalog.combine("ratio", "energy", "power"))
    factor = catalog.combine("ratio", "energy", "energy")
    assert factor == {}
    assert catalog.combine("product", "currency_per_energy", "energy") == {"money": 1}
    assert catalog.matches("money", catalog.combine("product", "energy", "currency_per_energy"))


def _exponents() -> dict[str, dict[str, int]]:
    return {
        "money": {"money": 1},
        "energy": {"power": 1, "duration": 1},
        "power": {"power": 1},
        "duration": {"duration": 1},
        "count": {"count": 1},
        "ratio": {},
        "currency_per_energy": {"money": 1, "power": -1, "duration": -1},
    }


def _bound(row_key: str, concept: str) -> dict:
    return {"row_key": row_key, "status": "bound", "effective_concept": concept}


def test_rule_flags_mismatched_sum_and_accepts_dscr_ratio():
    exponents = _exponents()
    concepts = {
        "revenue": "money",
        "energy_generation": "energy",
        "cfads": "money",
        "debt_service": "money",
        "dscr": "ratio",
        "payback": "duration",
        "installed_capacity": "power",
    }
    units = {"MWh": "energy", "years": "duration", "RUB/MWh": "currency_per_energy", "шт": "count"}
    rows = [row(A, unit="money"), row(B, unit="MWh"), row(C, unit="")]
    facts = [fact(A, "S!C5", "2024", "1"), fact(B, "S!C6", "2024", "2"), fact(C, "S!C7", "2024", "3")]
    summed = AuditInput(
        rows=rows,
        periods=PERIODS,
        facts=facts,
        links=link("S!C7", "=C5+C6", C, "2024", ("S!C5", "S!C6")),
        bindings=[_bound(A, "revenue"), _bound(B, "energy_generation")],
        concept_dimensions=concepts,
        dimension_exponents=exponents,
        unit_dimensions=units,
    )
    found = check("dimension_mismatch", summed)
    assert [item.params["op"] for item in found] == ["add"]
    silent = AuditInput(rows=rows, periods=PERIODS, facts=facts, links=summed.links)
    assert check("dimension_mismatch", silent) == []
    ratio_rows = [row(A, unit="money"), row(B, unit="money"), row(C, unit="rate")]
    ratio = AuditInput(
        rows=ratio_rows,
        periods=PERIODS,
        facts=facts,
        links=link("S!C7", "=C5/C6", C, "2024", ("S!C5", "S!C6")),
        bindings=[_bound(A, "cfads"), _bound(B, "debt_service"), _bound(C, "dscr")],
        concept_dimensions=concepts,
        dimension_exponents=exponents,
        unit_dimensions=units,
    )
    assert check("dimension_mismatch", ratio) == []
    hours = AuditInput(
        rows=[row(A, unit="MWh"), row(B, unit="MW"), row(C, unit="years")],
        periods=PERIODS,
        facts=facts,
        links=link("S!C7", "=C5/C6", C, "2024", ("S!C5", "S!C6")),
        bindings=[_bound(A, "energy_generation"), _bound(B, "installed_capacity"), _bound(C, "payback")],
        concept_dimensions=concepts,
        dimension_exponents=exponents,
        unit_dimensions={**units, "MW": "power"},
    )
    assert check("dimension_mismatch", hours) == []
    bad_ratio = AuditInput(
        rows=[row(A, unit="MWh"), row(B, unit="MW"), row(C, unit="rate")],
        periods=PERIODS,
        facts=facts,
        links=link("S!C7", "=C5/C6", C, "2024", ("S!C5", "S!C6")),
        bindings=[_bound(A, "energy_generation"), _bound(B, "installed_capacity"), _bound(C, "dscr")],
        concept_dimensions=concepts,
        dimension_exponents=exponents,
        unit_dimensions={**units, "MW": "power"},
    )
    assert [item.params["op"] for item in check("dimension_mismatch", bad_ratio)] == ["ratio"]
    same = AuditInput(
        rows=[row(A, unit="RUB/MWh"), row(B, unit="RUB/MW/year"), row(C, unit="RUB/MWh")],
        periods=PERIODS,
        facts=facts,
        links=link("S!C7", "=C5+C6", C, "2024", ("S!C5", "S!C6")),
        bindings=[_bound(A, "energy_tariff"), _bound(B, "capacity_payment"), _bound(C, "energy_tariff")],
        concept_dimensions={**concepts, "capacity_payment": "currency_per_power_time"},
        dimension_exponents={
            **exponents,
            "currency_per_power_time": {"money": 1, "power": -1, "duration": -1},
        },
        unit_dimensions={**units, "RUB/MW/year": "currency_per_power_time"},
        dimension_pricing={"currency_per_energy": "energy", "currency_per_power_time": "capacity"},
        concept_pricing={"energy_tariff": "energy", "capacity_payment": "capacity"},
        unit_currency={"RUB/MWh": "RUB", "RUB/MW/year": "RUB"},
        unit_billing={"RUB/MW/year": "year"},
    )
    assert check("dimension_mismatch", same) == []
    assert [item.params["reason"] for item in check("pricing_basis_mismatch", same)] == ["pricing_basis"]


def test_unbound_quotient_does_not_inherit_the_source_unit():
    data = AuditInput(
        rows=[
            row(A, unit="RUB", scale_factor=1000),
            row(B, unit="RUB", scale_factor=1000),
            row(C),
        ],
        periods=PERIODS,
        facts=[fact(A, "S!C5", "2024", "1000"), fact(B, "S!C6", "2024", "10"), fact(C, "S!C7", "2024", "100")],
        links=link("S!C7", "=C5/C6", C, "2024", ("S!C5", "S!C6")),
        concept_dimensions={"revenue": "money"},
        dimension_exponents=_exponents(),
        unit_dimensions={"RUB": "money"},
    )
    assert check("dimension_mismatch", data) == []


def test_capacity_over_generation_is_not_a_duration():
    exponents = _exponents()
    concepts = {"energy_generation": "energy", "installed_capacity": "power", "payback": "duration"}
    units = {"MWh": "energy", "MW": "power", "years": "duration"}
    facts = [fact(A, "S!C5", "2024", "1"), fact(B, "S!C6", "2024", "2"), fact(C, "S!C7", "2024", "3")]
    shared = {
        "periods": PERIODS,
        "facts": facts,
        "links": link("S!C7", "=C5/C6", C, "2024", ("S!C5", "S!C6")),
        "concept_dimensions": concepts,
        "dimension_exponents": exponents,
        "unit_dimensions": units,
    }
    correct = AuditInput(
        rows=[row(A, unit="MWh"), row(B, unit="MW"), row(C, unit="years")],
        bindings=[_bound(A, "energy_generation"), _bound(B, "installed_capacity"), _bound(C, "payback")],
        **shared,
    )
    assert check("dimension_mismatch", correct) == []
    inverted = AuditInput(
        rows=[row(A, unit="MW"), row(B, unit="MWh"), row(C, unit="years")],
        bindings=[_bound(A, "installed_capacity"), _bound(B, "energy_generation"), _bound(C, "payback")],
        **shared,
    )
    found = check("dimension_mismatch", inverted)
    assert [item.params["op"] for item in found] == ["ratio"]
    assert found[0].params["result"] == "duration"


def _priced(rows, formula_refs, bindings, concepts, **extra) -> AuditInput:
    exponents = _exponents()
    exponents["currency_per_power_time"] = {"money": 1, "power": -1, "duration": -1}
    return AuditInput(
        rows=rows,
        periods=PERIODS,
        facts=[fact(A, "S!C5", "2024", "1"), fact(B, "S!C6", "2024", "2"), fact(C, "S!C7", "2024", "3")],
        links=link("S!C7", formula_refs[0], C, "2024", formula_refs[1]),
        bindings=bindings,
        concept_dimensions=concepts,
        dimension_exponents=exponents,
        unit_dimensions={
            "RUB/MWh": "currency_per_energy",
            "USD/MWh": "currency_per_energy",
            "RUB/MW/year": "currency_per_power_time",
            "RUB/MW/month": "currency_per_power_time",
            "MWh": "energy",
            "MW": "power",
            "years": "duration",
            "%": "ratio",
        },
        concept_pricing=extra.get("concept_pricing", {}),
        concept_billing=extra.get("concept_billing", {}),
        dimension_pricing={"currency_per_energy": "energy", "currency_per_power_time": "capacity"},
        unit_currency={"RUB/MWh": "RUB", "USD/MWh": "USD", "RUB/MW/year": "RUB", "RUB/MW/month": "RUB"},
        unit_billing={"RUB/MW/year": "year", "RUB/MW/month": "month"},
    )


def test_tariff_basis_is_not_the_physical_dimension():
    concepts = {
        "energy_tariff": "currency_per_energy",
        "capacity_tariff": "currency_per_power_time",
        "capacity_month": "currency_per_power_time",
        "energy_generation": "energy",
        "installed_capacity": "power",
        "capacity_factor": "ratio",
    }
    pricing = {
        "energy_tariff": "energy",
        "capacity_tariff": "capacity",
        "capacity_month": "capacity",
        "capacity_factor": None,
    }
    pricing = {key: value for key, value in pricing.items() if value}
    billing = {"capacity_tariff": "year", "capacity_month": "month"}
    energy = [row(A, unit="RUB/MWh"), row(B, unit="RUB/MWh"), row(C, unit="RUB/MWh")]
    same_energy = _priced(
        energy,
        ("=C5+C6", ("S!C5", "S!C6")),
        [_bound(A, "energy_tariff"), _bound(B, "energy_tariff"), _bound(C, "energy_tariff")],
        concepts,
        concept_pricing=pricing,
    )
    assert check("dimension_mismatch", same_energy) == []
    assert check("pricing_basis_mismatch", same_energy) == []
    capacity = [row(A, unit="RUB/MW/year"), row(B, unit="RUB/MW/year"), row(C, unit="RUB/MW/year")]
    same_capacity = _priced(
        capacity,
        ("=C5+C6", ("S!C5", "S!C6")),
        [_bound(A, "capacity_tariff"), _bound(B, "capacity_tariff"), _bound(C, "capacity_tariff")],
        concepts,
        concept_pricing=pricing,
        concept_billing=billing,
    )
    assert check("dimension_mismatch", same_capacity) == []
    assert check("pricing_basis_mismatch", same_capacity) == []
    mixed = _priced(
        [row(A, unit="RUB/MWh"), row(B, unit="RUB/MW/year"), row(C, unit="RUB/MWh")],
        ("=C5+C6", ("S!C5", "S!C6")),
        [_bound(A, "energy_tariff"), _bound(B, "capacity_tariff"), _bound(C, "energy_tariff")],
        concepts,
        concept_pricing=pricing,
        concept_billing=billing,
    )
    assert check("dimension_mismatch", mixed) == []
    assert [item.params["reason"] for item in check("pricing_basis_mismatch", mixed)] == ["pricing_basis"]
    months = _priced(
        [row(A, unit="RUB/MW/year"), row(B, unit="RUB/MW/month"), row(C, unit="RUB/MW/year")],
        ("=C5+C6", ("S!C5", "S!C6")),
        [_bound(A, "capacity_tariff"), _bound(B, "capacity_month"), _bound(C, "capacity_tariff")],
        concepts,
        concept_pricing=pricing,
        concept_billing=billing,
    )
    assert [item.params["reason"] for item in check("pricing_basis_mismatch", months)] == ["billing_period"]
    currencies = _priced(
        [row(A, unit="RUB/MWh"), row(B, unit="USD/MWh"), row(C, unit="RUB/MWh")],
        ("=C5+C6", ("S!C5", "S!C6")),
        [_bound(A, "energy_tariff"), _bound(B, "energy_tariff"), _bound(C, "energy_tariff")],
        concepts,
        concept_pricing=pricing,
    )
    assert check("dimension_mismatch", currencies) == []
    assert [item.params["reason"] for item in check("pricing_basis_mismatch", currencies)] == ["currency"]
    copied = _priced(
        [row(A, unit="RUB/MW/year"), row(B, unit="years"), row(C, unit="RUB/MWh")],
        ("=C5", ("S!C5",)),
        [_bound(A, "capacity_tariff"), _bound(C, "energy_tariff")],
        concepts,
        concept_pricing=pricing,
        concept_billing=billing,
    )
    assert [item.params["reason"] for item in check("pricing_basis_mismatch", copied)] == ["conversion"]
    bridged = _priced(
        [row(A, unit="RUB/MW/year"), row(B, unit="%"), row(C, unit="RUB/MWh")],
        ("=C5*C6", ("S!C5", "S!C6")),
        [_bound(A, "capacity_tariff"), _bound(B, "capacity_factor"), _bound(C, "energy_tariff")],
        concepts,
        concept_pricing=pricing,
        concept_billing=billing,
    )
    assert check("dimension_mismatch", bridged) == []
    assert check("pricing_basis_mismatch", bridged) == []


def _weighted(concept_dimension: str, weight_dimension: str, *, weight_id: str = "weight_concept"):
    rate = {
        "semantic_role": "measure",
        "dimension": concept_dimension,
        "temporal_nature": "rate",
        "object_aggregation": "weighted_average",
        "weight": weight_id,
    }
    concepts = {"portfolio_rate": rate}
    glossaries = {"portfolio_rate": {"concept": "portfolio_rate", "pref": {"ru": "Ставка", "en": "Rate"}}}
    if weight_id != "portfolio_rate":
        concepts[weight_id] = {
            "semantic_role": "measure",
            "dimension": weight_dimension,
            "temporal_nature": "stock",
        }
        glossaries[weight_id] = {"concept": weight_id, "pref": {"ru": "Вес", "en": "Weight"}}
    return build_package({"taxonomy": "core-1", "concepts": concepts}, glossaries, _DICTS).concepts["portfolio_rate"]


def test_role_is_written_and_rates_are_not_averaged():
    kept = _package(
        {"semantic_role": "parameter", "dimension": "ratio", "temporal_nature": "rate", "input": True}
    ).concepts["cfads"]
    assert kept.semantic_role == "parameter"
    assert kept.effective_aggregation == "none"
    assert kept.object_aggregation is None
    explicit = _package(
        {"semantic_role": "assumption", "dimension": "ratio", "temporal_nature": "rate", "aggregation": "average"}
    ).concepts["cfads"]
    assert explicit.effective_aggregation == "average"
    with pytest.raises(GlossaryInvalid):
        _package({"semantic_role": "assumption", "dimension": "ratio", "object_aggregation": "weighted_average"})
    with pytest.raises(GlossaryInvalid):
        _package(
            {
                "semantic_role": "assumption",
                "dimension": "ratio",
                "temporal_nature": "rate",
                "object_aggregation": "weighted_average",
                "weight": "debt_outstanding",
            }
        )
    weighted = build_package(
        {
            "taxonomy": "core-1",
            "concepts": {
                "portfolio_rate": {
                    "semantic_role": "measure",
                    "dimension": "ratio",
                    "temporal_nature": "rate",
                    "object_aggregation": "weighted_average",
                    "weight": "debt_outstanding",
                },
                "debt_outstanding": {"semantic_role": "measure", "dimension": "money", "temporal_nature": "stock"},
            },
        },
        {
            "portfolio_rate": {"concept": "portfolio_rate", "pref": {"ru": "Ставка", "en": "Rate"}},
            "debt_outstanding": {"concept": "debt_outstanding", "pref": {"ru": "Долг", "en": "Debt"}},
        },
        _DICTS,
    ).concepts["portfolio_rate"]
    assert weighted.object_aggregation == "weighted_average"
    assert weighted.weight == "debt_outstanding"
    assert weighted.effective_aggregation == "none"
    with pytest.raises(GlossaryInvalid):
        _weighted("ratio", "ratio")
    with pytest.raises(GlossaryInvalid):
        _weighted("ratio", "ratio", weight_id="portfolio_rate")
    with pytest.raises(GlossaryInvalid):
        _weighted("currency_per_energy", "money")
    with pytest.raises(GlossaryInvalid):
        _weighted("currency_per_power_time", "energy")
    with pytest.raises(GlossaryInvalid):
        _weighted("money", "count")
    by_energy = _weighted("currency_per_energy", "energy")
    assert by_energy.weight == "weight_concept"
    by_power = _weighted("currency_per_power_time", "power")
    assert by_power.weight == "weight_concept"


def test_concrete_unit_and_scale_follow_the_same_source_walk():
    rows = [row(A, unit=""), row(B, unit="MWh", scale_factor=1000)]
    facts = [fact(A, "S!C5", "2024", "1"), fact(B, "S!C6", "2024", "2")]
    data = AuditInput(
        rows=rows,
        periods=PERIODS,
        facts=facts,
        links=link("S!C5", "=C6", A, "2024", ("S!C6",)),
        unit_dimensions={"MWh": "energy"},
    )
    assert dependency_measure(data, A, data.unit_dimensions) == (Decimal(1000), "MWh")
    stamped = stamp_facts(data.facts, data.rows, data.unit_dimensions)
    copied = next(item for item in stamped if item["row_key"] == B)
    assert copied["scale_factor"] == 1000
    assert copied["unit"] == "MWh"
    bare = next(item for item in stamped if item["row_key"] == A)
    assert "unit" not in bare or bare.get("unit") in (None, "")
