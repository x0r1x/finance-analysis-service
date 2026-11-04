"""Роль component и сценарий alt (§5.5.2)."""

from __future__ import annotations

import json

from finance_analysis.application.catalog import load_catalog
from finance_analysis.application.model_types import load_model_types
from finance_analysis.application.sheet_roles import load_sheet_roles
from finance_analysis.domain.audit import AuditInput
from finance_analysis.domain.book import (
    FAS_DERIVE_VERSION,
    FAS_SCHEMA_VERSION,
    FAS_VERSION,
)
from finance_analysis.domain.mapping import assign_rows
from finance_analysis.domain.questions import concept_questions
from finance_analysis.domain.references import summed_row_refs
from tests.unit.rule_inputs import check
from tests.unit.test_row_selection import _row

_ROLES = load_sheet_roles()


def _assigned(rows, **extra):
    return assign_rows(rows, extra.pop("events", []), load_catalog(), roles=_ROLES, **extra)


def test_sum_formula_marks_the_rows_it_adds():
    assert summed_row_refs("=C10+C11", default_sheet="Debt") == (("Debt", 10), ("Debt", 11))
    assert summed_row_refs("=SUM(C10:C12)", default_sheet="Debt") == (("Debt", 10), ("Debt", 11), ("Debt", 12))
    assert summed_row_refs("=C10", default_sheet="Debt") is None
    assert summed_row_refs("=C10*1.1", default_sheet="Debt") is None
    rows = [
        _row("total", "Interest", sheet="Debt", row_num=30, formula="=C10+C11"),
        _row("senior", "Interest", sheet="Debt", row_num=10, parent_label="Senior loan"),
        _row("bond", "Interest", sheet="Debt", row_num=11, parent_label="Bond"),
    ]
    got = _assigned(rows)
    assert got["total"].is_primary and got["total"].evidence["selection"] == "component"
    assert got["total"].evidence["scenario"] == "base"
    for key in ("senior", "bond"):
        assert got[key].is_primary is False
        assert got[key].status == "bound"
        assert got[key].evidence["role"] == "component"
        assert got[key].evidence["component_of"] == "total"
        assert got[key].evidence["total_row"] == "total"
    assert got["senior"].evidence["member"]
    assert "role" not in got["total"].evidence


def test_sum_range_and_cross_sheet_links_are_components():
    rows = [
        _row("total", "Interest", sheet="Debt", row_num=40, has_formula=True),
        _row("one", "Interest", sheet="Debt", row_num=10),
        _row("two", "Interest", sheet="Notes", row_num=11),
    ]
    links = [
        {"row_key": "total", "cell": "Debt!C40", "formula": "=SUM(C10:C11)", "ref_cell": "Debt!C10"},
        {"row_key": "total", "cell": "Debt!C40", "formula": "=SUM(C10:C11)", "ref_cell": "Notes!C11"},
    ]
    got = _assigned(rows, links=links)
    assert got["one"].evidence["total_row"] == "total"
    assert got["two"].evidence["component_of"] == "total"
    assert got["total"].is_primary
    assert got["one"].is_primary is False and got["two"].is_primary is False


def test_single_link_and_scale_are_not_components():
    rows = [
        _row("src", "Interest", sheet="Debt", row_num=10),
        _row("echo", "Interest", sheet="Notes", row_num=20, formula="=Debt!C10"),
    ]
    got = _assigned(rows)
    assert got["echo"].evidence["role"] == "reference"
    assert got["echo"].evidence["reference_of"] == "src"
    assert got["src"].is_primary
    uplift = _assigned(
        [
            _row("src", "Interest", sheet="Debt", row_num=10),
            _row("uplift", "Interest", sheet="Model", row_num=21, formula="=Debt!C10*1.1"),
        ]
    )
    assert "role" not in uplift["uplift"].evidence
    horizontal = [
        _row("total", "Interest", sheet="Debt", row_num=30, has_formula=True),
        _row("src", "Interest", sheet="Debt", row_num=10),
    ]
    links = [
        {"row_key": "total", "formula": "SUM(C30:Z30)", "ref_cell": "Debt!C30"},
        {"row_key": "total", "formula": "-C10", "ref_cell": "Debt!C10"},
    ]
    signed = _assigned(horizontal, links=links)
    assert "role" not in signed["src"].evidence
    assert "role" not in signed["total"].evidence


def test_a_sum_of_another_concept_does_not_mark_a_component():
    rows = [
        _row("ebitda", "EBITDA", sheet="P&L", row_num=5, formula="=C10+C11"),
        _row("interest", "Interest", sheet="P&L", row_num=10),
        _row("tax", "Tax", sheet="P&L", row_num=11),
    ]
    got = _assigned(rows)
    assert "role" not in got["interest"].evidence
    assert got["interest"].is_primary
    assert got["ebitda"].is_primary


def test_debt_parents_mark_a_component_when_there_is_no_formula():
    rows = [
        _row("total", "Interest", sheet="Debt", parent_label="Итого"),
        _row("loan", "Interest", sheet="Debt", parent_label="Кредит senior"),
        _row("tranche", "Interest", sheet="Debt", parent_label="Транш A"),
    ]
    got = _assigned(rows)
    assert got["total"].is_primary and got["total"].evidence["selection"] == "component"
    assert got["loan"].evidence["role"] == "component"
    assert got["loan"].evidence["component_of"] == "total"
    assert "total_row" not in got["loan"].evidence
    assert got["tranche"].is_primary is False
    assert got["loan"].evidence["member"]
    plain = [
        _row("ops", "Interest", sheet="Debt", parent_label="Операционные"),
        _row("tax", "Interest", sheet="Debt", parent_label="Налог"),
    ]
    repeated = _assigned(plain)
    assert "role" not in repeated["ops"].evidence
    assert "role" not in repeated["tax"].evidence
    indented = [
        _row("head", "Interest", sheet="Debt", indent=0),
        _row("child", "Interest", sheet="Debt", indent=2, parent_label="Interest"),
    ]
    nest = _assigned(indented)
    assert "role" not in nest["child"].evidence


def test_stress_and_optimistic_blocks_leave_the_base_row():
    rows = [
        _row("base", "Interest", sheet="Model", label_path=["Базовый"]),
        _row("stress", "Interest", sheet="Model", label_path=["Стресс-сценарий"]),
        _row("up", "Interest", sheet="Model", parent_label="Optimistic case"),
        _row("down", "Interest", sheet="Debt", parent_label="Downside case"),
    ]
    got = _assigned(rows)
    assert got["base"].is_primary and got["base"].evidence["selection"] == "scenario"
    assert got["base"].evidence["scenario"] == "base"
    for key in ("stress", "up", "down"):
        assert got[key].is_primary is False
        assert got[key].status == "bound"
        assert got[key].evidence["scenario"] == "alt"
    mixed = [_row("both", "Interest", sheet="Model", label_path=["Базовый стресс"])]
    alone = _assigned(mixed)
    assert alone["both"].evidence["scenario"] == "alt"
    assert alone["both"].is_primary is False
    assert alone["both"].status == "bound"


def test_confirmed_component_keeps_primary_and_warns():
    rows = [
        _row("total", "Interest", sheet="Debt", row_num=30, formula="=C10+C11"),
        _row("senior", "Interest", sheet="Debt", row_num=10, parent_label="Senior loan"),
        _row("bond", "Interest", sheet="Debt", row_num=11, parent_label="Bond"),
    ]
    events = [{"seq": 1, "type": "concept.set", "target": "senior", "binding_key": "senior", "value": "interest"}]
    got = _assigned(rows, events=events)
    assert got["senior"].source == "confirmed"
    assert got["senior"].is_primary
    assert got["senior"].status == "bound"
    assert got["senior"].evidence["warnings"] == ["component_over_total"]
    assert got["total"].is_primary is False
    assert got["bond"].is_primary is False
    assert FAS_SCHEMA_VERSION == "1.0"
    assert FAS_VERSION == "0.23.0"
    assert FAS_DERIVE_VERSION == "4"


def test_components_without_a_total_raise_missing_total_row():
    rows = [
        _row("loan", "Interest", sheet="Debt", parent_label="Кредит"),
        _row("bond", "Interest", sheet="Debt", parent_label="Облигации"),
    ]
    got = _assigned(rows)
    assert got["loan"].is_primary is False and got["bond"].is_primary is False
    assert got["loan"].evidence["role"] == "component"
    assert got["loan"].evidence["component_of"] == "interest"
    data = AuditInput(
        bindings=[
            {
                "row_key": key,
                "effective_concept": "interest",
                "status": "bound",
                "is_primary": item.is_primary,
                "evidence_json": json.dumps(item.evidence),
            }
            for key, item in got.items()
        ]
    )
    found = check("missing_total_row", data)
    assert found[0].params["concept"] == "interest"
    assert "icr" in found[0].params["needed_by"]
    assert sorted(found[0].params["components"]) == ["bond", "loan"]


def test_component_and_reference_rows_skip_the_question_pack():
    asked = concept_questions(
        job_id="synthetic",
        bindings=[
            {
                "binding_key": "part",
                "row_key": "part",
                "status": "ambiguous",
                "effective_concept": "interest",
                "evidence_json": json.dumps(
                    {"role": "component", "candidates": [{"concept": "interest", "structure_pass": True}]}
                ),
            }
        ],
        rows=[{"binding_key": "part", "sheet": "Debt", "label": "Interest"}],
        events=[],
        catalog=load_model_types(),
        labels=("corporate",),
        concepts=load_catalog().concepts,
        limit=5,
    )
    interest = next(item for item in asked if item["subject"] == "interest")
    assert interest["candidates"] == []
