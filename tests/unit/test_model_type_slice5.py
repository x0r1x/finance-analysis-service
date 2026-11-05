"""Срез 5: новые типы не срабатывают от одной соседней метки."""

from __future__ import annotations

from finance_analysis.application.catalog import load_catalog
from finance_analysis.domain.model_type import infer
from tests.workbook_labels import resolved_workbook


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


def test_sources_exit_and_catalog_irr_without_moic_are_not_a_confident_lbo():
    """Связка sources_and_uses, exit_enterprise_value и каталожного irr без moic не даёт уверенный lbo_ma.

    Срабатывает только первый сигнал. Score равен 0.5 и остаётся ниже порога принятия 0.6.
    """
    got = _infer(
        bound=frozenset({"sources_and_uses", "exit_enterprise_value", "irr"}),
        sheets=frozenset(),
    )
    assert got.scores["lbo_ma"] == 0.5
    assert got.confident is False
    assert got.reason == "unknown"
    assert got.labels == ()


def test_halyard_stays_confident_lbo_ma_at_full_score():
    """Книга Halyard остаётся уверенным lbo_ma со score 1.0, потому что привязан moic."""
    bound, sheets = resolved_workbook("halyard/project_halyard.recalc_libreoffice.xlsx")
    got = _infer(bound=bound, sheets=sheets)
    assert got.confident is True
    assert got.primary == "lbo_ma"
    assert got.labels == ("lbo_ma",)
    assert got.scores["lbo_ma"] == 1.0


def test_meridian_stays_confident_dcf_valuation_at_full_score():
    """Книга Meridian остаётся уверенным dcf_valuation со score 1.0, потому что привязаны все четыре понятия сигнала."""
    bound, sheets = resolved_workbook("meridian/meridian_dcf.recalc_libreoffice.xlsx")
    got = _infer(bound=bound, sheets=sheets)
    assert got.confident is True
    assert got.primary == "dcf_valuation"
    assert got.labels == ("dcf_valuation",)
    assert got.scores["dcf_valuation"] == 1.0


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


def test_wacc_and_terminal_value_without_enterprise_and_equity_are_not_confident_dcf():
    """Связка wacc и terminal_value без enterprise_value и equity_value не даёт уверенный dcf_valuation.

    Сигнал один и имеет вид concepts_bound_all по всем четырём понятиям, поэтому score равен 0.0.
    """
    got = _infer(bound=frozenset({"wacc", "terminal_value"}), sheets=frozenset())
    assert got.scores["dcf_valuation"] == 0.0
    assert got.confident is False
    assert got.reason == "unknown"
    assert got.labels == ()


def test_enterprise_and_equity_without_wacc_are_not_confident_dcf():
    """Связка enterprise_value и equity_value без wacc и без terminal_value не даёт уверенный dcf_valuation.

    Сигнал один и имеет вид concepts_bound_all по всем четырём понятиям, поэтому score равен 0.0.
    """
    got = _infer(bound=frozenset({"enterprise_value", "equity_value"}), sheets=frozenset())
    assert got.scores["dcf_valuation"] == 0.0
    assert got.confident is False
    assert got.reason == "unknown"
    assert got.labels == ()


def test_fixture_workbooks_classify_from_their_own_labels():
    """Тип берётся из подписей книги, а не из вручную перечисленных id."""
    package = load_catalog()
    assert package.resolve("IRR") is None
    expect = {
        "halyard/project_halyard.recalc_libreoffice.xlsx": "lbo_ma",
        "meridian/meridian_dcf.recalc_libreoffice.xlsx": "dcf_valuation",
        "debtlens/DebtLens_Underwriting_Model.xlsx": "real_estate_income",
        "solar/Solar Financial Model.xlsx": "renewables_dpm",
        "leasing/lease_portfolio.recalc_libreoffice.xlsx": "bank_leasing",
    }
    catalog = _catalog()
    for book, primary in expect.items():
        bound, sheets = resolved_workbook(book)
        got = infer(catalog, bound=bound, sheets=sheets, accept=0.6, gap=0.15)
        assert got.confident is True and got.primary == primary and got.labels == (primary,), book


def test_project_finance_book_does_not_become_a_new_type():
    got = _infer(bound=frozenset({"cfads", "debt_service"}), sheets=frozenset({"Debt", "CFS"}))
    assert got.confident is True
    assert got.primary == "project_finance"
    assert got.labels == ("project_finance",)
    assert got.scores["lbo_ma"] == 0.0
    assert got.scores["renewables_dpm"] == 0.0
