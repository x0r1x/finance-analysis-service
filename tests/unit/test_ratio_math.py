"""DSCR и ICR: частное Decimal, без второй формулы и без нуля-заглушки."""

from decimal import Decimal

from finance_analysis.domain.audit import AuditInput
from finance_analysis.domain.metrics import coverage_ratio
from finance_analysis.domain.rematch import pair_status
from finance_analysis.plugins.rules.coverage import (
    PERIOD_GRAIN_MISMATCH,
    SCULPTING_DEVIATION,
    dscr_rows,
)
from finance_analysis.plugins.rules.ratios import (
    ICR_REFERENCE,
    MARKER_MIX,
    RATIO_MISMATCH,
    STATEMENT_REFERENCE,
    UNMAPPED_IN_METRIC_CHAIN,
)


def _binding(concept: str, row_key: str, **extra) -> dict:
    return {
        "row_key": row_key,
        "binding_key": row_key,
        "is_primary": True,
        "status": "bound",
        "effective_concept": concept,
        "source": "inferred",
        **extra,
    }


def _fact(row_key: str, value: str, period: str = "p") -> dict:
    return {
        "row_key": row_key,
        "axis_id": "Sheet!r1",
        "period_id": period,
        "normalized_value": value,
        "value_status": "cached",
    }


def _period(period: str = "p", marker: str | None = None) -> dict:
    return {"axis_id": "Sheet!r1", "period_id": period, "period_key_base": period, "marker_class": marker}


def test_negative_cfads_stays_negative_and_missing_concept_has_no_number():
    negative = coverage_ratio(
        metric="dscr",
        facts=[_fact("c", "-8"), _fact("d", "4")],
        bindings=[_binding("cfads", "c"), _binding("debt_service", "d")],
        periods=[_period()],
        period_phase={},
        explicit_phases=False,
    )
    assert negative["rows"][0]["status"] == "computed"
    assert negative["rows"][0]["value"] == Decimal("-2.0000000000")
    missing = coverage_ratio(
        metric="dscr",
        facts=[_fact("c", "8")],
        bindings=[_binding("cfads", "c")],
        periods=[_period()],
        period_phase={},
        explicit_phases=False,
    )
    assert missing["rows"] == []
    assert missing["needs_input"] == [{"kind": "concept", "reason": "concept_unknown", "subject": "debt_service"}]


def test_zero_debt_is_outside_the_window_and_absent_concept_is_named():
    zero = coverage_ratio(
        metric="dscr",
        facts=[_fact("c", "8"), _fact("d", "0")],
        bindings=[_binding("cfads", "c"), _binding("debt_service", "d")],
        periods=[_period()],
        period_phase={},
        explicit_phases=False,
    )
    assert zero["rows"] == []
    absent = coverage_ratio(
        metric="dscr",
        facts=[_fact("c", "8")],
        bindings=[
            _binding("cfads", "c"),
            _binding("debt_service", "d", is_primary=False, status="unknown", source="confirmed"),
        ],
        periods=[_period()],
        period_phase={},
        explicit_phases=False,
    )
    assert absent["rows"] == []
    assert absent["needs_input"][0]["reason"] == "absent_in_book"


def test_ambiguous_pair_and_icr_numerator():
    ambiguous = coverage_ratio(
        metric="dscr",
        facts=[],
        bindings=[
            _binding("debt_service", "d1", status="ambiguous", is_primary=False),
            _binding("debt_service", "d2", status="ambiguous", is_primary=False),
            _binding("cfads", "c"),
        ],
        periods=[_period()],
        period_phase={},
        explicit_phases=False,
    )
    assert ambiguous["needs_input"][0]["reason"] == "ambiguous"
    icr = coverage_ratio(
        metric="icr",
        facts=[_fact("e", "10"), _fact("b", "6"), _fact("i", "0")],
        bindings=[_binding("ebitda", "e"), _binding("ebit", "b"), _binding("interest", "i")],
        periods=[_period()],
        period_phase={},
        explicit_phases=False,
    )
    assert icr["warnings"][0]["code"] == "icr_numerator"
    assert icr["rows"][0]["status"] == "missing_input"
    assert icr["rows"][0]["value"] is None


def test_icr_reference_distinguishes_an_empty_numerator_from_a_divergence():
    rows = [
        {"row_key": "m", "binding_key": "m"},
        {"row_key": "e", "binding_key": "e"},
        {"row_key": "i", "binding_key": "i"},
        {"row_key": "n", "binding_key": "n"},
    ]
    bindings = [_binding("ebitda", "e"), _binding("interest", "i"), _binding("icr", "m")]
    periods = [_period()]
    far = AuditInput(
        rows=rows,
        periods=periods,
        facts=[
            {**_fact("e", "40"), "cell_id": "ДДС!B34"},
            {**_fact("i", "10"), "cell_id": "ДДС!B38"},
            {**_fact("m", "9"), "cell_id": "К!B10"},
        ],
        bindings=bindings,
    )
    mismatch = ICR_REFERENCE.check(far)
    assert [item.params["cause"] for item in mismatch] == ["mismatch"]
    empty_source = AuditInput(
        rows=rows,
        periods=periods,
        facts=[{**_fact("i", "10"), "cell_id": "ДДС!B38"}],
        bindings=bindings,
    )
    assert [item.params["message"] for item in ICR_REFERENCE.check(empty_source)] == ["справочная строка пуста"]
    incomplete = AuditInput(
        rows=rows,
        periods=periods,
        facts=[
            {**_fact("e", "40"), "cell_id": "ДДС!B34"},
            {**_fact("i", "10"), "cell_id": "ДДС!B38"},
            {**_fact("m", "0"), "cell_id": "К!B10"},
        ],
        bindings=bindings,
        links=[{"row_key": "m", "ref_cell": "К!B41"}, {"row_key": "n", "ref_cell": "ДДС!B34"}],
    )
    incomplete.facts.append({"row_key": "n", "axis_id": "Sheet!r1", "period_id": "other", "cell_id": "К!B41", "normalized_value": None})
    found = ICR_REFERENCE.check(incomplete)
    assert [item.params["cause"] for item in found] == ["empty_numerator"]
    assert found[0].params["message"] == "справочный расчёт книги неполон: числитель пуст"
    assert "ДДС!B34" in found[0].params["cells"]
    assert "К!B41" in found[0].params["cells"]


def test_icr_reference_uses_the_coverage_row_on_the_calculation_axis():
    periods = [_period("p"), {**_period(), "period_id": "q"}]
    other = [
        {**_period("p"), "axis_id": "Outputs!r1"},
        {**_period("q"), "axis_id": "Outputs!r1"},
    ]
    data = AuditInput(
        rows=[{"row_key": key, "binding_key": key} for key in ("book", "out", "e", "i")],
        periods=[*periods, *other],
        facts=[
            {**_fact("e", "40", "p"), "cell_id": "К!B41"},
            {**_fact("e", "40", "q"), "cell_id": "К!C41"},
            {**_fact("i", "10", "p"), "cell_id": "ДДС!B38"},
            {**_fact("i", "10", "q"), "cell_id": "ДДС!C38"},
            {**_fact("book", "4", "p"), "cell_id": "К!B28"},
            {**_fact("book", "9", "q"), "cell_id": "К!C28"},
            {**_fact("out", "1", "p"), "axis_id": "Outputs!r1", "cell_id": "Outputs!B58"},
            {**_fact("out", "1", "q"), "axis_id": "Outputs!r1", "cell_id": "Outputs!C58"},
        ],
        bindings=[_binding("ebitda", "e"), _binding("interest", "i"), _binding("icr", "out")],
        links=[
            {"row_key": "book", "ref_cell": "К!B41"},
            {"row_key": "book", "ref_cell": "ДДС!B38"},
            {"row_key": "book", "ref_cell": "К!C41"},
            {"row_key": "book", "ref_cell": "ДДС!C38"},
        ],
    )
    found = ICR_REFERENCE.check(data)
    assert [item.params["cause"] for item in found] == ["mismatch"]
    assert found[0].locations[0].row_key == "book"
    assert found[0].locations[0].period_id == "q"
    assert found[0].locations[0].axis_id == "Sheet!r1"
    second = AuditInput(
        rows=data.rows + [{"row_key": "other", "binding_key": "other"}],
        periods=data.periods,
        facts=data.facts + [{**_fact("other", "8", "p"), "cell_id": "К!B29"}, {**_fact("other", "8", "q"), "cell_id": "К!C29"}],
        bindings=data.bindings,
        links=data.links
        + [
            {"row_key": "other", "ref_cell": "К!B41"},
            {"row_key": "other", "ref_cell": "ДДС!B38"},
        ],
    )
    ambiguous = ICR_REFERENCE.check(second)
    assert len(ambiguous) == 1
    assert ambiguous[0].params["message"] == "На оси расчёта ICR несколько справочных строк покрытия. Сверка не выполнена."


def test_statement_reference_reports_when_actual_periods_are_unknown():
    data = AuditInput(
        rows=[{"row_key": "model", "binding_key": "model"}, {"row_key": "form", "binding_key": "form"}],
        periods=[_period(), {**_period(), "period_id": "q"}],
        facts=[
            {**_fact("model", "100"), "cell_id": "ДДС!B10"},
            {**_fact("form", "110"), "cell_id": "ОФР!B10"},
        ],
        bindings=[
            _binding("revenue", "model"),
            _binding("revenue", "form", is_primary=False, evidence={"role": "reference"}),
        ],
    )
    found = STATEMENT_REFERENCE.check(data)
    assert len(found) == 1
    assert found[0].params["message"] == "фактические периоды не определены, сверка с отчётностью не выполнена"
    assert "actuals_source" not in found[0].params
    assert STATEMENT_REFERENCE.check(AuditInput(periods=[_period()])) == []


def test_actual_quarter_compares_a_model_primary_with_a_reference_statement():
    period = {**_period(), "marker_class": "actual"}
    plan = {**_period(), "period_id": "plan", "marker_class": "estimate"}
    data = AuditInput(
        rows=[{"row_key": "model", "binding_key": "model"}, {"row_key": "form", "binding_key": "form"}],
        periods=[period, plan],
        facts=[
            {**_fact("model", "100"), "cell_id": "ДДС!B10"},
            {**_fact("form", "110"), "cell_id": "ОФР!B10"},
            {**_fact("model", "100", "plan"), "cell_id": "ДДС!C10"},
            {**_fact("form", "50", "plan"), "cell_id": "ОФР!C10"},
        ],
        bindings=[
            _binding("revenue", "model"),
            _binding("revenue", "form", is_primary=False, evidence={"role": "reference"}),
        ],
    )
    found = STATEMENT_REFERENCE.check(data)
    assert len(found) == 1
    assert found[0].params["message"] == "Строка модели расходится с отчётной формой на фактическом квартале."
    assert found[0].params["concept"] == "revenue"
    assert found[0].params["actuals_source"] == "explicit"
    assert found[0].params["actuals_end"] == "p"
    assert found[0].locations[0].period_id == "p"
    close = AuditInput(
        rows=data.rows,
        periods=[period],
        facts=[{**_fact("model", "100"), "cell_id": "ДДС!B10"}, {**_fact("form", "100.1"), "cell_id": "ОФР!B10"}],
        bindings=data.bindings,
    )
    assert STATEMENT_REFERENCE.check(close) == []


def _quarter(period: str, index: int, *, end: str | None = None) -> dict:
    row = {
        "axis_id": "Sheet!r1",
        "period_id": period,
        "period_key_base": period,
        "period_index": index,
        "grain": "quarter",
        "marker_class": None,
    }
    if end:
        row["period_end"] = end
    return row


def _statement_pair() -> tuple[list[dict], list[dict]]:
    rows = [{"row_key": "model", "binding_key": "model"}, {"row_key": "form", "binding_key": "form"}]
    bindings = [
        _binding("revenue", "model"),
        _binding("revenue", "form", is_primary=False, evidence={"role": "reference"}),
    ]
    return rows, bindings


def test_actuals_end_decision_stops_before_a_structural_cut():
    """Решение `actuals_end.set` сильнее согласованного среза по формуле и форме."""

    rows, bindings = _statement_pair()
    data = AuditInput(
        rows=rows,
        periods=[_quarter("q1", 1), _quarter("q2", 2), _quarter("q3", 3)],
        facts=[
            {**_fact("model", "100", "q1"), "cell_id": "ДДС!B10"},
            {**_fact("model", "100", "q2"), "cell_id": "ДДС!C10"},
            {**_fact("model", "100", "q3"), "cell_id": "ДДС!D10"},
            {**_fact("form", "110", "q1"), "cell_id": "ОФР!B10"},
            {**_fact("form", "120", "q2"), "cell_id": "ОФР!C10"},
        ],
        bindings=bindings,
        links=[{"cell": "ДДС!D10", "row_key": "model", "period_id": "q3", "formula": "=C10"}],
        actuals_end="q1",
    )
    found = STATEMENT_REFERENCE.check(data)
    assert [item.locations[0].period_id for item in found] == ["q1"]
    assert found[0].params["actuals_source"] == "explicit"
    assert found[0].params["actuals_end"] == "q1"


def test_actuals_end_from_profile_is_explicit():
    rows, bindings = _statement_pair()
    data = AuditInput(
        rows=rows,
        periods=[
            _quarter("q1", 1, end="2024-03-31"),
            _quarter("q2", 2, end="2024-06-30"),
            _quarter("q3", 3, end="2024-09-30"),
        ],
        facts=[
            *[{**_fact("model", "100", period), "cell_id": cell} for period, cell in (("q1", "ДДС!B"), ("q2", "ДДС!C"), ("q3", "ДДС!D"))],
            *[{**_fact("form", "110", period), "cell_id": cell} for period, cell in (("q1", "ОФР!B"), ("q2", "ОФР!C"), ("q3", "ОФР!D"))],
        ],
        bindings=bindings,
        profile={"actuals_end": "2024-06-30"},
    )
    found = STATEMENT_REFERENCE.check(data)
    assert [item.locations[0].period_id for item in found] == ["q1", "q2"]
    assert {item.params["actuals_source"] for item in found} == {"explicit"}
    assert {item.params["actuals_end"] for item in found} == {"2024-06-30"}


def test_structural_cut_reconciles_when_formula_and_statement_agree():
    from finance_analysis.application.analyses import _citations

    rows, bindings = _statement_pair()
    data = AuditInput(
        rows=rows,
        periods=[_quarter("q1", 1), _quarter("q2", 2), _quarter("q3", 3)],
        facts=[
            {**_fact("model", "100", "q1"), "cell_id": "ДДС!B10"},
            {**_fact("model", "100", "q2"), "cell_id": "ДДС!C10"},
            {**_fact("model", "130", "q3"), "cell_id": "ДДС!D10"},
            {**_fact("form", "100", "q1"), "cell_id": "ОФР!B10"},
            {**_fact("form", "110", "q2"), "cell_id": "ОФР!C10"},
        ],
        bindings=bindings,
        links=[{"cell": "ДДС!D10", "row_key": "model", "period_id": "q3", "formula": "=C10*1.1"}],
    )
    found = STATEMENT_REFERENCE.check(data)
    assert [item.locations[0].period_id for item in found] == ["q2"]
    assert found[0].params["actuals_source"] == "structural"
    assert found[0].params["actuals_end"] == "q2"
    cited = _citations(data, found)
    assert cited
    assert {item["actuals_source"] for item in cited} == {"structural"}
    assert {item["actuals_end"] for item in cited} == {"q2"}


def test_conflicting_structural_signals_do_not_reconcile():
    rows, bindings = _statement_pair()
    data = AuditInput(
        rows=rows,
        periods=[_quarter("q1", 1), _quarter("q2", 2), _quarter("q3", 3)],
        facts=[
            {**_fact("model", "100", "q1"), "cell_id": "ДДС!B10"},
            {**_fact("model", "100", "q2"), "cell_id": "ДДС!C10"},
            {**_fact("model", "130", "q3"), "cell_id": "ДДС!D10"},
            {**_fact("form", "110", "q1"), "cell_id": "ОФР!B10"},
        ],
        bindings=bindings,
        links=[{"cell": "ДДС!D10", "row_key": "model", "period_id": "q3", "formula": "=C10"}],
    )
    found = STATEMENT_REFERENCE.check(data)
    assert len(found) == 1
    assert found[0].params["message"] == "фактические периоды не определены, сверка с отчётностью не выполнена"
    assert "actuals_source" not in found[0].params


def test_boundary_skips_an_axis_that_does_not_contain_it():
    """period_id уникален только с осью: баланс без q2 не роняет срез ОПУ по q2."""

    rows, bindings = _statement_pair()
    pl = [{**_quarter(period, index), "axis_id": "pl"} for index, period in enumerate(("q1", "q2", "q3"), start=1)]
    balance = [{**_quarter("q1", 1), "axis_id": "bs"}]
    data = AuditInput(
        rows=rows,
        periods=[*pl, *balance],
        facts=[
            {**_fact("model", "100", "q1"), "axis_id": "pl", "cell_id": "ОПУ!B"},
            {**_fact("model", "100", "q2"), "axis_id": "pl", "cell_id": "ОПУ!C"},
            {**_fact("form", "110", "q1"), "axis_id": "pl", "cell_id": "ОФР!B"},
            {**_fact("form", "120", "q2"), "axis_id": "pl", "cell_id": "ОФР!C"},
        ],
        bindings=bindings,
        actuals_end="q2",
    )
    found = STATEMENT_REFERENCE.check(data)
    assert [item.locations[0].period_id for item in found] == ["q1", "q2"]
    assert {item.params["actuals_end"] for item in found} == {"q2"}


def test_structural_cut_ignores_another_sheet_of_the_same_grain():
    """Чужой лист с другими period_id не дырявит срез ОПУ и не прячет 110 против 100."""

    rows, bindings = _statement_pair()
    cash = [{**_quarter(period, index), "axis_id": "cf"} for index, period in enumerate(("cf-q1", "cf-q2"), start=1)]
    pl = [{**_quarter(period, index), "axis_id": "pl"} for index, period in enumerate(("pl-q1", "pl-q2", "pl-q3"), start=1)]
    data = AuditInput(
        rows=rows,
        periods=[*cash, *pl],
        facts=[
            {**_fact("model", "100", "pl-q1"), "axis_id": "pl", "cell_id": "ОПУ!B"},
            {**_fact("model", "100", "pl-q2"), "axis_id": "pl", "cell_id": "ОПУ!C"},
            {**_fact("model", "130", "pl-q3"), "axis_id": "pl", "cell_id": "ОПУ!D"},
            {**_fact("form", "100", "pl-q1"), "axis_id": "pl", "cell_id": "ОФР!B"},
            {**_fact("form", "110", "pl-q2"), "axis_id": "pl", "cell_id": "ОФР!C"},
        ],
        bindings=bindings,
        links=[{"cell": "ОПУ!D", "row_key": "model", "period_id": "pl-q3", "formula": "=C10"}],
    )
    found = STATEMENT_REFERENCE.check(data)
    assert [item.locations[0].period_id for item in found] == ["pl-q2"]
    assert found[0].params["actuals_source"] == "structural"
    assert found[0].params["model"] == "100"
    assert found[0].params["reported"] == "110"


def test_unresolved_boundary_does_not_silence_the_statement_check():
    """База периода режет окно. Значение, которого нет в книге, оставляет находку, а не пустой список."""

    rows, bindings = _statement_pair()
    periods = [
        {**_quarter("2024@факт", 1), "period_key_base": "2024"},
        {**_quarter("2025", 2), "period_key_base": "2025"},
    ]
    facts = [
        {**_fact("model", "100", "2024@факт"), "cell_id": "ДДС!B"},
        {**_fact("form", "110", "2024@факт"), "cell_id": "ОФР!B"},
        {**_fact("model", "100", "2025"), "cell_id": "ДДС!C"},
        {**_fact("form", "90", "2025"), "cell_id": "ОФР!C"},
    ]
    by_base = STATEMENT_REFERENCE.check(
        AuditInput(rows=rows, periods=periods, facts=facts, bindings=bindings, actuals_end="2024")
    )
    assert [item.locations[0].period_id for item in by_base] == ["2024@факт"]
    assert by_base[0].params["actuals_source"] == "explicit"
    assert by_base[0].params["actuals_end"] == "2024"
    unknown = STATEMENT_REFERENCE.check(
        AuditInput(
            rows=rows,
            periods=[_quarter("q1", 1), _quarter("q2", 2)],
            facts=[
                {**_fact("model", "100", "q1"), "cell_id": "ДДС!B"},
                {**_fact("form", "110", "q1"), "cell_id": "ОФР!B"},
            ],
            bindings=bindings,
            profile={"actuals_end": "нет"},
        )
    )
    assert len(unknown) == 1
    assert unknown[0].params["message"] == "фактические периоды не определены, сверка с отчётностью не выполнена"
    assert "actuals_source" not in unknown[0].params


def test_actuals_end_journal_keeps_the_latest_value():
    from finance_analysis.domain.audit import (
        actuals_end_from_journal,
        actuals_end_value_error,
    )

    events = [
        {"type": "actuals_end.set", "seq": 1, "value": "q1"},
        {"type": "actuals_end.set", "seq": 2, "value": "q2"},
        {"type": "phase.set", "seq": 3, "value": "operation"},
    ]
    assert actuals_end_from_journal(events, 2) == "q2"
    assert actuals_end_from_journal(events, 1) == "q1"
    assert actuals_end_value_error("q1", [{"period_id": "q1"}]) is None
    assert actuals_end_value_error("2024-06-30", []) is None
    assert actuals_end_value_error("нет", []) == "период границы факта не найден"


def test_bound_statement_row_is_compared_only_at_the_primary_grain():
    from finance_analysis.application.sheet_roles import load_sheet_roles
    from tests.unit.test_row_selection import _assigned, _row

    assigned = _assigned(
        [
            _row("cash", "Выручка за кв.", sheet="Денежные потоки"),
            _row("form", "Выручка", sheet="ОФР", label_path=["нарастающим итогом"]),
        ]
    )
    assert assigned["cash"].is_primary and assigned["cash"].evidence["selection"] == "period_basis"
    assert assigned["form"].status == "bound" and assigned["form"].is_primary is False
    assert assigned["form"].evidence.get("role") != "reference"
    sheets = frozenset(load_sheet_roles().statement)
    quarters = [
        {
            "axis_id": "cash",
            "period_id": f"Q{index}",
            "period_key_base": f"Q{index}",
            "marker_class": "actual",
            "grain": "quarter",
        }
        for index in range(1, 5)
    ]
    year = {
        "axis_id": "year",
        "period_id": "Y",
        "period_key_base": "Y",
        "marker_class": "actual",
        "grain": "year",
    }
    cash_values = ["10", "20", "30", "40"]
    form_values = ["100", "200", "300", "400"]
    data = AuditInput(
        rows=[
            {"row_key": "cash", "binding_key": "cash", "sheet": "Денежные потоки"},
            {"row_key": "form", "binding_key": "form", "sheet": "ОФР"},
        ],
        periods=[*quarters, year],
        facts=[
            *[_fact("cash", value, f"Q{index}") | {"axis_id": "cash", "cell_id": f"ДДС!{index}"} for index, value in enumerate(cash_values, start=1)],
            *[_fact("form", value, f"Q{index}") | {"axis_id": "form", "cell_id": f"ОФР!{index}"} for index, value in enumerate(form_values, start=1)],
            _fact("cash", "1", "Y") | {"axis_id": "cash", "cell_id": "ДДС!Y"},
            _fact("form", "9", "Y") | {"axis_id": "form", "cell_id": "ОФР!Y"},
        ],
        bindings=[
            {
                "row_key": "cash",
                "binding_key": "cash",
                "is_primary": assigned["cash"].is_primary,
                "status": assigned["cash"].status,
                "effective_concept": assigned["cash"].concept,
                "evidence": assigned["cash"].evidence,
            },
            {
                "row_key": "form",
                "binding_key": "form",
                "is_primary": assigned["form"].is_primary,
                "status": assigned["form"].status,
                "effective_concept": assigned["form"].concept,
                "evidence": assigned["form"].evidence,
            },
        ],
        statement_sheets=sheets,
    )
    found = STATEMENT_REFERENCE.check(data)
    assert [item.locations[0].period_id for item in found] == ["Q1", "Q2", "Q3", "Q4"]
    assert {item.params["message"] for item in found} == {
        "Строка модели расходится с отчётной формой на фактическом квартале."
    }
    month = AuditInput(
        rows=data.rows,
        periods=[{**quarters[0], "grain": "month"}],
        facts=[_fact("cash", "10", "Q1") | {"axis_id": "cash"}, _fact("form", "100", "Q1") | {"axis_id": "form"}],
        bindings=data.bindings,
        statement_sheets=sheets,
    )
    assert STATEMENT_REFERENCE.check(month)[0].params["message"] == (
        "Строка модели расходится с отчётной формой на фактическом месяце."
    )
    interest = AuditInput(
        rows=data.rows,
        periods=[quarters[0]],
        facts=[_fact("cash", "10", "Q1") | {"axis_id": "cash"}, _fact("form", "80", "Q1") | {"axis_id": "form"}],
        bindings=[
            _binding("interest", "cash"),
            _binding("interest", "form", is_primary=False),
        ],
        statement_sheets=sheets,
    )
    assert STATEMENT_REFERENCE.check(interest) == []


def test_ratio_mismatch_and_marker_mix_and_pair_status():
    bindings = [_binding("cfads", "c"), _binding("debt_service", "d"), _binding("dscr", "m")]
    far = AuditInput(
        rows=[{"row_key": "m", "binding_key": "m"}],
        periods=[_period()],
        facts=[_fact("c", "10"), _fact("d", "4"), _fact("m", "9")],
        bindings=bindings,
    )
    assert [item.code for item in RATIO_MISMATCH.check(far)] == ["ratio_mismatch"]
    close = AuditInput(
        rows=[{"row_key": "m", "binding_key": "m"}],
        periods=[_period()],
        facts=[_fact("c", "10"), _fact("d", "4"), _fact("m", "2.5")],
        bindings=bindings,
    )
    assert RATIO_MISMATCH.check(close) == []
    assert RATIO_MISMATCH.check(AuditInput()) == []
    assert MARKER_MIX.check(
        AuditInput(
            bindings=[{"is_primary": True}],
            periods=[_period("p", "actual"), _period("q", "plan")],
        )
    ) == []
    mixed = AuditInput(
        rows=[{"row_key": "s", "binding_key": "s"}],
        periods=[_period("p", "actual"), _period("q", "plan")],
        facts=[
            {**_fact("a", "1", "p"), "cell_id": "A"},
            {**_fact("b", "1", "q"), "cell_id": "B"},
        ],
        links=[{"row_key": "s", "ref_cell": "A"}, {"row_key": "s", "ref_cell": "B"}],
    )
    [mix] = MARKER_MIX.check(mixed)
    assert mix.params["markers"] == ["actual", "plan"]
    assert pair_status([("keep", 4.0)]) == ("keep", False)
    assert pair_status([("a", 4.0), ("b", 3.5)]) == (None, True)
    assert pair_status([("low", 2.0)]) == (None, True)


def test_dscr_findings_stay_quiet_when_only_icr_applies():
    """Привязанные cfads, debt_service и dscr не дают находок DSCR, если применима только ICR."""

    from datetime import date

    bindings = [_binding("cfads", "c"), _binding("debt_service", "d"), _binding("dscr", "m")]
    periods = []
    facts = []
    for name in ("p", "q", "r"):
        periods.append(
            {
                "axis_id": "Sheet!r1",
                "period_id": name,
                "period_key_base": name,
                "grain": "quarter",
                "period_start": date(2024, 1, 1),
                "period_end": date(2024, 1, 15),
            }
        )
        facts.extend([_fact("c", "10", name), _fact("d", "4", name), _fact("m", "9", name)])
    quiet = AuditInput(periods=periods, facts=facts, bindings=bindings, applicable_metrics=frozenset({"icr"}))
    assert dscr_rows(quiet) == []
    assert RATIO_MISMATCH.check(quiet) == []
    assert SCULPTING_DEVIATION.check(quiet) == []
    assert PERIOD_GRAIN_MISMATCH.check(quiet) == []
    live = AuditInput(periods=periods, facts=facts, bindings=bindings, applicable_metrics=frozenset({"dscr"}))
    assert [item.code for item in RATIO_MISMATCH.check(live)] == ["ratio_mismatch", "ratio_mismatch", "ratio_mismatch"]
    assert len(PERIOD_GRAIN_MISMATCH.check(live)) == 3
    corporate = AuditInput(
        periods=periods,
        facts=facts,
        bindings=bindings,
        applicable_metrics=frozenset({"dscr"}),
        dscr_variant="corporate_covenant",
    )
    assert RATIO_MISMATCH.check(corporate) == []
    assert dscr_rows(corporate) == []
    assert SCULPTING_DEVIATION.check(corporate) == []
    assert PERIOD_GRAIN_MISMATCH.check(corporate) == []
    project = AuditInput(
        periods=periods,
        facts=facts,
        bindings=bindings,
        applicable_metrics=frozenset({"dscr"}),
        dscr_variant="pf",
    )
    assert len(RATIO_MISMATCH.check(project)) == 3
    assert len(PERIOD_GRAIN_MISMATCH.check(project)) == 3


def test_dscr_cache_must_match_the_model_row():
    bindings = [_binding("cfads", "c"), _binding("debt_service", "d"), _binding("dscr", "m")]
    rows = [{"row_key": "m", "binding_key": "m"}]
    same = AuditInput(
        rows=rows,
        periods=[_period()],
        facts=[_fact("c", "10"), _fact("d", "4"), _fact("m", "2.5")],
        bindings=bindings,
    )
    assert RATIO_MISMATCH.check(same) == []
    drifted = AuditInput(
        rows=rows,
        periods=[_period()],
        facts=[_fact("c", "10"), _fact("d", "4"), _fact("m", "9")],
        bindings=bindings,
    )
    assert [item.params["model"] for item in RATIO_MISMATCH.check(drifted)] == ["9"]


def _unknown(row_key: str) -> dict:
    return {"row_key": row_key, "binding_key": row_key, "is_primary": False, "status": "unknown"}


def test_unmapped_walks_up_to_dscr_and_icr():
    deep = AuditInput(
        rows=[{"row_key": key, "binding_key": key} for key in ("u", "mid", "d", "m")],
        periods=[_period()],
        bindings=[
            _binding("dscr", "m"),
            _binding("debt_service", "d"),
            _unknown("u"),
            _binding("other", "mid"),
        ],
        facts=[
            {"cell_id": "U", "row_key": "u", "axis_id": "Sheet!r1", "period_id": "p"},
            {"cell_id": "M", "row_key": "mid", "axis_id": "Sheet!r1", "period_id": "p"},
            {"cell_id": "D", "row_key": "d", "axis_id": "Sheet!r1", "period_id": "p"},
        ],
        links=[
            {"row_key": "mid", "ref_cell": "U"},
            {"row_key": "d", "ref_cell": "M"},
            {"row_key": "m", "ref_cell": "D"},
        ],
    )
    [high] = UNMAPPED_IN_METRIC_CHAIN.check(deep)
    assert high.severity == "high"
    near = AuditInput(
        rows=[{"row_key": "u", "binding_key": "u"}, {"row_key": "m", "binding_key": "m"}],
        periods=[_period()],
        bindings=[_binding("dscr", "m"), _unknown("u")],
        facts=[{"cell_id": "U", "row_key": "u", "axis_id": "Sheet!r1", "period_id": "p"}],
        links=[{"row_key": "m", "ref_cell": "U"}],
    )
    [medium] = UNMAPPED_IN_METRIC_CHAIN.check(near)
    assert medium.severity == "medium"
    interest = AuditInput(
        rows=[{"row_key": key, "binding_key": key} for key in ("u", "i", "r")],
        periods=[_period()],
        bindings=[_binding("icr", "r"), _binding("interest", "i"), _unknown("u")],
        facts=[
            {"cell_id": "U", "row_key": "u", "axis_id": "Sheet!r1", "period_id": "p"},
            {"cell_id": "I", "row_key": "i", "axis_id": "Sheet!r1", "period_id": "p"},
        ],
        links=[{"row_key": "i", "ref_cell": "U"}, {"row_key": "r", "ref_cell": "I"}],
    )
    assert UNMAPPED_IN_METRIC_CHAIN.check(interest)[0].severity == "high"


def test_marked_period_stays_until_the_profile_picks_one():
    bindings = [_binding("cfads", "c"), _binding("debt_service", "d")]
    period = {**_period("2024@факт"), "period_key_base": "2024", "marker_class": "actual"}
    facts = [
        {**_fact("c", "10"), "period_id": "2024@факт"},
        {**_fact("d", "4"), "period_id": "2024@факт"},
    ]
    kept = coverage_ratio(
        metric="dscr",
        facts=facts,
        bindings=bindings,
        periods=[period],
        period_phase={("Sheet!r1", "2024@факт"): "operation"},
        explicit_phases=True,
    )
    assert kept["rows"][0]["value"] == Decimal("2.5000000000")
    dropped = coverage_ratio(
        metric="dscr",
        facts=facts,
        bindings=bindings,
        periods=[period],
        period_phase={("Sheet!r1", "2024@факт"): "operation"},
        explicit_phases=True,
        marker_class="plan",
    )
    assert dropped["rows"] == []


def test_construction_phase_is_not_a_dscr_mismatch():
    bindings = [_binding("cfads", "c"), _binding("debt_service", "d"), _binding("dscr", "m")]
    built = {**_period("q"), "phase": "construction"}
    data = AuditInput(
        rows=[{"row_key": "m", "binding_key": "m"}],
        periods=[built],
        facts=[_fact("c", "10", "q"), _fact("d", "4", "q"), _fact("m", "9", "q")],
        bindings=bindings,
    )
    assert RATIO_MISMATCH.check(data) == []


def test_two_formulas_on_one_row_are_not_one_mix():
    data = AuditInput(
        rows=[{"row_key": "s", "binding_key": "s"}],
        periods=[_period("p", "actual"), _period("q", "plan")],
        facts=[
            {**_fact("a", "1", "p"), "cell_id": "A"},
            {**_fact("b", "1", "q"), "cell_id": "B"},
        ],
        links=[
            {"row_key": "s", "cell": "S!C1", "ref_cell": "A"},
            {"row_key": "s", "cell": "S!D1", "ref_cell": "B"},
        ],
    )
    assert MARKER_MIX.check(data) == []
