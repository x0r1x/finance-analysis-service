"""ADSCR, min/avg DSCR, LLCR и PLCR: ручной re-performance на синтетической книге (§5.7, §12 фаза 3)."""

from datetime import date
from decimal import Decimal, localcontext

from finance_analysis.domain.cover_metrics import (
    add_months,
    adscr,
    dscr_reductions,
    loan_life_ratio,
)
from finance_analysis.domain.metrics import coverage_ratio, quantize_ratio

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


def _expected(flows: list[tuple[str, Decimal]], balance: str) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 38
        ctx.rounding = "ROUND_HALF_EVEN"
        factor = Decimal(1)
        total = Decimal(0)
        for flow, fraction in flows:
            factor = factor / Decimal("1.10") ** fraction
            total += Decimal(flow) * factor
        return quantize_ratio(total / Decimal(balance))


def _by_period(result: dict) -> dict[str, dict]:
    return {row["period_id"]: row for row in result["rows"]}


def test_llcr_reperformed_and_not_computed_in_final_period():
    periods, facts, bindings = _loan_book()
    common = {"facts": facts, "bindings": bindings, "periods": periods, "period_phase": {}, "explicit_phases": False}
    llcr = _by_period(loan_life_ratio("llcr", **common))
    year = Decimal(1)
    assert llcr["2025"]["value"] == _expected([("100", year), ("100", year)], "140")
    assert llcr["2026"]["value"] == _expected([("100", year)], "95")
    assert llcr["2027"]["status"] == "not_computed"
    assert llcr["2027"]["reason"] == "final_debt_service_period"
    assert "2028" not in llcr

    plcr = _by_period(loan_life_ratio("plcr", **common))
    leap = Decimal(366) / Decimal(365)
    assert plcr["2025"]["value"] == _expected([("100", year), ("100", year), ("100", leap)], "140")
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
    year = Decimal(1)
    assert llcr["2026"]["value"] == _expected([("100", year), ("100", year)], "95")


def test_llcr_without_dates_discounts_by_grain_and_warns():
    _periods, facts, bindings = _loan_book()
    periods = _years(2025, 2026, 2027, 2028, grain="model_year", dated=False)
    result = loan_life_ratio(
        "llcr", facts=facts, bindings=bindings, periods=periods, period_phase={}, explicit_phases=False
    )
    assert _by_period(result)["2025"]["value"] == _expected([("100", Decimal(1)), ("100", Decimal(1))], "140")
    assert result["warnings"][0]["code"] == "npv_by_grain"


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
