"""ГЧП, инвестиционный проект и сверка NPV/IRR со строкой книги (срез 3)."""

from __future__ import annotations

import json
from datetime import date, timedelta
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


def test_toll_road_npv_brings_the_first_filled_year_to_exponent_zero():
    """Шкала книги начинается с года 1. Интервал приведения получает степень 0.

    Опубликованный NPV дисконтировал годом как степенью. IRR от сдвига не меняется.
    """

    book = _load("toll_road.json")
    book = {**book, "discount_rate": book["wacc"]}
    npv, irr = _returns(book, field="fcff", book_npv=book["npv"], book_irr=book["project_irr"])
    rate = Decimal(book["wacc"])
    low = min(int(item["year"]) for item in book["years"])
    expected = sum(
        (Decimal(str(item["fcff"])) / (Decimal(1) + rate) ** (int(item["year"]) - low) for item in book["years"]),
        Decimal(0),
    )
    assert npv["rows"][0]["value"] == expected.quantize(Decimal("0.000001"))
    assert npv["warnings"][0]["code"] == "npv_book_mismatch"
    assert irr["warnings"] == []
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


_TABLE_21 = (
    "-100",
    "-48.40",
    "49.33",
    "49.66",
    "-25.61",
    "80.70",
    "81.15",
    "66.00",
    "-80",
)


def _metric(metric: str, flows, **kwargs):
    got = _quote(flows, **kwargs) if metric == "npv" else None
    if metric == "npv":
        return got
    catalog = _catalog()
    facts, periods, bindings = [], [], [_bind("project_fcf")]
    for index, value in flows:
        period = f"Y{index}"
        periods.append(_period(period, index))
        facts.append(_fact("project_fcf", period, value) if value is not None else {
            "row_key": "project_fcf",
            "axis_id": "a",
            "period_id": period,
            "normalized_value": value,
            "cell_id": f"a!{period}",
        })
    return select_ratio(
        metric,
        kwargs.get("variant"),
        _common(facts, bindings, periods),
        profile={},
        profile_ref=None,
        composed=catalog.composed,
        concepts=catalog.concepts,
        money=frozenset(),
    )


def test_vk477_table_2_1_npv_uses_powers_of_one_tenth_and_irr_is_published():
    flows = [(index, value) for index, value in enumerate(_TABLE_21)]
    npv = _quote(flows, rate="0.10")
    expected = sum((Decimal(value) / Decimal("1.10") ** index for index, value in enumerate(_TABLE_21)), Decimal(0))
    assert npv["status"] == "succeeded"
    assert npv["rows"][0]["value"] == expected.quantize(Decimal("0.000001"))
    assert npv["warnings"] == []
    irr = _metric("irr", flows)
    assert irr["status"] == "succeeded"
    assert abs(irr["rows"][0]["value"] - Decimal("0.1192")) <= Decimal("0.0001")


def test_quarter_dates_use_the_year_fraction_not_the_index():
    origin = date(2024, 3, 31)
    spans = (0, 91, 182, 273)
    flows = [(0, "-100"), (1, "0"), (2, "0"), (3, "110")]
    catalog = _catalog()
    facts, periods = [], []
    bindings = [_bind("project_fcf"), _bind("discount_rate")]
    for index, value in flows:
        period = f"Q{index}"
        end = origin + timedelta(days=spans[index])
        periods.append(
            {
                "axis_id": "a",
                "period_id": period,
                "period_index": index,
                "grain": "quarter",
                "timeline_id": "t",
                "period_start": end - timedelta(days=90),
                "period_end": end,
            }
        )
        facts.append(_fact("project_fcf", period, value))
    facts.append(_fact("discount_rate", "rate", "0.10", axis="p"))
    periods.append(_period("rate", None, axis="p"))
    got = select_ratio(
        "npv",
        None,
        _common(facts, bindings, periods),
        profile={},
        profile_ref=None,
        composed=catalog.composed,
        concepts=catalog.concepts,
        money=frozenset(),
    )
    manual = sum(
        (
            Decimal(value) / Decimal("1.10") ** (Decimal(spans[index]) / Decimal(365))
            for index, value in flows
        ),
        Decimal(0),
    )
    by_index = sum((Decimal(value) / Decimal("1.10") ** index for index, value in flows), Decimal(0))
    assert got["status"] == "succeeded"
    assert got["rows"][0]["value"] == manual.quantize(Decimal("0.000001"))
    assert got["rows"][0]["value"] != by_index.quantize(Decimal("0.000001"))


def test_subyear_grain_without_dates_is_not_computed():
    catalog = _catalog()
    facts, periods = [], []
    bindings = [_bind("project_fcf"), _bind("discount_rate")]
    for index, value in ((0, "-100"), (1, "60")):
        period = f"Q{index}"
        periods.append({**_period(period, index), "grain": "quarter"})
        facts.append(_fact("project_fcf", period, value))
    facts.append(_fact("discount_rate", "rate", "0.10", axis="p"))
    periods.append(_period("rate", None, axis="p"))
    got = select_ratio(
        "npv",
        None,
        _common(facts, bindings, periods),
        profile={},
        profile_ref=None,
        composed=catalog.composed,
        concepts=catalog.concepts,
        money=frozenset(),
    )
    assert got["status"] == "not_computed"
    assert got["warnings"][0]["code"] == "npv_subyear_without_dates"


def test_terminal_value_is_added_once_on_the_last_interval():
    catalog = _catalog()
    facts, periods = [], []
    bindings = [_bind("project_fcf"), _bind("discount_rate"), _bind("terminal_value")]
    for index, value in ((0, "-100"), (1, "60")):
        period = f"Y{index}"
        periods.append(_period(period, index))
        facts.append(_fact("project_fcf", period, value))
    facts.append(_fact("terminal_value", "Y1", "10"))
    facts.append(_fact("discount_rate", "rate", "0.10", axis="p"))
    periods.append(_period("rate", None, axis="p"))
    got = select_ratio(
        "npv",
        None,
        _common(facts, bindings, periods),
        profile={},
        profile_ref=None,
        composed=catalog.composed,
        concepts=catalog.concepts,
        money=frozenset(),
    )
    # −100 + 70 / 1.10
    assert got["rows"][0]["value"] == Decimal("-36.363636")
    assert "terminal_value" in got["rows"][0]["inputs"]


def test_two_terminal_values_are_not_summed():
    catalog = _catalog()
    facts, periods = [], []
    bindings = [_bind("project_fcf"), _bind("discount_rate"), _bind("terminal_value")]
    periods.append(_period("Y0", 0))
    facts.append(_fact("project_fcf", "Y0", "-100"))
    facts.append(_fact("project_fcf", "Y1", "60"))
    periods.append(_period("Y1", 1))
    facts.append(_fact("terminal_value", "Y1", "10"))
    facts.append(_fact("terminal_value", "Y1b", "12", axis="b"))
    periods.append(_period("Y1b", 1, axis="b"))
    facts.append(_fact("discount_rate", "rate", "0.10", axis="p"))
    periods.append(_period("rate", None, axis="p"))
    got = select_ratio(
        "npv",
        None,
        _common(facts, bindings, periods),
        profile={},
        profile_ref=None,
        composed=catalog.composed,
        concepts=catalog.concepts,
        money=frozenset(),
    )
    assert got["status"] == "not_computed"
    assert got["warnings"][0]["code"] == "terminal_value_not_unique"
    assert applicability(_catalog(), ("dcf_valuation",), "npv") == "optional"


def test_variable_rate_is_the_product_of_one_step_factors():
    catalog = _catalog()
    facts, periods = [], []
    bindings = [_bind("project_fcf"), _bind("discount_rate")]
    for index, value in ((0, "-100"), (1, "0"), (2, "121")):
        period = f"Y{index}"
        periods.append(_period(period, index))
        facts.append(_fact("project_fcf", period, value))
        if index:
            facts.append(_fact("discount_rate", period, "0.10" if index == 1 else "0.20"))
    got = select_ratio(
        "npv",
        None,
        _common(facts, bindings, periods),
        profile={},
        profile_ref=None,
        composed=catalog.composed,
        concepts=catalog.concepts,
        money=frozenset(),
    )
    # α0 = 1, α2 = 1 / (1.10 × 1.20)
    expected = Decimal("-100") + Decimal("121") / (Decimal("1.10") * Decimal("1.20"))
    assert got["rows"][0]["value"] == expected.quantize(Decimal("0.000001"))


def test_wacc_beats_discount_rate():
    catalog = _catalog()
    facts, periods = [], []
    bindings = [_bind("project_fcf"), _bind("wacc"), _bind("discount_rate")]
    periods.append(_period("Y0", 0))
    periods.append(_period("Y1", 1))
    facts.append(_fact("project_fcf", "Y0", "-100"))
    facts.append(_fact("project_fcf", "Y1", "60"))
    facts.append(_fact("wacc", "w", "0.20", axis="p"))
    facts.append(_fact("discount_rate", "d", "0.10", axis="p"))
    periods.append(_period("w", None, axis="p"))
    periods.append(_period("d", None, axis="p"))
    got = select_ratio(
        "npv",
        None,
        _common(facts, bindings, periods),
        profile={},
        profile_ref=None,
        composed=catalog.composed,
        concepts=catalog.concepts,
        money=frozenset(),
    )
    assert got["rows"][0]["value"] == (Decimal("-100") + Decimal("60") / Decimal("1.20")).quantize(Decimal("0.000001"))
    assert got["rows"][0]["inputs"][1] == "wacc"


def test_two_cumulative_sign_changes_refuse_irr_but_table_21_does_not():
    refused = _metric("irr", [(0, "-100"), (1, "150"), (2, "-70")])
    assert refused["status"] == "not_computed"
    assert refused["warnings"][0]["code"] == "irr_not_unique"
    npv = _quote([(0, "-100"), (1, "150"), (2, "-70")])
    assert npv["status"] == "succeeded"
    kept = _metric("irr", [(index, value) for index, value in enumerate(_TABLE_21)])
    assert kept["status"] == "succeeded"


def test_a_step_longer_than_a_year_warns_and_still_discounts_at_the_step_end():
    origin = date(2024, 12, 31)
    catalog = _catalog()
    facts, periods = [], []
    bindings = [_bind("project_fcf"), _bind("discount_rate")]
    for index, days, value in ((0, 0, "-100"), (1, 730, "121")):
        period = f"Y{index}"
        end = origin + timedelta(days=days)
        periods.append(
            {
                "axis_id": "a",
                "period_id": period,
                "period_index": index,
                "grain": "year",
                "period_start": end,
                "period_end": end,
            }
        )
        facts.append(_fact("project_fcf", period, value))
    facts.append(_fact("discount_rate", "rate", "0.10", axis="p"))
    periods.append(_period("rate", None, axis="p"))
    got = select_ratio(
        "npv",
        None,
        _common(facts, bindings, periods),
        profile={},
        profile_ref=None,
        composed=catalog.composed,
        concepts=catalog.concepts,
        money=frozenset(),
    )
    expected = Decimal("-100") + Decimal("121") / Decimal("1.10") ** (Decimal(730) / Decimal(365))
    assert got["rows"][0]["value"] == expected.quantize(Decimal("0.000001"))
    assert got["warnings"][0]["code"] == "intra_step_timing"


def _identity(variant, rows, *, convention="outflow_negative"):
    catalog = _catalog()
    facts, periods, bindings = [], [], []
    concepts = {name for row in rows for name in row}
    for concept in concepts:
        bindings.append(_bind(concept))
    for index, row in enumerate(rows):
        period = f"Y{index}"
        periods.append(_period(period, index))
        for concept, value in row.items():
            facts.append(_fact(concept, period, value))
    return select_ratio(
        "fcf_identity",
        variant,
        _common(facts, bindings, periods) | {"sign_convention": convention},
        profile={},
        profile_ref=None,
        composed=catalog.composed,
        concepts=catalog.concepts,
        money=frozenset(),
    )


def test_vk477_identity_normalizes_a_negative_capex_and_skips_interest():
    got = _identity(
        "vk477",
        [{"ocf": "100", "capex": "-30", "project_fcf": "70", "net_interest": "10"}],
    )
    assert got["status"] == "succeeded"
    assert got["warnings"] == []


def test_fcff_identity_matches_interest_after_tax_and_a_shift_warns_without_replacing_npv():
    row = {"ocf": "100", "capex": "30", "net_interest": "10", "tax_rate": "0.20", "project_fcf": "78"}
    assert _identity("fcff_after_interest", [row])["warnings"] == []
    shifted = {**row, "net_interest": "11"}
    warned = _identity("fcff_after_interest", [shifted])
    assert warned["warnings"][0]["code"] == "fcf_identity_mismatch"
    assert warned["rows"] == []
    catalog = _catalog()
    facts = [_fact("project_fcf", "Y0", "78"), _fact("project_fcf", "Y1", "0"), _fact("discount_rate", "rate", "0.10", axis="p")]
    periods = [_period("Y0", 0), _period("Y1", 1), _period("rate", None, axis="p")]
    npv = select_ratio(
        "npv",
        None,
        _common(facts, [_bind("project_fcf"), _bind("discount_rate")], periods),
        profile={},
        profile_ref=None,
        composed=catalog.composed,
        concepts=catalog.concepts,
        money=frozenset(),
    )
    assert npv["rows"][0]["inputs"] == ["project_fcf", "discount_rate"]
    assert "ocf" not in npv["rows"][0]["inputs"]


def test_unnamed_identity_variant_does_not_warn():
    got = _identity(None, [{"ocf": "100", "capex": "30", "project_fcf": "0"}])
    assert got["status"] == "succeeded"
    assert got["warnings"] == []
    assert got["rows"] == []


def test_full_lease_payment_does_not_match_the_interest_portion():
    # Строка собрана по процентной части 10. В сверку подставлен весь лизинговый платёж 40.
    built = {"ocf": "100", "capex": "30", "net_interest": "40", "tax_rate": "0.20", "project_fcf": "78"}
    got = _identity("fcff_after_interest", [built])
    assert got["warnings"][0]["code"] == "fcf_identity_mismatch"
    assert got["warnings"][0]["params"]["cells"]
