"""Банковский ICR: срезы 1–5. Рецепт РСБУ и МСФО остаётся not_computed."""

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


def test_ras_recipe_stays_not_computed():
    got = _select(
        "icr",
        _common(
            [_fact("ebitda", "Y1", "30"), _fact("interest", "Y1", "10")],
            [_bind("ebitda"), _bind("interest")],
            [_year()],
        ),
        {"ebitda_definition": "ras", **_profile()},
    )
    assert got["status"] == "not_computed"
    assert got["rows"] == []


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


def test_gaap_is_not_the_ifrs_recipe():
    from finance_analysis.domain.metrics import _recipe_message

    got = _select(
        "icr",
        _common(
            [_fact("ebitda", "Y1", "30"), _fact("interest", "Y1", "10")],
            [_bind("ebitda"), _bind("interest")],
            [_year()],
        ),
        {"ebitda_definition": "gaap", **_profile()},
    )
    assert got["status"] == "not_computed"
    assert got["rows"] == []
    assert got["message"] == _recipe_message("gaap")
    assert got["message"] != _recipe_message("ifrs")


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
        _profile(denominator=_evidence(period="Y1")),
    )
    assert _at(got, "Y1")["value"] == Decimal("2.0000000000")
    assert _at(got, "Y2")["status"] == "needs_input"
    assert _at(got, "Y2")["reason"] == "denominator_period"


def _series(row: str, periods: list[dict], values: list[str]) -> list[dict]:
    return [_fact(row, period["period_id"], value) for period, value in zip(periods, values, strict=True)]
