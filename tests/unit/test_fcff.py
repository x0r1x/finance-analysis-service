"""FCFF: щит только при вычтенных процентах. Ставку 20% код не подставляет."""

from __future__ import annotations

from decimal import Decimal

from finance_analysis.application.financial_catalog import load_financial_catalog
from finance_analysis.domain.covenant import select_ratio

_MONEY = Decimal("0.000001")


def test_fcff_shield_follows_basis_rate_and_capex_sign():
    item = load_financial_catalog().get("fcff")
    assert item is not None
    assert item.unit == "money"
    assert item.formula.rate == "income_tax_rate"
    assert item.formula.denominator is None
    assert "не перемножает" in (item.definition or "")
    assert item.inputs.concepts == {"operating_cash_flow", "capex", "income_tax_rate"}
    assert item.model_types["corporate"].use == "optional"
    assert item.model_types["project_finance"].use == "not_applicable"
    assert item.model_types["investment_project"].use == "not_applicable"
    assert item.model_types["other"].use == "optional"

    included = _run(_case(code_ocf="стр. 4100", code_interest="стр. 4123", rate="0.2"))
    assert included["status"] == "succeeded"
    assert included["rows"][0]["value"] == Decimal(78).quantize(_MONEY)
    assert included["rows"][0]["components"]["interest_paid"] == ["S!C1"]
    assert "S!A1" in included["rows"][0]["components"]["operating_cash_flow"]
    assert not any(
        note["code"] == "fcff_interest_excluded" for note in included["warnings"]
    )

    excluded = _run(
        _case(section="Финансовая деятельность", rate="0.2", capex="-30"),
    )
    assert excluded["rows"][0]["value"] == Decimal(70).quantize(_MONEY)
    assert "interest_paid" not in excluded["rows"][0]["components"]
    assert any(
        note["code"] == "fcff_interest_excluded" for note in excluded["warnings"]
    )

    genitive = _run(
        _case(section="Денежные потоки от финансовой деятельности", rate="0.2")
    )
    assert genitive["rows"][0]["value"] == Decimal(70).quantize(_MONEY)

    english = _run(_case(section="Financing activities", rate="0.2"))
    assert english["rows"][0]["value"] == Decimal(70).quantize(_MONEY)

    pnl = _run(_case(section="Финансовые расходы", rate="0.2"))
    assert pnl["rows"][0]["reason"] == "ocf_basis_unknown"
    assert pnl["rows"][0]["value"] is None

    unknown = _run(_case(rate="0.2"))
    assert unknown["status"] == "not_computed"
    assert unknown["rows"][0]["reason"] == "ocf_basis_unknown"
    assert unknown["rows"][0]["value"] is None

    gap = _run(
        _case(
            formula="net_income+depreciation",
            code_interest="стр. 4123",
            accrued="-12",
            paid="-10",
            rate="0.2",
        )
    )
    assert gap["rows"][0]["reason"] == "interest_accrual_cash_gap"
    assert gap["rows"][0]["value"] is None

    matched = _run(
        _case(
            formula="net_income+depreciation",
            code_interest="стр. 4123",
            accrued="-10",
            paid="-10",
            rate="0.2",
        )
    )
    assert matched["rows"][0]["value"] == Decimal(78).quantize(_MONEY)
    assert matched["rows"][0]["components"]["interest_paid"] == ["S!C1"]

    missing_rate = _run(_case(code_ocf="стр. 4100", code_interest="стр. 4123"))
    assert missing_rate["rows"][0]["reason"] == "missing_tax_rate"
    assert missing_rate["rows"][0]["value"] is None

    percent_points = _run(
        _case(code_ocf="стр. 4100", code_interest="стр. 4123", rate="20")
    )
    assert percent_points["rows"][0]["reason"] == "missing_tax_rate"
    assert percent_points["rows"][0]["value"] is None

    by_period = _run(
        _case(
            code_ocf="стр. 4100",
            code_interest="стр. 4123",
            periods=(("Y1", "0.2"), ("Y2", "0")),
        )
    )
    assert [row["value"] for row in by_period["rows"]] == [
        Decimal(78).quantize(_MONEY),
        Decimal(80).quantize(_MONEY),
    ]

    spread = _run(
        _case(
            code_ocf="стр. 4100",
            code_interest="стр. 4123",
            periods=(("Y1", "0.2"), ("Y2", None)),
        )
    )
    assert [row["value"] for row in spread["rows"]] == [
        Decimal(78).quantize(_MONEY)
    ] * 2

    flipped = _run(_case(section="Финансовая деятельность", capex="30"))
    assert flipped["rows"][0]["value"] == Decimal(70).quantize(_MONEY)
    assert any(note["code"] == "sign_mismatch" for note in flipped["warnings"])

    outputs = _run(
        _case(
            code_ocf="стр. 4100", code_interest="стр. 4123", sheet="Outputs", rate="0.2"
        )
    )
    assert outputs["rows"][0]["reason"] == "ocf_basis_unknown"
    assert outputs["rows"][0]["value"] is None

    absent = _run([])
    assert absent["status"] == "missing_input"
    assert absent["rows"] == []
    assert absent["needs_input"][0]["subject"] == "operating_cash_flow"


def _run(bindings_and_facts: tuple[list[dict], list[dict], list[dict]] | list) -> dict:
    if bindings_and_facts == []:
        bindings, facts, periods = [], [], [_period("Y1", 1)]
    else:
        bindings, facts, periods = bindings_and_facts
    return select_ratio(
        "fcff",
        None,
        {
            "facts": facts,
            "bindings": bindings,
            "periods": periods,
            "sign_convention": "outflow_negative",
            "absent": frozenset(),
        },
        profile=None,
        profile_ref=None,
        composed={},
        concepts=frozenset(),
        money=frozenset(),
    )


def _case(
    *,
    code_ocf: str | None = None,
    code_interest: str | None = None,
    section: str | None = None,
    formula: str | None = None,
    sheet: str | None = None,
    rate: str | None = None,
    capex: str = "-30",
    accrued: str | None = None,
    paid: str = "-10",
    periods: tuple[tuple[str, str | None], ...] = (("Y1", None),),
) -> tuple[list[dict], list[dict], list[dict]]:
    bindings = [
        _bind("operating_cash_flow", "ocf", code=code_ocf, formula=formula),
        _bind("capex", "capex"),
    ]
    if code_interest or section or sheet:
        bindings.append(
            _bind(
                "interest",
                "paid",
                primary=accrued is None,
                code=code_interest,
                section=section,
                sheet=sheet,
            )
        )
    if accrued is not None:
        bindings.append(_bind("interest", "accrued", code=None))
    if rate is not None or any(item[1] is not None for item in periods):
        bindings.append(_bind("income_tax_rate", "rate"))
    facts = []
    period_rows = []
    for index, (pid, own_rate) in enumerate(periods, start=1):
        period_rows.append(_period(pid, index))
        facts.append(_fact("ocf", pid, "100", "S!A1" if pid == "Y1" else f"S!A{index}"))
        facts.append(_fact("capex", pid, capex, f"S!B{index}"))
        if code_interest or section or sheet:
            facts.append(
                _fact("paid", pid, paid, "S!C1" if pid == "Y1" else f"S!C{index}")
            )
        if accrued is not None:
            facts.append(_fact("accrued", pid, accrued, f"S!E{index}"))
        chosen = rate if own_rate is None and len(periods) == 1 else own_rate
        if chosen is not None:
            facts.append(_fact("rate", pid, chosen, f"S!D{index}"))
    return bindings, facts, period_rows


def _bind(
    concept: str,
    row: str,
    *,
    primary: bool = True,
    code: str | None = None,
    section: str | None = None,
    formula: str | None = None,
    sheet: str | None = None,
) -> dict:
    item = {
        "effective_concept": concept,
        "row_key": row,
        "binding_key": row,
        "is_primary": primary,
        "status": "bound",
        "source": "inferred",
    }
    evidence = {}
    if code:
        evidence["line_code"] = code
    if section:
        item["label_path_text"] = f"ОДДС › {section} › Проценты к уплате"
    if evidence:
        item["evidence"] = evidence
    if formula:
        item["formula"] = formula
    if sheet:
        item["sheet"] = sheet
    return item


def _fact(row: str, period: str, value: str, cell: str) -> dict:
    return {
        "row_key": row,
        "axis_id": "a",
        "period_id": period,
        "normalized_value": value,
        "cell_id": cell,
    }


def _period(pid: str, index: int) -> dict:
    return {
        "axis_id": "a",
        "period_id": pid,
        "period_index": index,
        "timeline_id": "t",
        "grain": "quarter",
    }
