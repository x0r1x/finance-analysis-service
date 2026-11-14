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
        "operating_cash_flow",
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
    mixed = {"variant": "ocf_covenant", "numerator": {"plus": ["ebitda"]}}
    assert "либо имя варианта, либо состав" in dscr_definition_error(
        mixed, concepts=_CONCEPTS, money=_MONEY, variants=frozenset({"ocf_covenant"})
    )
    assert "неизвестный вариант" in dscr_definition_error(
        {"variant": "missing"}, concepts=_CONCEPTS, money=_MONEY, variants=frozenset({"ocf_covenant"})
    )


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
    assert catalog.types["development_escrow"].variants["dscr"] == "housing"
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


def test_two_stocks_with_one_period_end_follow_grain_not_list_order():
    from finance_analysis.domain.covenant import composed_ratio

    catalog = _catalog()
    quarters = [
        _quarter(1, date(2024, 1, 1), date(2024, 3, 31)),
        _quarter(2, date(2024, 4, 1), date(2024, 6, 30)),
        _quarter(3, date(2024, 7, 1), date(2024, 9, 30)),
        _quarter(4, date(2024, 10, 1), date(2024, 12, 31)),
    ]
    debt = [
        {**period, "axis_id": "debt", "timeline_id": "debt", "period_id": f"D{index}"}
        for index, period in enumerate(quarters, start=1)
    ]
    annual = {
        "axis_id": "year",
        "timeline_id": "year",
        "period_id": "Y",
        "period_index": 1,
        "grain": "year",
        "period_start": date(2024, 1, 1),
        "period_end": date(2024, 12, 31),
    }
    facts = [_fact("e", f"Q{index}", "10") for index in range(1, 5)]
    facts += [{**_fact("n", f"D{index}", "100"), "axis_id": "debt"} for index in range(1, 5)]
    facts.append({**_fact("n", "Y", "400"), "axis_id": "year"})
    bindings = [_bind("net_debt", "n"), _bind("ebitda", "e")]
    for periods in ([*quarters, *debt, annual], [annual, *reversed(debt), *reversed(quarters)]):
        got = composed_ratio(
            "net_debt_ebitda",
            catalog.composed["net_debt_ebitda"],
            facts=facts,
            bindings=bindings,
            periods=list(periods),
        )
        final = next(row for row in got["rows"] if row["period_id"] == "Q4")
        assert final["status"] == "computed"
        assert final["value"] == Decimal("2.5000000000")
    other = [
        {**period, "axis_id": "other", "timeline_id": "other", "period_id": f"O{index}"}
        for index, period in enumerate(quarters, start=1)
    ]
    mixed = facts + [{**_fact("n", f"O{index}", "250"), "axis_id": "other"} for index in range(1, 5)]
    ambiguous = composed_ratio(
        "net_debt_ebitda",
        catalog.composed["net_debt_ebitda"],
        facts=mixed,
        bindings=bindings,
        periods=[*quarters, *debt, *other],
    )
    final = next(row for row in ambiguous["rows"] if row["period_id"] == "Q4")
    assert final["status"] == "not_computed"
    assert final["value"] is None
    assert final["message"] == (
        "На одну дату конца периода приходится несколько остатков одной зернистости. "
        "Остаток не выбран, коэффициент не рассчитан."
    )


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
    assert got["warnings"] == []


def _coverage(facts, bindings=None):
    from finance_analysis.domain.covenant import composed_ratio

    catalog = _catalog()
    return composed_ratio(
        "escrow_coverage",
        catalog.composed["escrow_coverage"],
        facts=facts,
        bindings=bindings
        or [_bind("escrow_balance", "s"), _bind("debt_outstanding", "d"), _bind("escrow_coverage", "m")],
        periods=[_year()],
    )


def _coverage_fact(value, *, status="cached", normalized=None):
    item = {
        "row_key": "m",
        "axis_id": "a",
        "period_id": "Y1",
        "value_status": status,
        "cell_id": "Модель!M2",
    }
    if value is not None:
        item["value_dec"] = value
    else:
        item["value_dec"] = None
    if normalized is not None:
        item["normalized_value"] = normalized
    return item


def test_escrow_coverage_warns_when_the_book_row_is_outside_tolerance():
    agreed = _coverage(
        [_fact("s", "Y1", "200"), _fact("d", "Y1", "100"), _coverage_fact("2.005")]
    )
    assert agreed["warnings"] == []
    got = _coverage(
        [_fact("s", "Y1", "200"), _fact("d", "Y1", "100"), _coverage_fact("2.006")]
    )
    assert [item["code"] for item in got["warnings"]] == ["escrow_coverage_book_mismatch"]
    assert got["warnings"][0]["params"]["period_id"] == "Y1"
    assert got["warnings"][0]["params"]["fas"] == "2.0000000000"
    assert got["warnings"][0]["params"]["model"] == "2.006"
    assert got["rows"][0]["inputs"] == ["escrow_balance", "debt_outstanding"]


def test_coverage_on_the_other_axis_of_the_same_period_warns():
    """Остаток на Model и долг на Debt — один период шкалы. Покрытие 9 лежит на Model."""

    from finance_analysis.domain.covenant import composed_ratio

    catalog = _catalog()
    common = {
        "axis_id": None,
        "period_index": 1,
        "timeline_id": "t",
        "grain": "month",
    }
    got = composed_ratio(
        "escrow_coverage",
        catalog.composed["escrow_coverage"],
        facts=[
            {**_fact("s", "2024-01", "200"), "axis_id": "Model"},
            {**_fact("d", "M1", "100"), "axis_id": "Debt"},
            {
                "row_key": "m",
                "axis_id": "Model",
                "period_id": "2024-01",
                "value_dec": "9",
                "normalized_value": "9",
                "value_status": "cached",
            },
        ],
        bindings=[
            _bind("escrow_balance", "s"),
            _bind("debt_outstanding", "d"),
            _bind("escrow_coverage", "m"),
        ],
        periods=[
            {**common, "axis_id": "Model", "period_id": "2024-01"},
            {**common, "axis_id": "Debt", "period_id": "M1"},
        ],
    )
    assert got["rows"][0]["axis_id"] == "Debt"
    assert got["rows"][0]["value"] == Decimal("2.0000000000")
    assert [item["code"] for item in got["warnings"]] == ["escrow_coverage_book_mismatch"]
    assert got["warnings"][0]["params"]["fas"] == "2.0000000000"
    assert got["warnings"][0]["params"]["model"] == "9"


def test_blank_escrow_coverage_matches_zero_denominator_and_is_not_zero():
    blank = _coverage(
        [
            _fact("s", "Y1", "0"),
            _fact("d", "Y1", "0"),
            _coverage_fact(None, status="empty", normalized="0"),
            _fact("rate", "Y1", "0.99"),
        ],
        [
            _bind("escrow_balance", "s"),
            _bind("debt_outstanding", "d"),
            _bind("escrow_coverage", "m"),
            _bind("effective_rate", "rate"),
        ],
    )
    assert blank["rows"][0]["reason"] == "zero_denominator"
    assert blank["warnings"] == []
    assert "effective_rate" not in blank["rows"][0]["inputs"]
    explicit = _coverage(
        [_fact("s", "Y1", "0"), _fact("d", "Y1", "0"), _coverage_fact("0")]
    )
    assert [item["code"] for item in explicit["warnings"]] == ["escrow_coverage_book_mismatch"]
    assert explicit["warnings"][0]["params"]["model"] == "0"
    assert explicit["warnings"][0]["params"]["fas"] is None
    number_against_blank = _coverage(
        [
            _fact("s", "Y1", "200"),
            _fact("d", "Y1", "100"),
            _coverage_fact(None, status="cached", normalized="0"),
        ]
    )
    assert number_against_blank["rows"][0]["value"] == Decimal("2.0000000000")
    assert [item["code"] for item in number_against_blank["warnings"]] == [
        "escrow_coverage_book_mismatch"
    ]
    assert number_against_blank["warnings"][0]["params"]["model"] is None
    assert number_against_blank["warnings"][0]["params"]["fas"] == "2.0000000000"


def test_blank_coverage_does_not_warn_again_when_zero_denominator_already_warned():
    from finance_analysis.domain.covenant import _escrow_coverage_book

    row = {
        "axis_id": "a",
        "period_id": "Y1",
        "value": None,
        "reason": "zero_denominator",
        "status": "missing_input",
    }
    warnings = [
        {
            "code": "zero_denominator",
            "params": {"period_id": "Y1", "reason": "zero_denominator"},
        }
    ]
    extra = _escrow_coverage_book(
        [row],
        [_coverage_fact(None, status="empty", normalized="0")],
        [_bind("escrow_coverage", "m")],
        [],
        frozenset(),
        warnings,
    )
    assert extra == []


def test_interest_order_is_read_from_coverage_config():
    catalog = _catalog()
    order = catalog.interest_order
    assert order["icr"] == ("interest", "interest_paid")
    assert order["icr_ebit"] == ("interest", "interest_paid")
    assert order["corporate_covenant"] == ("interest", "interest_paid")
    assert order["pf"] == ("interest_paid", "interest")
    assert "interest_paid" in catalog.concepts
    assert "interest_paid" not in catalog.row_fallbacks


def test_icr_uses_accrued_interest_before_paid_interest():
    from finance_analysis.domain.metrics import INTEREST_BASIS_FALLBACK, coverage_ratio

    catalog = _catalog()
    order = catalog.interest_order
    fallbacks = catalog.row_fallbacks
    periods = [_year()]
    both = coverage_ratio(
        metric="icr",
        facts=[_fact("e", "Y1", "40"), _fact("i", "Y1", "-10"), _fact("p", "Y1", "-4")],
        bindings=[_bind("ebitda", "e"), _bind("interest", "i"), _bind("interest_paid", "p")],
        periods=periods,
        period_phase={},
        explicit_phases=False,
        interest_order=order,
        row_fallbacks=fallbacks,
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
        row_fallbacks=fallbacks,
    )
    assert paid["rows"][0]["value"] == Decimal("5.0000000000")
    assert paid["warnings"][-1]["params"]["message"] == INTEREST_BASIS_FALLBACK
    assert paid["warnings"][-1]["params"]["canonical"] == "interest"


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

    catalog = _catalog()
    common = {
        "periods": [_year()],
        "period_phase": {},
        "explicit_phases": False,
        "interest_order": catalog.interest_order,
        "row_fallbacks": catalog.row_fallbacks,
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


def test_interest_and_principal_of_opposite_signs_are_paid_apart():
    from finance_analysis.domain.metrics import coverage_ratio

    catalog = _catalog()
    got = coverage_ratio(
        metric="dscr",
        facts=[_fact("c", "Y1", "40"), _fact("i", "Y1", "10"), _fact("p", "Y1", "-40")],
        bindings=[_bind("cfads", "c"), _bind("interest", "i"), _bind("principal", "p")],
        periods=[_year()],
        period_phase={},
        explicit_phases=False,
        interest_order=catalog.interest_order,
        row_fallbacks=catalog.row_fallbacks,
    )
    assert got["rows"][0]["status"] == "computed"
    assert got["rows"][0]["value"] == Decimal("0.8000000000")


def test_debt_service_still_beats_the_interest_fallback():
    from finance_analysis.domain.metrics import coverage_ratio

    catalog = _catalog()
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
        interest_order=catalog.interest_order,
        row_fallbacks=catalog.row_fallbacks,
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
        concepts=_CONCEPTS,
        money=_MONEY,
        interest_order=catalog.interest_order,
        row_fallbacks=catalog.row_fallbacks,
    )
    assert got["rows"][0]["value"] == Decimal("1.7500000000")
    assert got["warnings"][-1]["params"]["message"] == INTEREST_BASIS_FALLBACK
    assert got["warnings"][-1]["params"]["canonical"] == "interest"


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


def test_corporate_default_still_needs_cash_taxes():
    catalog = _catalog()
    got = covenant_dscr(
        facts=[],
        bindings=[_bind(name, name) for name in ("ebitda", "capex", "interest", "principal")],
        periods=[],
        default=catalog.composed["dscr.corporate_covenant"],
        concepts=_CONCEPTS | {"operating_cash_flow"},
        money=_MONEY,
        profile=None,
        interest_order=catalog.interest_order,
        row_fallbacks=catalog.row_fallbacks,
    )
    assert got["status"] == "missing_input"
    assert "cash_taxes" in got["missing_inputs"]
    assert got["definition_source"] == "default"


def test_profile_names_ocf_covenant_and_ignores_cash_taxes():
    catalog = _catalog()
    # Зерно year: LTM — этот же период. Процент отрицательный:
    # add-back обязан прибавить 20, а не вычесть сырое значение.
    got = covenant_dscr(
        facts=[
            _fact("o", "Y1", "100"),
            _fact("i", "Y1", "-20"),
            _fact("c", "Y1", "-10"),
            _fact("p", "Y1", "-30"),
        ],
        bindings=[
            _bind("operating_cash_flow", "o"),
            _bind("interest", "i"),
            _bind("capex", "c"),
            _bind("principal", "p"),
        ],
        periods=[_year()],
        default=catalog.composed["dscr.corporate_covenant"],
        concepts=_CONCEPTS | {"operating_cash_flow"},
        money=_MONEY,
        profile={"dscr_definition": {"variant": "ocf_covenant", "basis_ref": "Формулы!B53"}},
        profile_ref="auchan@1",
        interest_order=catalog.interest_order,
        row_fallbacks=catalog.row_fallbacks,
        composed=catalog.composed,
    )
    assert got["definition_source"] == "profile"
    assert got["rows"][0]["status"] == "computed"
    # (100 + 20 - 10) / (20 + 30) = 2.2, квант как у соседнего теста (10 знаков).
    assert got["rows"][0]["value"] == Decimal("2.2000000000")
    assert "cash_taxes" not in got.get("missing_inputs", [])


def test_ocf_label_does_not_bind_a_tax_row():
    from finance_analysis.application.catalog import load_catalog
    from finance_analysis.domain.mapping import assign_rows
    from tests.unit.test_mapping_ml import _row

    glossary = load_catalog()
    rows = assign_rows(
        [
            _row(
                "taxmix",
                "Налоговые обязательства, отложеннные налоговые обязательства, налог на прибыль",
                unit="money",
            ),
            _row("ocf", "ИТОГО - Операционный денежный поток", unit="money"),
        ],
        [],
        glossary,
    )
    assert rows["taxmix"].status == "unknown"
    assert rows["taxmix"].concept is None
    assert rows["ocf"].concept == "operating_cash_flow"
    assert rows["ocf"].status == "bound"


def test_select_ratio_uses_named_profile_variant_for_any_book():
    catalog = _catalog()
    common = {
        "facts": [
            _fact("o", "Y1", "100"),
            _fact("i", "Y1", "-20"),
            _fact("c", "Y1", "-10"),
            _fact("p", "Y1", "-30"),
        ],
        "bindings": [
            _bind("operating_cash_flow", "o"),
            _bind("interest", "i"),
            _bind("capex", "c"),
            _bind("principal", "p"),
        ],
        "periods": [_year()],
        "period_phase": {},
        "explicit_phases": False,
        "sign_convention": "outflow_negative",
        "marker_class": None,
        "absent": frozenset(),
    }
    profile = {"dscr_definition": {"variant": "ocf_covenant", "basis_ref": "Формулы!B53"}}
    kwargs = {
        "profile_ref": "auchan@1",
        "composed": catalog.composed,
        "concepts": _CONCEPTS | {"operating_cash_flow"},
        "money": _MONEY,
        "interest_order": catalog.interest_order,
        "row_fallbacks": catalog.row_fallbacks,
    }
    # corporate_covenant + профиль: снятие composed= внутри select_ratio
    # возвращает корпоративный дефолт и не даёт 2.2.
    for book_variant in ("corporate_covenant", "pf", None):
        got = select_ratio("dscr", book_variant, common, profile=profile, **kwargs)
        assert got["definition_source"] == "profile", book_variant
        assert got["rows"][0]["value"] == Decimal("2.2000000000"), book_variant
        assert "cash_taxes" not in got.get("missing_inputs", [])
    plain = select_ratio("dscr", "pf", common, profile=None, **kwargs)
    assert plain.get("definition_source") != "profile"
    assert all(row.get("value") != Decimal("2.2000000000") for row in plain["rows"])
