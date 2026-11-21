"""Контракт SemanticCompatibility: три ответа, без второй вероятности."""

from __future__ import annotations

import pytest

from finance_analysis.application.catalog import load_catalog
from finance_analysis.domain.candidates import Candidate, RowEvidence
from finance_analysis.domain.mapping import assign_rows, decide
from finance_analysis.domain.semantic_compatibility import assess, metric_use

CATALOG = load_catalog()


def _row(label: str, **extra) -> dict:
    return {"label": label, "unit": "money", "nature": "flow", "sign": "outflow", **extra}


def _codes(report) -> dict[str, str]:
    return {item.code: item.severity for item in report.compatibility.checks}


def test_interest_and_interest_paid_share_economic_axes():
    """«Проценты» и «Проценты уплаченные» близки лексически и совместимы экономически."""

    cases = (("interest", "Проценты"), ("interest_paid", "Проценты уплаченные"))
    for name, label in cases:
        report = assess(
            CATALOG.concepts[name],
            row=_row(label),
            label=label,
            probability=0.91,
            basis=("recall", "rerank"),
        )
        assert report.concept == name
        assert report.likelihood.probability == 0.91
        assert report.likelihood.basis == ("recall", "rerank")
        assert report.compatibility.verdict == "compatible"
        assert report.uses == ()
        assert "hard" not in _codes(report).values()


def test_unit_mismatch_is_a_code_and_does_not_rewrite_likelihood():
    concept = CATALOG.concepts["interest"]
    report = assess(
        concept,
        row=_row("Проценты %", unit="%"),
        label="Проценты %",
        probability=0.91,
        basis=("recall",),
    )
    assert report.likelihood.probability == 0.91
    assert report.compatibility.verdict == "incompatible"
    assert _codes(report)["unit_mismatch"] == "hard"


def test_sign_conflict_is_soft():
    report = assess(
        CATALOG.concepts["interest"],
        row=_row("Проценты", sign="inflow"),
        label="Проценты",
        probability=0.8,
        basis=("rerank",),
    )
    assert report.likelihood.probability == 0.8
    assert report.compatibility.verdict == "soft"
    assert _codes(report)["sign"] == "soft"


def test_missing_nature_is_unknown_not_incompatible():
    row = _row("Проценты")
    row["nature"] = None
    report = assess(CATALOG.concepts["interest"], row=row, label="Проценты", probability=0.7)
    assert report.compatibility.verdict == "unknown"
    assert _codes(report)["flow_stock"] == "unknown"


def test_flow_stock_clash_is_soft_without_touching_likelihood():
    report = assess(
        CATALOG.concepts["interest"],
        row=_row("Проценты", nature="stock"),
        label="Проценты",
        probability=0.88,
        basis=("recall",),
    )
    assert report.likelihood.probability == 0.88
    assert report.compatibility.verdict == "soft"
    assert _codes(report)["flow_stock"] == "soft"
    use = metric_use(
        "interest",
        "icr",
        primaries={"interest": {"is_primary": True}},
        interest_order=("interest", "interest_paid"),
        compatibility=report.compatibility,
    )
    assert use.verdict == "usable"


def _binding(key: str, label: str, **extra) -> dict:
    return {
        "kind": "fact",
        "binding_key": key,
        "row_key": key,
        "label": label,
        "label_path_text": label,
        "sign": None,
        **extra,
    }


def _strong(concept: str) -> Candidate:
    return Candidate(concept, recall_cos=0.92, rerank_rank=1, rerank_gap=0.6)


def test_decide_annotates_unit_gate_without_changing_status_or_confidence():
    item = decide(
        _binding("a", "CFADS margin %"),
        RowEvidence(candidates=(_strong("cfads"),)),
        CATALOG,
        None,
    )
    assert item.status == "unknown" and item.concept is None and item.confidence is None
    assert item.evidence["nil"] == "structure_filtered"
    assert item.evidence["candidates"][0]["p"] == 0.0
    body = item.evidence["compatibility"]
    assert body["likelihood"]["probability"] == 0.0
    assert body["compatibility"]["verdict"] == "incompatible"
    codes = {check["code"] for check in body["compatibility"]["checks"]}
    assert "unit_mismatch" in codes


def test_decide_keeps_confidence_when_sign_is_soft():
    found = RowEvidence(candidates=(_strong("interest"),))
    conflict = decide(_binding("a", "Debt payment", unit="money", sign="inflow"), found, CATALOG, None)
    plain = decide(_binding("a", "Debt payment", unit="money", sign="outflow"), found, CATALOG, None)
    assert conflict.status == "bound_with_warning"
    assert conflict.confidence == plain.confidence
    assert conflict.confidence is not None and conflict.confidence > 0.6
    assert conflict.concept == "interest"
    checks = conflict.evidence["compatibility"]["compatibility"]["checks"]
    assert any(item["code"] == "sign" and item["severity"] == "soft" for item in checks)


def test_lexical_path_has_no_likelihood_number():
    item = assign_rows([_binding("a", "Проценты", unit="money")], [], CATALOG)["a"]
    assert item.concept == "interest" and item.confidence is None
    body = item.evidence["compatibility"]
    assert body["likelihood"]["probability"] is None
    assert body["likelihood"]["basis"] == ["lexical"]
    assert body["concept"] == "interest"


def test_graph_note_does_not_change_the_stored_concept():
    row = _binding("a", "Проценты", unit="money", section="ОДДС", role="component")
    item = assign_rows([row], [], CATALOG)["a"]
    assert item.concept == "interest" and item.confidence is None
    codes = {check["code"]: check["severity"] for check in item.evidence["compatibility"]["compatibility"]["checks"]}
    assert codes["section"] == "context"
    assert codes["graph_component"] == "context"


def test_interest_paid_is_not_a_synonym_and_fallback_keeps_its_code():
    order = ("interest", "interest_paid")
    both = {"interest": {"is_primary": True}, "interest_paid": {"is_primary": True}}
    assert metric_use("interest", "icr", primaries=both, interest_order=order).verdict == "usable"
    held = metric_use("interest_paid", "icr", primaries=both, interest_order=order)
    assert held.role == "input" and held.verdict == "declared_inactive"
    assert "interest_basis_fallback" not in held.codes
    only_paid = {"interest_paid": {"is_primary": True}}
    fallen = metric_use("interest_paid", "icr", primaries=only_paid, interest_order=order)
    assert fallen.verdict == "fallback"
    assert fallen.codes == ("interest_basis_fallback",)
    foreign = metric_use("interest_paid", "total_debt", primaries=only_paid, interest_order=order)
    assert foreign.verdict == "undeclared" and foreign.role is None


def test_paid_line_4123_explains_without_replacing_interest():
    row = {
        "effective_concept": "interest",
        "status": "bound",
        "source": "inferred",
        "is_primary": True,
        "line_code": "стр. 4123",
    }
    primaries = {"interest": row}
    order = ("interest", "interest_paid")
    interest = metric_use("interest", "icr", primaries=primaries, interest_order=order, row=row)
    paid = metric_use("interest_paid", "icr", primaries=primaries, interest_order=order, row=row)
    assert list(primaries) == ["interest"]
    assert interest.verdict == "usable" and interest.codes == ("paid_line_4123",)
    assert paid.verdict == "declared_inactive" and paid.codes == ("paid_line_4123",)
    coded = {**row, "line_code": "стр. 4224"}
    skipped = metric_use("interest", "icr", primaries={"interest": coded}, interest_order=order, row=coded)
    assert skipped.codes == ()
    bare = {**row, "line_code": "4123"}
    assert metric_use("interest", "icr", primaries={"interest": bare}, interest_order=order, row=bare).codes == ()


def test_dynamic_branch_stays_inactive():
    present = {"operating_lease_liability": {"is_primary": True}}
    branch = metric_use("operating_lease_liability", "total_debt", primaries=present, interest_order=())
    assert branch.role == "dynamic" and branch.verdict == "declared_inactive"
    group = metric_use("borrowings_lt", "total_debt", primaries={"borrowings_lt": {}}, interest_order=())
    assert group.role == "dynamic" and group.verdict == "usable"


def test_metric_use_rejects_an_empty_formula():
    with pytest.raises(ValueError, match="formula_id пуст"):
        metric_use("interest", "", primaries={})


def test_section_and_graph_are_context():
    report = assess(
        CATALOG.concepts["interest"],
        row=_row("Проценты", section="ОДДС", role="component"),
        label="Проценты",
        probability=0.9,
        notes=("section",),
    )
    assert report.compatibility.verdict == "compatible"
    codes = _codes(report)
    assert codes["section"] == "context"
    assert codes["graph_component"] == "context"
    assert "period_basis" not in codes
    assert "model_type" not in codes


def test_period_basis_mismatch_is_soft():
    report = assess(
        CATALOG.concepts["interest"],
        row=_row("Проценты", period_basis="ytd"),
        label="Проценты",
        probability=0.9,
        expected_period_basis="period",
    )
    assert report.likelihood.probability == 0.9
    assert report.compatibility.verdict == "soft"
    check = next(item for item in report.compatibility.checks if item.code == "period_basis")
    assert check.severity == "soft" and check.expected == "period" and check.observed == "ytd"
    same = assess(
        CATALOG.concepts["interest"],
        row=_row("Проценты", period_basis="period"),
        label="Проценты",
        probability=0.9,
        expected_period_basis="period",
    )
    assert same.compatibility.verdict == "compatible"
    unknown = assess(
        CATALOG.concepts["interest"],
        row=_row("Проценты", period_basis="unknown"),
        label="Проценты",
        probability=0.9,
        expected_period_basis="period",
    )
    assert "period_basis" not in _codes(unknown)


def test_model_type_mismatch_is_soft():
    report = assess(
        CATALOG.concepts["interest"],
        row=_row("Проценты"),
        label="Проценты",
        probability=0.86,
        expected_model_type="corporate",
        observed_model_type="project_finance",
    )
    assert report.likelihood.probability == 0.86
    assert report.compatibility.verdict == "soft"
    check = next(item for item in report.compatibility.checks if item.code == "model_type")
    assert check.severity == "soft" and check.expected == "corporate" and check.observed == "project_finance"
    same = assess(
        CATALOG.concepts["interest"],
        row=_row("Проценты"),
        label="Проценты",
        probability=0.86,
        expected_model_type="corporate",
        observed_model_type="corporate",
    )
    assert same.compatibility.verdict == "compatible"


def test_decide_does_not_promise_uses_or_row_expectations():
    row = _binding(
        "a",
        "Debt payment",
        unit="money",
        sign="outflow",
        period_basis="ytd",
        expected_period_basis="period",
        model_type="project_finance",
        expected_model_type="corporate",
    )
    item = decide(row, RowEvidence(candidates=(_strong("interest"),)), CATALOG, None)
    body = item.evidence["compatibility"]
    assert "uses" not in body
    codes = {check["code"] for check in body["compatibility"]["checks"]}
    assert "period_basis" not in codes and "model_type" not in codes
    assert item.status == "bound"
    assert item.confidence is not None and item.confidence > 0.6
    lexical = assign_rows(
        [
            _binding(
                "b",
                "Проценты",
                unit="money",
                period_basis="ytd",
                expected_period_basis="period",
                model_type="project_finance",
                expected_model_type="corporate",
            )
        ],
        [],
        CATALOG,
    )["b"]
    lexical_body = lexical.evidence["compatibility"]
    assert "uses" not in lexical_body
    lexical_codes = {check["code"] for check in lexical_body["compatibility"]["checks"]}
    assert "period_basis" not in lexical_codes and "model_type" not in lexical_codes


def test_hard_incompatibility_blocks_metric_use():
    report = assess(
        CATALOG.concepts["interest"],
        row=_row("Проценты %", unit="%"),
        label="Проценты %",
        probability=0.91,
    )
    assert report.compatibility.verdict == "incompatible"
    use = metric_use(
        "interest",
        "icr",
        primaries={"interest": {"is_primary": True}},
        interest_order=("interest", "interest_paid"),
        compatibility=report.compatibility,
    )
    assert use.verdict == "blocked" and use.role == "input"
    assert use.codes[0] == "unit_mismatch"
