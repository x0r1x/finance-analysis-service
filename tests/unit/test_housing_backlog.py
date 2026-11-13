"""Отложенный набор: номинальный LLCR, ставка эскроу, комиссии, свопы, min/avg/ADSCR.

ПКП отдельной метрикой не заводится. Вариант pf и жилищный DSCR без флага не меняются.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from finance_analysis.application.catalog import load_catalog
from finance_analysis.application.financial_catalog import load_financial_catalog
from finance_analysis.application.model_types import load_model_types
from finance_analysis.application.report import render_markdown
from finance_analysis.domain.housing_cover import (
    dispatch_cover,
    housing_cover,
    scale_error,
    use_housing_cover,
)
from finance_analysis.domain.housing_dscr import housing_dscr
from finance_analysis.domain.metrics import quantize_ratio
from finance_analysis.domain.model_type import applicability


def _bind(concept: str, row: str, label: str, **extra) -> dict:
    item = {
        "effective_concept": concept,
        "row_key": row,
        "is_primary": extra.pop("is_primary", True),
        "status": "bound",
        "source": "inferred",
        "label": label,
        "label_path_text": extra.pop("label_path_text", label),
    }
    item.update(extra)
    return item


def _fact(row: str, period: str, value) -> dict:
    return {
        "row_key": row,
        "axis_id": "a",
        "period_id": period,
        "value": value,
        "normalized_value": value,
        "cell_id": f"{row}!{period}",
    }


def _period(period: str, index: int, *, grain: str = "quarter", start: date | None = None, end: date | None = None) -> dict:
    item = {
        "period_id": period,
        "axis_id": "a",
        "grain": grain,
        "period_index": index,
        "timeline_id": "t",
    }
    if start is not None:
        item["period_start"] = start
        item["period_end"] = end
    return item


def _quarters() -> list[dict]:
    spans = (
        ("Q1", 1, date(2024, 1, 1), date(2024, 3, 31)),
        ("Q2", 2, date(2024, 4, 1), date(2024, 6, 30)),
        ("Q3", 3, date(2024, 7, 1), date(2024, 9, 30)),
        ("Q4", 4, date(2024, 10, 1), date(2024, 12, 31)),
    )
    return [_period(name, index, start=start, end=end) for name, index, start, end in spans]


def _cash(periods: list[str], numbers: dict[str, list]) -> tuple[list[dict], list[dict]]:
    roles = (
        ("cfo_statement", "cfo", "Сальдо денежных потоков от текущих операций"),
        ("cfi_statement", "cfi", "Сальдо денежных потоков от инвестиционных операций"),
        ("financing_inflows", "in", "Поступления по финансовой деятельности"),
        ("senior_principal", "prin", "Погашение основного долга по несубординированным кредитам"),
        ("senior_interest_paid", "intr", "Уплаченные проценты по несубординированным кредитам"),
    )
    bindings = [_bind(concept, row, label) for concept, row, label in roles]
    facts = []
    for concept, row, _label in roles:
        for period, value in zip(periods, numbers[concept], strict=True):
            if value is not None:
                facts.append(_fact(row, period, value))
    return bindings, facts


def _cover(metric: str, bindings, facts, periods, **extra):
    return housing_cover(
        metric,
        facts=facts,
        bindings=bindings,
        periods=periods,
        sign_convention="outflow_negative",
        absent=frozenset(),
        profile=extra.pop("profile", None),
        variant=extra.pop("variant", None),
        direction=extra.pop("direction", "lookback"),
    )


def test_pf_cover_is_not_routed_without_a_flag():
    assert use_housing_cover("llcr", None, "pf", None) is False
    assert use_housing_cover("dscr_min", None, "pf", None) is False
    assert use_housing_cover("adscr", None, "pf", None) is False
    assert use_housing_cover("dscr_avg", None, "pf", {"dscr_definition": {"variant": "pf"}}) is False
    assert dispatch_cover(
        "llcr",
        metric_variant=None,
        dscr_variant="pf",
        profile=None,
        basis="period_end",
        direction="lookback",
        common={"facts": [], "bindings": [], "periods": [], "sign_convention": "outflow_negative", "absent": frozenset()},
    ) is None
    assert use_housing_cover("llcr", "cbr590", "housing", None) is True
    assert use_housing_cover("dscr_min", None, "housing", None) is True
    assert use_housing_cover("escrow_blended_rate", None, "pf", None) is True


def test_cbr590_sums_nominal_cash_and_refuses_a_missing_guarantee():
    periods = [_period("Q1", 1), _period("Q2", 2)]
    bindings, facts = _cash(
        ["Q1", "Q2"],
        {
            "cfo_statement": ["100", "80"],
            "cfi_statement": ["0", "0"],
            "financing_inflows": ["0", "0"],
            "senior_principal": ["40", "32"],
            "senior_interest_paid": ["10", "8"],
        },
    )
    missing = _cover("llcr", bindings, facts, periods, variant="cbr590")
    assert missing["rows"][0]["status"] == "not_computed"
    assert missing["rows"][0]["value"] is None
    assert "guaranteed_funds" in missing["rows"][0]["missing"]
    assert missing["rows"][0]["variant"] == "cbr590"
    assert "не универсальный DSCR" in missing["rows"][0]["methodology"]
    assert "NPV" in missing["rows"][0]["methodology"]

    named = _cover(
        "llcr",
        bindings,
        facts,
        periods,
        profile={"guaranteed_funds_none": True},
    )
    assert named["rows"][0]["value"] == quantize_ratio(Decimal(180) / Decimal(90))
    assert named["rows"][0]["variant"] == "cbr590"

    hole = _cash(
        ["Q1", "Q2"],
        {
            "cfo_statement": ["100", "80"],
            "cfi_statement": [None, "0"],
            "financing_inflows": ["0", "0"],
            "senior_principal": ["40", "32"],
            "senior_interest_paid": ["10", "8"],
        },
    )
    blocked = _cover("llcr", *hole, periods, profile={"guaranteed_funds_none": True})
    assert blocked["rows"][0]["value"] is None
    assert "cfi_statement" in blocked["rows"][0]["missing"]

    stock = bindings + [_bind("guaranteed_funds", "g", "Иные деньги, гарантированно доступные для целевого кредита")]
    stock_facts = facts + [_fact("g", "Q2", "20")]
    got = _cover("llcr", stock, stock_facts, periods, variant="cbr590")
    assert got["rows"][0]["status"] == "computed"
    assert got["rows"][0]["value"] == quantize_ratio(Decimal(200) / Decimal(90))
    assert got["rows"][0]["components"]["guaranteed_funds"] == "20"

    escrow = bindings + [
        _bind("escrow_balance", "e", "Остаток на счетах эскроу"),
        _bind("debt_outstanding", "d", "Остаток долга"),
    ]
    substituted = _cover(
        "llcr",
        escrow,
        facts + [_fact("e", "Q2", "999"), _fact("d", "Q2", "999")],
        periods,
        profile={"guaranteed_funds_none": False},
    )
    assert substituted["rows"][0]["value"] is None
    assert "999" not in substituted["rows"][0]["components"].values()


def test_cbr590_keeps_a_negative_numerator_and_a_zero_denominator():
    periods = [_period("Q1", 1)]
    negative, facts = _cash(
        ["Q1"],
        {
            "cfo_statement": ["-30"],
            "cfi_statement": ["0"],
            "financing_inflows": ["0"],
            "senior_principal": ["10"],
            "senior_interest_paid": ["0"],
        },
    )
    got = _cover("llcr", negative, facts, periods, profile={"guaranteed_funds_none": True})
    assert got["rows"][0]["value"] == quantize_ratio(Decimal(-30) / Decimal(10))
    zero, zero_facts = _cash(
        ["Q1"],
        {
            "cfo_statement": ["10"],
            "cfi_statement": ["0"],
            "financing_inflows": ["0"],
            "senior_principal": ["0"],
            "senior_interest_paid": ["0"],
        },
    )
    empty = _cover("llcr", zero, zero_facts, periods, profile={"guaranteed_funds_none": True})
    assert empty["rows"][0]["status"] == "no_debt_service"
    assert empty["rows"][0]["value"] is None


def test_domrf_uses_the_limit_plus_interest_and_not_outstanding():
    periods = [_period("Q1", 1), _period("Q2", 2)]
    bindings, facts = _cash(
        ["Q1", "Q2"],
        {
            "cfo_statement": ["100", "80"],
            "cfi_statement": ["0", "0"],
            "financing_inflows": ["0", "0"],
            "senior_principal": ["40", "32"],
            "senior_interest_paid": ["10", "8"],
        },
    )
    outstanding = bindings + [_bind("debt_outstanding", "d", "Остаток долга")]
    refused = _cover(
        "llcr",
        outstanding,
        facts + [_fact("d", "Q2", "70")],
        periods,
        variant="domrf",
    )
    assert refused["rows"][0]["value"] is None
    assert "credit_limit" in refused["rows"][0]["missing"]
    assert "70" not in refused["rows"][0]["components"].values()

    limited = outstanding + [_bind("credit_limit", "lim", "Лимит кредита проектного финансирования")]
    got = _cover("llcr", limited, facts + [_fact("d", "Q2", "70"), _fact("lim", "Q2", "100")], periods, variant="domrf")
    assert got["rows"][0]["value"] == quantize_ratio(Decimal(180) / Decimal(118))
    assert got["rows"][0]["variant"] == "domrf"
    assert "credit_limit" in got["rows"][0]["composition"]
    assert "гарантированно" not in got["rows"][0]["composition"]
    text = render_markdown(
        {"analysis_id": "a", "status": "succeeded", "builder_ref": {}, "versions": {}, "result_data": {"ratios": got["rows"]}}
    )
    assert "variant: domrf" in text
    assert "не универсальный DSCR" in text


def test_rate_scale_is_profile_math_and_does_not_invent_a_ladder():
    periods = [_period("Q1", 1)]
    bindings = [
        _bind("debt_outstanding", "d", "Остаток долга"),
        _bind("escrow_balance", "e", "Остаток на счетах эскроу"),
    ]
    bare = _cover("escrow_blended_rate", bindings, [_fact("d", "Q1", "100"), _fact("e", "Q1", "40")], periods)
    assert bare["rows"][0]["status"] == "not_computed"
    assert bare["rows"][0]["reason"] == "rate_scale_unconfigured"
    assert bare["rows"][0]["value"] is None

    scale = {"base_rate": "0.12", "special_rate": "0.05"}
    blended = _cover(
        "escrow_blended_rate",
        bindings,
        [_fact("d", "Q1", "100"), _fact("e", "Q1", "40")],
        periods,
        profile={"escrow_rate_scale": scale},
    )
    assert blended["rows"][0]["value"] == quantize_ratio(Decimal("9.2") / Decimal(100))
    assert "DSCR" not in blended["rows"][0]["methodology"]

    covered = _cover(
        "escrow_blended_rate",
        bindings,
        [_fact("d", "Q1", "100"), _fact("e", "Q1", "200")],
        periods,
        profile={"escrow_rate_scale": scale},
    )
    assert covered["rows"][0]["value"] == quantize_ratio(Decimal("0.05"))

    rung = _cover(
        "escrow_blended_rate",
        bindings,
        [_fact("d", "Q1", "100"), _fact("e", "Q1", "160")],
        periods,
        profile={"escrow_rate_scale": {**scale, "rungs": [{"coverage": "1.5", "rate": "0.03"}]}},
    )
    assert rung["rows"][0]["value"] == quantize_ratio(Decimal("0.03"))
    below = _cover(
        "escrow_blended_rate",
        bindings,
        [_fact("d", "Q1", "100"), _fact("e", "Q1", "40")],
        periods,
        profile={"escrow_rate_scale": {**scale, "rungs": [{"coverage": "1.5", "rate": "0.03"}]}},
    )
    assert below["rows"][0]["value"] == quantize_ratio(Decimal("9.2") / Decimal(100))

    absent = _cover(
        "escrow_blended_rate",
        bindings,
        [_fact("d", "Q1", "100")],
        periods,
        profile={"escrow_rate_scale": scale},
    )
    assert absent["rows"][0]["value"] is None
    assert "escrow_balance" in absent["rows"][0]["missing"]
    zero = _cover(
        "escrow_blended_rate",
        bindings,
        [_fact("d", "Q1", "0"), _fact("e", "Q1", "0")],
        periods,
        profile={"escrow_rate_scale": scale},
    )
    assert zero["rows"][0]["status"] == "no_debt_service"
    assert zero["rows"][0]["value"] is None


def test_fees_and_swaps_stay_out_until_a_senior_flag_is_set():
    periods = [_period("Q1", 1)]
    bindings, facts = _cash(
        ["Q1"],
        {
            "cfo_statement": ["20"],
            "cfi_statement": ["0"],
            "financing_inflows": ["0"],
            "senior_principal": ["8"],
            "senior_interest_paid": ["2"],
        },
    )
    fee = _bind(
        "senior_fees",
        "fee",
        "Комиссии по несубординированным кредитам",
        label_path_text="Senior Debt › Комиссии по несубординированным кредитам",
    )
    junior = _bind(
        "senior_fees",
        "jfee",
        "Комиссия по займу участника",
        label_path_text="Заём участника › Комиссия по займу участника",
    )
    mixed = _bind(
        "senior_fees",
        "mfee",
        "Комиссия по кредитам",
        label_path_text="Комиссия по несубординированному и субординированному кредиту",
    )
    off = housing_dscr(
        facts=facts + [_fact("fee", "Q1", "5")],
        bindings=bindings + [fee],
        periods=periods,
    )
    assert off["rows"][0]["value"] == Decimal("2.0000000000")
    assert "senior_fees" not in off["rows"][0]["components"]

    on = housing_dscr(
        facts=facts + [_fact("fee", "Q1", "5")],
        bindings=bindings + [fee],
        periods=periods,
        profile={"include_senior_fees": True},
    )
    assert on["rows"][0]["value"] == quantize_ratio(Decimal(20) / Decimal(15))
    assert on["rows"][0]["components"]["senior_fees"] == "5"
    assert "senior_fees" in on["rows"][0]["composition"]

    confirmed = housing_dscr(
        facts=facts + [_fact("fee", "Q1", "0")],
        bindings=bindings + [fee],
        periods=periods,
        profile={"include_senior_fees": True},
    )
    assert confirmed["rows"][0]["value"] == Decimal("2.0000000000")
    assert confirmed["rows"][0]["components"]["senior_fees"] == "0"

    only_junior = housing_dscr(
        facts=facts + [_fact("jfee", "Q1", "5")],
        bindings=bindings + [junior],
        periods=periods,
        profile={"include_senior_fees": True},
    )
    assert only_junior["rows"][0]["value"] is None
    assert "senior_fees" in only_junior["rows"][0]["missing"]
    assert "5" not in only_junior["rows"][0]["components"].values()

    aggregate = housing_dscr(
        facts=facts + [_fact("mfee", "Q1", "5")],
        bindings=bindings + [mixed],
        periods=periods,
        profile={"include_senior_fees": True},
    )
    assert aggregate["rows"][0]["value"] is None
    assert aggregate["rows"][0]["reason"] == "seniority_unsplit"

    swap = _bind(
        "senior_swaps",
        "swap",
        "Чистые платежи по свопу несубординированного долга",
        label_path_text="Senior Debt › Чистые платежи по свопу несубординированного долга",
    )
    quiet = housing_dscr(facts=facts, bindings=bindings + [swap], periods=periods)
    assert quiet["rows"][0]["value"] == Decimal("2.0000000000")
    missing_swap = housing_dscr(
        facts=facts,
        bindings=bindings + [swap],
        periods=periods,
        profile={"include_senior_swaps": True},
    )
    assert missing_swap["rows"][0]["value"] is None
    assert "senior_swaps" in missing_swap["rows"][0]["missing"]
    paid = housing_dscr(
        facts=facts + [_fact("swap", "Q1", "1")],
        bindings=bindings + [swap],
        periods=periods,
        profile={"include_senior_swaps": True},
    )
    assert paid["rows"][0]["value"] == quantize_ratio(Decimal(20) / Decimal(11))


def test_housing_min_avg_and_adscr_fail_closed():
    periods = _quarters()
    names = [item["period_id"] for item in periods]
    bindings, facts = _cash(
        names,
        {
            "cfo_statement": ["100", "80", "60", "40"],
            "cfi_statement": ["0", "0", "0", "0"],
            "financing_inflows": ["0", "0", "0", "0"],
            "senior_principal": ["40", "32", "30", "32"],
            "senior_interest_paid": ["10", "8", "10", "8"],
        },
    )
    lowest = _cover("dscr_min", bindings, facts, periods, variant="housing")
    assert lowest["rows"][0]["value"] == quantize_ratio(Decimal(40) / Decimal(40))
    assert lowest["rows"][0]["variant"] == "housing"
    assert "не универсальный DSCR" in lowest["rows"][0]["methodology"]

    average = _cover("dscr_avg", bindings, facts, periods, variant="housing")
    by_reduction = {row["reduction"]: row for row in average["rows"]}
    assert set(by_reduction) == {"mean_of_ratios", "ratio_of_sums"}
    assert by_reduction["ratio_of_sums"]["value"] == quantize_ratio(Decimal(280) / Decimal(170))
    assert all(row["variant"] == "housing" for row in average["rows"])

    annual = _cover("adscr", bindings, facts, periods, variant="housing")
    by_period = {row["period_id"]: row for row in annual["rows"]}
    assert by_period["Q1"]["reason"] == "partial_window"
    assert by_period["Q1"]["value"] is None
    assert by_period["Q4"]["value"] == quantize_ratio(Decimal(280) / Decimal(170))
    assert by_period["Q4"]["variant"] == "housing"

    hole_bindings, hole_facts = _cash(
        names,
        {
            "cfo_statement": ["100", "80", "60", "40"],
            "cfi_statement": ["0", None, "0", "0"],
            "financing_inflows": ["0", "0", "0", "0"],
            "senior_principal": ["40", "32", "30", "32"],
            "senior_interest_paid": ["10", "8", "10", "8"],
        },
    )
    blocked = _cover("dscr_min", hole_bindings, hole_facts, periods, variant="housing")
    assert blocked["rows"][0]["value"] is None
    assert blocked["rows"][0]["status"] == "not_computed"
    blocked_avg = _cover("dscr_avg", hole_bindings, hole_facts, periods, variant="housing")
    assert all(row["value"] is None for row in blocked_avg["rows"])
    blocked_year = _cover("adscr", hole_bindings, hole_facts, periods, variant="housing")
    assert blocked_year["rows"][3]["value"] is None

    idle_bindings, idle_facts = _cash(
        names,
        {
            "cfo_statement": ["100", "80", "60", "40"],
            "cfi_statement": ["0", "0", "0", "0"],
            "financing_inflows": ["0", "0", "0", "0"],
            "senior_principal": ["40", "0", "30", "32"],
            "senior_interest_paid": ["10", "0", "10", "8"],
        },
    )
    skipped = _cover("dscr_min", idle_bindings, idle_facts, periods, variant="housing")
    assert skipped["rows"][0]["value"] == quantize_ratio(Decimal(40) / Decimal(40))
    assert "Q2" in skipped["rows"][0]["excluded_periods"]
    window = _cover("adscr", idle_bindings, idle_facts, periods, variant="housing")
    assert window["rows"][3]["value"] == quantize_ratio(Decimal(280) / Decimal(130))


def test_year_grain_does_not_invent_an_adscr_window():
    periods = [_period("Y", 1, grain="year", start=date(2024, 1, 1), end=date(2024, 12, 31))]
    bindings, facts = _cash(
        ["Y"],
        {
            "cfo_statement": ["100"],
            "cfi_statement": ["0"],
            "financing_inflows": ["0"],
            "senior_principal": ["40"],
            "senior_interest_paid": ["10"],
        },
    )
    got = _cover("adscr", bindings, facts, periods, variant="housing")
    assert got["rows"][0]["reason"] == "adscr_not_applicable"
    assert got["rows"][0]["value"] is None


def test_pkp_is_not_invented_and_escrow_types_select_the_new_variants():
    catalog = load_financial_catalog()
    assert "pkp" not in catalog.indicators
    assert "escrow_coverage" in catalog.indicators
    assert "escrow_blended_rate" in catalog.indicators
    types = load_model_types()
    assert applicability(types, ("development_escrow",), "dscr_min") == "optional"
    assert types.types["development_escrow"].variants["dscr_min"] == "housing"
    assert types.types["development_escrow"].variants["adscr"] == "housing"
    assert types.types["development_escrow"].variants["llcr"] == "cbr590"
    assert applicability(types, ("development_escrow",), "escrow_blended_rate") == "optional"
    assert "llcr" not in types.types["project_finance"].variants or types.types["project_finance"].variants.get("llcr") != "cbr590"
    assert types.types["project_finance"].variants["dscr"] == "pf"
    package = load_catalog()
    assert {"guaranteed_funds", "credit_limit", "senior_fees", "senior_swaps"} <= set(package.concepts)


def test_profile_variant_selects_domrf_without_touching_pf():
    periods = [_period("Q1", 1)]
    bindings, facts = _cash(
        ["Q1"],
        {
            "cfo_statement": ["20"],
            "cfi_statement": ["0"],
            "financing_inflows": ["0"],
            "senior_principal": ["8"],
            "senior_interest_paid": ["2"],
        },
    )
    bindings.append(_bind("credit_limit", "lim", "Лимит кредита проектного финансирования"))
    facts.append(_fact("lim", "Q1", "50"))
    got = _cover("llcr", bindings, facts, periods, profile={"llcr_definition": {"variant": "domrf"}})
    assert got["rows"][0]["variant"] == "domrf"
    assert got["rows"][0]["value"] == quantize_ratio(Decimal(20) / Decimal(52))


def _senior_interest(row: str = "intr") -> dict:
    return _bind(
        "senior_interest_paid",
        row,
        "Уплаченные проценты по несубординированным кредитам",
        evidence={"line_code": "стр. 4123"},
        label_path_text="Senior Debt › Уплаченные проценты по несубординированным кредитам",
    )


def test_llcr_does_not_inherit_periodic_dscr_flags():
    periods = [_period("Q1", 1), _period("Q2", 2)]
    bindings, facts = _cash(
        ["Q1", "Q2"],
        {
            "cfo_statement": ["20", "30"],
            "cfi_statement": ["0", "0"],
            "financing_inflows": ["0", "0"],
            "senior_principal": ["8", "6"],
            "senior_interest_paid": ["2", "4"],
        },
    )
    bindings = [row for row in bindings if row["effective_concept"] != "senior_interest_paid"]
    bindings.append(_senior_interest())
    bindings.append(
        _bind(
            "senior_fees",
            "fee",
            "Комиссии по несубординированным кредитам",
            label_path_text="Senior Debt › Комиссии по несубординированным кредитам",
        )
    )
    bindings.append(
        _bind(
            "senior_swaps",
            "swap",
            "Чистые платежи по свопу несубординированного долга",
            label_path_text="Senior Debt › Чистые платежи по свопу несубординированного долга",
        )
    )
    plain = {"guaranteed_funds_none": True}
    flagged = {
        "guaranteed_funds_none": True,
        "interest_addback": True,
        "include_senior_fees": True,
        "include_senior_swaps": True,
    }
    housing_off = housing_dscr(facts=facts, bindings=bindings, periods=periods, profile={"interest_addback": False})
    housing_on = housing_dscr(facts=facts, bindings=bindings, periods=periods, profile={"interest_addback": True})
    assert housing_on["rows"][0]["value"] != housing_off["rows"][0]["value"]
    base = _cover("llcr", bindings, facts, periods, variant="cbr590", profile=plain)
    touched = _cover("llcr", bindings, facts, periods, variant="cbr590", profile=flagged)
    assert base["rows"][0]["status"] == "computed"
    assert touched["rows"][0]["value"] == base["rows"][0]["value"]
    assert touched["rows"][0]["status"] == "computed"
    assert "interest_addback" not in touched["rows"][0]["components"]
    assert "senior_fees" not in touched["rows"][0]["components"]
    assert touched["rows"][0]["definition"] == "llcr.cbr590@service-v1"
    assert "не воспроизведение закрытой модели банка" in touched["rows"][0]["methodology"]
    limit = bindings + [_bind("credit_limit", "lim", "Лимит кредита проектного финансирования")]
    limited = facts + [_fact("lim", "Q2", "40")]
    domrf_off = _cover("llcr", limit, limited, periods, variant="domrf", profile={"interest_addback": False})
    domrf_on = _cover("llcr", limit, limited, periods, variant="domrf", profile=flagged)
    assert domrf_on["rows"][0]["value"] == domrf_off["rows"][0]["value"]
    assert domrf_on["rows"][0]["definition"] == "llcr.domrf@service-v1"
    assert housing_on["rows"][0]["definition"] == "dscr.housing@service-v1"


def test_rate_scale_rejects_a_weak_profile():
    assert scale_error({"base_rate": "0", "special_rate": "1"}) is None
    assert scale_error({"base_rate": "1", "special_rate": "0", "rungs": [{"coverage": "0", "rate": "1"}]}) is None
    assert scale_error({"base_rate": "-0.01", "special_rate": "0.05"}) is not None
    assert scale_error({"base_rate": "1.01", "special_rate": "0.05"}) is not None
    assert scale_error({"base_rate": "0.12", "special_rate": "-0.01"}) is not None
    assert scale_error({"base_rate": "0.12", "special_rate": "1.01"}) is not None
    assert scale_error({"base_rate": "0.12", "special_rate": "0.05", "rungs": [{"coverage": "-0.1", "rate": "0.04"}]}) is not None
    assert scale_error({"base_rate": "0.12", "special_rate": "0.05", "rungs": [{"coverage": "1", "rate": "1.01"}]}) is not None
    duplicate = scale_error(
        {"base_rate": "0.12", "special_rate": "0.05", "rungs": [{"coverage": "1", "rate": "0.04"}, {"coverage": "1", "rate": "0.03"}]}
    )
    assert duplicate is not None
    ordered = scale_error(
        {"base_rate": "0.12", "special_rate": "0.05", "rungs": [{"coverage": "1.5", "rate": "0.03"}, {"coverage": "1", "rate": "0.04"}]}
    )
    assert ordered is not None
    assert scale_error({"base_rate": "0.12", "special_rate": "0.05", "rungs": ""}) is not None
    assert scale_error({"base_rate": "0.12", "special_rate": "0.05", "rungs": None}) is not None
    periods = [_period("Q1", 1)]
    bindings = [
        _bind("debt_outstanding", "d", "Остаток долга"),
        _bind("escrow_balance", "e", "Остаток на счетах эскроу"),
    ]
    refused = _cover(
        "escrow_blended_rate",
        bindings,
        [_fact("d", "Q1", "100"), _fact("e", "Q1", "100")],
        periods,
        profile={"escrow_rate_scale": {"base_rate": "1.5", "special_rate": "0.05"}},
    )
    assert refused["rows"][0]["value"] is None
    edge = {"base_rate": "0.12", "special_rate": "0.05", "rungs": [{"coverage": "1", "rate": "0.04"}, {"coverage": "1.5", "rate": "0.03"}]}
    at_one = _cover(
        "escrow_blended_rate",
        bindings,
        [_fact("d", "Q1", "100"), _fact("e", "Q1", "100")],
        periods,
        profile={"escrow_rate_scale": edge},
    )
    at_one_and_half = _cover(
        "escrow_blended_rate",
        bindings,
        [_fact("d", "Q1", "100"), _fact("e", "Q1", "150")],
        periods,
        profile={"escrow_rate_scale": edge},
    )
    assert at_one["rows"][0]["value"] == quantize_ratio(Decimal("0.04"))
    assert at_one_and_half["rows"][0]["value"] == quantize_ratio(Decimal("0.03"))
    assert at_one["rows"][0]["definition"] == "escrow_blended_rate@service-v1"


def test_stock_uses_the_last_period_and_rejects_a_conflict():
    periods = [_period("Q1", 1), _period("Q2", 2)]
    bindings, facts = _cash(
        ["Q1", "Q2"],
        {
            "cfo_statement": ["10", "10"],
            "cfi_statement": ["0", "0"],
            "financing_inflows": ["0", "0"],
            "senior_principal": ["4", "4"],
            "senior_interest_paid": ["1", "1"],
        },
    )
    stock = bindings + [_bind("guaranteed_funds", "g", "Иные деньги, гарантированно доступные для целевого кредита")]
    conflict = _cover(
        "llcr",
        stock,
        facts + [_fact("g", "Q1", "10"), _fact("g", "Q2", "25")],
        periods,
        variant="cbr590",
    )
    assert conflict["rows"][0]["reason"] == "stock_conflict"
    assert conflict["rows"][0]["value"] is None
    same = _cover(
        "llcr",
        stock,
        facts + [_fact("g", "Q1", "25"), _fact("g", "Q2", "25")],
        periods,
        variant="cbr590",
    )
    assert same["rows"][0]["value"] == quantize_ratio(Decimal(45) / Decimal(10))
    only_last = _cover("llcr", stock, facts + [_fact("g", "Q2", "25")], periods, variant="cbr590")
    assert only_last["rows"][0]["value"] == same["rows"][0]["value"]
    only_early = _cover("llcr", stock, facts + [_fact("g", "Q1", "25")], periods, variant="cbr590")
    assert only_early["rows"][0]["value"] is None
    assert only_early["rows"][0]["reason"] == "missing_component"
    limited = bindings + [_bind("credit_limit", "lim", "Лимит кредита проектного финансирования")]
    limit_conflict = _cover(
        "llcr",
        limited,
        facts + [_fact("lim", "Q1", "40"), _fact("lim", "Q2", "80")],
        periods,
        variant="domrf",
    )
    assert limit_conflict["rows"][0]["reason"] == "stock_conflict"
    assert limit_conflict["rows"][0]["value"] is None


def test_mixed_lengths_and_a_calendar_gap_do_not_silently_sum():
    month = _period("M", 1, grain="month", start=date(2024, 1, 1), end=date(2024, 1, 31))
    quarter = _period("Q", 2, grain="quarter", start=date(2024, 2, 1), end=date(2024, 4, 30))
    mixed_periods = [month, quarter]
    bindings, facts = _cash(
        ["M", "Q"],
        {
            "cfo_statement": ["10", "30"],
            "cfi_statement": ["0", "0"],
            "financing_inflows": ["0", "0"],
            "senior_principal": ["4", "6"],
            "senior_interest_paid": ["1", "2"],
        },
    )
    life = _cover("llcr", bindings, facts, mixed_periods, profile={"guaranteed_funds_none": True})
    assert life["rows"][0]["value"] == quantize_ratio(Decimal(40) / Decimal(13))
    assert _cover("dscr_min", bindings, facts, mixed_periods, variant="housing")["rows"][0]["reason"] == "mixed_grain"
    assert _cover("dscr_avg", bindings, facts, mixed_periods, variant="housing")["rows"][0]["reason"] == "mixed_grain"
    assert _cover("adscr", bindings, facts, mixed_periods, variant="housing")["rows"][0]["reason"] == "mixed_grain"
    gap = [
        _period("Q1", 1, start=date(2024, 1, 1), end=date(2024, 3, 31)),
        _period("Q3", 2, start=date(2024, 7, 1), end=date(2024, 9, 30)),
    ]
    gap_bindings, gap_facts = _cash(
        ["Q1", "Q3"],
        {
            "cfo_statement": ["10", "10"],
            "cfi_statement": ["0", "0"],
            "financing_inflows": ["0", "0"],
            "senior_principal": ["4", "4"],
            "senior_interest_paid": ["1", "1"],
        },
    )
    for metric in ("llcr", "dscr_min", "dscr_avg", "adscr"):
        profile = {"guaranteed_funds_none": True} if metric == "llcr" else None
        got = _cover(metric, gap_bindings, gap_facts, gap, variant="cbr590" if metric == "llcr" else "housing", profile=profile)
        assert got["rows"][0]["reason"] == "calendar_gap", metric
        assert got["rows"][0]["value"] is None


def test_synthetic_developer_pf_model_checks_every_component():
    """Синтетика, не отчётность застройщика. Четыре квартала одной оси."""

    periods = _quarters()
    names = [item["period_id"] for item in periods]
    roles = (
        ("cfo_statement", "cfo", "Сальдо денежных потоков от текущих операций"),
        ("cfi_statement", "cfi", "Сальдо денежных потоков от инвестиционных операций"),
        ("financing_inflows", "in", "Поступления по финансовой деятельности"),
        ("senior_principal", "prin_a", "Погашение основного долга по несубординированным кредитам"),
        ("senior_principal", "prin_b", "Погашение основного долга по несубординированным кредитам"),
        ("senior_interest_paid", "intr", "Уплаченные проценты по несубординированным кредитам"),
        ("principal", "sub", "Погашение займа участника"),
        ("senior_fees", "fee", "Комиссии по несубординированным кредитам"),
        ("debt_outstanding", "debt", "Остаток долга"),
        ("escrow_balance", "escrow", "Остаток на счетах эскроу"),
        ("credit_limit", "lim", "Лимит кредита проектного финансирования"),
        ("guaranteed_funds", "g", "Иные деньги, гарантированно доступные для целевого кредита"),
    )
    bindings = []
    for concept, row, label in roles:
        path = label
        if row == "prin_a":
            path = "Senior Debt › Транш A › Погашение"
        elif row == "prin_b":
            path = "Senior Debt › Транш B › Погашение"
        elif row == "sub":
            path = "Заём участника › Погашение займа участника"
        elif row == "fee":
            path = "Senior Debt › Комиссии по несубординированным кредитам"
        elif row == "intr":
            path = "Senior Debt › Уплаченные проценты по несубординированным кредитам"
        bindings.append(_bind(concept, row, label, label_path_text=path))
    columns = {
        "cfo": ["10", "20", "30", "40"],
        "cfi": ["-40", "-10", "0", "50"],
        "in": ["100", "80", "40", "0"],
        "prin_a": ["0", "0", "10", "20"],
        "prin_b": ["0", "0", "10", "10"],
        "intr": ["5", "8", "10", "12"],
        "sub": ["0", "0", "999", "0"],
        "fee": ["1", "1", "1", "4"],
        "debt": ["100", "180", "160", "130"],
        "escrow": ["0", "50", "120", "200"],
        "lim": ["200", "200", "200", "200"],
        "g": [None, None, None, "15"],
    }
    facts = []
    for row, values in columns.items():
        for period, value in zip(names, values, strict=True):
            if value is not None:
                facts.append(_fact(row, period, value))
    housing = housing_dscr(facts=facts, bindings=bindings, periods=periods, profile={"include_senior_fees": False})
    expected = {
        "Q1": {"cfo_statement": "10", "cfi_statement": "-40", "financing_inflows": "100", "senior_principal": "0", "senior_interest_paid": "5", "denominator": "5"},
        "Q2": {"cfo_statement": "20", "cfi_statement": "-10", "financing_inflows": "80", "senior_principal": "0", "senior_interest_paid": "8", "denominator": "8"},
        "Q3": {"cfo_statement": "30", "cfi_statement": "0", "financing_inflows": "40", "senior_principal": "20", "senior_interest_paid": "10", "denominator": "30"},
        "Q4": {"cfo_statement": "40", "cfi_statement": "50", "financing_inflows": "0", "senior_principal": "30", "senior_interest_paid": "12", "denominator": "42"},
    }
    for row in housing["rows"]:
        for key, value in expected[row["period_id"]].items():
            assert row["components"][key] == value
        assert "999" not in row["components"].values()
        assert "senior_fees" not in row["components"]
        assert row["definition"] == "dscr.housing@service-v1"
    life = _cover("llcr", bindings, facts, periods, variant="cbr590")
    assert life["rows"][0]["components"]["project_cash"] == "320"
    assert life["rows"][0]["components"]["guaranteed_funds"] == "15"
    assert life["rows"][0]["components"]["denominator"] == "85"
    assert life["rows"][0]["value"] == quantize_ratio(Decimal(335) / Decimal(85))
    domrf = _cover("llcr", bindings, facts, periods, variant="domrf")
    assert domrf["rows"][0]["value"] == quantize_ratio(Decimal(320) / Decimal(235))
    scale = {
        "base_rate": "0.12",
        "special_rate": "0.05",
        "rungs": [{"coverage": "1", "rate": "0.04"}, {"coverage": "1.5", "rate": "0.03"}],
    }
    rate = _cover("escrow_blended_rate", bindings, facts, periods, profile={"escrow_rate_scale": scale})
    by_period = {row["period_id"]: row["value"] for row in rate["rows"]}
    assert by_period["Q1"] == quantize_ratio(Decimal("0.12"))
    assert by_period["Q2"] == quantize_ratio((Decimal(50) * Decimal("0.05") + Decimal(130) * Decimal("0.12")) / Decimal(180))
    assert by_period["Q3"] == quantize_ratio((Decimal(120) * Decimal("0.05") + Decimal(40) * Decimal("0.12")) / Decimal(160))
    assert by_period["Q4"] == quantize_ratio(Decimal("0.03"))
    hole = [fact for fact in facts if not (fact["row_key"] == "cfi" and fact["period_id"] == "Q3")]
    blocked = _cover("llcr", bindings, hole, periods, variant="cbr590")
    assert blocked["rows"][0]["value"] is None
    assert "cfi_statement" in blocked["rows"][0]["missing"]
