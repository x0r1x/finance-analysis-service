"""ADSCR, min/avg DSCR, LLCR и PLCR: ручной re-performance на синтетической книге (§5.7, §12 фаза 3)."""

from datetime import date
from decimal import Decimal

from finance_analysis.domain.cover_metrics import (
    add_months,
    adscr,
    dscr_reductions,
    loan_life_ratio,
)
from finance_analysis.domain.metrics import coverage_ratio

AXIS = "Debt!r3"


def _binding(concept: str, row_key: str, **extra) -> dict:
    return {
        "row_key": row_key,
        "binding_key": row_key,
        "is_primary": True,
        "status": "bound",
        "effective_concept": concept,
        "source": "inferred",
        **extra,
    }


def _years(*years: int, grain: str = "year", dated: bool = True) -> list[dict]:
    return [
        {
            "axis_id": AXIS,
            "timeline_id": AXIS,
            "period_id": str(year),
            "period_index": index,
            "period_key_base": str(year),
            "grain": grain,
            "period_start": date(year, 1, 1) if dated else None,
            "period_end": date(year, 12, 31) if dated else None,
        }
        for index, year in enumerate(years)
    ]


def _quarters(year: int, count: int) -> list[dict]:
    found = []
    for index in range(count):
        start = add_months(date(year, 1, 1), 3 * index)
        found.append(
            {
                "axis_id": AXIS,
                "timeline_id": AXIS,
                "period_id": f"{start.year}Q{(start.month - 1) // 3 + 1}",
                "period_index": index,
                "period_key_base": f"{start.year}Q{(start.month - 1) // 3 + 1}",
                "grain": "quarter",
                "period_start": start,
                "period_end": add_months(start, 3) - (date(2000, 1, 2) - date(2000, 1, 1)),
            }
        )
    return found


def _series(row_key: str, periods: list[dict], values: list[str], axis: str = AXIS) -> list[dict]:
    return [
        {"row_key": row_key, "axis_id": axis, "period_id": period["period_id"], "normalized_value": Decimal(value)}
        for period, value in zip(periods, values, strict=True)
    ]


def _loan_book():
    periods = _years(2025, 2026, 2027, 2028)
    facts = (
        _series("c", periods, ["100", "100", "100", "100"])
        + _series("d", periods, ["-50", "-50", "-50", "0"])
        + _series("b", periods, ["140", "95", "0", "0"])
        + [{"row_key": "r", "axis_id": "Inputs!r5", "period_id": "v", "normalized_value": Decimal("0.10")}]
    )
    bindings = [
        _binding("cfads", "c"),
        _binding("debt_service", "d"),
        _binding("debt_outstanding", "b"),
        _binding("discount_rate", "r"),
    ]
    return periods, facts, bindings


# Ручной счёт при ставке 10%:
# LLCR 2025 = (100/1.1 + 100/1.1²) / 140 = 1.2396694215
# LLCR 2026 = (100/1.1) / 95 = 0.9569377990
# PLCR 2025 = (100/1.1 + 100/1.1² + 100/(1.1² · 1.1^(366/365))) / 140 = 1.7761827360 (2028 високосный)
# LLCR 2026 от начала периода = (100/1.1 + 100/1.1²) / 95 = 1.8268812527
LLCR_2025 = Decimal("1.2396694215")
LLCR_2026 = Decimal("0.9569377990")
PLCR_2025 = Decimal("1.7761827360")
LLCR_2026_START = Decimal("1.8268812527")


def _common(periods, facts, bindings) -> dict:
    return {"facts": facts, "bindings": bindings, "periods": periods, "period_phase": {}, "explicit_phases": False}


def _by_period(result: dict) -> dict[str, dict]:
    return {row["period_id"]: row for row in result["rows"]}


def test_llcr_reperformed_and_not_computed_in_final_period():
    periods, facts, bindings = _loan_book()
    common = {"facts": facts, "bindings": bindings, "periods": periods, "period_phase": {}, "explicit_phases": False}
    llcr = _by_period(loan_life_ratio("llcr", **common))
    assert llcr["2025"]["value"] == LLCR_2025
    assert llcr["2025"]["window"] == ["2026", "2027"]
    assert llcr["2026"]["value"] == LLCR_2026
    assert llcr["2027"]["status"] == "not_computed"
    assert llcr["2027"]["reason"] == "final_debt_service_period"
    assert "2028" not in llcr

    plcr = _by_period(loan_life_ratio("plcr", **common))
    assert plcr["2025"]["value"] == PLCR_2025
    assert plcr["2027"]["status"] == "not_computed"
    assert plcr["2027"]["reason"] == "zero_balance"


def test_llcr_without_rate_asks_for_the_rate_cell():
    periods, facts, bindings = _loan_book()
    result = loan_life_ratio(
        "llcr",
        facts=facts,
        bindings=[item for item in bindings if item["effective_concept"] != "discount_rate"],
        periods=periods,
        period_phase={},
        explicit_phases=False,
    )
    assert result["status"] == "missing_input"
    assert result["needs_input"] == [{"kind": "concept", "reason": "concept_unknown", "subject": "discount_rate"}]
    assert result["rows"] == []


def test_llcr_period_start_basis_takes_the_current_period():
    periods, facts, bindings = _loan_book()
    llcr = _by_period(
        loan_life_ratio(
            "llcr",
            facts=facts,
            bindings=bindings,
            periods=periods,
            period_phase={},
            explicit_phases=False,
            basis="period_start",
        )
    )
    assert llcr["2026"]["value"] == LLCR_2026_START


def test_llcr_without_dates_discounts_by_grain_and_warns():
    _periods, facts, bindings = _loan_book()
    periods = _years(2025, 2026, 2027, 2028, grain="model_year", dated=False)
    result = loan_life_ratio(
        "llcr", facts=facts, bindings=bindings, periods=periods, period_phase={}, explicit_phases=False
    )
    assert _by_period(result)["2025"]["value"] == LLCR_2025
    assert result["warnings"][0]["code"] == "npv_by_grain"


def test_llcr_window_with_empty_cfads_is_missing_input():
    periods, facts, bindings = _loan_book()
    facts = [item for item in facts if not (item["row_key"] == "c" and item["period_id"] == "2027")]
    llcr = _by_period(loan_life_ratio("llcr", **_common(periods, facts, bindings)))
    assert (llcr["2025"]["status"], llcr["2025"]["reason"]) == ("missing_input", "no_binding")
    assert (llcr["2026"]["status"], llcr["2026"]["reason"]) == ("missing_input", "no_binding")


def test_llcr_rate_out_of_range_is_missing_input():
    for rate in ("-1", "-1.5", "8", "1.5", "0.31"):
        periods, facts, bindings = _loan_book()
        facts = [{**item, "normalized_value": Decimal(rate)} if item["row_key"] == "r" else item for item in facts]
        result = loan_life_ratio("plcr", **_common(periods, facts, bindings))
        reasons = {(row["status"], row["reason"]) for row in result["rows"] if row["period_id"] != "2027"}
        assert reasons == {("missing_input", "rate_out_of_range")}, rate


def test_llcr_negative_balance_is_not_computed():
    periods, facts, bindings = _loan_book()
    facts = [
        {**item, "normalized_value": Decimal(-20)} if item["row_key"] == "b" and item["period_id"] == "2025" else item
        for item in facts
    ]
    llcr = _by_period(loan_life_ratio("llcr", **_common(periods, facts, bindings)))
    assert (llcr["2025"]["status"], llcr["2025"]["reason"]) == ("not_computed", "negative_balance")


def test_llcr_warns_that_dsra_is_not_included():
    periods, facts, bindings = _loan_book()
    llcr = loan_life_ratio("llcr", **_common(periods, facts, bindings))
    computed = [row["period_id"] for row in llcr["rows"] if row["status"] == "computed"]
    warned = [item["params"]["period_id"] for item in llcr["warnings"] if item["code"] == "dsra_not_included"]
    assert warned == computed == ["2025", "2026"]
    plcr = loan_life_ratio("plcr", **_common(periods, facts, bindings))
    assert not [item for item in plcr["warnings"] if item["code"] == "dsra_not_included"]


def test_adscr_not_applicable_without_grain():
    periods = [{**period, "grain": None} for period in _years(2025, 2026)]
    facts = _series("c", periods, ["10", "10"]) + _series("d", periods, ["-5", "-5"])
    bindings = [_binding("cfads", "c"), _binding("debt_service", "d")]
    result = adscr(**_common(periods, facts, bindings))
    assert result["rows"] == []
    assert result["warnings"][0]["code"] == "adscr_not_applicable"


def test_adscr_rolls_twelve_months_and_skips_partial_windows():
    periods = _quarters(2025, 8)
    facts = _series("c", periods, ["15"] * 4 + ["20"] * 4) + _series("d", periods, ["-10"] * 8)
    bindings = [_binding("cfads", "c"), _binding("debt_service", "d")]
    result = _by_period(
        adscr(facts=facts, bindings=bindings, periods=periods, period_phase={}, explicit_phases=False)
    )
    assert result["2025Q3"]["status"] == "not_computed"
    assert result["2025Q4"]["value"] == Decimal("1.5000000000")
    assert result["2026Q1"]["value"] == Decimal("1.6250000000")
    assert result["2026Q1"]["window"] == ["2025Q2", "2025Q3", "2025Q4", "2026Q1"]

    annual, facts, bindings = _loan_book()
    yearly = adscr(facts=facts, bindings=bindings, periods=annual, period_phase={}, explicit_phases=False)
    assert yearly["rows"] == []
    assert yearly["warnings"][0]["code"] == "adscr_not_applicable"


def test_dscr_min_and_both_averages():
    periods = _years(2025, 2026, 2027)
    facts = _series("c", periods, ["10", "30", "8"]) + _series("d", periods, ["-5", "-10", "0"])
    bindings = [_binding("cfads", "c"), _binding("debt_service", "d")]
    common = {"facts": facts, "bindings": bindings, "periods": periods, "period_phase": {}, "explicit_phases": False}
    lowest = dscr_reductions("dscr_min", **common)["rows"]
    assert [(row["period_id"], row["value"]) for row in lowest] == [("2025", Decimal("2.0000000000"))]
    averages = {row["variant"]: row["value"] for row in dscr_reductions("dscr_avg", **common)["rows"]}
    assert averages == {"mean_of_ratios": Decimal("2.5000000000"), "ratio_of_sums": Decimal("2.6666666667")}


def test_dscr_aligns_rows_of_different_sheets_by_timeline():
    debt = _years(2025, 2026)
    cash = [{**period, "axis_id": "CFS!r3"} for period in debt]
    facts = _series("c", cash, ["12", "9"], axis="CFS!r3") + _series("d", debt, ["-4", "-3"])
    result = coverage_ratio(
        metric="dscr",
        facts=facts,
        bindings=[_binding("cfads", "c"), _binding("debt_service", "d")],
        periods=debt + cash,
        period_phase={},
        explicit_phases=False,
    )
    assert [(row["axis_id"], row["value"]) for row in result["rows"]] == [
        (AXIS, Decimal("3.0000000000")),
        (AXIS, Decimal("3.0000000000")),
    ]
