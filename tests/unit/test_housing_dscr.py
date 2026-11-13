"""Вариант DSCR housing: ряд интервалов, без подстановки нуля и без займа участника."""

from __future__ import annotations

from decimal import Decimal

from finance_analysis.application.catalog import load_catalog
from finance_analysis.application.model_types import load_model_types
from finance_analysis.application.report import render_markdown
from finance_analysis.domain.covenant import select_ratio
from finance_analysis.domain.cover_metrics import adscr
from finance_analysis.domain.mapping import assign_rows, marked_line_code
from finance_analysis.domain.metrics import confirm_paid_interest
from finance_analysis.domain.model_type import (
    Effective,
    applicability,
    confirmed_variants,
    infer,
    open_concepts,
)

_NUMERATOR = ("cfo_statement", "cfi_statement", "financing_inflows")
_DENOMINATOR = ("senior_principal", "senior_interest_paid")


def _row(key: str, label: str, **extra) -> dict:
    item = {
        "kind": "fact",
        "binding_key": key,
        "row_key": key,
        "label": label,
        "label_path_text": extra.pop("label_path_text", label),
        "sign": None,
        "unit": "money",
        "sheet": extra.pop("sheet", "ОДДС"),
    }
    item.update(extra)
    return item


def _assign(rows: list[dict]) -> dict:
    return assign_rows(rows, [], load_catalog())


def _bind(concept: str, row: str, label: str, **extra) -> dict:
    item = {
        "effective_concept": concept,
        "row_key": row,
        "is_primary": extra.pop("is_primary", True),
        "status": "bound",
        "source": "inferred",
        "label": label,
        "label_path_text": extra.pop("label_path_text", label),
    }
    item.update(extra)
    return item


def _fact(row: str, period: str, value, **extra) -> dict:
    item = {
        "row_key": row,
        "axis_id": extra.pop("axis_id", "a"),
        "period_id": period,
        "value": value,
        "normalized_value": value,
        "cell_id": extra.pop("cell_id", f"{row}!{period}"),
    }
    item.update(extra)
    return item


def _period(period: str, index: int = 0) -> dict:
    return {
        "period_id": period,
        "axis_id": "a",
        "grain": "quarter",
        "period_index": index,
        "timeline_id": "t",
    }


def _run(bindings, facts, periods, profile=None, variant="housing"):
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
    types = load_model_types()
    package = load_catalog()
    money = frozenset(name for name, item in package.concepts.items() if item.unit == "money")
    return select_ratio(
        "dscr",
        variant,
        common,
        profile=profile,
        profile_ref=None,
        composed=types.composed,
        concepts=package.ids,
        money=money,
    )


def _base_bindings() -> list[dict]:
    return [
        _bind("cfo_statement", "cfo", "Сальдо денежных потоков от текущих операций"),
        _bind("cfi_statement", "cfi", "Сальдо денежных потоков от инвестиционных операций"),
        _bind(
            "financing_inflows",
            "in",
            "Поступления по финансовой деятельности",
            evidence={"line_code": "4310", "flow_role": "total"},
        ),
        _bind(
            "senior_principal",
            "prin",
            "Погашение основного долга по несубординированным кредитам",
        ),
        _bind(
            "senior_interest_paid",
            "intr",
            "Уплаченные проценты по несубординированным кредитам",
        ),
    ]


def _base_facts(cfo="10", cfi="-30", inflow="40", principal="4", interest="6", period="Q1") -> list[dict]:
    return [
        _fact("cfo", period, cfo),
        _fact("cfi", period, cfi),
        _fact("in", period, inflow),
        _fact("prin", period, principal),
        _fact("intr", period, interest),
    ]


def test_line_codes_bind_statement_balances_and_leave_net_financing():
    assert marked_line_code("4310") == "4310"
    assert marked_line_code("4224") is None
    assert marked_line_code("стр. 4224") == "стр. 4224"
    assert marked_line_code("4323") is None
    assert marked_line_code("4300") is None
    assert marked_line_code("4320") is None
    assert marked_line_code("1410") == "1410"
    assert marked_line_code("ф.5 (740)") == "ф.5 (740)"
    got = _assign(
        [
            _row("cfo", "Сальдо текущих", line_code="4100"),
            _row("cfi", "Сальдо инвестиционных", line_code="4200"),
            _row("in", "Поступления - всего", line_code="4310"),
            _row("loan", "Получение кредитов и займов", line_code="4311"),
            _row("net", "Сальдо денежных потоков от финансовых операций", line_code="4300"),
            _row("pay", "Платежи - всего", line_code="4320"),
            _row("body", "Возврат кредитов и займов", line_code="4323"),
            _row("cap", "Проценты по долговым обязательствам", line_code="4224"),
            _row("accrued", "2330"),
            _row("value", "Прочее", values=["4310"]),
            _row("note", "Амортизация", line_code="ф.5 (740)"),
            _row("escrow", "Остаток на счетах эскроу"),
            _row("release", "Раскрытие эскроу"),
        ]
    )
    assert got["cfo"].concept == "cfo_statement"
    assert got["cfi"].concept == "cfi_statement"
    assert got["in"].concept == "financing_inflows"
    assert got["in"].evidence.get("flow_role") == "total"
    assert got["loan"].concept == "financing_inflows"
    assert got["loan"].evidence.get("flow_role") == "part"
    assert got["in"].is_primary and got["loan"].is_primary
    assert got["net"].concept != "financing_inflows"
    assert got["pay"].concept != "financing_inflows"
    assert got["body"].concept != "financing_inflows"
    assert got["body"].concept != "senior_principal"
    assert got["cap"].concept != "senior_interest_paid"
    assert got["cap"].concept != "interest"
    assert got["accrued"].concept == "interest"
    assert got["accrued"].concept != "senior_interest_paid"
    assert got["value"].concept != "financing_inflows"
    assert got["note"].concept == "depreciation_notes"
    assert got["escrow"].concept == "escrow_balance"
    assert got["release"].concept == "escrow_disclosure"
    paid = {}
    confirm_paid_interest(paid, [{"effective_concept": "interest", "is_primary": True, "status": "bound", "label": "4224", "evidence": {"line_code": "4224"}, "source": "inferred"}], frozenset())
    assert "interest_paid" not in paid


def test_senior_path_binds_cash_codes_and_keeps_both_tranches():
    got = _assign(
        [
            _row(
                "total",
                "Total debt service",
                label_path=["Senior Debt", "Total debt service"],
                label_path_text="Senior Debt › Total debt service",
            ),
            _row(
                "one",
                "Погашение основного долга по несубординированным кредитам",
                label_path_text="Senior Debt › Транш 1",
            ),
            _row(
                "two",
                "Погашение основного долга по несубординированным кредитам",
                label_path_text="Senior Debt › Транш 2",
            ),
            _row(
                "member",
                "Погашение займа участника",
                label_path_text="Заём участника › Погашение займа участника",
            ),
            _row("bare", "Обслуживание долга"),
            _row(
                "cash",
                "Проценты по долговым обязательствам",
                line_code="стр. 4224",
                label_path=["Senior Debt", "Проценты"],
                label_path_text="Senior Debt › Проценты",
            ),
        ]
    )
    assert got["total"].concept == "debt_service"
    assert got["one"].concept == "senior_principal"
    assert got["two"].concept == "senior_principal"
    assert got["one"].is_primary and got["two"].is_primary
    assert got["member"].concept != "senior_principal"
    assert got["bare"].concept == "debt_service"
    assert got["cash"].concept == "senior_interest_paid"


def test_interval_ratio_uses_signed_balances_and_cash_service():
    got = _run(_base_bindings(), _base_facts(), [_period("Q1")])
    row = got["rows"][0]
    assert row["status"] == "computed"
    assert row["value"] == Decimal("2.0000000000")
    assert row["variant"] == "housing"
    assert "financing_inflows_included" in row["warnings"]
    assert "жилищн" in row["methodology"].casefold()


def test_each_missing_component_is_named_and_explicit_zero_is_kept():
    periods = [_period("Q1")]
    for concept, row_key, value_key in (
        ("cfo_statement", "cfo", "cfo"),
        ("cfi_statement", "cfi", "cfi"),
        ("financing_inflows", "in", "inflow"),
        ("senior_principal", "prin", "principal"),
        ("senior_interest_paid", "intr", "interest"),
    ):
        facts = _base_facts()
        facts = [item for item in facts if item["row_key"] != row_key]
        facts.append(_fact(row_key, "Q1", None))
        got = _run(_base_bindings(), facts, periods)
        row = got["rows"][0]
        assert row["status"] == "not_computed", concept
        assert row["value"] is None
        assert row["reason"] == "missing_component"
        assert concept in row["missing"]
    present = {"cfo": "10", "cfi": "0", "inflow": "40", "principal": "4", "interest": "6"}
    zero_cfi = _run(_base_bindings(), _base_facts(**present), periods)
    assert zero_cfi["rows"][0]["status"] == "computed"
    assert zero_cfi["rows"][0]["value"] == Decimal("5.0000000000")


def test_zero_denominator_stays_in_the_series_and_pf_still_drops_it():
    bindings = _base_bindings()
    facts = _base_facts(period="Q1", principal="0", interest="0") + _base_facts(period="Q2")
    got = _run(bindings, facts, [_period("Q1", 0), _period("Q2", 1)])
    by_period = {row["period_id"]: row for row in got["rows"]}
    assert by_period["Q1"]["status"] == "no_debt_service"
    assert by_period["Q1"]["reason"] == "zero_denominator"
    assert by_period["Q1"]["value"] is None
    assert by_period["Q2"]["status"] == "computed"
    assert by_period["Q2"]["value"] == Decimal("2.0000000000")
    pf = _run(
        [_bind("cfads", "c", "CFADS"), _bind("debt_service", "d", "Debt service")],
        [_fact("c", "Y", "8"), _fact("d", "Y", "0")],
        [_period("Y")],
        variant="pf",
    )
    assert pf["rows"] == []
    kept = _run(
        [_bind("cfads", "c", "CFADS"), _bind("debt_service", "d", "Debt service")],
        [_fact("c", "Y", "100"), _fact("d", "Y", "40")],
        [_period("Y")],
        variant="pf",
    )
    assert kept["rows"][0]["value"] == Decimal("2.5000000000")
    assert kept["rows"][0].get("variant") != "housing"


def test_negative_numerator_stays_a_negative_ratio():
    got = _run(
        _base_bindings(),
        _base_facts(cfo="-8", cfi="0", inflow="0", principal="4", interest="0"),
        [_period("Q1")],
    )
    assert got["rows"][0]["status"] == "computed"
    assert got["rows"][0]["value"] == Decimal("-2.0000000000")


def test_unmarked_debt_service_is_not_the_housing_denominator():
    bindings = [
        _bind("cfo_statement", "cfo", "Сальдо денежных потоков от текущих операций"),
        _bind("cfi_statement", "cfi", "Сальдо денежных потоков от инвестиционных операций"),
        _bind("financing_inflows", "in", "Поступления по финансовой деятельности", evidence={"line_code": "4310", "flow_role": "total"}),
        _bind("debt_service", "debt", "Обслуживание долга"),
    ]
    got = _run(bindings, [_fact("cfo", "Q1", "10"), _fact("cfi", "Q1", "-30"), _fact("in", "Q1", "40"), _fact("debt", "Q1", "10")], [_period("Q1")])
    row = got["rows"][0]
    assert row["status"] == "not_computed"
    assert row["reason"] == "seniority_unknown"
    assert row["value"] is None


def test_senior_total_parts_and_participant_loan():
    numerator = [
        _bind("cfo_statement", "cfo", "Сальдо денежных потоков от текущих операций"),
        _bind("cfi_statement", "cfi", "Сальдо денежных потоков от инвестиционных операций"),
        _bind("financing_inflows", "in", "Поступления по финансовой деятельности", evidence={"line_code": "4310", "flow_role": "total"}),
    ]
    facts = [_fact("cfo", "Q1", "10"), _fact("cfi", "Q1", "-30"), _fact("in", "Q1", "40")]
    periods = [_period("Q1")]
    total_only = _run(
        [
            *numerator,
            _bind("debt_service", "total", "Total debt service", label_path_text="Senior Debt › Total debt service"),
        ],
        [*facts, _fact("total", "Q1", "10")],
        periods,
    )
    assert total_only["rows"][0]["value"] == Decimal("2.0000000000")
    parts = _run(
        [
            *numerator,
            _bind("senior_principal", "a", "Погашение основного долга по несубординированным кредитам", label_path_text="Senior Debt › Транш 1"),
            _bind("senior_principal", "b", "Погашение основного долга по несубординированным кредитам", label_path_text="Senior Debt › Транш 2"),
            _bind("principal", "member", "Погашение займа участника", label_path_text="Заём участника › Погашение займа участника"),
            _bind("senior_interest_paid", "intr", "Уплаченные проценты по несубординированным кредитам"),
        ],
        [*facts, _fact("a", "Q1", "4"), _fact("b", "Q1", "6"), _fact("member", "Q1", "100"), _fact("intr", "Q1", "0")],
        periods,
    )
    assert parts["rows"][0]["value"] == Decimal("2.0000000000")
    once = _run(
        [
            *numerator,
            _bind("debt_service", "total", "Total debt service", label_path_text="Senior Debt › Total debt service"),
            _bind("senior_principal", "a", "Погашение основного долга по несубординированным кредитам", label_path_text="Senior Debt › Транш 1"),
            _bind("senior_principal", "b", "Погашение основного долга по несубординированным кредитам", label_path_text="Senior Debt › Транш 2"),
            _bind("senior_interest_paid", "intr", "Уплаченные проценты по несубординированным кредитам"),
        ],
        [*facts, _fact("total", "Q1", "10"), _fact("a", "Q1", "4"), _fact("b", "Q1", "6"), _fact("intr", "Q1", "0")],
        periods,
    )
    assert once["rows"][0]["value"] == Decimal("2.0000000000")


def test_interest_addback_defaults_off_and_draws_are_marked():
    bindings = _base_bindings() + [
        _bind("interest", "paid", "4123", evidence={"line_code": "стр. 4123"}),
    ]
    facts = _base_facts() + [_fact("paid", "Q1", "5")]
    off = _run(bindings, facts, [_period("Q1")])
    assert off["rows"][0]["value"] == Decimal("2.0000000000")
    assert "interest_inside_numerator" in off["rows"][0]["warnings"]
    on = _run(bindings, facts, [_period("Q1")], profile={"interest_addback": True})
    assert on["rows"][0]["status"] == "not_computed"
    assert on["rows"][0]["reason"] == "interest_addback_unattributed"
    assert on["rows"][0]["value"] is None
    assert "interest_addback" not in on["rows"][0]["components"]
    draw = _run(
        [
            _bind("cfo_statement", "cfo", "Сальдо денежных потоков от текущих операций"),
            _bind("cfi_statement", "cfi", "Сальдо денежных потоков от инвестиционных операций"),
            _bind("financing_inflows", "draw", "Получение кредитов и займов", evidence={"line_code": "4311", "flow_role": "part"}),
            _bind("senior_principal", "prin", "Погашение основного долга по несубординированным кредитам"),
            _bind("senior_interest_paid", "intr", "Уплаченные проценты по несубординированным кредитам"),
        ],
        [
            _fact("cfo", "Q1", "10"),
            _fact("cfi", "Q1", "0"),
            _fact("draw", "Q1", "40"),
            _fact("prin", "Q1", "4"),
            _fact("intr", "Q1", "6"),
        ],
        [_period("Q1")],
    )
    assert draw["rows"][0]["value"] == Decimal("5.0000000000")
    assert "same_interval_draw_and_repay" in draw["rows"][0]["warnings"]
    assert "financing_inflows_included" in draw["rows"][0]["warnings"]


def test_capitalized_interest_without_a_cash_line_is_a_confirmed_zero():
    bindings = [
        _bind("cfo_statement", "cfo", "Сальдо денежных потоков от текущих операций"),
        _bind("cfi_statement", "cfi", "Сальдо денежных потоков от инвестиционных операций"),
        _bind("financing_inflows", "in", "Поступления по финансовой деятельности", evidence={"line_code": "4310", "flow_role": "total"}),
        _bind("senior_principal", "prin", "Погашение основного долга по несубординированным кредитам"),
        _bind("interest", "cap", "Капитализация процентов", label_path_text="Senior Debt › Капитализация процентов"),
    ]
    facts = [_fact("cfo", "Q1", "8"), _fact("cfi", "Q1", "0"), _fact("in", "Q1", "0"), _fact("prin", "Q1", "4"), _fact("cap", "Q1", "9")]
    proved = _run(bindings, facts, [_period("Q1")])
    assert proved["rows"][0]["status"] == "computed"
    assert proved["rows"][0]["value"] == Decimal("2.0000000000")
    missing = _run(bindings[:-1], facts[:-1], [_period("Q1")])
    assert missing["rows"][0]["status"] == "not_computed"
    assert "senior_interest_paid" in missing["rows"][0]["missing"]


def test_book_rows_are_compared_and_escrow_stays_out_of_the_numerator():
    bindings = _base_bindings() + [
        _bind("cfads", "book_cfads", "CFADS"),
        _bind("dscr", "book_dscr", "DSCR"),
        _bind("escrow_balance", "escrow", "Остаток на счетах эскроу"),
        _bind("escrow_disclosure", "release", "Раскрытие счетов эскроу"),
    ]
    same = _run(
        bindings,
        _base_facts() + [_fact("book_cfads", "Q1", "20"), _fact("book_dscr", "Q1", "2"), _fact("escrow", "Q1", "100"), _fact("release", "Q1", "0")],
        [_period("Q1")],
    )
    assert same["rows"][0]["value"] == Decimal("2.0000000000")
    assert "housing_book_mismatch" not in same["rows"][0]["warnings"]
    assert "escrow_outside_cfads" not in same["rows"][0]["warnings"]
    other = _run(
        bindings,
        _base_facts(cfo="0") + [_fact("book_cfads", "Q1", "999"), _fact("book_dscr", "Q1", "9"), _fact("escrow", "Q1", "100"), _fact("release", "Q1", "50")],
        [_period("Q1")],
    )
    assert other["rows"][0]["value"] == Decimal("1.0000000000")
    assert "housing_book_mismatch" in other["rows"][0]["warnings"]
    assert "escrow_outside_cfads" in other["rows"][0]["warnings"]
    assert "100" not in other["rows"][0]["components"].values()


def test_report_names_the_housing_formula():
    got = _run(_base_bindings(), _base_facts(), [_period("Q1")])
    text = render_markdown(
        {
            "analysis_id": "a",
            "status": "succeeded",
            "builder_ref": {},
            "versions": {},
            "result_data": {"ratios": [{**got["rows"][0], "metric": "dscr"}]},
        }
    )
    assert "variant: housing" in text
    assert "не универсальный DSCR" in text
    assert "cfo_statement + cfi_statement + financing_inflows" in text
    assert "senior_principal + senior_interest_paid" in text
    assert "поступления по финансовой деятельности" in text
    missing = _run(
        [row for row in _base_bindings() if row["row_key"] != "cfi"],
        _base_facts(),
        [_period("Q1")],
    )
    missing_text = render_markdown(
        {
            "analysis_id": "a",
            "status": "not_computed",
            "builder_ref": {},
            "versions": {},
            "result_data": {"ratios": [{**missing["rows"][0], "metric": "dscr"}]},
        }
    )
    assert "variant: housing" in missing_text
    assert "не универсальный DSCR" in missing_text
    pf = _run(
        [_bind("cfads", "c", "CFADS"), _bind("debt_service", "d", "Debt service")],
        [_fact("c", "Y", "100"), _fact("d", "Y", "40")],
        [_period("Y")],
        variant="pf",
    )
    pf_text = render_markdown(
        {
            "analysis_id": "a",
            "status": "succeeded",
            "builder_ref": {},
            "versions": {},
            "result_data": {"ratios": [{**pf["rows"][0], "metric": "dscr"}]},
        }
    )
    assert "variant: housing" not in pf_text
    assert "не универсальный DSCR" not in pf_text


def test_escrow_type_requires_housing_and_other_types_do_not():
    catalog = load_model_types()
    assert applicability(catalog, ("development_escrow",), "dscr") == "required"
    assert catalog.types["development_escrow"].variants["dscr"] == "housing"
    assert applicability(catalog, ("project_finance",), "dscr") == "required"
    assert catalog.types["project_finance"].variants["dscr"] == "pf"
    assert catalog.types["development_escrow"].metrics["dscr_min"] == "not_applicable"
    assert catalog.types["development_escrow"].metrics["adscr"] == "not_applicable"
    escrow = infer(catalog, bound=frozenset({"escrow_balance"}), sheets=frozenset(), accept=0.6, gap=0.15)
    assert escrow.confident is True and escrow.primary == "development_escrow"
    verdict = Effective(
        labels=escrow.labels,
        primary=escrow.primary,
        source="inferred",
        reason=None,
        seq=None,
        profile_version=None,
        score=escrow.scores[escrow.primary],
        scores=escrow.scores,
        candidates=escrow.candidates,
    )
    assert confirmed_variants(catalog, verdict)["dscr"] == "housing"
    project = infer(catalog, bound=frozenset({"cfads", "debt_service"}), sheets=frozenset({"Debt"}), accept=0.6, gap=0.15)
    assert project.primary == "project_finance"
    project_verdict = Effective(
        labels=project.labels,
        primary=project.primary,
        source="inferred",
        reason=None,
        seq=None,
        profile_version=None,
        score=project.scores[project.primary],
        scores=project.scores,
        candidates=project.candidates,
    )
    assert confirmed_variants(catalog, project_verdict)["dscr"] == "pf"
    unresolved = Effective(
        labels=(),
        primary=None,
        source="unresolved",
        reason="ambiguous",
        seq=None,
        profile_version=None,
        score=None,
        scores={},
        candidates=(),
    )
    assert confirmed_variants(catalog, unresolved) == {}
    asked = open_concepts(
        catalog,
        ("development_escrow",),
        bound=frozenset({"escrow_balance", "debt_outstanding"}),
        absent=frozenset(),
    )
    assert set(_NUMERATOR) | set(_DENOMINATOR) <= set(asked)
    assert "cfads" not in asked and "debt_service" not in asked
    hybrid = open_concepts(
        catalog,
        ("development_escrow", "project_finance"),
        bound=frozenset({"escrow_balance", "debt_outstanding"}),
        absent=frozenset(),
    )
    # Разные обязательные варианты: вопросы остаются на базовой формуле.
    assert "cfads" in hybrid and "debt_service" in hybrid
    assert "cfo_statement" not in hybrid
    mixed = Effective(
        labels=("development_escrow", "project_finance"),
        primary="development_escrow",
        source="inferred",
        reason=None,
        seq=None,
        profile_version=None,
        score=None,
        scores={},
        candidates=(),
    )
    assert confirmed_variants(catalog, mixed)["dscr"] == "housing"
    other = open_concepts(
        catalog,
        ("project_finance",),
        bound=frozenset({"cfads", "debt_service"}),
        absent=frozenset(),
    )
    assert "cfo_statement" not in other
    forced = _run(
        [_bind("cfads", "c", "CFADS"), _bind("debt_service", "d", "Debt service")],
        [_fact("c", "Q1", "20"), _fact("d", "Q1", "10")],
        [_period("Q1")],
        variant="housing",
    )
    assert forced["rows"][0]["status"] == "not_computed"
    assert forced["rows"][0]["value"] is None
    named = _run(
        _base_bindings(),
        _base_facts(),
        [_period("Q1")],
        profile={"dscr_definition": {"variant": "housing"}},
        variant="pf",
    )
    assert named["rows"][0]["variant"] == "housing"
    assert named["rows"][0]["value"] == Decimal("2.0000000000")


def test_adscr_does_not_invent_debt_service_after_the_pf_fallback():
    got = adscr(
        facts=[_fact("c", "Y", "8"), _fact("i", "Y", "2"), _fact("p", "Y", "2")],
        bindings=[
            _bind("cfads", "c", "CFADS"),
            _bind("interest", "i", "Interest"),
            _bind("principal", "p", "Principal"),
        ],
        periods=[{**_period("Y"), "grain": "year", "period_start": "2025-01-01", "period_end": "2025-12-31"}],
        period_phase={},
        explicit_phases=False,
    )
    assert got["rows"] == []
    assert got["status"] == "missing_input"


def _numerator() -> list[dict]:
    return [
        _bind("cfo_statement", "cfo", "Сальдо денежных потоков от текущих операций"),
        _bind("cfi_statement", "cfi", "Сальдо денежных потоков от инвестиционных операций"),
        _bind(
            "financing_inflows",
            "in",
            "Поступления по финансовой деятельности",
            evidence={"line_code": "4310", "flow_role": "total"},
        ),
    ]


def _cash_line(concept: str, row: str, label: str, code: str, path: str, **extra) -> dict:
    return _bind(
        concept,
        row,
        label,
        label_path_text=path,
        evidence={"line_code": code},
        **extra,
    )


def _facts_20() -> list[dict]:
    return [_fact("cfo", "Q1", "10"), _fact("cfi", "Q1", "-30"), _fact("in", "Q1", "40")]


def test_addback_adds_primary_senior_interest_and_leaves_subordinated_out():
    senior = _cash_line(
        "senior_interest_paid",
        "intr",
        "Уплаченные проценты по несубординированным кредитам",
        "стр. 4123",
        "Senior Debt › Транш A › Уплаченные проценты по несубординированным кредитам",
    )
    junior = _cash_line(
        "interest",
        "sub",
        "Уплаченные проценты по займу участника",
        "стр. 4123",
        "Заём участника › Уплаченные проценты по займу участника",
    )
    bindings = [
        *_numerator(),
        _bind(
            "senior_principal",
            "prin",
            "Погашение основного долга по несубординированным кредитам",
            label_path_text="Senior Debt › Транш A › Погашение",
        ),
        senior,
        junior,
    ]
    facts = [*_facts_20(), _fact("prin", "Q1", "4"), _fact("intr", "Q1", "6"), _fact("sub", "Q1", "100")]
    off = _run(bindings, facts, [_period("Q1")])
    assert off["rows"][0]["value"] == Decimal("2.0000000000")
    assert "interest_inside_numerator" in off["rows"][0]["warnings"]
    on = _run(bindings, facts, [_period("Q1")], profile={"interest_addback": True})
    assert on["rows"][0]["status"] == "computed"
    assert on["rows"][0]["value"] == Decimal("2.6000000000")
    assert on["rows"][0]["components"]["interest_addback"] == "6"
    assert "100" not in on["rows"][0]["components"].values()


def test_addback_refuses_an_aggregate_cash_interest_line():
    bindings = [
        *_numerator(),
        _bind("senior_principal", "prin", "Погашение основного долга по несубординированным кредитам"),
        _bind("senior_interest_paid", "intr", "Уплаченные проценты по несубординированным кредитам"),
        _cash_line(
            "interest",
            "agg",
            "Проценты по старшим и субординированным кредитам",
            "стр. 4123",
            "ОДДС › Проценты по старшим и субординированным кредитам",
        ),
    ]
    facts = [*_facts_20(), _fact("prin", "Q1", "4"), _fact("intr", "Q1", "6"), _fact("agg", "Q1", "15")]
    off = _run(bindings, facts, [_period("Q1")])
    assert off["rows"][0]["status"] == "computed"
    assert off["rows"][0]["value"] == Decimal("2.0000000000")
    on = _run(bindings, facts, [_period("Q1")], profile={"interest_addback": True})
    assert on["rows"][0]["status"] == "not_computed"
    assert on["rows"][0]["reason"] == "interest_addback_unattributed"
    assert on["rows"][0]["value"] is None
    assert "interest_addback_unattributed" in on["rows"][0]["warnings"]
    assert "15" not in on["rows"][0]["components"].values()
    only = _run(
        [
            *_numerator(),
            _bind("senior_principal", "prin", "Погашение основного долга по несубординированным кредитам"),
            _cash_line(
                "interest",
                "agg",
                "Проценты по старшим и субординированным кредитам",
                "стр. 4123",
                "ОДДС › Проценты по старшим и субординированным кредитам",
            ),
        ],
        [*_facts_20(), _fact("prin", "Q1", "4"), _fact("agg", "Q1", "15")],
        [_period("Q1")],
    )
    assert only["rows"][0]["status"] == "not_computed"
    assert only["rows"][0]["reason"] == "seniority_unsplit"
    assert only["rows"][0]["value"] is None


def test_addback_ignores_a_non_primary_cash_interest_line():
    extra = _cash_line(
        "senior_interest_paid",
        "paid",
        "Уплаченные проценты по несубординированным кредитам",
        "стр. 4123",
        "Senior Debt › Транш A › Уплаченные проценты",
        is_primary=False,
    )
    bindings = _base_bindings() + [extra]
    facts = _base_facts() + [_fact("paid", "Q1", "5")]
    off = _run(bindings, facts, [_period("Q1")])
    assert off["rows"][0]["value"] == Decimal("2.0000000000")
    on = _run(bindings, facts, [_period("Q1")], profile={"interest_addback": True})
    assert on["rows"][0]["status"] == "not_computed"
    assert on["rows"][0]["reason"] == "interest_addback_unattributed"
    assert on["rows"][0]["value"] is None
    primary = _cash_line(
        "senior_interest_paid",
        "intr",
        "Уплаченные проценты по несубординированным кредитам",
        "стр. 4123",
        "Senior Debt › Транш A › Уплаченные проценты по несубординированным кредитам",
    )
    both = [
        *_numerator(),
        _bind(
            "senior_principal",
            "prin",
            "Погашение основного долга по несубординированным кредитам",
            label_path_text="Senior Debt › Транш A › Погашение",
        ),
        primary,
        _cash_line(
            "senior_interest_paid",
            "copy",
            "Уплаченные проценты по несубординированным кредитам",
            "стр. 4123",
            "Senior Debt › Транш A › черновик",
            is_primary=False,
        ),
    ]
    summed = _run(
        both,
        [*_facts_20(), _fact("prin", "Q1", "4"), _fact("intr", "Q1", "6"), _fact("copy", "Q1", "50")],
        [_period("Q1")],
        profile={"interest_addback": True},
    )
    assert summed["rows"][0]["status"] == "computed"
    assert summed["rows"][0]["value"] == Decimal("2.6000000000")
    assert summed["rows"][0]["components"]["interest_addback"] == "6"


def _tranche_principal(row: str, token: str) -> dict:
    label = "Погашение основного долга по несубординированным кредитам"
    return _bind("senior_principal", row, label, label_path_text=f"Senior Debt › Транш {token} › {label}")


def _cap(row: str, token: str) -> dict:
    return _bind(
        "interest",
        row,
        "Капитализация процентов",
        label_path_text=f"Senior Debt › Транш {token} › Капитализация процентов",
    )


def test_missing_cash_interest_of_another_tranche_stays_missing():
    bindings = [
        *_numerator(),
        _tranche_principal("prin_a", "A"),
        _tranche_principal("prin_b", "B"),
        _cap("cap_a", "A"),
        _bind(
            "senior_interest_paid",
            "intr_b",
            "Уплаченные проценты по несубординированным кредитам",
            label_path_text="Senior Debt › Транш B › Уплаченные проценты",
        ),
    ]
    facts = [*_facts_20(), _fact("prin_a", "Q1", "4"), _fact("prin_b", "Q1", "6"), _fact("cap_a", "Q1", "9")]
    got = _run(bindings, facts, [_period("Q1")])
    assert got["rows"][0]["status"] == "not_computed"
    assert got["rows"][0]["reason"] == "missing_component"
    assert "senior_interest_paid" in got["rows"][0]["missing"]
    assert got["rows"][0]["value"] is None


def test_each_capitalized_tranche_confirms_its_own_zero():
    bindings = [
        *_numerator(),
        _tranche_principal("prin_a", "A"),
        _tranche_principal("prin_b", "B"),
        _cap("cap_a", "A"),
        _cap("cap_b", "B"),
    ]
    facts = [
        *_facts_20(),
        _fact("prin_a", "Q1", "4"),
        _fact("prin_b", "Q1", "6"),
        _fact("cap_a", "Q1", "9"),
        _fact("cap_b", "Q1", "8"),
    ]
    got = _run(bindings, facts, [_period("Q1")])
    assert got["rows"][0]["status"] == "computed"
    assert got["rows"][0]["value"] == Decimal("2.0000000000")
    assert "9" not in got["rows"][0]["components"].values()
    assert "8" not in got["rows"][0]["components"].values()


def test_present_cash_interest_is_added_to_the_capitalized_tranche():
    bindings = [
        *_numerator(),
        _tranche_principal("prin_a", "A"),
        _tranche_principal("prin_b", "B"),
        _cap("cap_a", "A"),
        _bind(
            "senior_interest_paid",
            "intr_b",
            "Уплаченные проценты по несубординированным кредитам",
            label_path_text="Senior Debt › Транш B › Уплаченные проценты",
        ),
    ]
    facts = [
        *_facts_20(),
        _fact("prin_a", "Q1", "4"),
        _fact("prin_b", "Q1", "6"),
        _fact("cap_a", "Q1", "9"),
        _fact("intr_b", "Q1", "6"),
    ]
    got = _run(bindings, facts, [_period("Q1")])
    assert got["rows"][0]["status"] == "computed"
    assert got["rows"][0]["value"] == Decimal("1.2500000000")
    assert got["rows"][0]["components"]["denominator"] == "16"


def test_capitalization_in_another_period_does_not_confirm_zero():
    bindings = [*_numerator(), _tranche_principal("prin_a", "A"), _cap("cap_a", "A")]
    facts = []
    for period, cap in (("Q1", None), ("Q2", "9")):
        facts.extend(
            [
                _fact("cfo", period, "8"),
                _fact("cfi", period, "0"),
                _fact("in", period, "0"),
                _fact("prin_a", period, "4"),
            ]
        )
        if cap is not None:
            facts.append(_fact("cap_a", period, cap))
    got = _run(bindings, facts, [_period("Q1", 0), _period("Q2", 1)])
    by_period = {row["period_id"]: row for row in got["rows"]}
    assert by_period["Q1"]["status"] == "not_computed"
    assert "senior_interest_paid" in by_period["Q1"]["missing"]
    assert by_period["Q1"]["value"] is None
    assert by_period["Q2"]["status"] == "computed"
    assert by_period["Q2"]["value"] == Decimal("2.0000000000")


def test_shareholder_capitalization_does_not_confirm_senior_interest():
    bindings = [
        *_numerator(),
        _bind("senior_principal", "prin", "Погашение основного долга по несубординированным кредитам"),
        _bind(
            "interest",
            "cap",
            "Капитализация процентов",
            label_path_text="Заём участника › Капитализация процентов",
        ),
    ]
    facts = [*_facts_20(), _fact("prin", "Q1", "4"), _fact("cap", "Q1", "9")]
    got = _run(bindings, facts, [_period("Q1")])
    assert got["rows"][0]["status"] == "not_computed"
    assert "senior_interest_paid" in got["rows"][0]["missing"]
    assert got["rows"][0]["value"] is None


def _book_rows() -> list[dict]:
    """Синтетический ОДДС застройщика. Это не живая книга и не выгрузка 1С."""

    def path(sheet: str, *parts: str) -> dict:
        return {"label_path": [sheet, *parts], "label_path_text": " › ".join((sheet, *parts))}

    return [
        _row("cfo", "Сальдо денежных потоков от текущих операций", line_code="4100", **path("ОДДС", "Текущие операции", "Сальдо")),
        _row("ocf", "Операционный денежный поток", **path("Модель", "Операционный денежный поток")),
        _row("cfi", "Сальдо денежных потоков от инвестиционных операций", line_code="4200", **path("ОДДС", "Инвестиционные операции", "Сальдо")),
        _row("spend", "Приобретение внеоборотных активов", **path("ОДДС", "Инвестиционные операции", "Приобретение")),
        _row("in", "Поступления - всего", line_code="4310", **path("ОДДС", "Финансовые операции", "Поступления")),
        _row("draw", "Получение кредитов и займов", line_code="4311", **path("ОДДС", "Финансовые операции", "Кредиты")),
        _row("equity", "Денежные вклады собственников", line_code="4312", **path("ОДДС", "Финансовые операции", "Вклады")),
        _row("shares", "Поступления от выпуска акций", line_code="4313", **path("ОДДС", "Финансовые операции", "Акции")),
        _row("bonds", "Поступления от выпуска облигаций", line_code="4314", **path("ОДДС", "Финансовые операции", "Облигации")),
        _row("other_in", "Прочие поступления по финансовой деятельности", line_code="4319", **path("ОДДС", "Финансовые операции", "Прочие")),
        _row("net", "Сальдо денежных потоков от финансовых операций", line_code="4300", **path("ОДДС", "Финансовые операции", "Сальдо")),
        _row("pay", "Платежи - всего", line_code="4320", **path("ОДДС", "Финансовые операции", "Платежи")),
        _row(
            "prin_a",
            "Возврат кредитов и займов",
            line_code="стр. 4323",
            **path("Senior Debt", "Транш A", "Возврат кредитов и займов"),
        ),
        _row(
            "prin_b",
            "Возврат кредитов и займов",
            line_code="стр. 4323",
            **path("Senior Debt", "Транш B", "Возврат кредитов и займов"),
        ),
        _row(
            "member",
            "Погашение кредитов и займов",
            line_code="стр. 4323",
            **path("Заём участника", "Погашение кредитов и займов"),
        ),
        _row(
            "intr_a",
            "Проценты по долговым обязательствам",
            line_code="стр. 4224",
            **path("Senior Debt", "Транш A", "Проценты по долговым обязательствам"),
        ),
        _row(
            "intr_b",
            "Проценты по долговым обязательствам",
            line_code="стр. 4123",
            **path("Senior Debt", "Транш B", "Проценты по долговым обязательствам"),
        ),
        _row(
            "cap_a",
            "Капитализация процентов",
            **path("Senior Debt", "Транш A", "Капитализация процентов"),
        ),
        _row("accrued", "Проценты к уплате", **path("ОФР", "Проценты к уплате")),
        _row("escrow", "Остаток на счетах эскроу", **path("Эскроу", "Остаток")),
        _row("release", "Раскрытие эскроу", **path("Эскроу", "Раскрытие")),
    ]


def _book_bindings(rows: list[dict]) -> tuple[dict, list[dict]]:
    assigned = _assign(rows)
    bindings = []
    for row in rows:
        item = assigned[row["binding_key"]]
        bindings.append(
            {
                "effective_concept": item.concept,
                "row_key": row["row_key"],
                "is_primary": item.is_primary,
                "status": item.status,
                "source": item.source,
                "label": row["label"],
                "label_path": row.get("label_path"),
                "label_path_text": row.get("label_path_text", row["label"]),
                "evidence": dict(item.evidence),
            }
        )
    return assigned, bindings


def test_synthetic_developer_statement_is_not_a_live_book():
    """Ожидаемые привязки и ряд интервалов синтетического ОДДС, не сверка с файлом заказчика."""

    rows = _book_rows()
    assigned, bindings = _book_bindings(rows)
    assert assigned["cfo"].concept == "cfo_statement"
    assert assigned["cfo"].evidence.get("flow_role") == "total"
    assert assigned["ocf"].concept == "operating_cash_flow"
    assert assigned["ocf"].concept != "cfo_statement"
    assert assigned["cfi"].concept == "cfi_statement"
    assert assigned["cfi"].evidence.get("flow_role") == "total"
    assert assigned["spend"].concept != "cfi_statement"
    assert assigned["in"].concept == "financing_inflows"
    assert assigned["in"].evidence.get("flow_role") == "total"
    for key in ("draw", "equity", "shares", "bonds", "other_in"):
        assert assigned[key].concept == "financing_inflows"
        assert assigned[key].evidence.get("flow_role") == "part"
        assert assigned[key].is_primary
    assert assigned["net"].concept != "financing_inflows"
    assert assigned["pay"].concept != "financing_inflows"
    assert assigned["prin_a"].concept == "senior_principal"
    assert assigned["prin_b"].concept == "senior_principal"
    assert assigned["prin_a"].is_primary and assigned["prin_b"].is_primary
    assert assigned["member"].concept == "principal"
    assert assigned["member"].concept != "senior_principal"
    assert assigned["cap_a"].concept is None
    assert assigned["intr_a"].concept == "senior_interest_paid"
    assert assigned["intr_b"].concept == "senior_interest_paid"
    assert assigned["accrued"].concept == "interest"
    assert assigned["accrued"].concept != "senior_interest_paid"
    assert assigned["escrow"].concept == "escrow_balance"
    assert assigned["release"].concept == "escrow_disclosure"
    facts = []
    quarters = {
        "Q1": {
            "cfo": "0",
            "ocf": "999",
            "cfi": "-30",
            "spend": "-30",
            "in": "40",
            "draw": "40",
            "equity": "0",
            "shares": "0",
            "bonds": "0",
            "other_in": "0",
            "net": "40",
            "pay": "0",
            "prin_a": "0",
            "prin_b": "0",
            "member": "0",
            "intr_a": "0",
            "intr_b": "0",
            "cap_a": "7",
            "accrued": "11",
            "escrow": "500",
            "release": "0",
        },
        "Q2": {
            "cfo": "0",
            "ocf": "999",
            "cfi": "-10",
            "spend": "-10",
            "in": "40",
            "draw": "999",
            "equity": "0",
            "shares": "0",
            "bonds": "0",
            "other_in": "0",
            "net": "-64",
            "pay": "104",
            "prin_a": "0",
            "prin_b": "4",
            "member": "100",
            "intr_a": "0",
            "intr_b": "6",
            "cap_a": "5",
            "accrued": "9",
            "escrow": "500",
            "release": "50",
        },
        "Q3": {
            "cfo": "20",
            "ocf": "999",
            "cfi": "-5",
            "spend": "-5",
            "in": "0",
            "draw": "0",
            "equity": "0",
            "shares": "0",
            "bonds": "0",
            "other_in": "0",
            "net": "-17",
            "pay": "17",
            "prin_a": "10",
            "prin_b": "4",
            "member": "80",
            "intr_a": "2",
            "intr_b": "1",
            "accrued": "3",
            "escrow": "0",
            "release": "0",
        },
    }
    for period, values in quarters.items():
        for row, value in values.items():
            facts.append(_fact(row, period, value))
    got = _run(bindings, facts, [_period("Q1", 0), _period("Q2", 1), _period("Q3", 2)])
    by_period = {row["period_id"]: row for row in got["rows"]}
    assert by_period["Q1"]["status"] == "no_debt_service"
    assert by_period["Q1"]["reason"] == "zero_denominator"
    assert by_period["Q1"]["variant"] == "housing"
    assert "financing_inflows_included" in by_period["Q1"]["warnings"]
    assert "escrow_outside_cfads" not in by_period["Q1"]["warnings"]
    assert by_period["Q2"]["status"] == "computed"
    assert by_period["Q2"]["value"] == Decimal("3.0000000000")
    assert "same_interval_draw_and_repay" in by_period["Q2"]["warnings"]
    assert "escrow_outside_cfads" in by_period["Q2"]["warnings"]
    assert by_period["Q3"]["status"] == "computed"
    assert by_period["Q3"]["value"] == Decimal("0.8823529412")
    assert "escrow_outside_cfads" not in by_period["Q3"]["warnings"]
    for row in by_period.values():
        assert row["variant"] == "housing"
        assert "не универсальный DSCR" in row["methodology"]
        amounts = {value for value in row["components"].values() if isinstance(value, str)}
        leaked = {"999", "100", "80", "50", "500", "7", "5", "11", "9"}
        assert leaked.isdisjoint(amounts)
