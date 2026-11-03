"""ГЧП, инвестиционный проект и сверка NPV/IRR со строкой книги (срез 3)."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from finance_analysis.domain.covenant import select_ratio
from finance_analysis.domain.metrics import coverage_ratio, quantize_ratio
from finance_analysis.domain.model_type import applicability, infer

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "ppp"
_NPV_TOL = Decimal("0.01")
_IRR_TOL = Decimal("1e-9")


def _catalog():
    from finance_analysis.application.model_types import load_model_types

    return load_model_types()


def _load(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def _bind(concept: str) -> dict:
    return {
        "effective_concept": concept,
        "row_key": concept,
        "is_primary": True,
        "status": "bound",
        "source": "inferred",
    }


def _fact(row: str, period: str, value: str, *, axis: str = "a") -> dict:
    return {
        "row_key": row,
        "axis_id": axis,
        "period_id": period,
        "normalized_value": value,
        "cell_id": f"{axis}!{period}",
    }


def _period(period: str, index: int | None, *, axis: str = "a") -> dict:
    item = {"axis_id": axis, "period_id": period, "grain": "year", "timeline_id": "t"}
    if index is not None:
        item["period_index"] = index
    return item


def _flows(years: list[dict], field: str) -> tuple[list[dict], list[dict]]:
    facts, periods = [], []
    for item in years:
        period = f"Y{item['year']}"
        periods.append(_period(period, int(item["year"])))
        facts.append(_fact("project_fcf", period, str(item[field])))
    return facts, periods


def _common(facts, bindings, periods) -> dict:
    return {
        "facts": facts,
        "bindings": bindings,
        "periods": periods,
        "period_phase": {},
        "explicit_phases": False,
        "sign_convention": "outflow_negative",
        "marker_class": None,
        "absent": frozenset(),
    }


def _returns(book: dict, *, field: str, book_npv: str | None, book_irr: str | None):
    catalog = _catalog()
    facts, periods = _flows(book["years"], field)
    bindings = [_bind("project_fcf"), _bind("discount_rate")]
    facts.append(_fact("discount_rate", "rate", book["discount_rate"], axis="p"))
    periods.append(_period("rate", None, axis="p"))
    if book_npv is not None:
        bindings.append(_bind("npv"))
        facts.append(_fact("npv", "npv", book_npv, axis="p"))
        periods.append(_period("npv", None, axis="p"))
    if book_irr is not None:
        bindings.append(_bind("irr"))
        facts.append(_fact("irr", "irr", book_irr, axis="p"))
        periods.append(_period("irr", None, axis="p"))
    common = _common(facts, bindings, periods)
    npv = select_ratio(
        "npv", None, common, profile={}, profile_ref=None, composed=catalog.composed, concepts=catalog.concepts, money=frozenset()
    )
    irr = select_ratio(
        "irr", None, common, profile={}, profile_ref=None, composed=catalog.composed, concepts=catalog.concepts, money=frozenset()
    )
    return npv, irr


def test_grantor_and_debt_service_are_a_ppp_hybrid():
    catalog = _catalog()
    got = infer(
        catalog,
        bound=frozenset({"grantor_payment", "cfads", "debt_service"}),
        sheets=frozenset({"Cash Flow"}),
        accept=0.6,
        gap=0.15,
    )
    assert got.confident is True
    assert got.labels == ("ppp_concession", "project_finance")
    assert got.primary == "ppp_concession"
    assert catalog.types["ppp_concession"].variants["dscr"] == "pf"
    assert applicability(catalog, got.labels, "dscr") == "required"
    assert applicability(catalog, got.labels, "npv") == "optional"


def test_cited_npv_without_debt_service_is_an_investment_project():
    catalog = _catalog()
    got = infer(
        catalog,
        bound=frozenset({"npv", "irr", "discount_rate", "project_fcf"}),
        sheets=frozenset({"Base Model"}),
        accept=0.6,
        gap=0.15,
    )
    assert got.confident is True
    assert got.primary == "investment_project"
    assert got.scores["investment_project"] == 1.0
    assert applicability(catalog, got.labels, "npv") == "required"
    assert applicability(catalog, got.labels, "dscr") == "not_applicable"


def test_project_finance_book_that_also_has_npv_stays_project_finance():
    catalog = _catalog()
    got = infer(
        catalog,
        bound=frozenset({"cfads", "debt_service", "npv", "irr", "discount_rate"}),
        sheets=frozenset({"Debt"}),
        accept=0.6,
        gap=0.15,
    )
    assert got.primary == "project_finance"
    assert got.scores["investment_project"] == 0.0
    assert got.scores["ppp_concession"] == 0.0
    assert applicability(catalog, got.labels, "npv") == "not_applicable"


def test_a_three_statement_book_with_npv_stays_corporate():
    catalog = _catalog()
    got = infer(
        catalog,
        bound=frozenset({"npv", "irr", "discount_rate", "ebitda", "interest"}),
        sheets=frozenset({"Income statement", "Balance sheet", "Cash flow"}),
        accept=0.6,
        gap=0.15,
    )
    assert got.confident is True
    assert got.primary == "corporate"
    assert got.labels == ("corporate",)
    assert applicability(catalog, got.labels, "npv") == "not_applicable"


def test_ppp_and_escrow_keep_their_type_beside_an_investment_score():
    catalog = _catalog()
    ppp = infer(
        catalog,
        bound=frozenset({"grantor_payment", "npv", "irr", "discount_rate"}),
        sheets=frozenset(),
        accept=0.6,
        gap=0.15,
    )
    escrow = infer(
        catalog,
        bound=frozenset({"escrow_balance", "npv", "irr", "discount_rate"}),
        sheets=frozenset(),
        accept=0.6,
        gap=0.15,
    )
    assert ppp.confident is True and ppp.primary == "ppp_concession" and ppp.labels == ("ppp_concession",)
    assert escrow.confident is True and escrow.primary == "development_escrow"


def test_an_empty_book_does_not_score_investment_just_because_debt_is_absent():
    catalog = _catalog()
    got = infer(catalog, bound=frozenset(), sheets=frozenset({"Model"}), accept=0.6, gap=0.15)
    assert got.scores["investment_project"] == 0.0
    assert got.confident is False


def test_toll_road_min_dscr_matches_the_published_minimum():
    book = _load("toll_road.json")
    facts, bindings, periods = [], [], []
    for item in book["years"]:
        period = f"Y{item['year']}"
        periods.append(_period(period, int(item["year"])))
        facts.append(_fact("cfads", period, str(item["cfads"])))
        facts.append(_fact("debt_service", period, str(item["debt_service"])))
    bindings.extend([_bind("cfads"), _bind("debt_service")])
    got = coverage_ratio(
        metric="dscr",
        facts=facts,
        bindings=bindings,
        periods=periods,
        period_phase={},
        explicit_phases=False,
    )
    computed = [row["value"] for row in got["rows"] if row["status"] == "computed"]
    lowest = min(computed)
    assert lowest == quantize_ratio(Decimal(book["min_dscr"]))
    assert round(lowest, 2) == Decimal("0.88")
    assert len(computed) == sum(1 for item in book["years"] if Decimal(item["debt_service"]) != 0)


def test_port_npv_and_irr_match_the_book():
    book = _load("port.json")
    npv, irr = _returns(book, field="project_fcf", book_npv=book["npv"], book_irr=book["project_irr"])
    assert npv["status"] == "succeeded"
    assert irr["status"] == "succeeded"
    assert npv["warnings"] == []
    assert irr["warnings"] == []
    assert abs(npv["rows"][0]["value"] - Decimal(book["npv"])) <= _NPV_TOL
    assert abs(irr["rows"][0]["value"] - Decimal(book["project_irr"])) <= _IRR_TOL


def test_toll_road_npv_and_irr_use_the_year_index():
    book = _load("toll_road.json")
    book = {**book, "discount_rate": book["wacc"]}
    npv, irr = _returns(book, field="fcff", book_npv=book["npv"], book_irr=book["project_irr"])
    assert npv["warnings"] == []
    assert irr["warnings"] == []
    assert abs(npv["rows"][0]["value"] - Decimal(book["npv"])) <= _NPV_TOL
    assert abs(irr["rows"][0]["value"] - Decimal(book["project_irr"])) <= _IRR_TOL


def _quote(flows: list[tuple[int, str | None]], *, rate: str = "0.10", rates: list[str] | None = None, book: list[str] | None = None):
    catalog = _catalog()
    facts, periods = [], []
    bindings = [_bind("project_fcf"), _bind("discount_rate")]
    for index, value in flows:
        period = f"Y{index}"
        periods.append(_period(period, index))
        facts.append(
            {
                "row_key": "project_fcf",
                "axis_id": "a",
                "period_id": period,
                "normalized_value": value,
                "cell_id": f"a!{period}",
            }
        )
    for number, item in enumerate(rates if rates is not None else [rate]):
        period = f"R{number}"
        facts.append(_fact("discount_rate", period, item, axis="p"))
        periods.append(_period(period, None, axis="p"))
    if book is not None:
        bindings.append(_bind("npv"))
        for number, item in enumerate(book):
            period = f"B{number}"
            facts.append(_fact("npv", period, item, axis="p"))
            periods.append(_period(period, None, axis="p"))
    return select_ratio(
        "npv",
        None,
        _common(facts, bindings, periods),
        profile={},
        profile_ref=None,
        composed=catalog.composed,
        concepts=catalog.concepts,
        money=frozenset(),
    )


def test_an_empty_period_outside_the_filled_span_is_ignored():
    plain = _quote([(0, "-100"), (1, "60")])
    edged = _quote([(0, None), (1, "-100"), (2, "60"), (3, None)])
    same_indexes = _quote([(1, "-100"), (2, "60")])
    assert plain["status"] == "succeeded"
    assert plain["rows"][0]["value"] == Decimal("-45.454545")
    assert edged["warnings"] == []
    assert edged["rows"][0]["value"] == same_indexes["rows"][0]["value"]


def test_a_hole_inside_the_span_is_not_computed():
    got = _quote([(0, "-100"), (1, None), (2, "60")])
    assert got["status"] == "not_computed"
    assert got["rows"] == []
    assert got["needs_input"] == []
    assert got["warnings"][0]["code"] == "project_return_incomplete"


def test_two_discount_rates_are_not_computed():
    got = _quote([(0, "-100"), (1, "60")], rates=["0.10", "0.12"])
    assert got["status"] == "not_computed"
    assert got["rows"] == []
    assert got["needs_input"] == []
    assert got["warnings"][0]["code"] == "discount_rate_not_unique"


def test_one_matching_cell_on_the_book_row_does_not_warn():
    got = _quote([(0, "-100"), (1, "60")], book=["10", "-45.454545"])
    assert got["rows"][0]["value"] == Decimal("-45.454545")
    assert got["warnings"] == []


def test_a_book_row_with_no_matching_cell_warns_once():
    got = _quote([(0, "-100"), (1, "60")], book=["10", "11"])
    assert got["rows"][0]["status"] == "computed"
    assert [item["code"] for item in got["warnings"]] == ["npv_book_mismatch"]
    assert got["warnings"][0]["params"]["model"] in {"10", "11"}


def test_book_row_that_disagrees_is_a_warning():
    book = _load("port.json")
    npv, irr = _returns(book, field="project_fcf", book_npv="100", book_irr="0.5")
    assert npv["warnings"][0]["code"] == "npv_book_mismatch"
    assert irr["warnings"][0]["code"] == "irr_book_mismatch"
    assert npv["rows"][0]["status"] == "computed"
    assert irr["rows"][0]["status"] == "computed"
