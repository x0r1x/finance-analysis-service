"""Контракт SemanticCompatibility: три ответа, без второй вероятности."""

from __future__ import annotations

from finance_analysis.application.catalog import load_catalog
from finance_analysis.domain.candidates import Candidate, RowEvidence
from finance_analysis.domain.mapping import assign_rows, decide
from finance_analysis.domain.semantic_compatibility import assess

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


def test_flow_stock_clash_is_hard_without_touching_likelihood():
    report = assess(
        CATALOG.concepts["interest"],
        row=_row("Проценты", nature="stock"),
        label="Проценты",
        probability=0.88,
        basis=("recall",),
    )
    assert report.likelihood.probability == 0.88
    assert report.compatibility.verdict == "incompatible"
    assert _codes(report)["flow_stock"] == "hard"


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


def test_section_and_graph_are_context():
    report = assess(
        CATALOG.concepts["interest"],
        row=_row("Проценты", section="ОДДС", role="component", period_basis="period"),
        label="Проценты",
        probability=0.9,
        notes=("section",),
    )
    assert report.compatibility.verdict == "compatible"
    codes = _codes(report)
    assert codes["section"] == "context"
    assert codes["graph_component"] == "context"
    assert codes["period_basis"] == "context"
