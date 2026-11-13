"""Явный код строки 4123 выбирает уплаченные проценты. Голое число кодом не является."""

from __future__ import annotations

from decimal import Decimal

from finance_analysis.application.catalog import load_catalog
from finance_analysis.application.model_types import load_model_types
from finance_analysis.domain.covenant import covenant_dscr
from finance_analysis.domain.mapping import assign_rows, marked_line_code
from finance_analysis.domain.metrics import coverage_ratio


def test_marked_line_code_accepts_only_an_explicit_form():
    assert marked_line_code("стр. 4123") == "стр. 4123"
    assert marked_line_code("код 4123") == "стр. 4123"
    assert marked_line_code("строка 4123") == "стр. 4123"
    assert marked_line_code("Стр.  4123") == "стр. 4123"
    assert marked_line_code(marked_line_code("код 4123")) == "стр. 4123"
    assert marked_line_code("Ф. 5 (740)") == "ф.5 (740)"
    assert marked_line_code("4123") is None
    assert marked_line_code(4123) is None
    assert marked_line_code("70") is None

    glossary = load_catalog()
    unknown = {"kind": "fact", "binding_key": "u", "row_key": "u", "label": "Прочая строка без кода", "unit": "money"}
    unknown["line_code"] = "стр. 4123"
    missed = assign_rows([unknown], [], glossary)["u"]
    assert missed.concept is None
    assert "line_code" not in missed.evidence

    labeled = {
        "kind": "fact",
        "binding_key": "i",
        "row_key": "i",
        "label": "Проценты к уплате",
        "unit": "money",
        "line_code": "код 4123",
    }
    hit = assign_rows([labeled], [], glossary)["i"]
    assert hit.concept == "interest"
    assert hit.evidence["line_code"] == "стр. 4123"


def _bind(concept: str, row: str, *, primary: bool = True, code: str | None = None, sheet: str | None = None) -> dict:
    item = {
        "effective_concept": concept,
        "row_key": row,
        "is_primary": primary,
        "status": "bound",
        "source": "inferred",
    }
    if code:
        item["evidence_json"] = '{"line_code": "' + code + '"}'
    if sheet:
        item["sheet"] = sheet
    return item


def _fact(row: str, value: str) -> dict:
    return {"row_key": row, "axis_id": "a", "period_id": "Y1", "normalized_value": value}


def _year() -> dict:
    return {"axis_id": "a", "period_id": "Y1", "period_index": 1, "grain": "year", "timeline_id": "t"}


def _common() -> dict:
    catalog = load_model_types()
    return {
        "periods": [_year()],
        "period_phase": {},
        "explicit_phases": False,
        "interest_order": catalog.interest_order,
        "row_fallbacks": catalog.row_fallbacks,
    }


def test_one_explicit_4123_row_is_paid_interest_and_accrued_stays():
    paid = _bind("interest", "paid", primary=False, code="стр. 4123")
    accrued = _bind("interest", "i")
    common = _common()
    icr = coverage_ratio(
        metric="icr",
        facts=[_fact("e", "40"), _fact("i", "-10"), _fact("paid", "-2")],
        bindings=[_bind("ebitda", "e"), accrued, paid],
        **common,
    )
    assert icr["rows"][0]["value"] == Decimal("4.0000000000")
    assert not any(item["code"] == "interest_basis_fallback" for item in icr["warnings"])

    pf = coverage_ratio(
        metric="dscr",
        facts=[_fact("c", "40"), _fact("i", "-10"), _fact("paid", "-2"), _fact("p", "-4")],
        bindings=[_bind("cfads", "c"), accrued, paid, _bind("principal", "p")],
        **common,
    )
    assert pf["rows"][0]["value"] == Decimal("6.6666666667")
    assert "interest_paid" in pf["rows"][0]["components"]
    assert not any(item["code"] == "interest_basis_fallback" for item in pf["warnings"])

    second = _bind("interest", "other", primary=False, code="стр. 4123")
    ambiguous = coverage_ratio(
        metric="dscr",
        facts=[_fact("c", "40"), _fact("i", "-10"), _fact("paid", "-2"), _fact("other", "-2"), _fact("p", "-4")],
        bindings=[_bind("cfads", "c"), accrued, paid, second, _bind("principal", "p")],
        **common,
    )
    assert ambiguous["rows"][0]["value"] == Decimal("2.8571428571")

    outputs = _bind("interest", "out", primary=False, code="стр. 4123", sheet="Outputs")
    by_key = _bind("interest", "Итоги|18|Итоги!r1", primary=False, code="стр. 4123")
    ignored = coverage_ratio(
        metric="dscr",
        facts=[_fact("c", "40"), _fact("i", "-10"), _fact("out", "-2"), _fact("p", "-4")],
        bindings=[_bind("cfads", "c"), accrued, outputs, _bind("principal", "p")],
        **common,
    )
    assert ignored["rows"][0]["value"] == Decimal("2.8571428571")
    from_key = coverage_ratio(
        metric="dscr",
        facts=[_fact("c", "40"), _fact("i", "-10"), _fact("Итоги|18|Итоги!r1", "-2"), _fact("p", "-4")],
        bindings=[_bind("cfads", "c"), accrued, by_key, _bind("principal", "p")],
        **common,
    )
    assert from_key["rows"][0]["value"] == Decimal("2.8571428571")

    bare = _bind("interest", "bare", primary=False, code="4123")
    naked = coverage_ratio(
        metric="dscr",
        facts=[_fact("c", "40"), _fact("i", "-10"), _fact("bare", "-2"), _fact("p", "-4")],
        bindings=[_bind("cfads", "c"), accrued, bare, _bind("principal", "p")],
        **common,
    )
    assert naked["rows"][0]["value"] == Decimal("2.8571428571")

    kept = coverage_ratio(
        metric="dscr",
        facts=[_fact("c", "40"), _fact("i", "-10"), _fact("paid", "-2"), _fact("manual", "-4"), _fact("p", "-4")],
        bindings=[_bind("cfads", "c"), accrued, paid, _bind("interest_paid", "manual"), _bind("principal", "p")],
        **common,
    )
    assert "interest_paid" in kept["rows"][0]["components"]
    assert kept["rows"][0]["value"] == Decimal("5.0000000000")

    catalog = load_model_types()
    formula = catalog.composed["dscr.corporate_covenant"]
    stayed = covenant_dscr(
        facts=[_fact("e", "100"), _fact("t", "10"), _fact("x", "20"), _fact("i", "15"), _fact("paid", "1"), _fact("p", "5")],
        bindings=[
            _bind("ebitda", "e"),
            _bind("cash_taxes", "t"),
            _bind("capex", "x"),
            accrued,
            paid,
            _bind("principal", "p"),
        ],
        periods=[_year()],
        default=formula,
        concepts=frozenset({"ebitda", "cash_taxes", "capex", "interest", "principal", "dscr"}),
        money=frozenset({"ebitda", "cash_taxes", "capex", "interest", "principal"}),
        interest_order=catalog.interest_order,
        row_fallbacks=catalog.row_fallbacks,
    )
    assert stayed["rows"][0]["value"] == Decimal("3.5000000000")

    only_paid = dict(paid)
    only_paid["row_key"] = "paid"
    swapped = covenant_dscr(
        facts=[_fact("e", "100"), _fact("t", "10"), _fact("x", "20"), _fact("paid", "15"), _fact("p", "5")],
        bindings=[
            _bind("ebitda", "e"),
            _bind("cash_taxes", "t"),
            _bind("capex", "x"),
            only_paid,
            _bind("principal", "p"),
        ],
        periods=[_year()],
        default=formula,
        concepts=frozenset({"ebitda", "cash_taxes", "capex", "interest", "principal", "dscr"}),
        money=frozenset({"ebitda", "cash_taxes", "capex", "interest", "principal"}),
        interest_order=catalog.interest_order,
        row_fallbacks=catalog.row_fallbacks,
    )
    assert swapped["rows"][0]["value"] == Decimal("3.5000000000")
    assert any(item["code"] == "interest_basis_fallback" for item in swapped["warnings"])
