"""ICR с процентами лизинга в знаменателе. Классический icr эта формула не заменяет."""

from datetime import date
from decimal import Decimal

from finance_analysis.application.catalog import load_catalog
from finance_analysis.domain.covenant import select_ratio
from finance_analysis.domain.metrics import (
    MIXED_BASIS,
    PARTIAL_DENOMINATOR,
    coverage_ratio,
    lease_interest_coverage,
    quantize_ratio,
)
from tests.unit.test_cover_metrics import _quarters, _series
from tests.unit.test_ratio_math import _binding, _fact, _period

FOUR = Decimal("4.0000000000")
FIVE = Decimal("5.0000000000")


def _lease_book(**interest):
    return (
        [
            _fact("e", "100"),
            _fact("i", "20"),
            _fact("p", "15"),
            _fact("n", "10"),
        ],
        [
            _binding("ebitda", "e"),
            _binding("interest", "i", **interest),
            _binding("lease_payment", "p"),
            _binding("lease_principal", "n"),
        ],
        [_period()],
    )


def _value(result: dict):
    values = [row["value"] for row in result["rows"] if row.get("value") is not None]
    assert len(values) == 1
    return values[0]


def test_lease_interest_enters_the_denominator_only_with_evidence():
    facts, bindings, periods = _lease_book(evidence={"excludes_lease_interest": True})
    got = lease_interest_coverage(facts=facts, bindings=bindings, periods=periods)
    assert got["metric"] == "icr_lease"
    assert got["status"] == "succeeded"
    assert _value(got) == FOUR
    bare = lease_interest_coverage(
        facts=facts,
        bindings=[
            _binding("ebitda", "e"),
            _binding("interest", "i", label="2330"),
            _binding("lease_payment", "p"),
            _binding("lease_principal", "n"),
        ],
        periods=periods,
    )
    assert bare["status"] == "needs_input"
    assert bare["needs_input"][0]["reason"] == "lease_interest_overlap"
    assert all(row.get("value") is None for row in bare["rows"])
    confirmed = lease_interest_coverage(
        facts=facts,
        bindings=[
            _binding("ebitda", "e"),
            _binding("interest", "i", source="confirmed", label="Проценты к уплате"),
            _binding("lease_payment", "p"),
            _binding("lease_principal", "n"),
        ],
        periods=periods,
    )
    assert confirmed["needs_input"][0]["reason"] == "lease_interest_overlap"
    loan = lease_interest_coverage(
        facts=facts,
        bindings=[
            _binding("ebitda", "e"),
            _binding("interest", "i", label="Проценты по кредитам и займам"),
            _binding("lease_payment", "p"),
            _binding("lease_principal", "n"),
        ],
        periods=periods,
    )
    assert _value(loan) == FOUR


def test_direct_lease_interest_row_is_the_addend():
    got = lease_interest_coverage(
        facts=[_fact("e", "100"), _fact("i", "20"), _fact("L", "5")],
        bindings=[
            _binding("ebitda", "e"),
            _binding("interest", "i", evidence={"excludes_lease_interest": True}),
            _binding("lease_interest", "L"),
        ],
        periods=[_period()],
    )
    assert got["metric"] == "icr_lease"
    assert _value(got) == FOUR


def test_signed_outflows_use_each_part_before_the_difference():
    facts = [_fact("e", "100"), _fact("i", "-20"), _fact("p", "-15"), _fact("n", "-10")]
    bindings = [
        _binding("ebitda", "e"),
        _binding("interest", "i", evidence={"excludes_lease_interest": True}),
        _binding("lease_payment", "p"),
        _binding("lease_principal", "n"),
    ]
    got = lease_interest_coverage(facts=facts, bindings=bindings, periods=[_period()])
    assert _value(got) == FOUR


def test_negative_lease_split_and_a_direct_row_beside_the_pair_have_no_number():
    facts, bindings, periods = _lease_book(evidence={"excludes_lease_interest": True})
    facts = [_fact("e", "100"), _fact("i", "20"), _fact("p", "10"), _fact("n", "15")]
    refused = lease_interest_coverage(facts=facts, bindings=bindings, periods=periods)
    assert refused["status"] == "not_computed"
    assert refused["rows"][0]["reason"] == "negative_lease_interest"
    assert refused["rows"][0]["value"] is None
    both = lease_interest_coverage(
        facts=[*facts, _fact("L", "5")],
        bindings=[*bindings, _binding("lease_interest", "L")],
        periods=periods,
    )
    assert both["status"] == "needs_input"
    assert both["needs_input"][0]["reason"] == "ambiguous"
    assert all(row.get("value") is None for row in both["rows"])


def test_missing_lease_rows_do_not_fall_back_to_classic_icr():
    facts = [_fact("e", "100"), _fact("i", "20")]
    bindings = [_binding("ebitda", "e"), _binding("interest", "i")]
    periods = [_period()]
    missing = lease_interest_coverage(facts=facts, bindings=bindings, periods=periods)
    assert missing["metric"] == "icr_lease"
    assert missing["status"] == "needs_input"
    assert missing["rows"] == []
    classic = coverage_ratio(
        metric="icr",
        facts=facts,
        bindings=bindings,
        periods=periods,
        period_phase={},
        explicit_phases=False,
    )
    assert classic["metric"] == "icr"
    assert classic["rows"][0]["value"] == FIVE
    absent = lease_interest_coverage(
        facts=facts,
        bindings=[
            *bindings,
            _binding("lease_payment", "p", is_primary=False, status="unknown", source="confirmed"),
            _binding("lease_principal", "n", is_primary=False, status="unknown", source="confirmed"),
        ],
        periods=periods,
    )
    assert absent["metric"] == "icr_lease"
    assert _value(absent) == FIVE


def test_operating_lease_warns_and_does_not_add_the_payment_to_ebitda():
    facts, bindings, periods = _lease_book(evidence={"excludes_lease_interest": True})
    bindings[2] = _binding("lease_payment", "p", evidence={"operating_lease_in_opex": True})
    got = lease_interest_coverage(facts=facts, bindings=bindings, periods=periods)
    assert _value(got) == FOUR
    assert got["warnings"][0]["code"] == "operating_lease_numerator"


def test_select_ratio_uses_the_lease_formula_before_the_composed_catalog():
    facts, bindings, periods = _lease_book(evidence={"excludes_lease_interest": True})
    common = {
        "facts": facts,
        "bindings": bindings,
        "periods": periods,
        "sign_convention": "outflow_negative",
        "marker_class": None,
        "absent": frozenset(),
        "period_phase": {},
        "explicit_phases": False,
    }
    got = select_ratio(
        "icr_lease",
        None,
        common,
        profile=None,
        profile_ref=None,
        composed={"icr_lease": object()},
        concepts=frozenset(),
        money=frozenset(),
    )
    assert _value(got) == FOUR


def _ytd_year():
    periods = []
    for index in range(1, 5):
        period_id = f"q{index}"
        periods.append(
            {
                "axis_id": "Sheet!r1",
                "timeline_id": "t",
                "period_id": period_id,
                "period_index": index,
                "period_key_base": period_id,
                "grain": "quarter",
                "calendar_year": 2024,
                "period_start": date(2024, 3 * index - 2, 1),
            }
        )
    facts = []
    for period, ebitda, interest in zip(
        periods, (100, 180, 250, 400), (20, 50, 70, 100), strict=True
    ):
        facts.append({**_fact("e", str(ebitda), period["period_id"]), "axis_id": "Sheet!r1"})
        facts.append({**_fact("i", str(interest), period["period_id"]), "axis_id": "Sheet!r1"})
    evidence = {"period_basis": "ytd", "period_basis_source": "header"}
    bindings = [
        _binding("ebitda", "e", evidence=evidence),
        _binding("interest", "i", evidence=evidence),
        _binding("lease_payment", "p", is_primary=False, status="unknown", source="confirmed"),
        _binding("lease_principal", "n", is_primary=False, status="unknown", source="confirmed"),
    ]
    return facts, bindings, periods


def test_restated_quarters_stay_separate_and_the_year_sums_flows():
    facts, bindings, periods = _ytd_year()
    quarters = lease_interest_coverage(facts=facts, bindings=bindings, periods=periods)
    assert quarters["status"] == "succeeded"
    assert [row["value"] for row in quarters["rows"]] == [
        FIVE,
        quantize_ratio(Decimal(80) / Decimal(30)),
        Decimal("3.5000000000"),
        FIVE,
    ]
    annual = lease_interest_coverage(facts=facts, bindings=bindings, periods=periods, annual=True)
    assert annual["metric"] == "icr_lease"
    assert len(annual["rows"]) == 1
    assert _value(annual) == FOUR


def test_half_year_is_not_divided_by_quarterly_interest_nor_a_year_by_a_quarter():
    def call(left_grain: str, right_grain: str):
        periods = [
            {
                "axis_id": "pl",
                "timeline_id": "t",
                "period_id": "h",
                "period_index": 1,
                "grain": left_grain,
                "calendar_year": 2024,
            },
            {
                "axis_id": "debt",
                "timeline_id": "t",
                "period_id": "q",
                "period_index": 1,
                "grain": right_grain,
                "calendar_year": 2024,
            },
        ]
        facts = [
            {"row_key": "e", "axis_id": "pl", "period_id": "h", "normalized_value": "100"},
            {"row_key": "i", "axis_id": "debt", "period_id": "q", "normalized_value": "20"},
        ]
        bindings = [
            _binding(
                "ebitda",
                "e",
                evidence={"period_basis": "ytd", "period_basis_source": "header"},
            ),
            _binding("interest", "i"),
        ]
        return lease_interest_coverage(
            facts=facts,
            bindings=bindings,
            periods=periods,
            absent=frozenset({"lease_payment", "lease_principal"}),
        )

    half = call("half", "quarter")
    assert half["status"] == "basis_mismatch"
    assert half["message"] == MIXED_BASIS
    assert all(row["value"] is None for row in half["rows"])
    year = call("year", "quarter")
    assert year["status"] == "basis_mismatch"
    assert all(row["value"] is None for row in year["rows"])


def test_ltm_numerator_uses_twelve_months_of_interest():
    quarters = _quarters(2025, 4)
    annual = {
        "axis_id": "Ratios!r1",
        "timeline_id": "Ratios!r1",
        "period_id": "2025",
        "period_index": 0,
        "period_key_base": "2025",
        "grain": "year",
        "period_start": date(2025, 1, 1),
        "period_end": date(2025, 12, 31),
    }
    full = lease_interest_coverage(
        facts=[{"row_key": "e", "axis_id": "Ratios!r1", "period_id": "2025", "normalized_value": Decimal(40)}]
        + _series("i", quarters, ["-8", "-8", "-8", "-8"]),
        bindings=[
            _binding("ebitda", "e", evidence={"period_basis": "ltm", "period_basis_source": "header"}),
            _binding("interest", "i"),
        ],
        periods=[annual, *quarters],
        absent=frozenset({"lease_payment", "lease_principal"}),
    )
    assert full["status"] == "succeeded"
    assert full["rows"][0]["value"] == Decimal("1.2500000000")
    short = lease_interest_coverage(
        facts=_series("e", quarters[:3], ["40", "40", "40"]) + _series("i", quarters[:3], ["-10", "-10", "-10"]),
        bindings=[
            _binding("ebitda", "e", evidence={"period_basis": "ltm", "period_basis_source": "header"}),
            _binding("interest", "i"),
        ],
        periods=quarters[:3],
        absent=frozenset({"lease_payment", "lease_principal"}),
    )
    assert short["status"] == "partial_window"
    assert short["message"] == PARTIAL_DENOMINATOR
    assert all(row["value"] is None for row in short["rows"])


def test_lease_glossary_keeps_2330_on_interest():
    package = load_catalog()
    assert package.resolve("лизинговые платежи").concept == "lease_payments"
    assert package.resolve("Лизинговый платёж вместе с основным долгом").concept == "lease_payment"
    assert package.resolve("Основной долг в лизинговом платеже").concept == "lease_principal"
    assert package.resolve("Проценты по аренде").concept == "lease_interest"
    assert package.resolve("Коэффициент покрытия процентов с учётом лизинга").concept == "icr_lease"
    assert package.resolve("2330").concept == "interest"
    assert package.resolve("Проценты к уплате").concept == "interest"
    assert package.resolve("Процентный доход лизингодателя").concept == "lease_interest_income"
    assert package.resolve("Коэффициент покрытия процентов").concept == "icr"
