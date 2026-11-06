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
_DICTS = {"flows": {"inflow": ["приток"]}, "markers": {"actual": ["факт"]}}


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
    assert (tariff.semantic_role, tariff.dimension, tariff.kind, tariff.unit) == (
        "parameter",
        "currency_per_energy",
        "parameter",
        "currency_per_energy",
    )
    assert tariff.effective_aggregation == "none"
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
    catalog = load_dimensions()
    assert catalog.units["MWh"] == "energy"
    assert catalog.units["years"] == "duration"
    assert catalog.units["RUB/MWh"] == "currency_per_energy"
    assert catalog.same("currency_per_energy", "currency_per_power_time")


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
    )
    assert check("dimension_mismatch", same) == []


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
