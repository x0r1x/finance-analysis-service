"""Контракт SemanticCompatibility: три ответа, без второй вероятности."""

from __future__ import annotations

from finance_analysis.application.catalog import load_catalog
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
