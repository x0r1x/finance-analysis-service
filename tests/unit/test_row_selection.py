"""Каскад выбора одной строки среди точных совпадений (§5.5)."""

from __future__ import annotations

import json
from pathlib import Path

from finance_analysis.application.catalog import load_catalog
from finance_analysis.application.model_types import load_model_types
from finance_analysis.application.sheet_roles import load_sheet_roles
from finance_analysis.domain.mapping import assign_rows
from finance_analysis.domain.questions import concept_questions

_ROLES = load_sheet_roles()


def _row(key: str, label: str, **extra) -> dict:
    row = {"kind": "fact", "binding_key": key, "row_key": key, "label": label, "sign": None, "sheet": "Model"}
    row.update(extra)
    return row


def _assigned(rows: list[dict], **extra):
    return assign_rows(rows, [], load_catalog(), roles=_ROLES, **extra)


def test_statement_roles_come_from_corporate_groups_without_a_second_copy():
    raw = (Path(__file__).resolve().parents[2] / "configs" / "sheet_roles.yaml").read_text(encoding="utf-8")
    assert "P&L" not in raw and "ОПиУ" not in raw
    assert "P&L" in _ROLES.statement
    assert "Отчет о финансовых результатах" in _ROLES.statement
    assert "Допущения" in _ROLES.assumptions
    assert "Итоги" in _ROLES.outputs


def test_single_exact_match_is_not_cascaded():
    got = _assigned([_row("a", "EBITDA", sheet="Assumptions")])
    assert got["a"].status == "bound" and got["a"].is_primary
    assert "selection" not in got["a"].evidence


def test_statement_sheet_beats_assumptions_and_outputs():
    rows = [
        _row("form", "Interest", sheet="P&L"),
        _row("out", "Interest", sheet="Итоги"),
        _row("asm", "Interest", sheet="Допущения"),
    ]
    got = _assigned(rows)
    assert got["form"].is_primary and got["form"].evidence["selection"] == "sheet_role"
    assert got["out"].is_primary is False and got["asm"].is_primary is False


def test_outputs_beat_an_unranked_sheet_and_assumptions():
    rows = [
        _row("out", "Interest", sheet="Outputs"),
        _row("plain", "Interest", sheet="Model"),
        _row("asm", "Interest", sheet="Inputs"),
    ]
    got = _assigned(rows)
    assert got["out"].is_primary and got["out"].evidence["selection"] == "sheet_role"
    assert got["plain"].is_primary is False


def test_unranked_sheet_beats_assumptions():
    rows = [
        _row("plain", "Interest", sheet="Model"),
        _row("asm", "Interest", sheet="Assumptions"),
    ]
    got = _assigned(rows)
    assert got["plain"].is_primary and got["plain"].evidence["selection"] == "sheet_role"


def test_unranked_peer_stays_beside_a_statement_formula():
    """CFS не алиас формы, поэтому строка денежного потока не проигрывает P&L молча."""

    rows = [
        _row("form", "Interest", sheet="P&L", has_formula=True),
        _row("cash", "Interest", sheet="CFS", has_formula=True),
    ]
    got = _assigned(rows)
    assert got["form"].status == "ambiguous" and got["cash"].status == "ambiguous"
    assert got["form"].is_primary is False and got["cash"].is_primary is False


def test_same_sheet_role_does_not_split_balance_sections():
    rows = [
        _row("long", "Interest", sheet="Баланс"),
        _row("short", "Interest", sheet="Бухгалтерский баланс"),
    ]
    got = _assigned(rows)
    assert got["long"].status == "ambiguous" and got["short"].status == "ambiguous"


def test_formula_on_the_form_beats_an_input_on_the_same_form():
    rows = [
        _row("calc", "Interest", sheet="P&L", has_formula=True),
        _row("driver", "Interest", sheet="P&L", has_formula=False),
    ]
    got = _assigned(rows)
    assert got["calc"].is_primary and got["calc"].evidence["selection"] == "formula"
    assert got["driver"].is_primary is False


def test_formula_without_a_form_sheet_does_not_pick_a_winner():
    rows = [
        _row("calc", "Interest", sheet="Model", has_formula=True),
        _row("driver", "Interest", sheet="Notes", has_formula=False),
    ]
    got = _assigned(rows)
    assert got["calc"].status == "ambiguous" and got["driver"].status == "ambiguous"


def test_check_formula_does_not_beat_a_statement_input():
    rows = [
        _row("form", "Interest", sheet="P&L", has_formula=False),
        _row("check", "Interest", sheet="Notes", has_formula=True),
    ]
    got = _assigned(rows)
    assert got["form"].is_primary and got["form"].evidence["selection"] == "formula"
    assert got["check"].is_primary is False


def test_aggregate_beats_a_component_and_indent_breaks_two_aggregates():
    rows = [
        _row("total", "Interest", sheet="Model", aggregation="aggregate", indent=2),
        _row("part", "Interest", sheet="Model", indent=0),
    ]
    got = _assigned(rows)
    assert got["total"].is_primary and got["total"].evidence["selection"] == "aggregate"
    tied = [
        _row("shallow", "Interest", sheet="Model", aggregation="aggregate", indent=0),
        _row("deep", "Interest", sheet="Model", aggregation="aggregate", indent=3),
    ]
    again = _assigned(tied)
    assert again["shallow"].is_primary and again["deep"].is_primary is False


def test_parent_in_the_label_path_beats_the_child():
    rows = [
        _row("parent", "Interest", sheet="Model", label_path=[]),
        _row("child", "Interest", sheet="Model", label_path=["Interest"]),
    ]
    got = _assigned(rows)
    assert got["parent"].is_primary and got["parent"].evidence["selection"] == "aggregate"
    assert got["child"].is_primary is False


def test_same_indent_total_and_parent_fall_through_to_coverage():
    rows = [
        _row("line", "Interest", sheet="Model", indent=0),
        _row("total", "Interest", sheet="Model", indent=0, aggregation="aggregate", label_path=["Interest"]),
    ]
    periods = {
        "line": {("ax", str(i)): 1 for i in range(20)},
        "total": {("ax", str(i)): 1 for i in range(2)},
    }
    got = _assigned(rows, periods=periods)
    assert got["line"].is_primary and got["line"].evidence["selection"] == "period_coverage"
    assert got["total"].is_primary is False


def test_plain_indent_does_not_pick_a_winner():
    rows = [
        _row("a", "Interest", sheet="Model", indent=0),
        _row("b", "Interest", sheet="Model", indent=2),
    ]
    got = _assigned(rows)
    assert got["a"].status == "ambiguous" and got["b"].status == "ambiguous"


def test_period_coverage_on_one_axis_picks_the_longer_row_and_is_silent_under_one_period():
    rows = [
        _row("long", "Interest", sheet="Model"),
        _row("short", "Interest", sheet="Model"),
    ]
    periods = {
        "long": {("ax", str(i)): 1 for i in range(5)},
        "short": {("ax", str(i)): 1 for i in range(3)},
    }
    got = _assigned(rows, periods=periods)
    assert got["long"].is_primary and got["long"].evidence["selection"] == "period_coverage"
    equal = {
        "long": {("ax", str(i)): 1 for i in range(4)},
        "short": {("ax", str(i)): 1 for i in range(4)},
    }
    tied = _assigned(rows, periods=equal)
    assert tied["long"].status == "ambiguous" and tied["short"].status == "ambiguous"


def test_period_coverage_is_silent_when_two_axes_are_shared():
    rows = [
        _row("forecast", "Interest", sheet="Model"),
        _row("actuals", "Interest", sheet="Notes"),
    ]
    periods = {
        "forecast": {("actual", str(i)): 1 for i in range(2)} | {("forecast", str(i)): 0 for i in range(30)},
        "actuals": {("actual", str(i)): 1 for i in range(10)} | {("forecast", str(i)): 0 for i in range(2)},
    }
    got = _assigned(rows, periods=periods)
    assert got["forecast"].status == "ambiguous" and got["actuals"].status == "ambiguous"


def test_missing_series_scores_zero_on_the_one_axis():
    rows = [
        _row("long", "Interest", sheet="Model"),
        _row("empty", "Interest", sheet="Notes"),
    ]
    got = _assigned(rows, periods={"long": {("ax", str(i)): 1 for i in range(12)}})
    assert got["long"].is_primary and got["long"].evidence["selection"] == "period_coverage"
    assert got["empty"].is_primary is False
    trio = [
        _row("wide", "Interest", sheet="Model"),
        _row("short", "Interest", sheet="Notes"),
        _row("other", "Interest", sheet="Debt"),
    ]
    periods = {
        "wide": {("ax", str(i)): 1 for i in range(10)},
        "short": {("ax", str(i)): 1 for i in range(2)},
        "other": {("side", str(i)): 1 for i in range(8)},
    }
    again = _assigned(trio, periods=periods)
    assert again["wide"].is_primary and again["wide"].evidence["selection"] == "period_coverage"
    assert again["short"].is_primary is False and again["other"].is_primary is False


def test_period_coverage_does_not_compare_different_axes():
    rows = [
        _row("wide", "Interest", sheet="Model"),
        _row("narrow", "Interest", sheet="Notes"),
    ]
    periods = {
        "wide": {("left", str(i)): 1 for i in range(40)},
        "narrow": {("right", "1"): 1},
    }
    got = _assigned(rows, periods=periods)
    assert got["wide"].status == "ambiguous" and got["narrow"].status == "ambiguous"


def test_tie_asks_only_for_a_required_metric_input():
    catalog = load_catalog()
    types = load_model_types()
    interest = [
        _row("long", "Interest", sheet="Баланс"),
        _row("short", "Interest", sheet="Баланс"),
    ]
    assigned = assign_rows(interest, [], catalog, roles=_ROLES)
    questions = _questions(interest, assigned, labels=("corporate",), catalog=types, concepts=catalog.concepts)
    asked = next(item for item in questions if item["subject"] == "interest")
    assert asked["reason"] == "ambiguous"
    assert {item["binding_key"] for item in asked["candidates"]} == {"long", "short"}
    assert "sheet_role" in asked["candidates"][0]["reasons"]
    capex = [
        _row("a", "CAPEX", sheet="Model"),
        _row("b", "CAPEX", sheet="Notes"),
    ]
    capex_assigned = assign_rows(capex, [], catalog, roles=_ROLES)
    optional = _questions(capex, capex_assigned, labels=("project_finance",), catalog=types, concepts=catalog.concepts)
    assert all(item["subject"] != "capex" for item in optional)
    assert capex_assigned["a"].status == "ambiguous"


def test_assumptions_winner_is_not_bound_when_a_statement_row_was_filtered():
    rows = [
        _row("asm", "Interest", sheet="Допущения"),
        _row("form", "Interest", sheet="P&L", unit="%"),
    ]
    got = _assigned(rows)
    assert got["asm"].status == "ambiguous" and got["asm"].is_primary is False
    assert got["form"].status == "unknown"


def _questions(rows, assigned, **extra):
    bindings = [
        {
            "binding_key": key,
            "row_key": key,
            "status": item.status,
            "source": item.source,
            "effective_concept": item.concept,
            "is_primary": item.is_primary,
            "evidence_json": json.dumps(item.evidence),
        }
        for key, item in assigned.items()
    ]
    dim = [
        {"binding_key": row["binding_key"], "row_key": row["row_key"], "sheet": row["sheet"], "label": row["label"]}
        for row in rows
    ]
    base = {
        "job_id": "synthetic",
        "bindings": bindings,
        "rows": dim,
        "events": [],
        "limit": 5,
    }
    base.update(extra)
    return concept_questions(**base)
