"""Банковский ICR: срезы 1–6. EBITDA по РСБУ и МСФО считается из отчётности."""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal

import pytest

from finance_analysis.application.catalog import load_catalog
from finance_analysis.application.model_types import load_model_types
from finance_analysis.domain.covenant import select_ratio
from finance_analysis.domain.mapping import assign_rows, marked_line_code
from finance_analysis.domain.metrics import quantize_ratio


def _bind(concept: str, row: str | None = None, **extra) -> dict:
    item = {
        "effective_concept": concept,
        "row_key": row or concept,
        "is_primary": True,
        "status": "bound",
        "source": "inferred",
    }
    item.update(extra)
    return item


def _fact(row: str, period: str, value: str) -> dict:
    return {"row_key": row, "axis_id": "a", "period_id": period, "normalized_value": value}


def _year() -> dict:
    return {
        "axis_id": "a",
        "period_id": "Y1",
        "period_index": 1,
        "grain": "year",
        "timeline_id": "t",
        "calendar_year": 2024,
        "period_end": "2024-12-31",
    }


def _ytd_periods() -> list[dict]:
    spans = [
        ("2024Q1", 1, 2024, "2024-01-01", "2024-03-31"),
        ("2024Q2", 2, 2024, "2024-04-01", "2024-06-30"),
        ("2024Q3", 3, 2024, "2024-07-01", "2024-09-30"),
        ("2024Q4", 4, 2024, "2024-10-01", "2024-12-31"),
        ("2025Q1", 5, 2025, "2025-01-01", "2025-03-31"),
        ("2025Q2", 6, 2025, "2025-04-01", "2025-06-30"),
    ]
    return [
        {
            "axis_id": "a",
            "period_id": period_id,
            "period_index": index,
            "grain": "quarter",
            "timeline_id": "t",
            "calendar_year": year,
            "period_start": start,
            "period_end": end,
        }
        for period_id, index, year, start, end in spans
    ]


def _flow_quarters() -> list[dict]:
    spans = [
        ("2024Q3", 1, "2024-07-01", "2024-09-30"),
        ("2024Q4", 2, "2024-10-01", "2024-12-31"),
        ("2025Q1", 3, "2025-01-01", "2025-03-31"),
        ("2025Q2", 4, "2025-04-01", "2025-06-30"),
    ]
    return [
        {
            "axis_id": "a",
            "period_id": period_id,
            "period_index": index,
            "grain": "quarter",
            "timeline_id": "t",
            "calendar_year": int(period_id[:4]),
            "period_start": start,
            "period_end": end,
        }
        for period_id, index, start, end in spans
    ]


def _evidence(**extra) -> dict:
    item = {
        "source": "statement line",
        "binding": "interest",
        "axis": "each",
        "period": "each",
        "standard": "ifrs16",
        "method": "interest_expense",
    }
    item.update(extra)
    return item


def _profile(mode: str | None = "in_interest", **extra) -> dict:
    raw: dict = {"variant": "bank", "denominator": _evidence()}
    if mode is not None:
        raw["lease_mode"] = mode
    raw.update(extra)
    return {"icr_definition": raw}


def _lease(scope: str) -> dict:
    return {"evidence_json": json.dumps({"lease_scope": scope})}


def _ytd() -> dict:
    return {"evidence_json": json.dumps({"period_basis": "ytd", "period_basis_source": "header"})}


def _select(metric: str, common: dict, profile: dict | None, variant: str | None = None) -> dict:
    catalog = load_model_types()
    return select_ratio(
        metric,
        variant,
        common,
        profile=profile,
        profile_ref=None,
        composed=catalog.composed,
        concepts=catalog.concepts,
        money=catalog.concepts,
        interest_order=catalog.interest_order,
        row_fallbacks=catalog.row_fallbacks,
    )


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


def _at(got: dict, period: str, variant: str = "bank") -> dict:
    return next(row for row in got["rows"] if row["period_id"] == period and row.get("variant") == variant)


def test_marked_form_codes_are_whitelisted():
    assert marked_line_code("Ф. 2 (2330)") == "ф.2 (2330)"
    assert marked_line_code("ф.2(070)") == "ф.2 (070)"
    assert marked_line_code("Ф. 5 (740)") == "ф.5 (740)"
    assert marked_line_code("2330") is None
    assert marked_line_code("070") is None
    assert marked_line_code("50") is None
    assert marked_line_code("Ф. 2 (50)") is None
    assert marked_line_code("Ф. 2 (740)") is None
    assert marked_line_code("Ф. 5 (2330)") is None


def test_form_2_code_binds_interest_and_a_bare_number_does_not():
    glossary = load_catalog()

    def row(key: str, code: str) -> dict:
        return {
            "kind": "fact",
            "binding_key": key,
            "row_key": key,
            "label": "Строка без названия",
            "label_path_text": "Строка без названия",
            "sign": None,
            "unit": "money",
            "line_code": code,
        }

    coded = assign_rows([row("form", "Ф. 2 (2330)")], [], glossary)["form"]
    assert coded.concept == "interest"
    assert coded.evidence.get("line_code") == "ф.2 (2330)"
    old = assign_rows([row("old", "Ф. 2 (070)")], [], glossary)["old"]
    assert old.concept == "interest"
    bare = assign_rows([row("bare", "2330")], [], glossary)["bare"]
    assert bare.concept is None
    assert bare.status == "unknown"
    assert "line_code" not in bare.evidence


def test_default_icr_still_uses_ebit_and_the_bank_variant_does_not():
    periods = [_year()]
    facts = [_fact("ebit", "Y1", "30"), _fact("interest", "Y1", "10")]
    bindings = [_bind("ebit"), _bind("interest")]
    common = _common(facts, bindings, periods)
    default = _select("icr", common, None)
    assert default["rows"][0]["value"] == Decimal("3.0000000000")
    bank = _select("icr", common, _profile())
    assert bank["status"] == "needs_input"
    assert bank["needs_input"][0]["subject"] == "ebitda"
    assert bank["rows"] == []


def test_icr_ebit_uses_ebit_even_when_ebitda_is_bound():
    common = _common(
        [_fact("ebitda", "Y1", "80"), _fact("ebit", "Y1", "10"), _fact("interest", "Y1", "20")],
        [_bind("ebitda"), _bind("ebit"), _bind("interest")],
        [_year()],
    )
    got = _select("icr_ebit", common, None)
    assert got["rows"][0]["value"] == Decimal("0.5000000000")
    assert got["warnings"] == []


def test_icr_ebit_falls_back_to_interest_paid_and_the_bank_path_does_not():
    paid = _common(
        [_fact("ebit", "Y1", "30"), _fact("interest_paid", "Y1", "10")],
        [_bind("ebit"), _bind("interest_paid")],
        [_year()],
    )
    got = _select("icr_ebit", paid, None)
    assert got["rows"][0]["value"] == Decimal("3.0000000000")
    assert got["warnings"][0]["code"] == "interest_basis_fallback"
    bank = _select(
        "icr",
        _common(
            [_fact("ebitda", "Y1", "30"), _fact("interest_paid", "Y1", "10")],
            [_bind("ebitda"), _bind("interest_paid")],
            [_year()],
        ),
        _profile(),
    )
    assert bank["status"] == "needs_input"
    assert bank["needs_input"][0]["subject"] == "interest"


def test_ras_without_depreciation_is_not_computed():
    got = _select(
        "icr",
        _common(
            [
                _fact("ebitda", "Y1", "999"),
                _fact("sales", "Y1", "30"),
                _fact("interest", "Y1", "10"),
            ],
            [
                _bind("ebitda"),
                _bind("profit_from_sales", "sales"),
                _bind("interest", **_form("ф.2 (2330)")),
            ],
            [_year()],
        ),
        {"ebitda_definition": "ras", **_profile(denominator=_evidence(standard="fsbu25"))},
    )
    assert got["status"] == "not_computed"
    assert got["rows"] == []
    assert got["reason"] == "depreciation_missing"
    assert "999" not in json.dumps(got)


def test_in_interest_warns_and_does_not_add_lease_interest_again():
    got = _select(
        "icr",
        _common(
            [_fact("ebitda", "Y1", "8"), _fact("interest", "Y1", "4"), _fact("lease_interest", "Y1", "9")],
            [_bind("ebitda"), _bind("interest"), _bind("lease_interest")],
            [_year()],
        ),
        _profile("in_interest"),
    )
    assert got["rows"][0]["value"] == Decimal("2.0000000000")
    assert got["rows"][0]["variant"] == "bank"
    assert "lease_interest" not in got["rows"][0]["inputs"]
    assert got["warnings"][0]["code"] == "lease_interest_double_count"


def test_add_interest_takes_an_explicit_lease_interest_row():
    got = _select(
        "icr",
        _common(
            [
                _fact("ebitda", "Y1", "8"),
                _fact("interest", "Y1", "4"),
                _fact("lease_interest", "Y1", "9"),
                _fact("lease_payments", "Y1", "10"),
                _fact("lease_principal", "Y1", "3"),
            ],
            [_bind(name) for name in ("ebitda", "interest", "lease_interest", "lease_payments", "lease_principal")],
            [_year()],
        ),
        _profile("add_interest"),
    )
    assert got["rows"][0]["value"] == quantize_ratio(Decimal(8) / Decimal(13))
    assert "lease_payments" not in got["rows"][0]["inputs"]


def test_add_interest_subtracts_principal_only_when_both_rows_exist():
    both = _select(
        "icr",
        _common(
            [
                _fact("ebitda", "Y1", "16"),
                _fact("interest", "Y1", "1"),
                _fact("lease_payments", "Y1", "10"),
                _fact("lease_principal", "Y1", "3"),
            ],
            [
                _bind("ebitda"),
                _bind("interest"),
                _bind("lease_payments", **_lease("one")),
                _bind("lease_principal", **_lease("one")),
            ],
            [_year()],
        ),
        _profile("add_interest"),
    )
    assert both["rows"][0]["value"] == Decimal("2.0000000000")
    missing = _select(
        "icr",
        _common(
            [_fact("ebitda", "Y1", "16"), _fact("interest", "Y1", "1"), _fact("lease_payments", "Y1", "10")],
            [_bind(name) for name in ("ebitda", "interest", "lease_payments")],
            [_year()],
        ),
        _profile("add_interest"),
    )
    assert missing["status"] == "needs_input"
    assert missing["needs_input"][0]["subject"] == "lease_interest"


def test_nominal_and_a_missing_lease_mode_ask_instead_of_guessing():
    common = _common(
        [_fact("ebitda", "Y1", "8"), _fact("interest", "Y1", "4")],
        [_bind("ebitda"), _bind("interest")],
        [_year()],
    )
    nominal = _select("icr", common, _profile("nominal"))
    assert nominal["needs_input"][0] == {"kind": "concept", "reason": "nominal", "subject": "lease_mode"}
    missing = _select("icr", common, _profile(None))
    assert missing["needs_input"][0]["reason"] == "missing"
    typed = _select(
        "icr",
        common,
        {"icr_definition": {"lease_mode": "in_interest", "denominator": _evidence()}},
        variant="bank",
    )
    assert typed["rows"][0]["value"] == Decimal("2.0000000000")
    untyped = _select("icr", common, None, variant="bank")
    assert untyped["needs_input"][0]["subject"] == "lease_mode"


def test_ytd_identity_and_a_quarter_reference_that_is_not_annualised():
    periods = _ytd_periods()
    facts = [
        *_series("ebitda", periods, ["10", "30", "60", "100", "12", "40"]),
        *_series("interest", periods, ["1", "3", "6", "10", "2", "5"]),
    ]
    bindings = [_bind("ebitda", **_ytd()), _bind("interest", **_ytd())]
    got = _select("icr", _common(facts, bindings, periods), _profile())
    row = _at(got, "2025Q2")
    assert row["value"] == quantize_ratio(Decimal(110) / Decimal(12))
    assert row["window"] == "LTM"
    step = _at(got, "2025Q2", "quarter_reference")
    assert step["value"] == quantize_ratio(Decimal(28) / Decimal(3))
    assert step["message"] == "за квартал, справочно"
    assert step["value"] != row["value"] * 4


def test_ytd_without_the_prior_year_is_needs_input():
    periods = [item for item in _ytd_periods() if item["calendar_year"] == 2025]
    facts = [
        *_series("ebitda", periods, ["12", "40"]),
        *_series("interest", periods, ["2", "5"]),
    ]
    got = _select(
        "icr",
        _common(facts, [_bind("ebitda", **_ytd()), _bind("interest", **_ytd())], periods),
        _profile(),
    )
    assert got["status"] == "needs_input"
    assert _at(got, "2025Q2")["reason"] == "fiscal_calendar_unknown"
    assert all(row["value"] is None for row in got["rows"])


def test_mixed_period_basis_is_not_summed():
    got = _select(
        "icr",
        _common(
            [_fact("ebitda", "Y1", "8"), _fact("interest", "Y1", "4")],
            [_bind("ebitda", **_ytd()), _bind("interest")],
            [_year()],
        ),
        _profile(),
    )
    assert got["needs_input"][0]["subject"] == "period_basis"


def test_period_ltm_sums_four_quarters_and_one_quarter_is_not_times_four():
    periods = _flow_quarters()
    facts = [
        *_series("ebitda", periods, ["10", "20", "30", "40"]),
        *_series("interest", periods, ["1", "2", "3", "4"]),
    ]
    got = _select("icr", _common(facts, [_bind("ebitda"), _bind("interest")], periods), _profile())
    assert _at(got, "2025Q2")["value"] == Decimal("10.0000000000")
    assert _at(got, "2025Q2", "quarter_reference")["value"] == Decimal("10.0000000000")
    alone = periods[-1:]
    one = _select(
        "icr",
        _common(
            [_fact("ebitda", "2025Q2", "40"), _fact("interest", "2025Q2", "4")],
            [_bind("ebitda"), _bind("interest")],
            alone,
        ),
        _profile(),
    )
    assert one["rows"][0]["status"] == "not_computed"
    assert one["rows"][0]["reason"] == "partial_window"
    assert one["rows"][0]["value"] is None
    assert all(row.get("variant") != "quarter_reference" for row in one["rows"])


def test_zero_and_negative_denominator_and_a_negative_numerator():
    zero = _select(
        "icr",
        _common(
            [_fact("ebitda", "Y1", "5"), _fact("interest", "Y1", "0")],
            [_bind("ebitda"), _bind("interest")],
            [_year()],
        ),
        _profile(),
    )
    assert zero["status"] == "missing_input"
    assert zero["rows"][0]["status"] == "missing_input"
    assert zero["rows"][0]["reason"] == "no_interest"
    assert zero["rows"][0]["value"] is None
    assert zero["rows"][0]["ebitda_sign"] == "positive"
    negative_ebitda = _select(
        "icr",
        _common(
            [_fact("ebitda", "Y1", "-4"), _fact("interest", "Y1", "0")],
            [_bind("ebitda"), _bind("interest")],
            [_year()],
        ),
        _profile(),
    )
    assert negative_ebitda["rows"][0]["ebitda_sign"] == "negative"
    zero_ebitda = _select(
        "icr",
        _common(
            [_fact("ebitda", "Y1", "0"), _fact("interest", "Y1", "0")],
            [_bind("ebitda"), _bind("interest")],
            [_year()],
        ),
        _profile(),
    )
    assert zero_ebitda["rows"][0]["ebitda_sign"] == "zero"
    loss = _select(
        "icr",
        _common(
            [_fact("ebitda", "Y1", "-4"), _fact("interest", "Y1", "2")],
            [_bind("ebitda"), _bind("interest")],
            [_year()],
        ),
        _profile(),
    )
    assert loss["rows"][0]["value"] == Decimal("-2.0000000000")
    assert loss["warnings"][0]["code"] == "negative_numerator"
    inverted = _select(
        "icr",
        _common(
            [
                _fact("ebitda", "Y1", "8"),
                _fact("interest", "Y1", "1"),
                _fact("lease_payments", "Y1", "10"),
                _fact("lease_principal", "Y1", "20"),
            ],
            [
                _bind("ebitda"),
                _bind("interest"),
                _bind("lease_payments", **_lease("one")),
                _bind("lease_principal", **_lease("one")),
            ],
            [_year()],
        ),
        _profile("add_interest"),
    )
    assert inverted["status"] == "not_computed"
    assert inverted["rows"][0]["status"] == "not_computed"
    assert inverted["rows"][0]["reason"] == "invalid_denominator"
    assert inverted["rows"][0]["value"] is None


def test_finance_costs_stay_unpublished_until_the_composition_is_confirmed():
    common = _common(
        [_fact("ebitda", "Y1", "12"), _fact("finance_costs", "Y1", "10"), _fact("other_expense", "Y1", "4")],
        [
            _bind("ebitda"),
            _bind("finance_costs", label="Финансовые расходы и курсовые разницы"),
            _bind("other_expense", label="Курсовые разницы"),
        ],
        [_year()],
    )
    held = _select("icr", common, _profile())
    assert held["status"] == "not_computed"
    assert held["rows"] == []
    assert held["warnings"][0]["code"] == "finance_cost_proxy"
    confirmed = _select(
        "icr",
        common,
        _profile(
            finance_costs_confirmed=True,
            denominator=_evidence(binding="finance_costs"),
        ),
    )
    assert confirmed["rows"][0]["value"] == Decimal("1.2000000000")
    assert confirmed["warnings"][0]["code"] == "finance_cost_proxy"
    assert "other_expense" not in confirmed["rows"][0]["inputs"]


def test_in_interest_needs_denominator_evidence_and_keeps_the_methods_apart():
    common = _common(
        [_fact("ebitda", "Y1", "8"), _fact("interest", "Y1", "4"), _fact("lease_payments", "Y1", "20")],
        [_bind("ebitda"), _bind("interest"), _bind("lease_payments")],
        [_year()],
    )
    bare = {"icr_definition": {"variant": "bank", "lease_mode": "in_interest"}}
    assert _select("icr", common, bare)["needs_input"][0]["subject"] == "denominator_evidence"
    capitalised = _select("icr", common, _profile(denominator=_evidence(method="capitalised")))
    assert capitalised["needs_input"][0]["subject"] == "capitalised"
    paid = _select("icr", common, _profile(denominator=_evidence(method="interest_paid")))
    assert paid["needs_input"][0]["subject"] == "interest_paid"
    expense = _select("icr", common, _profile())
    assert expense["rows"][0]["value"] == Decimal("2.0000000000")
    assert "lease_payments" not in expense["rows"][0]["inputs"]


def test_lease_split_needs_one_scope_on_both_rows():
    facts = [
        _fact("ebitda", "Y1", "16"),
        _fact("interest", "Y1", "1"),
        _fact("lease_payments", "Y1", "10"),
        _fact("lease_principal", "Y1", "3"),
    ]
    split = _select(
        "icr",
        _common(
            facts,
            [
                _bind("ebitda"),
                _bind("interest"),
                _bind("lease_payments", **_lease("fleet")),
                _bind("lease_principal", **_lease("building")),
            ],
            [_year()],
        ),
        _profile("add_interest"),
    )
    assert split["needs_input"][0]["subject"] == "lease_scope"
    bare = _select(
        "icr",
        _common(
            facts,
            [_bind("ebitda"), _bind("interest"), _bind("lease_payments"), _bind("lease_principal")],
            [_year()],
        ),
        _profile("add_interest"),
    )
    assert bare["needs_input"][0]["subject"] == "lease_scope"


def test_gaap_is_not_the_ifrs_methodology():
    from finance_analysis.domain.metrics import _methodology_message

    got = _select(
        "icr",
        _common(
            [
                _fact("ebitda", "Y1", "30"),
                _fact("profit", "Y1", "80"),
                _fact("dep", "Y1", "20"),
                _fact("interest", "Y1", "10"),
            ],
            [
                _bind("ebitda"),
                _bind("ifrs_operating_profit", "profit"),
                _bind("depreciation_notes", "dep"),
                _bind("interest"),
            ],
            [_year()],
        ),
        {"ebitda_definition": "gaap", **_profile()},
    )
    assert got["status"] == "not_computed"
    assert got["rows"] == []
    assert got["message"] == _methodology_message("gaap")
    assert got["message"] != _methodology_message("ifrs")
    assert got["warnings"][0]["code"] == "ebitda_methodology_unpublished"


def test_ytd_identity_rejects_a_shifted_fiscal_year_end():
    periods = _ytd_periods()
    prior = next(item for item in periods if item["period_id"] == "2024Q4")
    prior["period_end"] = "2024-03-31"
    prior["period_start"] = "2024-01-01"
    facts = [
        *_series("ebitda", periods, ["10", "30", "60", "100", "12", "40"]),
        *_series("interest", periods, ["1", "3", "6", "10", "2", "5"]),
    ]
    got = _select(
        "icr",
        _common(facts, [_bind("ebitda", **_ytd()), _bind("interest", **_ytd())], periods),
        _profile(),
    )
    assert _at(got, "2025Q2")["status"] == "needs_input"
    assert _at(got, "2025Q2")["reason"] == "fiscal_calendar_unknown"
    assert _at(got, "2025Q2")["value"] is None


def _dated_quarters(spans: list[tuple[str, str, str]]) -> list[dict]:
    return [
        {
            "axis_id": "a",
            "period_id": period_id,
            "period_index": index,
            "grain": "quarter",
            "timeline_id": "t",
            "calendar_year": int(end[:4]),
            "period_start": start,
            "period_end": end,
        }
        for index, (period_id, start, end) in enumerate(spans, start=1)
    ]


def _ytd_ratio(periods: list[dict], period_id: str):
    facts = [
        *_series("ebitda", periods, ["10", "30", "60", "100", "12", "40"]),
        *_series("interest", periods, ["1", "3", "6", "10", "2", "5"]),
    ]
    got = _select(
        "icr",
        _common(facts, [_bind("ebitda", **_ytd()), _bind("interest", **_ytd())], periods),
        _profile(),
    )
    return got, _at(got, period_id), _at(got, period_id, "quarter_reference")


def test_march_fiscal_year_uses_the_march_quarter_as_prior_q4():
    periods = _dated_quarters(
        [
            ("FY25Q1", "2024-04-01", "2024-06-30"),
            ("FY25Q2", "2024-07-01", "2024-09-30"),
            ("FY25Q3", "2024-10-01", "2024-12-31"),
            ("FY25Q4", "2025-01-01", "2025-03-31"),
            ("FY26Q1", "2025-04-01", "2025-06-30"),
            ("FY26Q2", "2025-07-01", "2025-09-30"),
        ]
    )
    _got, row, step = _ytd_ratio(periods, "FY26Q2")
    assert row["value"] == quantize_ratio(Decimal(110) / Decimal(12))
    assert row["status"] == "computed"
    assert step["value"] == quantize_ratio(Decimal(28) / Decimal(3))


def test_june_fiscal_year_uses_the_june_quarter_as_prior_q4():
    periods = _dated_quarters(
        [
            ("FY25Q1", "2024-07-01", "2024-09-30"),
            ("FY25Q2", "2024-10-01", "2024-12-31"),
            ("FY25Q3", "2025-01-01", "2025-03-31"),
            ("FY25Q4", "2025-04-01", "2025-06-30"),
            ("FY26Q1", "2025-07-01", "2025-09-30"),
            ("FY26Q2", "2025-10-01", "2025-12-31"),
        ]
    )
    _got, row, step = _ytd_ratio(periods, "FY26Q2")
    assert row["value"] == quantize_ratio(Decimal(110) / Decimal(12))
    assert row["status"] == "computed"
    assert step["value"] == quantize_ratio(Decimal(28) / Decimal(3))


def test_a_quarter_off_the_fiscal_grid_is_a_mismatch():
    periods = _ytd_periods()
    periods.append(
        {
            "axis_id": "a",
            "period_id": "stub",
            "period_index": 0,
            "grain": "quarter",
            "timeline_id": "t",
            "calendar_year": 2024,
            "period_start": "2024-02-01",
            "period_end": "2024-02-28",
        }
    )
    facts = [
        *_series("ebitda", _ytd_periods(), ["10", "30", "60", "100", "12", "40"]),
        *_series("interest", _ytd_periods(), ["1", "3", "6", "10", "2", "5"]),
    ]
    got = _select(
        "icr",
        _common(facts, [_bind("ebitda", **_ytd()), _bind("interest", **_ytd())], periods),
        _profile(),
    )
    assert _at(got, "2025Q2")["status"] == "needs_input"
    assert _at(got, "2025Q2")["reason"] == "fiscal_calendar_mismatch"
    assert _at(got, "2025Q2")["value"] is None


def test_profile_stores_icr_definition_and_rejects_a_number(tmp_path):
    from finance_analysis.adapters.storage.store import LocalStore
    from finance_analysis.application.glossary_store import GlossaryStore
    from finance_analysis.domain.errors import InvalidArgument

    async def run():
        gloss = GlossaryStore(LocalStore(tmp_path))
        body = {"sign_convention": "outflow_negative", "icr_definition": {"variant": "bank", "lease_mode": "nominal"}}
        saved = await gloss.put_profile("desk", body, if_match=None, if_none_match="*")
        assert saved["body"]["icr_definition"]["lease_mode"] == "nominal"
        kept = await gloss.put_profile(
            "desk",
            {"sign_convention": "outflow_negative"},
            if_match=saved["etag"],
            if_none_match=None,
        )
        assert kept["body"]["icr_definition"]["variant"] == "bank"
        with pytest.raises(InvalidArgument):
            await gloss.put_profile(
                "desk",
                {"icr_definition": {"variant": "bank", "spread": 0.02}},
                if_match=kept["etag"],
                if_none_match=None,
            )

    asyncio.run(run())


def test_denominator_evidence_for_one_period_does_not_cover_the_next():
    other = {**_year(), "period_id": "Y2", "period_index": 2, "calendar_year": 2025, "period_end": "2025-12-31"}
    got = _select(
        "icr",
        _common(
            [
                _fact("ebitda", "Y1", "8"),
                _fact("interest", "Y1", "4"),
                _fact("ebitda", "Y2", "8"),
                _fact("interest", "Y2", "4"),
            ],
            [_bind("ebitda"), _bind("interest")],
            [_year(), other],
        ),
        _profile(denominator=_evidence(axis="a", period="Y1")),
    )
    assert _at(got, "Y1")["value"] == Decimal("2.0000000000")
    assert _at(got, "Y2")["status"] == "needs_input"
    assert _at(got, "Y2")["reason"] == "denominator_period"


def test_denominator_evidence_does_not_cross_axes_unless_both_scopes_are_each():
    periods = [
        {**_year(), "axis_id": "actuals", "period_id": "2025Q4"},
        {**_year(), "axis_id": "forecast", "period_id": "2025Q4"},
    ]
    facts = []
    for axis in ("actuals", "forecast"):
        facts.append({"row_key": "ebitda", "axis_id": axis, "period_id": "2025Q4", "normalized_value": "8"})
        facts.append({"row_key": "interest", "axis_id": axis, "period_id": "2025Q4", "normalized_value": "4"})
    common = _common(facts, [_bind("ebitda"), _bind("interest")], periods)
    one = _select("icr", common, _profile(denominator=_evidence(axis="actuals", period="2025Q4")))
    by_axis = {row["axis_id"]: row for row in one["rows"] if row.get("variant") == "bank"}
    assert by_axis["actuals"]["value"] == Decimal("2.0000000000")
    assert by_axis["forecast"]["status"] == "needs_input"
    assert by_axis["forecast"]["reason"] == "denominator_axis"
    assert by_axis["forecast"]["value"] is None
    leaked = _select("icr", common, _profile(denominator=_evidence(axis="each", period="2025Q4")))
    assert leaked["rows"] == []
    assert leaked["needs_input"][0]["subject"] == "denominator_evidence"
    assert leaked["needs_input"][0]["reason"] == "axis"
    both = _select("icr", common, _profile())
    published = {row["axis_id"]: row["value"] for row in both["rows"] if row.get("variant") == "bank"}
    assert published == {
        "actuals": Decimal("2.0000000000"),
        "forecast": Decimal("2.0000000000"),
    }


def _series(row: str, periods: list[dict], values: list[str]) -> list[dict]:
    return [_fact(row, period["period_id"], value) for period, value in zip(periods, values, strict=True)]


def _form(code: str) -> dict:
    return {"evidence_json": json.dumps({"line_code": code})}


def _ytd_dep() -> dict:
    return {
        "evidence_json": json.dumps(
            {"period_basis": "ytd", "period_basis_source": "header", "value_basis": "ytd"}
        )
    }


def _ytd_form(code: str) -> dict:
    return {
        "evidence_json": json.dumps(
            {"period_basis": "ytd", "period_basis_source": "header", "line_code": code}
        )
    }


def test_ras_ebitda_is_sales_profit_plus_depreciation():
    got = _select(
        "icr",
        _common(
            [
                _fact("ebitda", "Y1", "999"),
                _fact("sales", "Y1", "100"),
                _fact("dep", "Y1", "40"),
                _fact("interest", "Y1", "20"),
            ],
            [
                _bind("ebitda"),
                _bind("profit_from_sales", "sales"),
                _bind("depreciation_notes", "dep", **_value_basis("period")),
                _bind("interest", **_form("ф.2 (2330)")),
            ],
            [_year()],
        ),
        {"ebitda_definition": "ras", **_profile(denominator=_evidence(standard="fsbu25"))},
    )
    row = got["rows"][0]
    assert row["value"] == Decimal("7.0000000000")
    assert row["inputs"] == ["profit_from_sales", "depreciation_notes", "interest"]
    assert "ebitda" not in row["inputs"]


def test_ifrs_ebitda_is_operating_profit_plus_depreciation():
    profile = {
        "ebitda_definition": "ifrs",
        **_profile(
            finance_costs_confirmed=True,
            denominator=_evidence(binding="finance_costs", standard="ifrs16"),
        ),
    }
    hidden = _select(
        "icr",
        _common(
            [
                _fact("ebitda", "Y1", "999"),
                _fact("model", "Y1", "1"),
                _fact("profit", "Y1", "100"),
                _fact("dep", "Y1", "30"),
                _fact("finance", "Y1", "25"),
            ],
            [
                _bind("ebitda"),
                _bind("operating_profit", "model"),
                _bind("ifrs_operating_profit", "profit"),
                _bind("depreciation_notes", "dep", **_value_basis("period")),
                _bind("finance_costs", "finance"),
            ],
            [_year()],
        ),
        profile,
    )
    assert hidden["status"] == "not_computed"
    assert hidden["reason"] == "depreciation_rou_completeness_unknown"
    assert hidden["rows"] == []
    disclosed = _select(
        "icr",
        _common(
            [
                _fact("ebitda", "Y1", "999"),
                _fact("model", "Y1", "1"),
                _fact("profit", "Y1", "80"),
                _fact("dep", "Y1", "20"),
                _fact("finance", "Y1", "25"),
            ],
            [
                _bind("ebitda"),
                _bind("operating_profit", "model"),
                _bind("ifrs_operating_profit", "profit"),
                _bind("depreciation_notes", "dep", **_notes(includes_rou=True)),
                _bind("finance_costs", "finance"),
            ],
            [_year()],
        ),
        profile,
    )
    row = disclosed["rows"][0]
    assert row["value"] == Decimal("4.0000000000")
    assert "operating_profit" not in row["inputs"]
    assert "ebitda" not in row["inputs"]
    assert row["inputs"] == ["ifrs_operating_profit", "depreciation_notes", "finance_costs"]
    assert "универсальн" in disclosed["profile_note"]
    model_only = _select(
        "icr",
        _common(
            [_fact("model", "Y1", "80"), _fact("dep", "Y1", "20"), _fact("finance", "Y1", "25")],
            [
                _bind("operating_profit", "model"),
                _bind("depreciation_notes", "dep"),
                _bind("finance_costs", "finance"),
            ],
            [_year()],
        ),
        {
            "ebitda_definition": "ifrs",
            **_profile(
                finance_costs_confirmed=True,
                denominator=_evidence(binding="finance_costs", standard="ifrs16"),
            ),
        },
    )
    assert model_only["status"] == "not_computed"
    assert model_only["reason"] == "statement_line_missing"


def test_quarterly_ras_ebitda_sums_matching_depreciation():
    periods = _flow_quarters()
    facts = [
        *_series("sales", periods, ["10", "20", "30", "40"]),
        *_series("dep", periods, ["1", "1", "1", "1"]),
        *_series("interest", periods, ["1", "2", "3", "4"]),
    ]
    got = _select(
        "icr",
        _common(
            facts,
            [
                _bind("profit_from_sales", "sales"),
                _bind("depreciation_notes", "dep", **_value_basis("period")),
                _bind("interest", **_form("ф.2 (2330)")),
            ],
            periods,
        ),
        {"ebitda_definition": "ras", **_profile(denominator=_evidence(standard="fsbu25"))},
    )
    assert _at(got, "2025Q2")["value"] == quantize_ratio(Decimal(104) / Decimal(10))
    step = _at(got, "2025Q2", "quarter_reference")
    assert step["value"] == quantize_ratio(Decimal(41) / Decimal(4))
    assert step["value"] != _at(got, "2025Q2")["value"] * 4


def test_annual_depreciation_does_not_fill_a_quarterly_ltm():
    periods = [
        *_flow_quarters(),
        {
            "axis_id": "notes",
            "period_id": "Y",
            "period_index": 1,
            "grain": "year",
            "timeline_id": "t",
            "calendar_year": 2025,
            "period_end": "2025-12-31",
        },
    ]
    facts = [
        *_series("sales", _flow_quarters(), ["10", "20", "30", "40"]),
        *_series("interest", _flow_quarters(), ["1", "2", "3", "4"]),
        {"row_key": "dep", "axis_id": "notes", "period_id": "Y", "normalized_value": "400"},
    ]
    got = _select(
        "icr",
        _common(
            facts,
            [
                _bind("profit_from_sales", "sales"),
                _bind("depreciation_notes", "dep", **_value_basis("annual")),
                _bind("interest", **_form("ф.2 (2330)")),
            ],
            periods,
        ),
        {"ebitda_definition": "ras", **_profile(denominator=_evidence(standard="fsbu25"))},
    )
    assert got["status"] == "not_computed"
    assert _at(got, "2025Q2")["reason"] == "depreciation_period_mismatch"
    assert _at(got, "2025Q2")["value"] is None
    assert "400" not in json.dumps([row.get("value") for row in got["rows"]])


def test_ytd_ltm_applies_to_profit_depreciation_and_interest():
    periods = _ytd_periods()
    facts = [
        *_series("sales", periods, ["10", "30", "60", "100", "12", "40"]),
        *_series("dep", periods, ["1", "2", "3", "4", "1", "2"]),
        *_series("interest", periods, ["1", "3", "6", "10", "2", "5"]),
    ]
    got = _select(
        "icr",
        _common(
            facts,
            [
                _bind("profit_from_sales", "sales", **_ytd()),
                _bind("depreciation_notes", "dep", **_ytd_dep()),
                _bind("interest", **_ytd_form("ф.2 (2330)")),
            ],
            periods,
        ),
        {"ebitda_definition": "ras", **_profile(denominator=_evidence(standard="fsbu25"))},
    )
    assert _at(got, "2025Q2")["value"] == quantize_ratio(Decimal(114) / Decimal(12))
    assert _at(got, "2025Q2", "quarter_reference")["value"] == quantize_ratio(Decimal(29) / Decimal(3))


def test_statement_basis_must_match_the_denominator():
    sales = [
        _fact("sales", "Y1", "100"),
        _fact("dep", "Y1", "40"),
        _fact("finance", "Y1", "20"),
        _fact("interest", "Y1", "20"),
    ]
    ras_on_ifrs = _select(
        "icr",
        _common(
            sales,
            [
                _bind("profit_from_sales", "sales"),
                _bind("depreciation_notes", "dep", **_value_basis("period")),
                _bind("finance_costs", "finance"),
            ],
            [_year()],
        ),
        {
            "ebitda_definition": "ras",
            **_profile(
                finance_costs_confirmed=True,
                denominator=_evidence(binding="finance_costs", standard="fsbu25"),
            ),
        },
    )
    assert ras_on_ifrs["status"] == "not_computed"
    assert ras_on_ifrs["reason"] == "statement_basis_mismatch"
    ifrs_on_ras = _select(
        "icr",
        _common(
            sales,
            [
                _bind("ifrs_operating_profit", "sales"),
                _bind("depreciation_notes", "dep", **_notes(includes_rou=True)),
                _bind("interest", **_form("ф.2 (2330)")),
            ],
            [_year()],
        ),
        {"ebitda_definition": "ifrs", **_profile(denominator=_evidence(standard="ifrs16"))},
    )
    assert ifrs_on_ras["status"] == "not_computed"
    assert ifrs_on_ras["reason"] == "statement_basis_mismatch"
    ras_without_code = _select(
        "icr",
        _common(
            sales,
            [
                _bind("profit_from_sales", "sales"),
                _bind("depreciation_notes", "dep", **_value_basis("period")),
                _bind("interest"),
            ],
            [_year()],
        ),
        {"ebitda_definition": "ras", **_profile(denominator=_evidence(standard="fsbu25"))},
    )
    assert ras_without_code["reason"] == "statement_basis_mismatch"


def test_capital_lease_ebitda_cannot_add_lease_interest_again():
    common = _common(
        [
            _fact("profit", "Y1", "80"),
            _fact("dep", "Y1", "20"),
            _fact("interest", "Y1", "10"),
            _fact("lease", "Y1", "7"),
        ],
        [
            _bind("ifrs_operating_profit", "profit"),
            _bind("depreciation_notes", "dep", **_notes(includes_rou=True)),
            _bind("interest"),
            _bind("lease_interest", "lease"),
        ],
        [_year()],
    )
    doubled = _select(
        "icr",
        common,
        {
            "ebitda_definition": "ifrs",
            **_profile("add_interest", denominator=_evidence(standard="ifrs16")),
        },
    )
    assert doubled["status"] == "not_computed"
    assert doubled["reason"] == "lease_ebitda_double_count"
    assert doubled["rows"] == []
    ras = _select(
        "icr",
        _common(
            [
                _fact("sales", "Y1", "80"),
                _fact("dep", "Y1", "20"),
                _fact("interest", "Y1", "10"),
                _fact("lease", "Y1", "7"),
            ],
            [
                _bind("profit_from_sales", "sales"),
                _bind("depreciation_notes", "dep", **_value_basis("period")),
                _bind("interest", **_form("ф.2 (2330)")),
                _bind("lease_interest", "lease"),
            ],
            [_year()],
        ),
        {
            "ebitda_definition": "ras",
            **_profile("add_interest", denominator=_evidence(standard="фсбу 25")),
        },
    )
    assert ras["reason"] == "lease_ebitda_double_count"
    matched = _select(
        "icr",
        common,
        {
            "ebitda_definition": "ifrs",
            **_profile("add_interest", denominator=_evidence(standard="operating")),
        },
    )
    assert matched["rows"][0]["value"] == quantize_ratio(Decimal(100) / Decimal(17))
    blank = _profile("add_interest")
    blank["icr_definition"]["denominator"]["standard"] = " "
    blank_result = _select("icr", common, {"ebitda_definition": "ifrs", **blank})
    assert blank_result["status"] == "needs_input"
    assert blank_result["needs_input"][0]["subject"] == "lease_standard"
    kept = _select(
        "icr",
        common,
        {"ebitda_definition": "ifrs", **_profile(denominator=_evidence(standard="ifrs16"))},
    )
    assert kept["rows"][0]["value"] == Decimal("10.0000000000")
    assert "lease_interest" not in kept["rows"][0]["inputs"]
    assert kept["warnings"][0]["code"] == "lease_interest_double_count"


def _value_basis(basis: str) -> dict:
    return {"evidence_json": json.dumps({"value_basis": basis})}


def _notes(**extra) -> dict:
    payload = {"value_basis": "period", "includes_rou_source": "пояснения", **extra}
    return {"evidence_json": json.dumps(payload)}


def _includes_rou() -> dict:
    return _notes(includes_rou=True)


def test_quarterly_cell_needs_its_own_depreciation_basis():
    """Ячейка 2025Q4 с годовой амортизацией не квартал, пока база суммы не подтверждена."""

    periods = _flow_quarters()
    facts = [
        *_series("sales", periods, ["10", "20", "30", "40"]),
        *_series("dep", periods, ["1", "1", "1", "400"]),
        *_series("interest", periods, ["1", "2", "3", "4"]),
    ]
    bindings = [
        _bind("profit_from_sales", "sales"),
        _bind("depreciation_notes", "dep"),
        _bind("interest", **_form("ф.2 (2330)")),
    ]
    profile = {"ebitda_definition": "ras", **_profile(denominator=_evidence(standard="fsbu25"))}
    unknown = _select("icr", _common(facts, bindings, periods), profile)
    assert unknown["status"] == "not_computed"
    assert unknown["reason"] == "depreciation_basis_unknown"
    assert unknown["rows"] == []
    annual = _select(
        "icr",
        _common(
            facts,
            [
                _bind("profit_from_sales", "sales"),
                _bind("depreciation_notes", "dep", **_value_basis("annual")),
                _bind("interest", **_form("ф.2 (2330)")),
            ],
            periods,
        ),
        profile,
    )
    assert annual["status"] == "not_computed"
    assert _at(annual, "2025Q2")["reason"] == "depreciation_period_mismatch"
    assert "400" not in json.dumps([row.get("value") for row in annual["rows"]])


def test_unknown_lease_standard_is_not_allowed():
    common = _common(
        [_fact("ebitda", "Y1", "80"), _fact("interest", "Y1", "10")],
        [_bind("ebitda"), _bind("interest")],
        [_year()],
    )
    for standard in ("ifrs17", "фсбу 52", "operatng"):
        got = _select("icr", common, _profile(denominator=_evidence(standard=standard)))
        assert got["status"] == "needs_input", standard
        assert got["needs_input"][0]["subject"] == "lease_standard"
        assert got["rows"] == []


def test_includes_rou_is_a_confirmed_mark_on_depreciation_notes_only(tmp_path):
    from finance_analysis.adapters.storage.store import LocalStore
    from finance_analysis.application.journal import Journal
    from finance_analysis.domain.binding_evidence import depreciation_evidence_error
    from finance_analysis.domain.book import Actor
    from finance_analysis.domain.errors import InvalidArgument

    assert depreciation_evidence_error("interest", {"includes_rou": True, "includes_rou_source": "пояснения"})
    assert depreciation_evidence_error("depreciation_notes", {"includes_rou": "yes"})
    assert depreciation_evidence_error("depreciation_notes", {"includes_rou": True})
    assert depreciation_evidence_error("depreciation_notes", {"value_basis": "quarter"})
    assert depreciation_evidence_error("interest", {"value_basis": "period"})
    assert (
        depreciation_evidence_error(
            "depreciation_notes",
            {"includes_rou": True, "includes_rou_source": "пояснение 4", "value_basis": "annual"},
        )
        is None
    )

    async def run():
        journal = Journal(LocalStore(tmp_path))
        job = "c" * 64
        actor = Actor(user_id="alex", client_id="desk")
        evidence = {"includes_rou": True, "includes_rou_source": "пояснение 4", "value_basis": "annual"}
        try:
            await journal.commit(
                job,
                target="row",
                event_type="concept.confirmed",
                value="interest",
                actor=actor,
                expected_seq=None,
                request_id="bad",
                binding_key="row",
                evidence={"includes_rou": True, "includes_rou_source": "пояснение 4"},
            )
        except InvalidArgument:
            pass
        else:
            raise AssertionError("includes_rou на interest должен быть отказом")
        event, duplicate = await journal.commit(
            job,
            target="row",
            event_type="concept.confirmed",
            value="depreciation_notes",
            actor=actor,
            expected_seq=None,
            request_id="ok",
            binding_key="row",
            evidence=evidence,
        )
        assert duplicate is False
        assert event["evidence"]["includes_rou"] is True
        row = {
            "kind": "fact",
            "binding_key": "row",
            "row_key": "row",
            "label": "Строка без метки",
            "label_path_text": "Строка без метки",
            "sign": None,
            "unit": "money",
        }
        item = assign_rows([row], await journal.read_all(job), load_catalog())["row"]
        assert item.evidence["includes_rou"] is True
        assert item.evidence["includes_rou_source"] == "пояснение 4"
        assert item.evidence["value_basis"] == "annual"
        provenance = item.evidence["includes_rou_provenance"]
        assert provenance["source"] == "пояснение 4"
        assert provenance["seq"] == event["seq"]
        assert provenance["actor"] == {"user_id": "alex", "client_id": "desk"}

    asyncio.run(run())


def _ras_profile(**extra) -> dict:
    return {"ebitda_definition": "ras", **_profile(denominator=_evidence(standard="fsbu25"), **extra)}


def _ifrs_profile(**extra) -> dict:
    return {"ebitda_definition": "ifrs", **_profile(denominator=_evidence(standard="ifrs16"), **extra)}


def test_the_same_depreciation_total_keeps_rou_out_of_ras_and_inside_ifrs():
    """Одна и та же амортизация: 25 по ОС и НМА и 15 по праву пользования, итог 40.

    РСБУ берёт только ФСБУ 6 и ФСБУ 14. МСФО берёт итог вместе с IFRS 16.
    Общая строка, из которой право пользования не вычитается, для РСБУ не считается.
    """

    split = [
        _fact("ebitda", "Y1", "999"),
        _fact("sales", "Y1", "100"),
        _fact("profit", "Y1", "80"),
        _fact("ppe", "Y1", "25"),
        _fact("rou", "Y1", "15"),
        _fact("interest", "Y1", "20"),
    ]
    ras = _select(
        "icr",
        _common(
            split,
            [
                _bind("ebitda"),
                _bind("profit_from_sales", "sales"),
                _bind("depreciation_notes", "ppe", **_value_basis("period")),
                _bind("depreciation_rou", "rou", **_value_basis("period")),
                _bind("interest", **_form("ф.2 (2330)")),
            ],
            [_year()],
        ),
        _ras_profile(),
    )
    ifrs = _select(
        "icr",
        _common(
            split,
            [
                _bind("ebitda"),
                _bind("ifrs_operating_profit", "profit"),
                _bind("depreciation_notes", "ppe", **_value_basis("period")),
                _bind("depreciation_rou", "rou", **_value_basis("period")),
                _bind("interest"),
            ],
            [_year()],
        ),
        _ifrs_profile(),
    )
    assert ras["rows"][0]["value"] == quantize_ratio(Decimal(125) / Decimal(20))
    assert "depreciation_rou" not in ras["rows"][0]["inputs"]
    assert ifrs["rows"][0]["value"] == quantize_ratio(Decimal(120) / Decimal(20))
    assert "depreciation_rou" in ifrs["rows"][0]["inputs"]
    assert ras["profile"] == "icr.bank"
    assert ras["regulatory_6960u"] is False
    assert "6960-У" in ras["profile_note"]
    mixed = [
        _fact("sales", "Y1", "100"),
        _fact("profit", "Y1", "80"),
        _fact("dep", "Y1", "40"),
        _fact("rou", "Y1", "15"),
        _fact("interest", "Y1", "20"),
    ]
    ras_split = _select(
        "icr",
        _common(
            mixed,
            [
                _bind("profit_from_sales", "sales"),
                _bind("depreciation_notes", "dep", **_includes_rou()),
                _bind("depreciation_rou", "rou", **_value_basis("period")),
                _bind("interest", **_form("ф.2 (2330)")),
            ],
            [_year()],
        ),
        _ras_profile(),
    )
    ifrs_total = _select(
        "icr",
        _common(
            mixed,
            [
                _bind("ifrs_operating_profit", "profit"),
                _bind("depreciation_notes", "dep", **_includes_rou()),
                _bind("depreciation_rou", "rou", **_value_basis("period")),
                _bind("interest"),
            ],
            [_year()],
        ),
        _ifrs_profile(),
    )
    assert ras_split["rows"][0]["value"] == quantize_ratio(Decimal(125) / Decimal(20))
    assert ifrs_total["rows"][0]["value"] == quantize_ratio(Decimal(120) / Decimal(20))
    assert "depreciation_rou" not in ifrs_total["rows"][0]["inputs"]
    held = _select(
        "icr",
        _common(
            [
                _fact("sales", "Y1", "100"),
                _fact("dep", "Y1", "40"),
                _fact("interest", "Y1", "20"),
            ],
            [
                _bind("profit_from_sales", "sales"),
                _bind("depreciation_notes", "dep", **_includes_rou()),
                _bind("interest", **_form("ф.2 (2330)")),
            ],
            [_year()],
        ),
        _ras_profile(),
    )
    assert held["status"] == "not_computed"
    assert held["reason"] == "depreciation_rou_unseparated"
    assert held["rows"] == []
    allowed = _select(
        "icr",
        _common(
            [
                _fact("sales", "Y1", "100"),
                _fact("dep", "Y1", "40"),
                _fact("interest", "Y1", "20"),
            ],
            [
                _bind("profit_from_sales", "sales"),
                _bind("depreciation_notes", "dep", **_includes_rou()),
                _bind("interest", **_form("ф.2 (2330)")),
            ],
            [_year()],
        ),
        _ras_profile(include_rou_depreciation=True),
    )
    assert allowed["rows"][0]["value"] == quantize_ratio(Decimal(140) / Decimal(20))
