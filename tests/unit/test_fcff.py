"""FCFF: щит только при вычтенных процентах. Ставку 20% код не подставляет."""

from __future__ import annotations

from decimal import Decimal

from finance_analysis.application.financial_catalog import load_financial_catalog
from finance_analysis.domain.covenant import select_ratio
from finance_analysis.domain.free_cash_flow import free_cash_flow

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


def test_ytd_flows_are_restated_before_the_shield_and_ltm_keeps_its_end():
    periods = [_period(f"Q{index}", index, 2025) for index in range(1, 5)]
    bindings = [
        _bind("operating_cash_flow", "ocf", code="стр. 4100", basis="ytd"),
        _bind("capex", "capex", basis="ytd"),
        _bind("interest", "paid", code="стр. 4123", basis="ytd"),
        _bind("income_tax_rate", "rate"),
    ]
    facts = []
    for index, (ocf, capex, paid) in enumerate(
        (
            ("100", "-30", "-10"),
            ("250", "-50", "-30"),
            ("400", "-90", "-40"),
            ("550", "-120", "-60"),
        ),
        start=1,
    ):
        facts.append(_fact("ocf", f"Q{index}", ocf, f"S!A{index}"))
        facts.append(_fact("capex", f"Q{index}", capex, f"S!B{index}"))
        facts.append(_fact("paid", f"Q{index}", paid, f"S!C{index}"))
        facts.append(_fact("rate", f"Q{index}", "0.2", f"S!D{index}"))
    restated = free_cash_flow(
        facts=facts,
        bindings=bindings,
        periods=periods,
        book=[{"cell_id": "Book!A1", "value": "478", "calendar_year": 2025}],
    )
    assert [row["value"] for row in restated["rows"]] == [
        Decimal(value).quantize(_MONEY) for value in (78, 146, 118, 136)
    ]
    assert restated["rows"][1]["components"]["interest_paid"] == ["S!C2"]
    assert not any(note["code"] == "fcff_book_mismatch" for note in restated["warnings"])

    ltm_bindings = [
        _bind("operating_cash_flow", "ocf", basis="ltm", basis_source="label"),
        _bind("capex", "capex", basis="ltm", basis_source="label"),
        _bind("interest", "paid", section="Финансовая деятельность"),
    ]
    ltm_facts = []
    for index, (ocf, capex) in enumerate(
        (("100", "-10"), ("110", "-20"), ("120", "-30"), ("400", "-50")),
        start=1,
    ):
        ltm_facts.append(_fact("ocf", f"Q{index}", ocf, f"S!A{index}"))
        ltm_facts.append(_fact("capex", f"Q{index}", capex, f"S!B{index}"))
    kept = free_cash_flow(
        facts=ltm_facts,
        bindings=ltm_bindings,
        periods=periods,
        book=[{"cell_id": "Book!B1", "value": "630", "calendar_year": 2025}],
    )
    assert [row["value"] for row in kept["rows"]] == [None, None, None, Decimal(350).quantize(_MONEY)]
    assert [row["reason"] for row in kept["rows"][:3]] == ["missing_input"] * 3
    [note] = [item for item in kept["warnings"] if item["code"] == "fcff_book_mismatch"]
    assert note["params"]["fas"] is None


def test_two_primaries_or_unconfirmed_scale_do_not_publish_fcff():
    periods = [_period("Y1", 1)]
    clash = _run(
        (
            [
                _bind("operating_cash_flow", "ocf", source="confirmed"),
                _bind("operating_cash_flow", "other", source="confirmed"),
                _bind("capex", "capex"),
                _bind("interest", "interest", section="Финансовая деятельность"),
            ],
            [
                _fact("ocf", "Y1", "100", "S!A1"),
                _fact("other", "Y1", "999", "S!A9"),
                _fact("capex", "Y1", "-30", "S!B1"),
            ],
            periods,
        )
    )
    assert clash["status"] == "needs_input"
    assert clash["needs_input"] == [
        {"kind": "concept", "reason": "ambiguous", "subject": "operating_cash_flow"}
    ]
    assert clash["rows"] == []

    capex_clash = _run(
        (
            [
                _bind("operating_cash_flow", "ocf"),
                _bind("capex", "capex", source="confirmed"),
                _bind("capex", "other", source="confirmed"),
                _bind("interest", "interest", section="Финансовая деятельность"),
            ],
            [
                _fact("ocf", "Y1", "100", "S!A1"),
                _fact("capex", "Y1", "-30", "S!B1"),
                _fact("other", "Y1", "-80", "S!B2"),
            ],
            periods,
        )
    )
    assert capex_clash["status"] == "needs_input"
    assert capex_clash["needs_input"][0]["subject"] == "capex"
    assert capex_clash["needs_input"][0]["reason"] == "ambiguous"
    assert capex_clash["rows"] == []

    capex_scale = _run(
        (
            [
                _bind("operating_cash_flow", "ocf"),
                _bind("capex", "capex"),
                _bind("interest", "interest", section="Финансовая деятельность"),
            ],
            [
                _fact("ocf", "Y1", "100", "S!A1"),
                _fact("capex", "Y1", "-15", "S!B1", raw="-30", scale="1000"),
            ],
            periods,
        )
    )
    assert capex_scale["status"] == "not_computed"
    assert capex_scale["rows"][0]["status"] == "not_computed"
    assert capex_scale["rows"][0]["reason"] == "scale_unconfirmed"
    assert capex_scale["rows"][0]["value"] is None

    ocf_scale = _run(
        (
            [
                _bind("operating_cash_flow", "ocf"),
                _bind("capex", "capex"),
                _bind("interest", "interest", section="Финансовая деятельность"),
            ],
            [
                _fact("ocf", "Y1", "40", "S!A1", raw="100", scale="1000"),
                _fact("capex", "Y1", "-30", "S!B1"),
            ],
            periods,
        )
    )
    assert ocf_scale["rows"][0]["reason"] == "scale_unconfirmed"
    assert ocf_scale["rows"][0]["value"] is None

    paid_scale = _run(
        (
            [
                _bind("operating_cash_flow", "ocf", code="стр. 4100"),
                _bind("capex", "capex"),
                _bind("interest", "paid", code="стр. 4123"),
                _bind("income_tax_rate", "rate"),
            ],
            [
                _fact("ocf", "Y1", "100", "S!A1"),
                _fact("capex", "Y1", "-30", "S!B1"),
                _fact("paid", "Y1", "-4", "S!C1", raw="-10", scale="1000"),
                _fact("rate", "Y1", "0.2", "S!D1"),
            ],
            periods,
        )
    )
    assert paid_scale["status"] == "not_computed"
    assert paid_scale["rows"][0]["reason"] == "scale_unconfirmed"
    assert paid_scale["rows"][0]["value"] is None


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
    basis: str | None = None,
    basis_source: str = "header",
    source: str = "inferred",
) -> dict:
    item = {
        "effective_concept": concept,
        "row_key": row,
        "binding_key": row,
        "is_primary": primary,
        "status": "bound",
        "source": source,
    }
    evidence = {}
    if code:
        evidence["line_code"] = code
    if basis:
        evidence["period_basis"] = basis
        evidence["period_basis_source"] = basis_source
    if section:
        item["label_path_text"] = f"ОДДС › {section} › Проценты к уплате"
    if evidence:
        item["evidence"] = evidence
    if formula:
        item["formula"] = formula
    if sheet:
        item["sheet"] = sheet
    return item


def _fact(
    row: str,
    period: str,
    value: str,
    cell: str,
    *,
    raw: str | None = None,
    scale: str | None = None,
) -> dict:
    item = {
        "row_key": row,
        "axis_id": "a",
        "period_id": period,
        "normalized_value": value,
        "cell_id": cell,
    }
    if raw is not None:
        item["value_dec"] = raw
    if scale is not None:
        item["scale_factor"] = scale
    return item


def _period(pid: str, index: int, year: int | None = None) -> dict:
    item = {
        "axis_id": "a",
        "period_id": pid,
        "period_index": index,
        "timeline_id": "t",
        "grain": "quarter",
    }
    if year is not None:
        item["calendar_year"] = year
    return item
