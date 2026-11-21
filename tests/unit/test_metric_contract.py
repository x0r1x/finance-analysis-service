"""Реестр реализаций совпадает с формулами каталога. Лестница расчёта реестр не читает."""

from __future__ import annotations

import pytest

from finance_analysis.application.model_types import load_coverage_document
from finance_analysis.domain.metric_contract import (
    REGISTRY,
    DuplicateImplementation,
    implements,
)

# Импорт модулей вешает @implements. Диспетчер расчёта эти метки не вызывает.
_IMPLEMENTATION_MODULES = (
    "finance_analysis.domain.cash_flow",
    "finance_analysis.domain.cover_metrics",
    "finance_analysis.domain.covenant",
    "finance_analysis.domain.debt_incl_off_balance",
    "finance_analysis.domain.free_cash_flow",
    "finance_analysis.domain.housing_cover",
    "finance_analysis.domain.housing_dscr",
    "finance_analysis.domain.metrics",
    "finance_analysis.domain.net_cash_flow",
    "finance_analysis.domain.returns",
    "finance_analysis.domain.total_debt",
)

# Нет отдельной функции: лестница не отличает формулу и считает её общим маршрутом.
# dscr.pf — ветки variant == "pf" нет, считает та же coverage_ratio, что базовая dscr.
# dscr.ocf_covenant — имени в коде нет; названный профиль отдаёт запись каталога в composed_ratio.
# Четыре метрики ниже — select_ratio → composed_ratio, состав целиком из каталога.
_COMMON_ROUTE = {
    ("dscr", "dscr.pf"),
    ("dscr", "dscr.ocf_covenant"),
    ("net_debt_ebitda", "net_debt_ebitda"),
    ("escrow_coverage", "escrow_coverage"),
    ("total_debt_ebitda", "total_debt_ebitda"),
    ("debt_off_balance_ebitda", "debt_off_balance_ebitda"),
}

# Ключ → модуль, функция, version, inputs. inputs пуст, если набор читаемых понятий не фиксирован.
_ROUTE = {
    ("dscr", "dscr"): ("metrics", "coverage_ratio", "dscr@1", ()),
    ("dscr", "dscr.corporate_covenant"): ("covenant", "covenant_dscr", "", ()),
    ("dscr", "dscr.housing"): ("housing_dscr", "housing_dscr", "", ()),
    ("dscr", "dscr.cash_covenant"): ("covenant", "cash_covenant_dscr", "", ()),
    ("icr", "icr"): ("metrics", "coverage_ratio", "", ()),
    ("icr", "icr.bank"): ("covenant", "bank_icr", "", ()),
    ("icr_ebit", "icr_ebit"): ("metrics", "coverage_ratio", "", ()),
    ("adscr", "adscr"): ("cover_metrics", "adscr", "", ()),
    ("adscr", "adscr.housing"): ("housing_cover", "_adscr", "", ()),
    ("dscr_min", "dscr_min"): ("cover_metrics", "dscr_reductions", "", ()),
    ("dscr_min", "dscr_min.housing"): ("housing_cover", "_minimum", "", ()),
    ("dscr_avg", "dscr_avg"): ("cover_metrics", "dscr_reductions", "", ()),
    ("dscr_avg", "dscr_avg.housing"): ("housing_cover", "_average", "", ()),
    ("llcr", "llcr"): (
        "cover_metrics",
        "loan_life_ratio",
        "",
        ("debt_service", "cfads", "debt_outstanding", "discount_rate"),
    ),
    ("llcr", "llcr.cbr590"): ("housing_cover", "_llcr", "", ()),
    ("llcr", "llcr.domrf"): ("housing_cover", "_llcr", "", ()),
    ("plcr", "plcr"): (
        "cover_metrics",
        "loan_life_ratio",
        "",
        ("debt_service", "cfads", "debt_outstanding", "discount_rate"),
    ),
    ("total_debt", "total_debt"): ("total_debt", "total_debt_result", "", ()),
    ("escrow_blended_rate", "escrow_blended_rate"): ("housing_cover", "_rate", "", ()),
    ("npv", "npv"): ("returns", "project_return", "", ("project_fcf", "discount_rate")),
    ("irr", "irr"): ("returns", "project_return", "", ("project_fcf",)),
    ("debt_incl_off_balance", "debt_incl_off_balance"): (
        "debt_incl_off_balance",
        "debt_incl_off_balance",
        "",
        (),
    ),
    ("fcff", "fcff"): ("free_cash_flow", "free_cash_flow", "", ()),
    ("ncf", "ncf"): (
        "net_cash_flow",
        "net_cash_flow",
        "",
        ("operating_cash_flow", "investing_cash_flow", "financing_cash_flow"),
    ),
    ("icr_lease", "icr_lease"): ("metrics", "lease_interest_coverage", "", ()),
    ("fcf_identity", "fcf_identity"): ("returns", "fcf_identity", "", ()),
    ("fcf_identity", "fcf_identity.vk477"): (
        "returns",
        "fcf_identity",
        "",
        ("project_fcf", "operating_cash_flow", "capex"),
    ),
    ("fcf_identity", "fcf_identity.fcff_after_interest"): (
        "returns",
        "fcf_identity",
        "",
        ("project_fcf", "operating_cash_flow", "capex", "net_interest", "tax_rate"),
    ),
    ("ncf_period", "ncf_period"): ("cash_flow", "net_cash_flow", "", ("cash_inflow", "cash_outflow")),
}


def _catalog_keys() -> set[tuple[str, str]]:
    document = load_coverage_document()
    metrics = document["metrics"]
    found: set[tuple[str, str]] = set()
    for metric_id, body in metrics.items():
        found.add((str(metric_id), _formula_id(str(metric_id), None, body)))
        for variant, spec in (body.get("variants") or {}).items():
            found.add((str(metric_id), _formula_id(str(metric_id), str(variant), spec)))
    return found


def _formula_id(metric_id: str, variant: str | None, body: dict) -> str:
    declared = body.get("formula_id")
    if isinstance(declared, str) and declared:
        return declared
    if variant is None:
        return metric_id
    return f"{metric_id}.{variant}"


def _load_implementations() -> None:
    for name in _IMPLEMENTATION_MODULES:
        __import__(name)


def test_registry_keys_match_coverage_formulas():
    _load_implementations()
    catalog = _catalog_keys()
    assert _COMMON_ROUTE.isdisjoint(_ROUTE)
    assert _COMMON_ROUTE <= catalog
    assert set(_ROUTE) | _COMMON_ROUTE == catalog
    assert set(REGISTRY) == catalog - _COMMON_ROUTE
    for key, (module, name, version, inputs) in _ROUTE.items():
        item = REGISTRY[key]
        assert (item.metric_id, item.formula_id) == key
        assert item.function.__module__.rsplit(".", 1)[-1] == module
        assert item.function.__name__ == name
        assert item.version == version
        assert item.inputs == inputs


def test_same_key_cannot_register_twice():
    def sample() -> int:
        return 1

    def other() -> int:
        return 2

    key = ("__probe__", "__probe__")
    marked = implements(*key, version="probe", inputs=("left",))(sample)
    try:
        assert marked is sample
        assert sample() == 1
        assert REGISTRY[key].function is sample
        assert REGISTRY[key].inputs == ("left",)
        with pytest.raises(DuplicateImplementation):
            implements(*key)(other)
    finally:
        REGISTRY.pop(key, None)


def test_same_qualified_name_registers_again():
    def sample() -> int:
        return 1

    def reloaded() -> int:
        return 2

    reloaded.__module__ = sample.__module__
    reloaded.__qualname__ = sample.__qualname__
    key = ("__probe__", "__probe__.reload")
    implements(*key, version="1")(sample)
    try:
        implements(*key, version="2", inputs=("cfads",))(sample)
        assert REGISTRY[key].function is sample
        assert REGISTRY[key].version == "2"
        implements(*key)(reloaded)
        assert REGISTRY[key].function is reloaded
        assert REGISTRY[key].function() == 2
    finally:
        REGISTRY.pop(key, None)


def test_reload_of_implementation_module_keeps_the_key():
    import importlib

    import finance_analysis.domain.cash_flow as cash_flow

    _load_implementations()
    importlib.reload(cash_flow)
    item = REGISTRY[("ncf_period", "ncf_period")]
    assert item.function.__module__ == "finance_analysis.domain.cash_flow"
    assert item.function.__name__ == "net_cash_flow"
    assert item.inputs == ("cash_inflow", "cash_outflow")
