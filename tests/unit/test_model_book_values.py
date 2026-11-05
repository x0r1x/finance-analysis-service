"""Сверка кэша книг среза 5 с опубликованными якорями. Метриками FAS эти числа не считаются."""

from __future__ import annotations

from pathlib import Path

import openpyxl

_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "model_books"


def _cell(folder: str, name: str, sheet: str, coord: str):
    book = openpyxl.load_workbook(_ROOT / folder / name, data_only=True)
    try:
        return book[sheet][coord].value
    finally:
        book.close()


def test_halyard_moic_irr_sources_and_leverage():
    moic = _cell("halyard", "project_halyard.recalc_libreoffice.xlsx", "Returns", "C9")
    irr = _cell("halyard", "project_halyard.recalc_libreoffice.xlsx", "Returns", "C10")
    uses = _cell("halyard", "project_halyard.recalc_libreoffice.xlsx", "Sources & Uses", "C8")
    sources = _cell("halyard", "project_halyard.recalc_libreoffice.xlsx", "Sources & Uses", "C15")
    leverage = _cell("halyard", "project_halyard.recalc_libreoffice.xlsx", "Sources & Uses", "D13")
    assert round(moic, 2) == 2.13
    assert round(irr, 3) == 0.163
    assert uses == sources == 1052.5
    assert leverage == 5


def test_meridian_wacc_and_equity_bridge():
    """Кэш Meridian хранит середину года, оба терминальных метода и полный мост к капиталу."""
    name = "meridian_dcf.recalc_libreoffice.xlsx"
    wacc = _cell("meridian", name, "WACC", "C19")
    ev_perpetuity = _cell("meridian", name, "DCF", "C36")
    ev_exit = _cell("meridian", name, "DCF", "D36")
    equity_perpetuity = _cell("meridian", name, "DCF", "C46")
    equity_exit = _cell("meridian", name, "DCF", "D46")
    mid_year = _cell("meridian", name, "Inputs", "C7")
    growth = _cell("meridian", name, "Inputs", "C15")
    exit_multiple = _cell("meridian", name, "Inputs", "C16")
    debt = _cell("meridian", name, "Inputs", "C19")
    preferred = _cell("meridian", name, "Inputs", "C20")
    minority = _cell("meridian", name, "Inputs", "C21")
    cash = _cell("meridian", name, "Inputs", "C22")
    non_operating = _cell("meridian", name, "Inputs", "C23")
    assert round(wacc, 4) == 0.0961
    assert round(ev_perpetuity, 1) == 5717.6
    assert round(ev_exit, 1) == 6192.8
    assert round(equity_perpetuity, 1) == 5087.6
    assert round(equity_exit, 1) == 5562.8
    assert mid_year == 1
    assert growth == 0.025
    assert exit_multiple == 10
    assert (debt, preferred, minority, cash, non_operating) == (900, 0, 40, 250, 60)
    assert equity_perpetuity == ev_perpetuity - 900 - 0 - 40 + 250 + 60
    assert equity_exit == ev_exit - 900 - 0 - 40 + 250 + 60


def test_debtlens_noi_cap_rate_vacancy_and_dscr():
    """Шесть ячеек инвентаря. Summary!G10/H10 — шапка ёмкости около 33,5 млн, не второй DSCR 1,30x."""

    name = "DebtLens_Underwriting_Model.xlsx"
    noi = _cell("debtlens", name, "Summary", "D7")
    noi_again = _cell("debtlens", name, "Operating Forecast", "D15")
    cap_rate = _cell("debtlens", name, "Assumptions", "D20")
    vacancy = _cell("debtlens", name, "Assumptions", "D13")
    vacancy_again = _cell("debtlens", name, "Operating Forecast", "D9")
    dscr = _cell("debtlens", name, "Summary", "D17")
    capacity = _cell("debtlens", name, "Summary", "H10")
    assert noi == noi_again == 3_288_000
    assert cap_rate == 0.0575
    assert vacancy == vacancy_again == 0.05
    assert round(dscr, 2) == 1.30
    assert _cell("debtlens", name, "Summary", "C7") == "Year 1 net operating income"
    assert (
        _cell("debtlens", name, "Operating Forecast", "C15") == "Net operating income"
    )
    assert (
        _cell("debtlens", name, "Assumptions", "C20")
        == "Underwriting capitalization rate"
    )
    assert _cell("debtlens", name, "Assumptions", "C13") == "Year 1 vacancy"
    assert _cell("debtlens", name, "Operating Forecast", "C9") == "Vacancy"
    assert _cell("debtlens", name, "Summary", "C17") == "Debt service coverage ratio"
    assert _cell("debtlens", name, "Summary", "G7") == "Capacity"
    assert _cell("debtlens", name, "Summary", "H7") == "Amount"
    assert _cell("debtlens", name, "Summary", "G10") == "DSCR"
    assert _cell("debtlens", name, "Summary", "C13") == "DSCR capacity"
    assert capacity == _cell("debtlens", name, "Summary", "D13")
    assert round(capacity / 1_000_000, 1) == 33.5
    assert round(capacity, 2) != 1.30


def test_solar_capacity_generation_tariff_and_dscr():
    dc = _cell("solar", "Solar Financial Model.xlsx", "Model", "D20")
    ac = _cell("solar", "Solar Financial Model.xlsx", "Model", "D21")
    degradation = _cell("solar", "Solar Financial Model.xlsx", "Model", "D23")
    p50 = _cell("solar", "Solar Financial Model.xlsx", "Model", "G18")
    tariff = _cell("solar", "Solar Financial Model.xlsx", "Model", "H61")
    dscr_p50 = _cell("solar", "Solar Financial Model.xlsx", "Model", "H108")
    dscr_p99 = _cell("solar", "Solar Financial Model.xlsx", "Model", "H109")
    assert dc == 25 and ac == 20
    assert degradation == 0.005
    assert round(p50, 0) == 50370
    assert tariff == 72.75
    assert dscr_p50 == 1.35
    assert round(dscr_p99, 3) == 1.132
    # В книге нет строки capacity factor: P50 МВт·ч / (мощность AC × 8760 ч).
    assert round(p50 / (ac * 8760), 4) == 0.2875


def test_lease_portfolio_interest_npl_and_coverage():
    name = "lease_portfolio.recalc_libreoffice.xlsx"
    assert _cell("leasing", name, "Summary", "B2") == 260
    assert _cell("leasing", name, "Summary", "B4") == 200
    assert _cell("leasing", name, "Summary", "B5") == 0.125
    assert _cell("leasing", name, "Summary", "B7") == 100
    assert _cell("leasing", name, "Summary", "B8") == 0.5
    book = openpyxl.load_workbook(_ROOT / "leasing" / name, data_only=False)
    try:
        assert book["Schedule"]["F2"].value == "=IF(E2>=90,0,C2*D2)"
    finally:
        book.close()
