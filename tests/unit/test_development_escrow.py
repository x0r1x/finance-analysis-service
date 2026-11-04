"""Книга 214-ФЗ: тип development_escrow и ручная сверка покрытия со ставкой."""

from __future__ import annotations

from pathlib import Path

import openpyxl

from finance_analysis.application.model_types import load_model_types
from finance_analysis.domain.model_type import infer
from tests.workbook_labels import resolved_workbook

_BOOK = "escrow/development_escrow_214.recalc_libreoffice.xlsx"
_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "model_books" / _BOOK

# Месяц 2: покрытие закрытия 4000/2005. Ставка — от входа 2000/1000, вес 1, проценты 5.
_MONTH2 = {"coverage": 4000 / 2005, "rate": 0.06, "interest": 5.0, "escrow": 4000.0, "loan": 2005.0}


def _params(sheet) -> dict:
    return {sheet.cell(row, 1).value: sheet.cell(row, 2).value for row in range(2, 20)}


def _recurrence(params: dict, months: int) -> list[dict]:
    """Та же рекуррентность, что в формулах книги. Ставки берутся из ячеек, не из констант теста."""

    price0 = params["Цена за м2"]
    area = params["Площадь в месяц, м2"]
    sales_until = params["Продажи до месяца включительно"]
    index = params["Индексация цены"]
    capex_m = params["Бюджет стройки в месяц"]
    capex_until = params["Стройка до месяца включительно"]
    equity_share = params["Доля собственных средств"]
    loan_limit = params["Лимит кредита"]
    base = params["Базовая ставка"]
    special = params["Специальная ставка"]
    pay_share = params["Доля оплаты на эскроу"]
    rve = params["Месяц РВЭ"]
    release_month = rve + params["Лаг раскрытия, мес"]
    to_loan = params["Доля раскрытия в погашение"]
    full = params["Порог полного покрытия"]
    per_year = params["Периодов в году"]
    equity_need = equity_share * capex_m * capex_until
    prev_escrow = prev_loan = cum_equity = cum_draw = 0.0
    rows = []
    for month in range(1, months + 1):
        sold = area if month <= sales_until else 0
        ddu = sold * price0 * (1 + index) ** (month - 1)
        escrow_in = 0.0 if month > release_month else ddu * pay_share
        release = (prev_escrow + escrow_in) if month == release_month else 0.0
        escrow = prev_escrow + escrow_in - release
        capex = capex_m if month <= capex_until else 0
        equity = min(capex, max(0.0, equity_need - cum_equity))
        draw = min(max(0.0, capex - equity), max(0.0, loan_limit - cum_draw))
        if prev_loan > 0 and full > 0:
            weight = min((prev_escrow / prev_loan) / full, 1)
            rate = weight * special + (1 - weight) * base
        else:
            rate = base
        interest = prev_loan * rate / per_year
        capitalized = interest if month <= rve else 0.0
        repay = min(prev_loan + draw + capitalized, release * to_loan)
        loan = prev_loan + draw + capitalized - repay
        coverage = None if loan <= 0 else escrow / loan
        rows.append(
            {
                "coverage": coverage,
                "rate": rate,
                "interest": interest,
                "escrow": escrow,
                "loan": loan,
                "escrow_in": escrow_in,
                "release": release,
            }
        )
        prev_escrow, prev_loan = escrow, loan
        cum_equity += equity
        cum_draw += draw
    return rows


def _close(got, expected) -> bool:
    if expected is None:
        return got in (None, "")
    return abs(float(got) - float(expected)) < 1e-6


def test_fixture_is_development_escrow_and_not_corporate_or_project_finance():
    bound, sheets = resolved_workbook(_BOOK)
    assert sheets == frozenset({"Вводы", "Модель", "Проверки"})
    assert {"escrow_balance", "escrow_inflow", "escrow_disclosure", "escrow_coverage", "effective_rate", "debt_outstanding"} <= bound
    assert "cfads" not in bound and "debt_service" not in bound
    got = infer(load_model_types(), bound=bound, sheets=sheets, accept=0.6, gap=0.15)
    assert got.confident is True
    assert got.primary == "development_escrow"
    assert got.labels == ("development_escrow",)
    assert got.scores["development_escrow"] == 1.0
    assert got.scores["corporate"] == 0.0
    assert got.scores["project_finance"] == 0.0


def test_coverage_and_effective_rate_match_the_hand_recurrence():
    cached = openpyxl.load_workbook(_PATH, data_only=True)
    formulas = openpyxl.load_workbook(_PATH, data_only=False)
    try:
        params = _params(cached["Вводы"])
        assert params["Месяцев"] == 36
        assert params["Базовая ставка"] == 0.12 and params["Специальная ставка"] == 0.06
        assert params["Порог полного покрытия"] == 1
        expected = _recurrence(params, 36)
        model = cached["Модель"]
        first, second = expected[0], expected[1]
        assert first["coverage"] == 2 and first["rate"] == 0.12 and first["interest"] == 0
        assert first["escrow"] == 2000 and first["loan"] == 1000
        assert second == {**_MONTH2, "escrow_in": 2000.0, "release": 0.0}
        assert expected[23]["coverage"] is None
        for offset, row in enumerate(expected, start=2):
            assert _close(model.cell(offset, 13).value, row["coverage"]), offset
            assert _close(model.cell(offset, 14).value, row["rate"]), offset
            assert _close(model.cell(offset, 15).value, row["interest"]), offset
            assert _close(model.cell(offset, 9).value, row["escrow"]), offset
            assert _close(model.cell(offset, 17).value, row["loan"]), offset
        assert expected[23]["escrow"] == 0 and abs(expected[-1]["loan"]) < 1e-6
        assert sum(row["escrow_in"] for row in expected) == sum(row["release"] for row in expected)
        checks = cached["Проверки"]
        for row in range(1, 11):
            assert checks.cell(row, 2).value is True, checks.cell(row, 1).value
        rate_formula = formulas["Модель"]["N3"].value
        interest_formula = formulas["Модель"]["O2"].value
        balance_formula = formulas["Модель"]["I2"].value
        assert formulas["Модель"]["M2"].value == '=IF(Q2<=0,"",I2/Q2)'
        assert "MIN((I2/Q2)/Вводы!$B$17,1)" in rate_formula
        assert "M3" not in rate_formula and "M2" not in rate_formula
        assert "$B$11" in rate_formula and "$B$12" in rate_formula
        assert "0.12" not in rate_formula and "0.06" not in rate_formula
        assert "/12" not in interest_formula and "$B$18" in interest_formula
        assert "O2" not in balance_formula
    finally:
        cached.close()
        formulas.close()


def test_threshold_other_than_one_still_reaches_the_special_rate():
    params = _params_of_fixture()
    params["Порог полного покрытия"] = 0.8
    second = _recurrence(params, 2)[1]
    assert second["rate"] == 0.06 and second["interest"] == 5
    params["Цена за м2"] = 10
    thin = _recurrence(params, 2)[1]
    assert abs(thin["rate"] - (0.25 * 0.06 + 0.75 * 0.12)) < 1e-9
    params["Порог полного покрытия"] = 0
    assert _recurrence(params, 2)[1]["rate"] == 0.12


def _params_of_fixture() -> dict:
    book = openpyxl.load_workbook(_PATH, data_only=True)
    try:
        return _params(book["Вводы"])
    finally:
        book.close()


def test_escrow_only_book_still_scores_one():
    got = infer(
        load_model_types(),
        bound=frozenset({"escrow_balance"}),
        sheets=frozenset(),
        accept=0.6,
        gap=0.15,
    )
    assert got.scores["development_escrow"] == 1.0
    assert got.primary == "development_escrow"
    assert got.confident is True
