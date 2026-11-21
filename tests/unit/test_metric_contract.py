"""Реестр реализаций совпадает с формулами каталога. Лестница расчёта реестр не читает."""

from __future__ import annotations

from decimal import Decimal

import pytest

from finance_analysis.application.model_types import load_coverage_document
from finance_analysis.domain.metric_contract import (
    REGISTRY,
    BoundInputs,
    DuplicateImplementation,
    ImplementationContractError,
    UndeclaredInput,
    check_registry,
    formula_id_of,
    implements,
    load_implementations,
    profile_definition_problems,
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
    ("dscr", "dscr.ocf_covenant"): (
        "covenant",
        "dscr_ocf_covenant",
        "dscr.ocf_covenant@1",
        ("operating_cash_flow", "interest", "capex", "principal"),
    ),
    ("dscr", "dscr.housing"): ("housing_dscr", "housing_dscr", "", ()),
    ("dscr", "dscr.cash_covenant"): (
        "covenant",
        "cash_covenant_dscr",
        "",
        ("operating_cash_flow", "interest_paid", "capex", "principal"),
    ),
    ("icr", "icr"): ("metrics", "coverage_ratio", "", ("ebitda", "ebit", "interest", "interest_paid")),
    ("icr", "icr.bank"): ("covenant", "bank_icr", "", ()),
    ("icr_ebit", "icr_ebit"): ("metrics", "coverage_ratio", "", ("ebit", "interest", "interest_paid")),
    ("adscr", "adscr"): ("cover_metrics", "adscr", "", ("cfads", "debt_service")),
    ("adscr", "adscr.housing"): ("housing_cover", "_adscr", "", ()),
    ("dscr_min", "dscr_min"): ("cover_metrics", "dscr_reductions", "", ("cfads", "debt_service")),
    ("dscr_min", "dscr_min.housing"): ("housing_cover", "_minimum", "", ()),
    ("dscr_avg", "dscr_avg"): ("cover_metrics", "dscr_reductions", "", ("cfads", "debt_service")),
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
    ("fcff", "fcff"): ("free_cash_flow", "free_cash_flow", "", ("operating_cash_flow", "capex")),
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

# Условные входы: профиль, concept.absent, щит процентов. Остальные реализации — пусто.
_OPTIONAL = {
    ("dscr", "dscr.ocf_covenant"): ("interest_paid",),
    ("dscr", "dscr.cash_covenant"): ("other_financial_debt_service",),
    ("fcff", "fcff"): ("interest", "interest_paid", "income_tax_rate"),
}

# Дополнительные понятия договорного состава. None — профильной формулы нет.
# interest_paid не выводится из interest: это отдельное имя.
_PROFILE_INPUTS = {
    ("dscr", "dscr.corporate_covenant"): (
        "ebitda",
        "cash_taxes",
        "capex",
        "operating_cash_flow",
        "interest",
        "interest_paid",
        "principal",
    ),
    ("dscr", "dscr.ocf_covenant"): ("ebitda", "cash_taxes"),
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
    composed = {key for key, item in REGISTRY.items() if item.mode == "composed"}
    assert composed.isdisjoint(_ROUTE)
    assert composed <= catalog
    assert set(_ROUTE) | composed == catalog
    assert set(REGISTRY) == catalog
    for key, (module, name, version, inputs) in _ROUTE.items():
        item = REGISTRY[key]
        assert (item.metric_id, item.formula_id) == key
        assert item.function.__module__.rsplit(".", 1)[-1] == module
        assert item.function.__name__ == name
        assert item.version == version
        assert item.inputs == inputs
        assert item.optional_inputs == _OPTIONAL.get(key, ())
        assert item.profile_inputs == _PROFILE_INPUTS.get(key)
        assert item.mode == ("dynamic" if not inputs else "registered")
        if item.mode == "dynamic":
            assert item.reason.strip()


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


_COMPOSED = (
    "net_debt_ebitda",
    "escrow_coverage",
    "total_debt_ebitda",
    "debt_off_balance_ebitda",
)


@pytest.mark.parametrize("metric_id", _COMPOSED)
def test_common_route_is_composed_ratio(metric_id, monkeypatch):
    from finance_analysis.domain import covenant
    from finance_analysis.domain.model_type import Composed, Side

    called: list[str] = []

    def fake(metric: str, _formula: object, **_kwargs: object) -> dict:
        called.append(metric)
        return {"status": "probe", "metric": metric}

    def coverage(**_kwargs: object) -> dict:
        raise AssertionError("coverage_ratio")

    monkeypatch.setattr(covenant, "composed_ratio", fake)
    monkeypatch.setattr(covenant, "coverage_ratio", coverage)
    formula = Composed(Side(("left",), ()), Side(("right",), ()), "LTM")
    got = covenant.select_ratio(
        metric_id,
        None,
        {
            "facts": [],
            "bindings": [],
            "periods": [],
            "sign_convention": "outflow_negative",
            "marker_class": None,
            "absent": frozenset(),
        },
        profile=None,
        profile_ref=None,
        composed={metric_id: formula},
        concepts=frozenset(),
        money=frozenset(),
    )
    assert called == [metric_id]
    assert got["metric"] == metric_id


def test_common_route_without_a_composed_case_fails():
    load_implementations()
    found = {key for key, item in REGISTRY.items() if item.mode == "composed"}
    assert {(metric, metric) for metric in _COMPOSED} == found


def test_common_route_records_a_reason():
    load_implementations()
    composed = [item for item in REGISTRY.values() if item.mode == "composed"]
    assert composed
    assert all(item.reason.strip() for item in composed)


def test_modes_replace_the_two_exception_lists():
    import finance_analysis.domain.metric_contract as contract

    assert not hasattr(contract, "COMMON_ROUTE")
    assert not hasattr(contract, "DYNAMIC_INPUTS")
    load_implementations()
    assert {item.mode for item in REGISTRY.values()} == {"registered", "composed", "dynamic"}


def test_common_route_does_not_need_an_implementation():
    load_implementations()
    check_registry(
        {
            "net_debt_ebitda": {
                "numerator": {"plus": ["net_debt"]},
                "denominator": {"plus": ["ebitda"]},
                "window": "LTM",
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


def test_empty_inputs_outside_dynamic_inputs_fail():
    def sample() -> None:
        return None

    key = ("__probe__", "__probe__")
    implements(*key, optional_inputs=("capex",))(sample)
    try:
        with pytest.raises(ImplementationContractError, match="__probe__: пустые inputs у registered"):
            check_registry({"__probe__": {"numerator": ["cfads"]}})
    finally:
        REGISTRY.pop(key, None)


def test_optional_input_covers_a_catalog_concept():
    def sample() -> None:
        return None

    key = ("__probe__", "__probe__")
    implements(*key, inputs=("cfads",), optional_inputs=("capex",))(sample)
    try:
        check_registry({"__probe__": {"numerator": {"plus": ["cfads"], "minus": ["capex"]}}})
        with pytest.raises(ImplementationContractError, match="__probe__: необъявленные входы: mystery"):
            check_registry({"__probe__": {"numerator": ["cfads", "mystery"]}})
    finally:
        REGISTRY.pop(key, None)


def test_dynamic_inputs_names_every_empty_declaration():
    load_implementations()
    empty = {key for key, item in REGISTRY.items() if not item.inputs and item.mode != "composed"}
    dynamic = {key for key, item in REGISTRY.items() if item.mode == "dynamic"}
    assert empty == dynamic
    assert dynamic
    assert all(item.reason.strip() for key, item in REGISTRY.items() if key in dynamic)


def test_bound_inputs_allows_an_optional_name():
    bound = BoundInputs(("cfads",), {"cfads": 1, "capex": 2}, optional=("capex",))
    assert bound.get("capex") == 2
    assert "capex" in bound
    with pytest.raises(UndeclaredInput, match="вход не объявлен: ebit"):
        bound["ebit"]


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


def test_loan_life_ratio_reads_through_bound_inputs(monkeypatch):
    from finance_analysis.domain.cover_metrics import loan_life_ratio

    seen: list[str] = []
    real = BoundInputs.__getitem__

    def spy(self: BoundInputs, name: str) -> object:
        seen.append(name)
        return real(self, name)

    monkeypatch.setattr(BoundInputs, "__getitem__", spy)
    bindings = [
        {
            "effective_concept": name,
            "row_key": name,
            "is_primary": True,
            "status": "bound",
            "source": "inferred",
        }
        for name in ("debt_service", "cfads", "debt_outstanding", "discount_rate")
    ]
    loan_life_ratio(
        "llcr",
        facts=[],
        bindings=bindings,
        periods=[],
        period_phase={},
        explicit_phases=False,
    )
    assert {"cfads", "debt_service", "debt_outstanding", "discount_rate"} <= set(seen)


def _bindings(*names: str) -> list[dict]:
    return [
        {
            "effective_concept": name,
            "row_key": name,
            "is_primary": True,
            "status": "bound",
            "source": "inferred",
        }
        for name in names
    ]


def test_adscr_and_dscr_reductions_read_through_bound_inputs(monkeypatch):
    from finance_analysis.domain import cover_metrics

    seen: list[tuple[str, ...]] = []
    real = BoundInputs.__init__

    def spy(self: BoundInputs, declared: tuple[str, ...], values: object, optional: tuple[str, ...] = ()) -> None:
        seen.append(tuple(declared))
        real(self, declared, values, optional)

    monkeypatch.setattr(BoundInputs, "__init__", spy)
    monkeypatch.setattr(
        cover_metrics,
        "coverage_ratio",
        lambda **_kwargs: {"status": "succeeded", "rows": [], "warnings": [], "metric": "dscr"},
    )
    call = {
        "facts": [],
        "bindings": _bindings("cfads", "debt_service"),
        "periods": [],
        "period_phase": {},
        "explicit_phases": False,
    }
    assert cover_metrics.adscr(**call)["status"] == "succeeded"
    cover_metrics.dscr_reductions("dscr_min", **call)
    cover_metrics.dscr_reductions("dscr_avg", **call)
    assert seen.count(("cfads", "debt_service")) == 3


def test_cash_covenant_reads_through_bound_inputs(monkeypatch):
    from finance_analysis.domain.covenant import cash_covenant_dscr

    seen: list[str] = []
    real = BoundInputs.__getitem__

    def spy(self: BoundInputs, name: str) -> object:
        seen.append(name)
        return real(self, name)

    monkeypatch.setattr(BoundInputs, "__getitem__", spy)
    bindings = [
        {
            "effective_concept": name,
            "row_key": name,
            "is_primary": True,
            "status": "bound",
            "source": "inferred",
        }
        for name in (
            "operating_cash_flow",
            "interest_paid",
            "capex",
            "principal",
            "other_financial_debt_service",
        )
    ]
    cash_covenant_dscr(facts=[], bindings=bindings, periods=[])
    assert {
        "operating_cash_flow",
        "interest_paid",
        "capex",
        "principal",
        "other_financial_debt_service",
    } <= set(seen)


def _definition(plus: list[str], minus: list[str] | None = None, denominator: list[str] | None = None) -> dict:
    return {
        "numerator": {"plus": plus, "minus": minus or []},
        "denominator": {"plus": denominator or ["interest"]},
        "window": "LTM",
    }


def test_profile_definition_problems_accepts_a_declared_composition():
    load_implementations()
    allowed = {
        ("dscr", "dscr.corporate_covenant"): _definition(
            ["ebitda"], ["cash_taxes", "capex"], ["interest", "principal"]
        ),
        ("dscr", "dscr.ocf_covenant"): _definition(
            ["operating_cash_flow", "interest"],
            ["capex"],
            ["interest_paid", "principal"],
        ),
    }
    assert profile_definition_problems(allowed, REGISTRY) == []


def test_profile_definition_problems_names_an_undeclared_concept():
    load_implementations()
    foreign = _definition(["revenue"])
    problems = profile_definition_problems(
        {
            ("dscr", "dscr.corporate_covenant"): foreign,
            ("dscr", "dscr.ocf_covenant"): foreign,
        },
        REGISTRY,
    )
    assert problems == [
        "dscr.corporate_covenant: необъявленные профильные входы: revenue",
        "dscr.ocf_covenant: необъявленные профильные входы: revenue",
    ]


def test_interest_paid_is_not_accepted_as_a_stand_in_for_another_name():
    """interest_paid объявлен сам по себе. Похожее имя в набор не попадает."""

    load_implementations()
    paid = {("dscr", "dscr.ocf_covenant"): _definition(["ebitda"], denominator=["interest_paid"])}
    assert profile_definition_problems(paid, REGISTRY) == []
    foreign = {("dscr", "dscr.ocf_covenant"): _definition(["ebitda"], denominator=["finance_costs"])}
    assert profile_definition_problems(foreign, REGISTRY) == [
        "dscr.ocf_covenant: необъявленные профильные входы: finance_costs"
    ]


def test_formula_without_profile_inputs_rejects_a_definition():
    load_implementations()
    problems = profile_definition_problems(
        {("dscr", "dscr.cash_covenant"): _definition(["operating_cash_flow"])},
        REGISTRY,
    )
    assert problems == ["dscr.cash_covenant: профильный состав не объявлен"]


def test_empty_profile_inputs_keep_the_union_closed():
    def sample() -> None:
        return None

    key = ("__probe__", "__probe__.covenant")
    implements(*key, inputs=("ebitda", "interest"), profile_inputs=())(sample)
    try:
        assert profile_definition_problems({key: _definition(["ebitda"])}, REGISTRY) == []
        assert profile_definition_problems({key: _definition(["ebitda", "capex"])}, REGISTRY) == [
            "__probe__.covenant: необъявленные профильные входы: capex"
        ]
    finally:
        REGISTRY.pop(key, None)


def test_unnamed_dscr_definition_maps_onto_both_covenant_formulas():
    from finance_analysis.application.glossary_store import profile_covenant_definitions

    raw = _definition(["revenue"])
    found = profile_covenant_definitions({"dscr_definition": raw})
    assert set(found) == {
        ("dscr", "dscr.corporate_covenant"),
        ("dscr", "dscr.ocf_covenant"),
    }
    assert found[("dscr", "dscr.ocf_covenant")] is raw
    assert profile_covenant_definitions({"dscr_definition": {"variant": "ocf_covenant"}}) == {}


def test_profile_calculation_keeps_the_contract_ratio():
    from finance_analysis.domain.covenant import covenant_dscr
    from tests.unit.test_covenant_dscr import (
        _CONCEPTS,
        _MONEY,
        _bind,
        _catalog,
        _fact,
        _year,
    )

    catalog = _catalog()
    raw = {
        "numerator": {"plus": ["ebitda"], "minus": []},
        "denominator": {"plus": ["interest"]},
        "window": "period",
        "basis_ref": "кредитный договор, п. 4.2",
    }
    got = covenant_dscr(
        facts=[
            _fact("e", "Y1", "100"),
            _fact("t", "Y1", "10"),
            _fact("c", "Y1", "20"),
            _fact("i", "Y1", "15"),
            _fact("p", "Y1", "5"),
        ],
        bindings=[
            _bind("ebitda", "e"),
            _bind("cash_taxes", "t"),
            _bind("capex", "c"),
            _bind("interest", "i"),
            _bind("principal", "p"),
        ],
        periods=[_year()],
        profile={"dscr_definition": raw},
        profile_ref="desk@p-3",
        default=catalog.composed["dscr.corporate_covenant"],
        concepts=_CONCEPTS,
        money=_MONEY,
    )
    assert got["definition_source"] == "profile"
    assert got["rows"][0]["value"] == Decimal("6.6666666667")


def test_check_config_prints_registry_problems(capsys, monkeypatch):
    from finance_analysis.cli import _check_config

    def fail(_metrics: object) -> None:
        raise ImplementationContractError("probe: нет реализации в реестре")

    monkeypatch.setattr("finance_analysis.domain.metric_contract.check_registry", fail)
    with pytest.raises(SystemExit):
        _check_config()
    assert "probe: нет реализации в реестре" in capsys.readouterr().err
