"""ncf_period: приток минус отток. Интервальный ncf этот файл не покрывает."""

from __future__ import annotations

from decimal import Decimal

from finance_analysis.application.catalog import load_catalog
from finance_analysis.application.financial_catalog import load_financial_catalog
from finance_analysis.application.model_types import (
    load_metric_inputs,
    load_model_types,
)
from finance_analysis.domain.cash_flow import net_cash_flow
from finance_analysis.domain.covenant import select_ratio
from finance_analysis.domain.mapping import Assignment, _one_primary
from finance_analysis.domain.model_type import applicability

_MONEY = Decimal("0.000001")


def _bind(
    concept: str,
    *,
    row: str | None = None,
    label: str | None = None,
    primary: bool = True,
    path: str | None = None,
    section: str | None = None,
) -> dict:
    item = {
        "effective_concept": concept,
        "row_key": row or concept,
        "is_primary": primary,
        "status": "bound",
        "source": "inferred",
    }
    if label:
        item["matched_label_id"] = label
    if path:
        item["label_path_text"] = path
    if section:
        item["section"] = section
    return item


def _fact(row: str, value: str, *, period: str = "Y1") -> dict:
    return {
        "row_key": row,
        "axis_id": "a",
        "period_id": period,
        "normalized_value": value,
        "cell_id": f"a!{period}",
    }


def _period(period: str = "Y1", index: int = 1) -> dict:
    return {"axis_id": "a", "period_id": period, "grain": "year", "timeline_id": "t", "period_index": index}


def _run(bindings: list[dict], facts: list[dict], periods: list[dict] | None = None) -> dict:
    common = {
        "facts": facts,
        "bindings": bindings,
        "periods": periods or [_period()],
        "sign_convention": "outflow_negative",
        "absent": frozenset(),
    }
    return select_ratio(
        "ncf_period",
        None,
        common,
        profile={},
        profile_ref=None,
        composed={},
        concepts=frozenset(),
        money=frozenset(),
    )


def _value(result: dict) -> Decimal:
    assert result["rows"], result
    return result["rows"][0]["value"]


def test_hundred_minus_forty_is_sixty():
    got = _run(
        [_bind("cash_inflow"), _bind("cash_outflow")],
        [_fact("cash_inflow", "100"), _fact("cash_outflow", "40")],
    )
    assert got["status"] == "succeeded"
    assert _value(got) == Decimal(60).quantize(_MONEY)
    assert got["needs_input"] == []


def test_outflow_in_parentheses_stays_a_subtraction():
    got = _run(
        [_bind("cash_inflow"), _bind("cash_outflow")],
        [_fact("cash_inflow", "100"), _fact("cash_outflow", "-40")],
    )
    assert _value(got) == Decimal(60).quantize(_MONEY)


def test_missing_outflow_has_no_number():
    got = _run([_bind("cash_inflow")], [_fact("cash_inflow", "100")])
    assert got["status"] == "missing_input"
    assert got["rows"] == []
    assert got["needs_input"][0]["subject"] == "cash_outflow"


def test_three_section_totals_sum_and_a_company_row_replaces_them():
    sections = [
        _bind("cash_inflow", row="op", label="Поступления — всего", path="Текущие › Поступления — всего"),
        _bind(
            "cash_inflow",
            row="inv",
            label="Поступления — всего",
            primary=False,
            path="Инвестиционные › Поступления — всего",
        ),
        _bind(
            "cash_inflow",
            row="fin",
            label="Поступления - всего",
            primary=False,
            path="Финансовые › Поступления — всего",
        ),
    ]
    outflow = [_bind("cash_outflow", label="Отток денежных средств")]
    facts = [
        _fact("op", "10"),
        _fact("inv", "20"),
        _fact("fin", "30"),
        _fact("cash_outflow", "40"),
    ]
    summed = _run([*sections, *outflow], facts)
    assert _value(summed) == Decimal(20).quantize(_MONEY)
    company = _bind("cash_inflow", row="all", label="Приток денежных средств", primary=False)
    replaced = _run([*sections, company, *outflow], [*facts, _fact("all", "100")])
    assert _value(replaced) == Decimal(60).quantize(_MONEY)


def test_two_rows_in_one_section_have_no_number():
    got = _run(
        [
            _bind("cash_inflow", row="a", label="Поступления — всего", section="Текущие"),
            _bind("cash_inflow", row="b", label="Поступления — всего", primary=False, section="Текущие"),
            _bind("cash_outflow"),
        ],
        [_fact("a", "10"), _fact("b", "20"), _fact("cash_outflow", "5")],
    )
    assert got["status"] == "not_computed"
    assert got["rows"] == []
    assert got["needs_input"] == []
    assert got["warnings"][0]["code"] == "ncf_ambiguous"


def test_internal_transfer_is_not_an_input_and_labels_resolve():
    package = load_catalog()
    assert package.resolve("перевод между счетами") is None
    assert package.resolve("Чистый денежный поток от текущих операций") is None
    assert package.resolve("Приток денежных средств").concept == "cash_inflow"
    assert package.resolve("Поступления — всего").concept == "cash_inflow"
    assert package.resolve("Сальдо денежных потоков за период").concept == "ncf"
    assert package.resolve("Сальдо денежных потоков за отчетный период").concept == "cash_net"
    assert package.concepts["cash_balance"].temporal_nature == "stock"
    assert package.concepts["ncf"].expected_sign is None
    got = _run(
        [
            _bind("cash_inflow", label="перевод между счетами"),
            _bind("cash_outflow", label="Отток денежных средств"),
        ],
        [_fact("cash_inflow", "100"), _fact("cash_outflow", "40")],
    )
    assert got["status"] == "missing_input"
    assert got["rows"] == []


def test_ncf_is_money_and_does_not_replace_project_fcf_or_cash():
    catalog = load_financial_catalog()
    ncf = catalog.indicators["ncf_period"]
    assert ncf.unit == "money"
    assert ncf.window == "period"
    assert ncf.inputs.concepts == frozenset({"cash_inflow", "cash_outflow"})
    assert catalog.indicators["irr"].unit == "ratio"
    assert "ncf_period" not in load_model_types().composed
    assert list(load_metric_inputs())[-1] == "ncf_period"
    types = load_model_types()
    assert applicability(types, ("corporate",), "ncf_period") == "optional"
    assert applicability(types, ("lbo_ma",), "ncf_period") == "not_applicable"
    got = _run(
        [_bind("cash_balance"), _bind("project_fcf")],
        [_fact("cash_balance", "100"), _fact("project_fcf", "100")],
    )
    assert got["rows"] == []
    assert got["status"] == "missing_input"


def test_cited_line_warns_and_does_not_replace_the_number():
    got = _run(
        [_bind("cash_inflow"), _bind("cash_outflow"), _bind("ncf", label="Чистый денежный поток")],
        [_fact("cash_inflow", "100"), _fact("cash_outflow", "40"), _fact("ncf", "50")],
    )
    assert _value(got) == Decimal(60).quantize(_MONEY)
    assert [item["code"] for item in got["warnings"]] == ["ncf_book_mismatch"]
    empty = _run(
        [_bind("cash_inflow"), _bind("cash_outflow"), _bind("ncf")],
        [_fact("cash_inflow", "100"), _fact("cash_outflow", "40")],
    )
    assert _value(empty) == Decimal(60).quantize(_MONEY)
    assert empty["warnings"] == []


def test_three_exact_section_labels_stay_bound_with_one_primary():
    draft = [
        ({"row_key": key}, _assignment("cash_inflow", "Поступления — всего"))
        for key in ("op", "inv", "fin")
    ]
    _one_primary(draft)
    assert [item.is_primary for _row, item in draft] == [True, False, False]
    assert {item.status for _row, item in draft} == {"bound"}
    other = [
        ({"row_key": "a"}, _assignment("ebitda", "EBITDA")),
        ({"row_key": "b"}, _assignment("ebitda", "EBITDA")),
    ]
    _one_primary(other)
    assert [item.status for _row, item in other] == ["ambiguous", "ambiguous"]


def test_direct_call_matches_select_ratio():
    bindings = [_bind("cash_inflow"), _bind("cash_outflow")]
    facts = [_fact("cash_inflow", "100"), _fact("cash_outflow", "40")]
    assert net_cash_flow(facts=facts, bindings=bindings, periods=[_period()])["rows"][0]["value"] == _value(
        _run(bindings, facts)
    )


def _assignment(concept: str, label: str) -> Assignment:
    return Assignment(
        concept=concept,
        status="bound",
        source="inferred",
        is_primary=True,
        matched_label=label,
        importance="normal",
        evidence={"match_strength": "exact"},
    )
