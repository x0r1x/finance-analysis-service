"""Наследование пометок: отчёт короткий, цепь в ответе полная."""

from finance_analysis.application.report import render_markdown
from finance_analysis.application.rule_engine import load_rules, run_rules, select_rules
from finance_analysis.domain.audit import AuditInput
from finance_analysis.domain.formula_origin import origin_view
from finance_analysis.domain.model_type import MetricExpression
from tests.unit.rule_inputs import PERIODS, fact, link, row


def _book():
    dscr, cfads, mid, driver, other = (
        "S|34|S!r2",
        "S|14|S!r2",
        "S|9|S!r2",
        "S|8|S!r2",
        "S|99|S!r2",
    )
    rows = [
        row(dscr, label="DSCR"),
        row(cfads, label="CFADS"),
        row(mid, label="середина"),
        row(driver, label="драйвер"),
        row(other, label="чужой"),
    ]
    facts = [
        fact(dscr, "S!D34", "2025", "1"),
        fact(cfads, "S!C14", "2024", "1"),
        fact(cfads, "S!D14", "2025", "1"),
        fact(cfads, "S!E14", "2026@план", "1"),
        fact(driver, "S!D8", "2025", "1"),
        fact(other, "S!C99", "2024", "1"),
        fact(other, "S!D99", "2025", "1"),
        fact(other, "S!E99", "2026@план", "1"),
    ]
    links = (
        link("S!D34", "D14", dscr, "2025", refs=("S!D14",))
        + link("S!C14", "C9+1", cfads, "2024", refs=("S!C9",))
        + link("S!D14", "D9+2", cfads, "2025", refs=("S!D9",))
        + link("S!E14", "E9+3", cfads, "2026@план", refs=("S!E9",))
        + link("S!C9", "C8", mid, "2024", refs=("S!C8",))
        + link("S!D9", "D8", mid, "2025", refs=("S!D8",))
        + link("S!E9", "E8", mid, "2026@план", refs=("S!E8",))
        + link("S!D8", "D7*1.5", driver, "2025", refs=("S!D7",))
        + link("S!C99", "C98+1", other, "2024")
        + link("S!D99", "D98+4", other, "2025")
        + link("S!E99", "E98+7", other, "2026@план")
    )
    data = AuditInput(
        rows=rows,
        periods=PERIODS,
        facts=facts,
        links=links,
        bindings=[
            {"status": "bound", "effective_concept": "dscr", "row_key": dscr},
            {"status": "bound", "effective_concept": "cfads", "row_key": cfads},
        ],
        applicable_metrics=frozenset({"dscr"}),
    )
    return data, driver


def test_direct_inputs_stay_short_and_the_chain_is_complete():
    data, driver = _book()
    findings = run_rules(select_rules(load_rules(), ["formula_pattern_break", "literal_in_formula"]), data)
    view = origin_view(
        data,
        findings,
        {"dscr": MetricExpression(numerator_plus=("cfads",), denominator_plus=("debt_service",))},
    )
    [metric] = view["metrics"]
    assert metric["metric"] == "dscr"
    labels = [item["label"] for item in metric["direct"]]
    assert labels == ["CFADS"]
    driver_marks = {item.fingerprint for item in findings if any(loc.row_key == driver for loc in item.locations)}
    inherited = [item for item in view["chain"] if item["fingerprint"] in driver_marks]
    assert [item["depth"] for item in inherited] == [2]
    assert all(item["metric"] == "dscr" for item in view["chain"])
    text = render_markdown({"analysis_id": "a", "status": "succeeded", "result_data": {"formula_origin": view}})
    assert "Происхождение формул" in text
    assert "CFADS" in text
    assert "драйвер" not in text
    assert "чужой" not in text
    assert view["book"]["literal_in_formula"]["low"] == 2
    assert view["book"]["formula_pattern_break"]["high"] == 2
