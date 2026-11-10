"""Отпечаток находки и номер оси (`domain/audit.py`, §6.1)."""

from __future__ import annotations

from finance_analysis.adapters.storage.parquet_io import load_schema, write_table
from finance_analysis.domain.audit import (
    FINDING_KINDS,
    AuditInput,
    Finding,
    Rule,
    axis_ordinals,
    default_finding_kind,
    fingerprint,
    promote_needs_findings,
)
from finance_analysis.domain.published_parquet import check_additive_evolution


def test_fingerprint_and_axis_ordinal():
    left = fingerprint("hardcoded_formula", "bk", "2024", "", "0")
    assert left == fingerprint("hardcoded_formula", "bk", "2024", "", "0")
    assert left != fingerprint("hardcoded_formula", "bk", "2024", "план", "0")
    assert len(left) == 40
    # Вставка строки сдвигает номер шапки, но не порядок осей листа.
    before = axis_ordinals(["PF!r7", "PF!r185", "PF!r11", "TBA!r2"])
    after = axis_ordinals(["PF!r8", "PF!r186", "PF!r12", "TBA!r3"])
    assert before == {"PF!r7": 0, "PF!r11": 1, "PF!r185": 2, "TBA!r2": 0}
    assert [after[key] for key in ("PF!r8", "PF!r12", "PF!r186", "TBA!r3")] == [0, 1, 2, 0]


def test_default_finding_kind_by_error_class_and_severity():
    assert default_finding_kind("mechanical", "high") == "error"
    assert default_finding_kind("logic", "medium") == "error"
    assert default_finding_kind("quantitative", "critical") == "error"
    assert default_finding_kind("quantitative", "high") == "error"
    assert default_finding_kind("quantitative", "info") == "warning"
    # omission → insufficient_data is the candidate default; required vs optional
    # narrowing / Rule.finding_kind overrides remain authoritative (§6.1 / #66).
    assert default_finding_kind("omission", "medium") == "insufficient_data"
    assert default_finding_kind("qualitative", "low") == "warning"
    assert set(FINDING_KINDS) == {"error", "warning", "methodology", "insufficient_data", "ambiguity"}


def test_finding_construction_keeps_severity_and_error_class():
    rule = Rule(
        "demo_rule",
        "1",
        "logic",
        "high",
        ("basis",),
        "demo",
        frozenset({"rows"}),
    )
    found = rule.finding(AuditInput(), params={"x": 1})
    assert isinstance(found, Finding)
    assert found.error_class == "logic"
    assert found.severity == "high"
    assert found.finding_kind == "error"
    payload = found.as_dict({"job_id": "j"})
    assert payload["finding_kind"] == "error"
    assert payload["error_class"] == "logic"
    assert payload["severity"] == "high"
    # Override на правиле не трогает severity/error_class.
    practice = Rule(
        "practice",
        "1",
        "qualitative",
        "info",
        (),
        "note",
        frozenset({"rows"}),
        finding_kind="methodology",
    )
    note = practice.finding(AuditInput())
    assert (note.finding_kind, note.severity, note.error_class) == ("methodology", "info", "qualitative")
    # Call-site kind (ambiguity) тоже ортогонален.
    ambiguous = rule.finding(AuditInput(), finding_kind="ambiguity", severity="low")
    assert (ambiguous.finding_kind, ambiguous.severity, ambiguous.error_class) == ("ambiguity", "low", "logic")


def test_promote_needs_findings_dedupes_subjects():
    needs = [
        {"kind": "concept", "reason": "concept_unknown", "subject": "cfads"},
        {"kind": "concept", "reason": "concept_unknown", "subject": "cfads"},
        {"kind": "concept", "reason": "ambiguous", "subject": "debt_service"},
        {"kind": "concept", "reason": "other", "subject": "ignored"},
    ]
    found = promote_needs_findings(needs)
    assert [(item.code, item.finding_kind, item.params["subject"]) for item in found] == [
        ("insufficient_input", "insufficient_data", "cfads"),
        ("binding_ambiguity", "ambiguity", "debt_service"),
    ]


def test_findings_schema_includes_finding_kind_append_only():
    doc = load_schema("findings")
    assert doc["version"] == "1.1"
    names = [column["name"] for column in doc["columns"]]
    assert names[-1] == "finding_kind"
    column = next(item for item in doc["columns"] if item["name"] == "finding_kind")
    assert column["nullable"] is True and column["since"] == "1.1"
    assert check_additive_evolution(doc) == []
    payload, count = write_table(
        "findings",
        [
            {
                "analysis_id": "01TEST",
                "model_id": "j" * 64,
                "build_key": "b" * 16,
                "state_seq": 1,
                "code": "hardcoded_formula",
                "rule_version": "1",
                "error_class": "logic",
                "severity": "high",
                "fingerprint": "a" * 40,
                "binding_key": None,
                "row_key": None,
                "axis_id": None,
                "period_id": None,
                "cell_id": None,
                "params_json": "{}",
                "basis_json": "[]",
                "locations_json": "[]",
                "truncated": False,
                "finding_kind": "error",
            }
        ],
        build_key="b" * 16,
    )
    assert count == 1
    assert payload[:4] == b"PAR1"
