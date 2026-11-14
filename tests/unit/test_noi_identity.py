"""Сверка ЧОД: число книги остаётся, расхождение и запрещённый состав — находки."""

from __future__ import annotations

from decimal import Decimal

from finance_analysis.application.catalog import load_catalog, load_identities
from finance_analysis.domain.audit import AuditInput
from finance_analysis.domain.noi_identity import load_noi_difference
from tests.unit.rule_inputs import PERIODS, check, fact, link, row

_EGI = "S|1|S!r2"
_OPEX = "S|2|S!r2"
_RESERVE = "S|3|S!r2"
_NOI = "S|4|S!r2"
_MANAGEMENT = "S|5|S!r2"
_LAND_TAX = "S|6|S!r2"
_LAND_RENT = "S|7|S!r2"
_INTEREST = "S|8|S!r2"


def test_russian_labels_bind_and_sum_identity_stays_a_sum():
    package = load_catalog()
    assert package.resolve("ЧОД").concept == "noi"
    assert package.resolve("Чистая операционная прибыль").concept == "noi"
    assert package.resolve("Валовый доход по объекту").concept == "effective_gross_income"
    assert package.resolve("Операционные расходы").concept == "operating_expenses"
    assert package.resolve("Капитальный резерв по объекту").concept == "capital_reserve"
    assert package.resolve("Year 1 net operating income").concept == "noi"
    assert load_identities() == {
        "debt_service": ["interest", "principal"],
        "lease_payments": ["lease_principal", "lease_interest"],
    }
    spec = load_noi_difference()
    assert spec.result == "noi"
    assert spec.plus == ("effective_gross_income",)
    assert spec.minus == ("operating_expenses", "capital_reserve")
    assert spec.optional_minus == ("property_management",)
    assert spec.forbid == ("interest", "debt_service", "income_tax", "depreciation")
    assert spec.exclusive == ("land_tax", "land_rent")


def test_matching_noi_is_silent_and_does_not_replace_the_cell():
    sheet = fact(_NOI, "S!C4", "2024", "65")
    data = _book(sheet, reserve="5")
    assert check("noi_mismatch", data) == []
    assert check("noi_method", data) == []
    coverage = check("noi_coverage", data)
    assert [item.params.get("concepts") for item in coverage] == [["property_management"]]
    assert coverage[0].finding_kind == "insufficient_data"
    assert sheet["value_dec"] == Decimal(65)


def test_mismatch_keeps_the_book_value():
    sheet = fact(_NOI, "S!C4", "2024", "50")
    data = _book(sheet, reserve="5")
    found = check("noi_mismatch", data)
    assert len(found) == 1
    assert found[0].error_class == "quantitative"
    assert found[0].params["periods"] == ["2024"]
    assert sheet["value_dec"] == Decimal(50)
    assert check("noi_method", data) == []


def test_missing_reserve_does_not_start_the_check():
    data = _book(fact(_NOI, "S!C4", "2024", "70"), reserve=None)
    assert check("noi_mismatch", data) == []
    assert check("noi_coverage", data) == []


def test_management_is_subtracted_and_not_imputed():
    without = _book(fact(_NOI, "S!C4", "2024", "65"), reserve="5")
    assert check("noi_mismatch", without) == []
    assert [item.params.get("concepts") for item in check("noi_coverage", without)] == [["property_management"]]
    with_fee = _book(fact(_NOI, "S!C4", "2024", "63"), reserve="5", management="2")
    assert check("noi_mismatch", with_fee) == []
    over = _book(fact(_NOI, "S!C4", "2024", "65"), reserve="5", management="2")
    assert check("noi_mismatch", over)[0].params["periods"] == ["2024"]
    assert check("noi_coverage", with_fee) == []
    assert check("noi_coverage", over) == []


def test_both_land_charges_block_the_sum():
    data = _book(fact(_NOI, "S!C4", "2024", "65"), reserve="5", land_tax=True, land_rent=True)
    assert check("noi_mismatch", data) == []
    found = check("noi_method", data)
    assert found[0].finding_kind == "methodology"
    assert found[0].params["concepts"] == ["land_tax", "land_rent"]


def test_reserve_inside_expenses_is_not_subtracted_twice():
    data = _book(
        fact(_NOI, "S!C4", "2024", "65"),
        reserve="5",
        links=link("S!C2", "=C3", _OPEX, "2024", ("S!C3",)),
    )
    assert check("noi_mismatch", data) == []
    assert check("noi_method", data)[0].params["reserve"] == _RESERVE


def test_interest_inside_noi_formula_is_methodology():
    data = _book(
        fact(_NOI, "S!C4", "2024", "65"),
        reserve="5",
        interest=True,
        links=link("S!C4", "=C1-C2-C3-C8", _NOI, "2024", ("S!C1", "S!C2", "S!C3", "S!C8")),
    )
    found = check("noi_method", data)
    assert [item.params["concept"] for item in found] == ["interest"]
    assert found[0].finding_kind == "methodology"


def test_a_later_period_without_a_term_is_not_a_silent_match():
    base = _book(fact(_NOI, "S!C4", "2024", "65"), reserve="5")
    data = AuditInput(
        rows=base.rows,
        periods=base.periods,
        facts=[
            *base.facts,
            fact(_EGI, "S!D1", "2025", "100"),
            fact(_OPEX, "S!D2", "2025", "30"),
            fact(_NOI, "S!D4", "2025", "70"),
        ],
        links=base.links,
        bindings=base.bindings,
    )
    assert check("noi_mismatch", data) == []
    coverage = check("noi_coverage", data)
    assert any(item.params.get("periods") == ["2025"] for item in coverage)
    assert all(item.finding_kind == "insufficient_data" for item in coverage)


def _book(
    noi_fact: dict,
    *,
    reserve: str | None,
    management: str | None = None,
    land_tax: bool = False,
    land_rent: bool = False,
    interest: bool = False,
    links: list[dict] | None = None,
) -> AuditInput:
    rows = [row(_EGI), row(_OPEX), row(_NOI)]
    facts = [
        fact(_EGI, "S!C1", "2024", "100"),
        fact(_OPEX, "S!C2", "2024", "30"),
        noi_fact,
    ]
    bindings = [_bind("effective_gross_income", _EGI), _bind("operating_expenses", _OPEX), _bind("noi", _NOI)]
    if reserve is not None:
        rows.append(row(_RESERVE))
        facts.append(fact(_RESERVE, "S!C3", "2024", reserve))
        bindings.append(_bind("capital_reserve", _RESERVE))
    if management is not None:
        rows.append(row(_MANAGEMENT))
        facts.append(fact(_MANAGEMENT, "S!C5", "2024", management))
        bindings.append(_bind("property_management", _MANAGEMENT))
    if land_tax:
        rows.append(row(_LAND_TAX))
        bindings.append(_bind("land_tax", _LAND_TAX))
    if land_rent:
        rows.append(row(_LAND_RENT))
        bindings.append(_bind("land_rent", _LAND_RENT))
    if interest:
        rows.append(row(_INTEREST))
        facts.append(fact(_INTEREST, "S!C8", "2024", "9"))
        bindings.append(_bind("interest", _INTEREST))
    return AuditInput(rows=rows, periods=PERIODS, facts=facts, links=links or [], bindings=bindings)


def _bind(concept: str, row_key: str) -> dict:
    return {"effective_concept": concept, "row_key": row_key, "status": "bound", "is_primary": True}
