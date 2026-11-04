"""Срез 5: новые типы не срабатывают от одной соседней метки."""

from __future__ import annotations

from finance_analysis.domain.model_type import infer


def _catalog():
    from finance_analysis.application.model_types import load_model_types

    return load_model_types()


def _infer(**kwargs):
    return infer(_catalog(), accept=0.6, gap=0.15, **kwargs)


def test_lbo_needs_sources_exit_and_a_return():
    full = _infer(
        bound=frozenset({"sources_and_uses", "exit_enterprise_value", "moic"}),
        sheets=frozenset(),
    )
    sources = _infer(bound=frozenset({"sources_and_uses", "moic"}), sheets=frozenset())
    assert full.confident is True and full.primary == "lbo_ma" and full.labels == ("lbo_ma",)
    assert sources.confident is False and sources.reason == "unknown"
    assert sources.scores["lbo_ma"] == 0.5


def test_ppa_allocation_is_not_renewables_but_capacity_or_tariff_is():
    allocation = _infer(bound=frozenset({"purchase_price_allocation"}), sheets=frozenset())
    capacity = _infer(bound=frozenset({"installed_capacity"}), sheets=frozenset())
    tariff = _infer(bound=frozenset({"energy_tariff"}), sheets=frozenset())
    assert allocation.confident is False
    assert allocation.scores["renewables_dpm"] == 0.0
    assert capacity.primary == "renewables_dpm" and capacity.confident is True
    assert tariff.primary == "renewables_dpm" and tariff.labels == ("renewables_dpm",)


def test_solar_sources_without_exit_stay_renewables():
    got = _infer(
        bound=frozenset(
            {"installed_capacity", "energy_generation", "degradation", "energy_tariff", "sources_and_uses", "moic"}
        ),
        sheets=frozenset(),
    )
    assert got.confident is True
    assert got.primary == "renewables_dpm"
    assert got.labels == ("renewables_dpm",)
    assert got.scores["lbo_ma"] == 0.5


def test_dcf_real_estate_and_leasing_need_their_full_set():
    dcf = _infer(
        bound=frozenset({"wacc", "terminal_value", "enterprise_value", "equity_value"}),
        sheets=frozenset(),
    )
    wacc = _infer(bound=frozenset({"wacc"}), sheets=frozenset())
    estate = _infer(bound=frozenset({"noi", "cap_rate", "vacancy"}), sheets=frozenset())
    noi = _infer(bound=frozenset({"noi", "cap_rate"}), sheets=frozenset())
    lease = _infer(
        bound=frozenset({"lease_interest_income", "npl_share", "provision_coverage"}),
        sheets=frozenset(),
    )
    assert dcf.primary == "dcf_valuation" and dcf.confident is True
    assert wacc.confident is False and wacc.scores["dcf_valuation"] == 0.0
    assert estate.primary == "real_estate_income"
    assert noi.confident is False
    assert lease.primary == "bank_leasing" and lease.labels == ("bank_leasing",)


def test_project_finance_book_does_not_become_a_new_type():
    got = _infer(bound=frozenset({"cfads", "debt_service"}), sheets=frozenset({"Debt", "CFS"}))
    assert got.confident is True
    assert got.primary == "project_finance"
    assert got.labels == ("project_finance",)
    assert got.scores["lbo_ma"] == 0.0
    assert got.scores["renewables_dpm"] == 0.0
