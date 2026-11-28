"""Runtime-матрица с причиной. Один evidence_matrix() её не доказывает."""

from __future__ import annotations

from finance_analysis.application.model_types import load_coverage_document
from finance_analysis.application.runtime_matrix import runtime_matrix
from finance_analysis.domain.metric_contract import (
    REGISTRY,
    composition_concepts,
    load_implementations,
)


def test_runtime_matrix_marks_llcr_and_plcr_plan_incomplete():
    load_implementations()
    metrics = load_coverage_document()["metrics"]
    rows = {(row.metric, row.implementation_version): row for row in runtime_matrix()}

    for metric, version in (("llcr", "llcr@1"), ("plcr", "plcr@1")):
        row = rows[(metric, version)]
        pinned = composition_concepts(metrics[metric])
        assert "debt_service" not in pinned
        assert "debt_service" in REGISTRY[(metric, metric)].inputs
        assert row.definition is True
        assert row.executor is True
        assert row.plan == "generated"
        assert row.evidence == "evidence_not_supported"
        assert row.reason == "plan_incomplete"

    dscr = rows[("dscr", "dscr@1")]
    assert "debt_service" in composition_concepts(metrics["dscr"])
    assert dscr.plan == "generated"
    assert dscr.evidence == "evidence_available"
    assert dscr.reason == ""

    adscr = rows[("adscr", "adscr@1")]
    assert adscr.plan == "generated"
    assert adscr.evidence == "evidence_available"
    assert adscr.reason != "plan_incomplete"

    npv = rows[("npv", "npv@1")]
    assert npv.plan == "generated"
    assert npv.evidence == "evidence_not_supported"
    assert npv.reason == "evidence_not_supported"

    nominal = rows[("llcr", "llcr.domrf@1")]
    assert nominal.evidence == "evidence_not_supported"
    assert nominal.reason != "plan_incomplete"


def test_evaluation_matrix_leaves_llcr_and_plcr_integration_not_inventoried():
    import ast
    from pathlib import Path

    import finance_analysis.application.runtime_matrix as runtime
    import tests.unit.evaluation_matrix as evaluation

    rows = {row.metric: row for row in evaluation.evaluation_matrix()}
    for metric in ("llcr", "plcr"):
        row = rows[metric]
        assert row.unit == "covered"
        assert row.golden == "covered"
        assert row.integration == "not_inventoried"
        assert row.evidence_assertions == "no_reference_test"
        assert not hasattr(row, "reason")

    text = Path(evaluation.__file__).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            imported = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            imported = [node.module or ""]
        else:
            continue
        assert all(not name.startswith("finance_analysis") for name in imported)
    runtime_text = Path(runtime.__file__).read_text(encoding="utf-8")
    assert "golden" not in runtime_text
    assert "not_inventoried" not in runtime_text
    assert Path(runtime.__file__) != Path(evaluation.__file__)
