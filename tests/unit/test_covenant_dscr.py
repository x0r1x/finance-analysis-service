"""Ковенантный DSCR, гибрид и покрытие эскроу (срез 2). Синтетические строки, без книг клиентов."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from finance_analysis.domain.covenant import (
    DEFAULT_DEFINITION_TEXT,
    covenant_dscr,
    dscr_definition_error,
    select_ratio,
)
from finance_analysis.domain.cover_metrics import ratio_cells
from finance_analysis.domain.model_type import (
    Effective,
    applicability,
    confirmed_variants,
    infer,
)

_MONEY = frozenset(
    {
        "ebitda",
        "cash_taxes",
        "capex",
        "interest",
        "principal",
        "net_debt",
        "escrow_balance",
        "debt_outstanding",
    }
)
_CONCEPTS = _MONEY | {"dscr", "dscr_covenant", "icr"}


def _catalog():
    from finance_analysis.application.model_types import load_model_types

    return load_model_types()


def _bind(concept: str, row: str) -> dict:
    return {
        "effective_concept": concept,
        "row_key": row,
        "is_primary": True,
        "status": "bound",
        "source": "inferred",
    }


def _fact(row: str, period: str, value: str, *, cell: str | None = None) -> dict:
    item = {
        "row_key": row,
        "axis_id": "a",
        "period_id": period,
        "normalized_value": value,
    }
    if cell:
        item["cell_id"] = cell
    return item


def _year(period: str = "Y1") -> dict:
    return {"axis_id": "a", "period_id": period, "period_index": 1, "grain": "year", "timeline_id": "t"}


def test_default_covenant_on_a_year_marks_that_it_is_not_from_a_contract():
    catalog = _catalog()
    formula = catalog.composed["dscr.corporate_covenant"]
    assert formula.window == "LTM"
    assert formula.numerator.plus == ("ebitda",)
    assert formula.numerator.minus == ("cash_taxes", "capex")
    assert formula.denominator.plus == ("interest", "principal")
    got = covenant_dscr(
        facts=[
            _fact("e", "Y1", "100", cell="ОПиУ!B2"),
            _fact("t", "Y1", "10", cell="ДДС!B3"),
            _fact("c", "Y1", "20"),
            _fact("i", "Y1", "15"),
            _fact("p", "Y1", "5"),
        ],
        bindings=[
            _bind("ebitda", "e"),
            _bind("cash_taxes", "t"),
            _bind("capex", "c"),
            _bind("interest", "i"),
            _bind("principal", "p"),
        ],
        periods=[_year()],
        default=formula,
        concepts=_CONCEPTS,
        money=_MONEY,
    )
    assert got["definition_source"] == "default"
    assert got["definition_ref"] is None
    assert got["warnings"][0] == {
        "code": "dscr_default_definition",
        "params": {"text": DEFAULT_DEFINITION_TEXT},
    }
    assert DEFAULT_DEFINITION_TEXT == "определение по умолчанию, не из договора"
    assert got["rows"][0]["value"] == Decimal("3.5000000000")
    cited = ratio_cells(got["rows"][0], [
        _fact("e", "Y1", "100", cell="ОПиУ!B2"),
        _fact("t", "Y1", "10", cell="ДДС!B3"),
        _fact("c", "Y1", "20"),
        _fact("i", "Y1", "15"),
        _fact("p", "Y1", "5"),
    ], [
        _bind("ebitda", "e"),
        _bind("cash_taxes", "t"),
        _bind("capex", "c"),
        _bind("interest", "i"),
        _bind("principal", "p"),
    ], [_year()], frozenset())
    assert {item["cell_id"] for item in cited} == {"ОПиУ!B2", "ДДС!B3"}


def test_profile_definition_overrides_structure_without_numbers():
    catalog = _catalog()
    raw = {
        "numerator": {"plus": ["ebitda"], "minus": []},
        "denominator": {"plus": ["interest"]},
        "window": "period",
        "basis_ref": "кредитный договор, п. 4.2",
    }
    assert dscr_definition_error(raw, concepts=_CONCEPTS, money=_MONEY) is None
    got = covenant_dscr(
        facts=[
            _fact("e", "Y1", "100"),
            _fact("t", "Y1", "10"),
            _fact("c", "Y1", "20"),
            _fact("i", "Y1", "15"),
            _fact("p", "Y1", "5"),
        ],
        bindings=[
            _bind("ebitda", "e"),
            _bind("cash_taxes", "t"),
            _bind("capex", "c"),
            _bind("interest", "i"),
            _bind("principal", "p"),
        ],
        periods=[_year()],
        profile={"dscr_definition": raw},
        profile_ref="desk@p-3",
        default=catalog.composed["dscr.corporate_covenant"],
        concepts=_CONCEPTS,
        money=_MONEY,
    )
    assert got["definition_source"] == "profile"
    assert got["definition_ref"] == {
        "profile_id": "desk",
        "profile_version": "desk@p-3",
        "basis_ref": "кредитный договор, п. 4.2",
    }
    assert all(item["code"] != "dscr_default_definition" for item in got["warnings"])
    assert got["rows"][0]["value"] == Decimal("6.6666666667")


def test_profile_definition_rejects_numbers_unknown_terms_and_a_cycle():
    numbered = {
        "numerator": {"plus": ["ebitda"], "minus": ["cash_taxes"]},
        "denominator": {"plus": ["interest"]},
        "window": "LTM",
        "threshold": 1.2,
    }
    assert dscr_definition_error(numbered, concepts=_CONCEPTS, money=_MONEY)
    cycle = {
        "numerator": {"plus": ["dscr"]},
        "denominator": {"plus": ["interest"]},
        "window": "LTM",
    }
    assert dscr_definition_error(cycle, concepts=_CONCEPTS, money=_MONEY)
    foreign = {
        "numerator": {"plus": ["ebitda"]},
        "denominator": {"plus": ["not_a_concept"]},
        "window": "year",
    }
    assert dscr_definition_error(foreign, concepts=_CONCEPTS, money=_MONEY)
    empty = {
        "numerator": {"plus": ["ebitda"]},
        "denominator": {"plus": []},
        "window": "LTM",
    }
    assert dscr_definition_error(empty, concepts=_CONCEPTS, money=_MONEY)


def test_ltm_sums_four_quarters_and_period_window_does_not():
    catalog = _catalog()
    periods = [
        _quarter(1, date(2024, 1, 1), date(2024, 3, 31)),
        _quarter(2, date(2024, 4, 1), date(2024, 6, 30)),
        _quarter(3, date(2024, 7, 1), date(2024, 9, 30)),
        _quarter(4, date(2024, 10, 1), date(2024, 12, 31)),
    ]
    facts = []
    for index, ebitda in ((1, "10"), (2, "10"), (3, "10"), (4, "70")):
        period = f"Q{index}"
        facts.extend(
            [
                _fact("e", period, ebitda),
                _fact("t", period, "0"),
                _fact("c", period, "0"),
                _fact("i", period, "5"),
                _fact("p", period, "0"),
            ]
        )
    bindings = [
        _bind("ebitda", "e"),
        _bind("cash_taxes", "t"),
        _bind("capex", "c"),
        _bind("interest", "i"),
        _bind("principal", "p"),
    ]
    default = covenant_dscr(
        facts=facts,
        bindings=bindings,
        periods=periods,
        default=catalog.composed["dscr.corporate_covenant"],
        concepts=_CONCEPTS,
        money=_MONEY,
    )
    by_period = {row["period_id"]: row for row in default["rows"]}
    assert by_period["Q1"]["status"] == "not_computed"
    assert by_period["Q4"]["value"] == Decimal("5.0000000000")
    period_only = {
        "numerator": {"plus": ["ebitda"], "minus": ["cash_taxes", "capex"]},
        "denominator": {"plus": ["interest", "principal"]},
        "window": "period",
    }
    scoped = covenant_dscr(
        facts=facts,
        bindings=bindings,
        periods=periods,
        profile={"dscr_definition": period_only},
        profile_ref="desk@p-1",
        default=catalog.composed["dscr.corporate_covenant"],
        concepts=_CONCEPTS,
        money=_MONEY,
    )
    last = {row["period_id"]: row for row in scoped["rows"]}["Q4"]
    assert last["value"] == Decimal("14.0000000000")


def test_a_hole_inside_the_ltm_window_keeps_a_missing_input_row():
    catalog = _catalog()
    periods = [
        _quarter(1, date(2024, 1, 1), date(2024, 3, 31)),
        _quarter(2, date(2024, 4, 1), date(2024, 6, 30)),
        _quarter(3, date(2024, 7, 1), date(2024, 9, 30)),
        _quarter(4, date(2024, 10, 1), date(2024, 12, 31)),
    ]
    facts = []
    for index in range(1, 5):
        period = f"Q{index}"
        facts.extend(
            [
                _fact("e", period, "10"),
                _fact("t", period, "0"),
                _fact("i", period, "5"),
                _fact("p", period, "0"),
            ]
        )
        if index != 2:
            facts.append(_fact("c", period, "0"))
    got = covenant_dscr(
        facts=facts,
        bindings=[
            _bind("ebitda", "e"),
            _bind("cash_taxes", "t"),
            _bind("capex", "c"),
            _bind("interest", "i"),
            _bind("principal", "p"),
        ],
        periods=periods,
        default=catalog.composed["dscr.corporate_covenant"],
        concepts=_CONCEPTS,
        money=_MONEY,
    )
    by_period = {row["period_id"]: row for row in got["rows"]}
    assert by_period["Q1"]["reason"] == "partial_window"
    assert by_period["Q4"]["status"] == "missing_input"
    assert by_period["Q4"]["reason"] == "no_binding"
    assert got["status"] == "succeeded"


def test_default_definition_mismatch_with_the_book_row_is_not_a_model_error():
    catalog = _catalog()
    common = {
        "facts": [
            _fact("e", "Y1", "100"),
            _fact("t", "Y1", "10"),
            _fact("c", "Y1", "20"),
            _fact("i", "Y1", "15"),
            _fact("p", "Y1", "5"),
            _fact("k", "Y1", "1.10"),
        ],
        "bindings": [
            _bind("ebitda", "e"),
            _bind("cash_taxes", "t"),
            _bind("capex", "c"),
            _bind("interest", "i"),
            _bind("principal", "p"),
            _bind("dscr_covenant", "k"),
        ],
        "periods": [_year()],
        "default": catalog.composed["dscr.corporate_covenant"],
        "concepts": _CONCEPTS,
        "money": _MONEY,
    }
    got = covenant_dscr(**common)
    assert got["rows"][0]["value"] == Decimal("3.5000000000")
    assert any(item["code"] == "covenant_definition_mismatch" for item in got["warnings"])
    same = covenant_dscr(
        **{
            **common,
            "facts": [item for item in common["facts"] if item["row_key"] != "k"] + [_fact("k", "Y1", "3.5")],
        }
    )
    assert all(item["code"] != "covenant_definition_mismatch" for item in same["warnings"])


def test_unresolved_tie_keeps_the_base_dscr_formula():
    catalog = _catalog()
    unresolved = Effective(
        ("corporate", "project_finance"),
        "corporate",
        "unresolved",
        "gap",
        None,
        None,
        1.0,
        {"corporate": 1.0, "project_finance": 1.0},
        (),
    )
    assert confirmed_variants(catalog, unresolved) == {}
    confirmed = Effective(("corporate",), "corporate", "inferred", None, None, None, 1.0, {"corporate": 1.0}, ())
    assert confirmed_variants(catalog, confirmed)["dscr"] == "corporate_covenant"
    common = {
        "facts": [
            _fact("e", "Y1", "100"),
            _fact("t", "Y1", "10"),
            _fact("c", "Y1", "20"),
            _fact("i", "Y1", "15"),
            _fact("p", "Y1", "5"),
            _fact("f", "Y1", "10"),
            _fact("d", "Y1", "4"),
        ],
        "bindings": [
            _bind("ebitda", "e"),
            _bind("cash_taxes", "t"),
            _bind("capex", "c"),
            _bind("interest", "i"),
            _bind("principal", "p"),
            _bind("cfads", "f"),
            _bind("debt_service", "d"),
        ],
        "periods": [_year()],
        "period_phase": {},
        "explicit_phases": False,
        "sign_convention": "outflow_negative",
        "marker_class": None,
        "absent": frozenset(),
    }
    base = select_ratio(
        "dscr",
        None,
        common,
        profile={},
        profile_ref=None,
        composed=catalog.composed,
        concepts=catalog.concepts,
        money=_MONEY,
    )
    covenant = select_ratio(
        "dscr",
        "corporate_covenant",
        common,
        profile={},
        profile_ref=None,
        composed=catalog.composed,
        concepts=catalog.concepts,
        money=_MONEY,
    )
    assert base["rows"][0]["value"] == Decimal("2.5000000000")
    assert covenant["rows"][0]["value"] == Decimal("3.5000000000")
    assert covenant["definition_source"] == "default"


def test_hybrid_of_escrow_and_project_finance_keeps_both_labels():
    catalog = _catalog()
    got = infer(
        catalog,
        bound=frozenset({"cfads", "debt_service", "escrow_balance"}),
        sheets=frozenset({"Debt"}),
        accept=0.6,
        gap=0.15,
    )
    assert got.confident is True
    assert got.labels == ("development_escrow", "project_finance")
    assert got.primary == "development_escrow"
    assert applicability(catalog, got.labels, "dscr") == "required"
    assert applicability(catalog, got.labels, "escrow_coverage") == "required"
    assert catalog.types["development_escrow"].variants["dscr"] == "pf"
    assert catalog.types["corporate"].variants["dscr"] == "corporate_covenant"


def test_ltm_ebitda_is_one_cell_and_cites_the_net_debt_cell():
    import json

    from finance_analysis.domain.covenant import composed_ratio

    catalog = _catalog()
    periods = [
        _quarter(1, date(2024, 1, 1), date(2024, 3, 31)),
        _quarter(2, date(2024, 4, 1), date(2024, 6, 30)),
        _quarter(3, date(2024, 7, 1), date(2024, 9, 30)),
        _quarter(4, date(2024, 10, 1), date(2024, 12, 31)),
    ]
    debt_periods = [
        {**period, "axis_id": "debt", "timeline_id": "debt", "period_id": f"D{index}"}
        for index, period in enumerate(periods, start=1)
    ]
    facts = []
    for index, ebitda in ((1, "10"), (2, "10"), (3, "10"), (4, "40")):
        facts.append(_fact("e", f"Q{index}", ebitda, cell=f"E{index}"))
        facts.append({**_fact("n", f"D{index}", "100", cell=f"N{index}"), "axis_id": "debt"})
    ebitda = _bind("ebitda", "e")
    ebitda["evidence_json"] = json.dumps({"period_basis": "ltm", "period_basis_source": "header"})
    got = composed_ratio(
        "net_debt_ebitda",
        catalog.composed["net_debt_ebitda"],
        facts=facts,
        bindings=[_bind("net_debt", "n"), ebitda],
        periods=[*periods, *debt_periods],
    )
    by_period = {row["period_id"]: row for row in got["rows"]}
    assert by_period["Q1"]["status"] == "computed"
    assert by_period["Q1"]["value"] == Decimal("10.0000000000")
    assert by_period["Q4"]["status"] == "computed"
    assert by_period["Q4"]["value"] == Decimal("2.5000000000")
    assert by_period["Q4"]["window"] == ["Q4"]
    cited = ratio_cells(by_period["Q4"], facts, [_bind("net_debt", "n"), ebitda], [*periods, *debt_periods], frozenset())
    assert {item["cell_id"] for item in cited} == {"N4", "E4"}


def test_net_debt_ebitda_uses_the_ending_stock_and_raw_ebitda():
    from finance_analysis.domain.covenant import composed_ratio

    catalog = _catalog()
    formula = catalog.composed["net_debt_ebitda"]
    periods = [
        _quarter(1, date(2024, 1, 1), date(2024, 3, 31)),
        _quarter(2, date(2024, 4, 1), date(2024, 6, 30)),
        _quarter(3, date(2024, 7, 1), date(2024, 9, 30)),
        _quarter(4, date(2024, 10, 1), date(2024, 12, 31)),
    ]
    facts = []
    for index in range(1, 5):
        facts.extend([_fact("n", f"Q{index}", "100"), _fact("e", f"Q{index}", "10")])
    got = composed_ratio(
        "net_debt_ebitda",
        formula,
        facts=facts,
        bindings=[_bind("net_debt", "n"), _bind("ebitda", "e")],
        periods=periods,
    )
    by_period = {row["period_id"]: row for row in got["rows"]}
    assert by_period["Q1"]["status"] == "not_computed"
    assert by_period["Q4"]["value"] == Decimal("2.5000000000")
    year = composed_ratio(
        "net_debt_ebitda",
        formula,
        facts=[_fact("n", "Y1", "100"), _fact("e", "Y1", "-40")],
        bindings=[_bind("net_debt", "n"), _bind("ebitda", "e")],
        periods=[_year()],
    )
    assert year["rows"][0]["value"] == Decimal("-2.5000000000")


def test_net_debt_with_one_scale_divides_the_sheet_figures():
    from finance_analysis.domain.covenant import composed_ratio
    from finance_analysis.domain.metrics import SCALE_ASSUMED

    catalog = _catalog()
    periods = [
        _quarter(1, date(2024, 1, 1), date(2024, 3, 31)),
        _quarter(2, date(2024, 4, 1), date(2024, 6, 30)),
        _quarter(3, date(2024, 7, 1), date(2024, 9, 30)),
        _quarter(4, date(2024, 10, 1), date(2024, 12, 31)),
    ]
    facts = []
    for index in range(1, 5):
        facts.append({**_fact("n", f"Q{index}", "100"), "value_dec": Decimal(100)})
        facts.append(
            {
                **_fact("e", f"Q{index}", "10000"),
                "value_dec": Decimal(10),
                "scale_factor": 1000,
            }
        )
    got = composed_ratio(
        "net_debt_ebitda",
        catalog.composed["net_debt_ebitda"],
        facts=facts,
        bindings=[_bind("net_debt", "n"), _bind("ebitda", "e")],
        periods=periods,
    )
    assert got["rows"][-1]["value"] == Decimal("2.5000000000")
    assert got["warnings"] == [{"code": "scale_assumed", "params": {"message": SCALE_ASSUMED}}]


def test_net_debt_ebitda_reports_when_net_debt_is_off_the_ratio_axis():
    from finance_analysis.domain.covenant import composed_ratio

    catalog = _catalog()
    periods = [
        _quarter(1, date(2024, 1, 1), date(2024, 3, 31)),
        _quarter(2, date(2024, 4, 1), date(2024, 6, 30)),
        _quarter(3, date(2024, 7, 1), date(2024, 9, 30)),
        _quarter(4, date(2024, 10, 1), date(2024, 12, 31)),
    ]
    facts = []
    for index in range(1, 5):
        facts.append(_fact("e", f"Q{index}", "10"))
        facts.append({**_fact("n", f"Q{index}", "100"), "axis_id": "debt"})
    got = composed_ratio(
        "net_debt_ebitda",
        catalog.composed["net_debt_ebitda"],
        facts=facts,
        bindings=[_bind("net_debt", "n"), _bind("ebitda", "e")],
        periods=periods,
    )
    assert got["status"] == "input_absent"
    assert got["message"] == (
        "Чистый долг не содержит значений на оси, по которой считается отношение к EBITDA. "
        "Коэффициент не рассчитан."
    )
    final = next(row for row in got["rows"] if row["period_id"] == "Q4")
    assert final["status"] == "input_absent"
    assert final["message"] == got["message"]
    assert not any(row["status"] == "computed" for row in got["rows"])


def test_net_debt_on_another_axis_is_read_at_the_same_period_end():
    from finance_analysis.domain.covenant import composed_ratio

    catalog = _catalog()
    periods = [
        _quarter(1, date(2024, 1, 1), date(2024, 3, 31)),
        _quarter(2, date(2024, 4, 1), date(2024, 6, 30)),
        _quarter(3, date(2024, 7, 1), date(2024, 9, 30)),
        _quarter(4, date(2024, 10, 1), date(2024, 12, 31)),
    ]
    debt_periods = [
        {**period, "axis_id": "debt", "timeline_id": "debt", "period_id": f"D{index}"}
        for index, period in enumerate(periods, start=1)
    ]
    facts = []
    for index in range(1, 5):
        facts.append(_fact("e", f"Q{index}", "10"))
        facts.append({**_fact("n", f"D{index}", "100"), "axis_id": "debt"})
    got = composed_ratio(
        "net_debt_ebitda",
        catalog.composed["net_debt_ebitda"],
        facts=facts,
        bindings=[_bind("net_debt", "n"), _bind("ebitda", "e")],
        periods=[*periods, *debt_periods],
    )
    final = next(row for row in got["rows"] if row["period_id"] == "Q4")
    assert final["status"] == "computed"
    assert final["value"] == Decimal("2.5000000000")


def test_net_debt_off_the_ratio_axis_is_reported_before_the_window_is_full():
    from finance_analysis.domain.covenant import composed_ratio

    catalog = _catalog()
    periods = [
        _quarter(1, date(2024, 1, 1), date(2024, 3, 31)),
        _quarter(2, date(2024, 4, 1), date(2024, 6, 30)),
        _quarter(3, date(2024, 7, 1), date(2024, 9, 30)),
    ]
    facts = []
    for index in range(1, 4):
        facts.append(_fact("e", f"Q{index}", "10"))
        facts.append({**_fact("n", f"Q{index}", "100"), "axis_id": "debt"})
    got = composed_ratio(
        "net_debt_ebitda",
        catalog.composed["net_debt_ebitda"],
        facts=facts,
        bindings=[_bind("net_debt", "n"), _bind("ebitda", "e")],
        periods=periods,
    )
    assert got["status"] == "input_absent"
    assert got["message"].startswith("Чистый долг не содержит значений")
    assert got["rows"]
    assert {row["status"] for row in got["rows"]} == {"input_absent"}


def test_escrow_coverage_is_balance_over_outstanding():
    from finance_analysis.domain.covenant import composed_ratio

    catalog = _catalog()
    got = composed_ratio(
        "escrow_coverage",
        catalog.composed["escrow_coverage"],
        facts=[_fact("s", "Y1", "200"), _fact("d", "Y1", "100")],
        bindings=[_bind("escrow_balance", "s"), _bind("debt_outstanding", "d")],
        periods=[_year()],
    )
    assert got["rows"][0]["value"] == Decimal("2.0000000000")
    assert got["status"] == "succeeded"


def test_interest_order_is_read_from_coverage_config():
    order = _catalog().interest_order
    assert order["icr"] == ("interest", "interest_paid")
    assert order["corporate_covenant"] == ("interest", "interest_paid")
    assert order["pf"] == ("interest_paid", "interest")


def test_icr_uses_accrued_interest_before_paid_interest():
    from finance_analysis.domain.metrics import INTEREST_BASIS_FALLBACK, coverage_ratio

    order = _catalog().interest_order
    periods = [_year()]
    both = coverage_ratio(
        metric="icr",
        facts=[_fact("e", "Y1", "40"), _fact("i", "Y1", "-10"), _fact("p", "Y1", "-4")],
        bindings=[_bind("ebitda", "e"), _bind("interest", "i"), _bind("interest_paid", "p")],
        periods=periods,
        period_phase={},
        explicit_phases=False,
        interest_order=order,
    )
    assert both["rows"][0]["value"] == Decimal("4.0000000000")
    assert not any(item["code"] == "interest_basis_fallback" for item in both["warnings"])
    paid = coverage_ratio(
        metric="icr",
        facts=[_fact("e", "Y1", "40"), _fact("p", "Y1", "-8")],
        bindings=[_bind("ebitda", "e"), _bind("interest_paid", "p")],
        periods=periods,
        period_phase={},
        explicit_phases=False,
        interest_order=order,
    )
    assert paid["rows"][0]["value"] == Decimal("5.0000000000")
    assert paid["warnings"][-1]["params"]["message"] == INTEREST_BASIS_FALLBACK


def test_corporate_dscr_names_each_missing_input():
    from finance_analysis.application.analyses import _absent_params
    from finance_analysis.domain.covenant import composed_ratio

    catalog = _catalog()
    got = composed_ratio(
        "dscr",
        catalog.composed["dscr.corporate_covenant"],
        facts=[_fact("e", "Y1", "100"), _fact("i", "Y1", "-10"), _fact("p", "Y1", "5")],
        bindings=[_bind("ebitda", "e"), _bind("interest", "i"), _bind("principal", "p")],
        periods=[_year()],
    )
    params = _absent_params("dscr", got)
    assert params["inputs"] == ["cash_taxes", "capex"]
    assert params["message"] == "Для расчёта DSCR не хватает понятий: cash_taxes, capex."
    quiet = _absent_params("llcr", {"needs_input": [{"subject": "cfads"}]})
    assert quiet == {"metric": "llcr"}


def test_pf_dscr_without_debt_service_names_the_missing_input():
    from finance_analysis.domain.metrics import coverage_ratio

    order = _catalog().interest_order
    common = {
        "periods": [_year()],
        "period_phase": {},
        "explicit_phases": False,
        "interest_order": order,
    }
    no_cfads = coverage_ratio(
        metric="dscr",
        facts=[_fact("i", "Y1", "-10"), _fact("d", "Y1", "100")],
        bindings=[_bind("interest", "i"), _bind("debt_outstanding", "d")],
        **common,
    )
    assert no_cfads["status"] == "missing_input"
    assert no_cfads["needs_input"][0]["subject"] == "cfads"
    from finance_analysis.application.analyses import _absent_params

    assert _absent_params("dscr", no_cfads)["message"] == "Для расчёта DSCR не хватает понятий: cfads."
    no_principal = coverage_ratio(
        metric="dscr",
        facts=[_fact("c", "Y1", "40"), _fact("i", "Y1", "-10"), _fact("d", "Y1", "100")],
        bindings=[_bind("cfads", "c"), _bind("interest", "i"), _bind("debt_outstanding", "d")],
        **common,
    )
    assert no_principal["needs_input"][0]["subject"] == "principal"
    summed = coverage_ratio(
        metric="dscr",
        facts=[_fact("c", "Y1", "40"), _fact("i", "Y1", "-6"), _fact("p", "Y1", "-4")],
        bindings=[_bind("cfads", "c"), _bind("interest", "i"), _bind("principal", "p")],
        **common,
    )
    assert summed["rows"][0]["value"] == Decimal("4.0000000000")
    assert "principal" in summed["rows"][0]["components"]


def test_debt_service_still_beats_the_interest_fallback():
    from finance_analysis.domain.metrics import coverage_ratio

    got = coverage_ratio(
        metric="dscr",
        facts=[_fact("c", "Y1", "40"), _fact("s", "Y1", "-10"), _fact("i", "Y1", "-1"), _fact("p", "Y1", "-1")],
        bindings=[
            _bind("cfads", "c"),
            _bind("debt_service", "s"),
            _bind("interest", "i"),
            _bind("principal", "p"),
        ],
        periods=[_year()],
        period_phase={},
        explicit_phases=False,
        interest_order=_catalog().interest_order,
    )
    assert got["rows"][0]["value"] == Decimal("4.0000000000")
    assert "principal" not in got["rows"][0]["components"]


def test_corporate_dscr_falls_back_to_paid_interest():
    from finance_analysis.domain.metrics import INTEREST_BASIS_FALLBACK

    catalog = _catalog()
    got = covenant_dscr(
        facts=[
            _fact("e", "Y1", "100"),
            _fact("t", "Y1", "10"),
            _fact("c", "Y1", "20"),
            _fact("p", "Y1", "30"),
            _fact("r", "Y1", "10"),
        ],
        bindings=[
            _bind("ebitda", "e"),
            _bind("cash_taxes", "t"),
            _bind("capex", "c"),
            _bind("interest_paid", "p"),
            _bind("principal", "r"),
        ],
        periods=[_year()],
        default=catalog.composed["dscr.corporate_covenant"],
        concepts=_CONCEPTS | {"interest_paid"},
        money=_MONEY | {"interest_paid"},
        interest_order=catalog.interest_order,
    )
    assert got["rows"][0]["value"] == Decimal("1.7500000000")
    assert got["warnings"][-1]["params"]["message"] == INTEREST_BASIS_FALLBACK


def _quarter(index: int, start: date, end: date) -> dict:
    return {
        "axis_id": "a",
        "period_id": f"Q{index}",
        "period_index": index,
        "grain": "quarter",
        "timeline_id": "t",
        "period_start": start,
        "period_end": end,
    }
