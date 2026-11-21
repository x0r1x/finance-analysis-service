"""Реестр реализаций совпадает с формулами каталога. Лестница расчёта реестр не читает."""

from __future__ import annotations

import pytest

from finance_analysis.application.model_types import load_coverage_document
from finance_analysis.domain.metric_contract import (
    COMMON_ROUTE,
    REGISTRY,
    BoundInputs,
    DuplicateImplementation,
    ImplementationContractError,
    UndeclaredInput,
    check_registry,
    formula_id_of,
    implements,
    load_implementations,
)

# Ключ → модуль, функция, version, inputs. inputs пуст, если набор читаемых понятий не фиксирован.
_ROUTE = {
    ("dscr", "dscr"): (
        "metrics",
        "coverage_ratio",
        "dscr@1",
        ("cfads", "debt_service", "interest", "interest_paid", "principal"),
    ),
    ("dscr", "dscr.pf"): (
        "metrics",
        "dscr_pf",
        "",
        ("cfads", "debt_service", "interest", "interest_paid", "principal"),
    ),
    ("dscr", "dscr.corporate_covenant"): ("covenant", "covenant_dscr", "", ()),
    ("dscr", "dscr.housing"): ("housing_dscr", "housing_dscr", "", ()),
    ("dscr", "dscr.cash_covenant"): ("covenant", "cash_covenant_dscr", "", ()),
    ("icr", "icr"): ("metrics", "coverage_ratio", "", ("ebitda", "ebit", "interest", "interest_paid")),
    ("icr", "icr.bank"): ("covenant", "bank_icr", "", ()),
    ("icr_ebit", "icr_ebit"): ("metrics", "coverage_ratio", "", ("ebit", "interest", "interest_paid")),
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
    ("icr_lease", "icr_lease"): (
        "metrics",
        "lease_interest_coverage",
        "",
        ("ebitda", "interest", "lease_interest", "lease_payment", "lease_principal"),
    ),
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
        found.add((str(metric_id), formula_id_of(str(metric_id), None, body)))
        for variant, spec in (body.get("variants") or {}).items():
            found.add((str(metric_id), formula_id_of(str(metric_id), str(variant), spec)))
    return found


def test_registry_keys_match_coverage_formulas():
    load_implementations()
    catalog = _catalog_keys()
    assert COMMON_ROUTE.isdisjoint(_ROUTE)
    assert COMMON_ROUTE <= catalog
    assert set(_ROUTE) | COMMON_ROUTE == catalog
    assert set(REGISTRY) == catalog - COMMON_ROUTE
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

    from finance_analysis.domain import cash_flow

    load_implementations()
    importlib.reload(cash_flow)
    item = REGISTRY[("ncf_period", "ncf_period")]
    assert item.function.__module__ == "finance_analysis.domain.cash_flow"
    assert item.function.__name__ == "net_cash_flow"
    assert item.inputs == ("cash_inflow", "cash_outflow")


def test_catalog_formulas_have_implementations():
    load_implementations()
    check_registry(load_coverage_document()["metrics"])


def test_missing_formula_is_named_in_russian():
    load_implementations()
    metrics = {"probe_metric": {"numerator": ["cfads"], "denominator": "debt_service"}}
    with pytest.raises(ImplementationContractError, match="probe_metric: нет реализации в реестре"):
        check_registry(metrics)


def test_common_route_does_not_need_an_implementation():
    load_implementations()
    check_registry(
        {
            "dscr": {
                "numerator": ["cfads"],
                "denominator": "debt_service",
                "variants": {"ocf_covenant": {"numerator": {"plus": ["operating_cash_flow"]}}},
            }
        }
    )


def test_every_gap_is_listed():
    with pytest.raises(ImplementationContractError) as caught:
        check_registry({"zeta": {"numerator": "a"}, "alpha": {"numerator": "b"}})
    text = str(caught.value)
    assert text.index("alpha: нет реализации в реестре") < text.index("zeta: нет реализации в реестре")


def test_undeclared_catalog_concept_is_named():
    load_implementations()
    metrics = {
        "llcr": {
            "numerator": ["mystery_b", "cfads", "mystery_a"],
            "denominator": "debt_outstanding",
            "rate": "discount_rate",
        }
    }
    with pytest.raises(ImplementationContractError, match="llcr: необъявленные входы: mystery_a, mystery_b"):
        check_registry(metrics)


def test_declared_inputs_may_exceed_the_catalog():
    load_implementations()
    check_registry(
        {"llcr": {"numerator": ["cfads"], "denominator": "debt_outstanding", "rate": "discount_rate"}}
    )


def test_empty_inputs_skip_the_catalog_composition():
    load_implementations()
    check_registry(
        {
            "dscr": {
                "numerator": ["cfads"],
                "denominator": "debt_service",
                "variants": {"corporate_covenant": {"numerator": {"plus": ["not_declared"]}}},
            }
        }
    )


def test_coverage_ratio_reads_through_bound_inputs(monkeypatch):
    from finance_analysis.domain.metrics import coverage_ratio

    seen: list[str] = []
    real = BoundInputs.__contains__

    def spy(self: BoundInputs, name: object) -> bool:
        if isinstance(name, str):
            seen.append(name)
        return real(self, name)

    monkeypatch.setattr(BoundInputs, "__contains__", spy)
    call = {
        "facts": [],
        "bindings": [],
        "periods": [],
        "period_phase": {},
        "explicit_phases": False,
    }
    assert coverage_ratio(metric="dscr", **call)["status"] == "missing_input"
    assert {"cfads", "debt_service"} <= set(seen)
    seen.clear()
    assert coverage_ratio(metric="icr", **call)["status"] == "missing_input"
    assert {"ebitda", "ebit", "interest"} <= set(seen)
    seen.clear()
    assert coverage_ratio(metric="icr_ebit", **call)["status"] == "missing_input"
    assert {"ebit", "interest"} <= set(seen)


def test_base_is_inheritance_not_an_input():
    def sample() -> None:
        return None

    key = ("__probe__", "__probe__")
    implements(*key, inputs=("cfads",))(sample)
    try:
        check_registry({"__probe__": {"base": "dscr"}})
    finally:
        REGISTRY.pop(key, None)


def test_bound_inputs_rejects_an_undeclared_name():
    bound = BoundInputs(("cfads", "debt_service"), {"cfads": 1, "ebit": 2})
    assert bound.get("cfads") == 1
    assert bound["cfads"] == 1
    assert "cfads" in bound
    assert "debt_service" not in bound
    with pytest.raises(UndeclaredInput, match="вход не объявлен: ebit"):
        bound.get("ebit")
    with pytest.raises(UndeclaredInput):
        bound["ebit"]
    with pytest.raises(UndeclaredInput):
        assert "ebit" in bound


def test_dscr_pf_reads_through_bound_inputs(monkeypatch):
    from finance_analysis.domain.metrics import dscr_pf

    seen: list[str] = []
    real = BoundInputs.__contains__

    def spy(self: BoundInputs, name: object) -> bool:
        if isinstance(name, str):
            seen.append(name)
        return real(self, name)

    monkeypatch.setattr(BoundInputs, "__contains__", spy)
    got = dscr_pf(
        facts=[],
        bindings=[],
        periods=[],
        period_phase={},
        explicit_phases=False,
    )
    assert got["status"] == "missing_input"
    assert "cfads" in seen
    assert "debt_service" in seen


def test_icr_lease_reads_through_bound_inputs(monkeypatch):
    from finance_analysis.domain.metrics import lease_interest_coverage

    seen: list[str] = []
    real = BoundInputs.__contains__

    def spy(self: BoundInputs, name: object) -> bool:
        if isinstance(name, str):
            seen.append(name)
        return real(self, name)

    monkeypatch.setattr(BoundInputs, "__contains__", spy)
    got = lease_interest_coverage(facts=[], bindings=[], periods=[])
    assert got["status"] == "missing_input"
    assert "ebitda" in seen


def test_check_config_prints_registry_problems(capsys, monkeypatch):
    from finance_analysis.cli import _check_config

    def fail(_metrics: object) -> None:
        raise ImplementationContractError("probe: нет реализации в реестре")

    monkeypatch.setattr("finance_analysis.domain.metric_contract.check_registry", fail)
    with pytest.raises(SystemExit):
        _check_config()
    assert "probe: нет реализации в реестре" in capsys.readouterr().err
