"""NCF — сумма трёх подписанных потоков. Прочерк строки формы читается как ноль."""

from __future__ import annotations

import inspect
from decimal import Decimal

from finance_analysis.application.analyses import Analyses
from finance_analysis.application.catalog import load_catalog
from finance_analysis.application.financial_catalog import load_financial_catalog
from finance_analysis.domain.covenant import select_ratio
from finance_analysis.domain.graphs import trace_metric, validate_metric_trace_document
from finance_analysis.domain.mapping import assign_rows, marked_line_code
from finance_analysis.domain.net_cash_flow import net_cash_flow

_MONEY = Decimal("0.000001")
_DASH = "прочерк на цитируемой строке формы"
_SHEETS = frozenset({"ОДДС"})


def test_ncf_is_the_signed_sum_and_stays_money():
    item = load_financial_catalog().get("ncf")
    assert item is not None
    assert item.unit == "money"
    assert load_financial_catalog().get("irr").unit == "ratio"
    assert item.formula.rate is None
    assert item.formula.denominator is None
    assert item.inputs.concepts == {
        "operating_cash_flow",
        "investing_cash_flow",
        "financing_cash_flow",
    }
    assert item.model_types["corporate"].use == "optional"
    assert item.model_types["project_finance"].use == "optional"
    assert item.model_types["bank_leasing"].use == "optional"
    assert "4400" in (item.definition or "")

    got = _run(_flows())
    assert got["status"] == "succeeded"
    assert got["rows"][0]["value"] == Decimal(75).quantize(_MONEY)
    assert got["rows"][0]["inputs"] == [
        "operating_cash_flow",
        "investing_cash_flow",
        "financing_cash_flow",
    ]
    assert not any(note["code"] == "ncf_book_mismatch" for note in got["warnings"])


def test_missing_cfi_row_leaves_the_interval_empty():
    bindings, facts, periods = _flows()
    bindings = [row for row in bindings if row["effective_concept"] != "investing_cash_flow"]
    got = _run((bindings, facts, periods))
    assert got["status"] == "missing_input"
    assert got["rows"] == []
    assert got["needs_input"][0]["subject"] == "investing_cash_flow"


def test_dash_on_a_cited_cfi_line_is_zero_and_the_trace_says_so():
    bindings, facts, periods = _flows()
    facts = [fact for fact in facts if fact["row_key"] != "cfi"]
    facts.append(_fact("cfi", "Y1", None, "S!B1", raw="—"))
    got = _run((bindings, facts, periods))
    assert got["rows"][0]["value"] == Decimal(115).quantize(_MONEY)
    assert any(
        note["code"] == "ncf_dashed_line" and note["params"]["message"] == _DASH
        for note in got["warnings"]
    )

    trace = trace_metric(
        "ncf",
        inputs={
            "all_of": [
                "operating_cash_flow",
                "investing_cash_flow",
                "financing_cash_flow",
            ],
            "one_of": [],
        },
        bindings=bindings,
        facts=facts,
        statement_sheets=_SHEETS,
    )
    ordinary = [step.concept for step in trace.steps if step.note is None]
    assert ordinary == [
        "operating_cash_flow",
        "investing_cash_flow",
        "financing_cash_flow",
    ]
    [dashed] = [step for step in trace.steps if step.note is not None]
    assert dashed.concept == "investing_cash_flow"
    assert dashed.note == _DASH
    assert dashed.cell_ids == ("S!B1",)
    validate_metric_trace_document(trace.as_dict())


def test_missing_fact_on_another_axis_is_not_a_dash():
    bindings, facts, periods = _flows()
    facts.extend(
        [
            _fact("cfo", "Y1", "10", "P!A1", axis="plan"),
            _fact("cff", "Y1", "5", "P!C1", axis="plan"),
        ]
    )
    periods.append(_period("Y1", 1, axis="plan", timeline="plan"))
    got = _run((bindings, facts, periods))
    form = next(row for row in got["rows"] if row["axis_id"] == "a")
    other = next(row for row in got["rows"] if row["axis_id"] == "plan")
    assert form["value"] == Decimal(75).quantize(_MONEY)
    assert form["status"] == "computed"
    assert other["value"] is None
    assert other["status"] == "not_computed"
    assert other["reason"] == "missing_input"
    assert not any(note["code"] == "ncf_dashed_line" for note in got["warnings"])


def test_book_4400_does_not_replace_the_sum_and_allows_one_scale_unit():
    bindings, facts, periods = _flows(scale="1000")
    same = _run((bindings, facts, periods), book=[{"value": "74", "cell_id": "F!D1"}])
    assert same["rows"][0]["value"] == Decimal(75).quantize(_MONEY)
    assert not any(note["code"] == "ncf_book_mismatch" for note in same["warnings"])

    off = _run((bindings, facts, periods), book=[{"value": "70", "cell_id": "F!D1"}])
    assert off["rows"][0]["value"] == Decimal(75).quantize(_MONEY)
    [note] = [item for item in off["warnings"] if item["code"] == "ncf_book_mismatch"]
    assert note["params"]["book"] == Decimal(70).quantize(_MONEY)
    assert note["params"]["fas"] == Decimal(75).quantize(_MONEY)

    other = _run(_flows(), book=[{"value": "90", "cell_id": "F!D2"}])
    assert other["rows"][0]["value"] == Decimal(75).quantize(_MONEY)
    assert any(note["code"] == "ncf_book_mismatch" for note in other["warnings"])

    source = inspect.getsource(Analyses.compute_metrics)
    assert "book_ncf" not in source
    assert "4400" not in source


def test_bare_4200_is_not_a_code_and_4223_does_not_replace_the_total():
    assert marked_line_code("4200") is None
    assert marked_line_code(4200) is None
    glossary = load_catalog()
    bare = assign_rows([_row("b", "4200", line_code="4200")], [], glossary)["b"]
    assert bare.concept is None
    detail = assign_rows(
        [_row("d", "Приобретение основных средств", line_code="стр. 4223")],
        [],
        glossary,
    )["d"]
    assert detail.concept != "investing_cash_flow"
    capex = assign_rows([_row("c", "Капитальные затраты")], [], glossary)["c"]
    assert capex.concept == "capex"

    coded = assign_rows(
        [_row("i", "Инвестиции", line_code="код 4200")],
        [],
        glossary,
    )["i"]
    assert coded.concept == "investing_cash_flow"
    assert coded.evidence["line_code"] == "стр. 4200"

    bindings, facts, periods = _flows()
    for row in bindings:
        if row["effective_concept"] == "investing_cash_flow":
            row["evidence"]["line_code"] = "стр. 4223"
    refused = _run((bindings, facts, periods))
    assert refused["status"] == "missing_input"
    assert refused["rows"] == []

    off_sheet = [
        {**row, "sheet": "Outputs"} if row["effective_concept"] == "investing_cash_flow" else row
        for row in _flows()[0]
    ]
    assert _run((off_sheet, facts, periods))["status"] == "missing_input"
    labeled = [{**row, "sheet": "Model", "evidence": {}} for row in _flows()[0]]
    assert _run((labeled, facts, periods))["rows"][0]["value"] == Decimal(75).quantize(_MONEY)


def test_npv_on_a_book_with_three_flows_still_reads_project_fcf():
    bindings, facts, periods = _flows()
    bindings.append(_bind("project_fcf", "fcf"))
    bindings.append(_bind("discount_rate", "rate"))
    facts.append(_fact("fcf", "Y1", "50", "S!P1"))
    facts.append(_fact("rate", "Y1", "0", "S!R1"))
    got = select_ratio(
        "npv",
        None,
        {
            "facts": facts,
            "bindings": bindings,
            "periods": periods,
            "absent": frozenset(),
            "sign_convention": "outflow_negative",
        },
        profile=None,
        profile_ref=None,
        composed={},
        concepts=frozenset(),
        money=frozenset(),
    )
    assert got["rows"][0]["value"] == Decimal(50).quantize(_MONEY)
    assert got["rows"][0]["inputs"] == ["project_fcf", "discount_rate"]


def test_ytd_is_restated_before_the_sum_and_two_primaries_publish_nothing():
    periods = [_period("Q1", 1, 2025), _period("Q2", 2, 2025)]
    bindings = [
        _bind("operating_cash_flow", "cfo", code="стр. 4100", basis="ytd"),
        _bind("investing_cash_flow", "cfi", code="стр. 4200"),
        _bind("financing_cash_flow", "cff", code="стр. 4300"),
    ]
    facts = [
        _fact("cfo", "Q1", "100", "S!A1"),
        _fact("cfo", "Q2", "180", "S!A2"),
        _fact("cfi", "Q1", "-40", "S!B1"),
        _fact("cfi", "Q2", "-40", "S!B2"),
        _fact("cff", "Q1", "15", "S!C1"),
        _fact("cff", "Q2", "15", "S!C2"),
    ]
    got = net_cash_flow(
        facts=facts,
        bindings=bindings,
        periods=periods,
        statement_sheets=_SHEETS,
    )
    assert [row["value"] for row in got["rows"]] == [
        Decimal(75).quantize(_MONEY),
        Decimal(55).quantize(_MONEY),
    ]

    clash_bindings, clash_facts, clash_periods = _flows()
    clash_bindings.append(_bind("investing_cash_flow", "other", source="confirmed"))
    clash_facts.append(_fact("other", "Y1", "-1", "S!B9"))
    clash = _run((clash_bindings, clash_facts, clash_periods))
    assert clash["status"] == "needs_input"
    assert clash["rows"] == []
    assert clash["needs_input"][0]["subject"] == "investing_cash_flow"


def test_absent_inferred_flow_is_not_summed():
    bindings, facts, periods = _flows()
    blocked = _run((bindings, facts, periods), absent=frozenset({"investing_cash_flow"}))
    assert blocked["status"] == "missing_input"
    assert blocked["rows"] == []
    for row in bindings:
        if row["effective_concept"] == "investing_cash_flow":
            row["source"] = "confirmed"
    kept = _run(
        (bindings, facts, periods),
        absent=frozenset({"investing_cash_flow"}),
    )
    assert kept["rows"][0]["value"] == Decimal(75).quantize(_MONEY)


def _run(case, *, book=None, absent=frozenset()):
    bindings, facts, periods = case
    return net_cash_flow(
        facts=facts,
        bindings=bindings,
        periods=periods,
        absent=absent,
        book=book,
        statement_sheets=_SHEETS,
    )


def _flows(*, scale: str | None = None):
    bindings = [
        _bind("operating_cash_flow", "cfo", code="стр. 4100"),
        _bind("investing_cash_flow", "cfi", code="стр. 4200"),
        _bind("financing_cash_flow", "cff", code="стр. 4300"),
    ]
    facts = [
        _fact("cfo", "Y1", "100", "S!A1", scale=scale),
        _fact("cfi", "Y1", "-40", "S!B1", scale=scale),
        _fact("cff", "Y1", "15", "S!C1", scale=scale),
    ]
    return bindings, facts, [_period("Y1", 1)]


def _bind(
    concept: str,
    row: str,
    *,
    code: str | None = None,
    basis: str | None = None,
    source: str = "inferred",
    sheet: str = "ОДДС",
) -> dict:
    item = {
        "effective_concept": concept,
        "row_key": row,
        "binding_key": row,
        "is_primary": True,
        "status": "bound",
        "source": source,
        "sheet": sheet,
    }
    evidence = {}
    if code:
        evidence["line_code"] = code
    if basis:
        evidence["period_basis"] = basis
        evidence["period_basis_source"] = "header"
    if evidence:
        item["evidence"] = evidence
    return item


def _fact(row, period, value, cell, *, raw=None, scale=None, axis="a"):
    item = {
        "row_key": row,
        "axis_id": axis,
        "period_id": period,
        "cell_id": cell,
    }
    if value is not None:
        item["normalized_value"] = value
    if raw is not None:
        item["value"] = raw
    if scale is not None:
        item["scale_factor"] = scale
    return item


def _period(
    pid: str,
    index: int,
    year: int | None = None,
    *,
    axis: str = "a",
    timeline: str = "t",
) -> dict:
    item = {
        "axis_id": axis,
        "period_id": pid,
        "period_index": index,
        "timeline_id": timeline,
        "grain": "quarter",
    }
    if year is not None:
        item["calendar_year"] = year
    return item


def _row(key: str, label: str, *, line_code: str | None = None) -> dict:
    item = {
        "kind": "fact",
        "binding_key": key,
        "row_key": key,
        "label": label,
        "unit": "money",
    }
    if line_code is not None:
        item["line_code"] = line_code
    return item
