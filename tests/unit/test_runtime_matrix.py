"""Runtime-матрица с причиной. Один evidence_matrix() её не доказывает."""

from __future__ import annotations

import finance_analysis.application.runtime_matrix as runtime
from finance_analysis.application.model_types import load_coverage_document
from finance_analysis.domain.metric_contract import (
    REGISTRY,
    Implementation,
    Mode,
    composition_concepts,
    load_implementations,
)
from finance_analysis.domain.model_type import MetricExpression


def _noop(**_kwargs: object) -> None:
    return None


def _impl(
    metric: str,
    formula: str,
    version: str,
    inputs: tuple[str, ...],
    mode: Mode = "registered",
) -> Implementation:
    return Implementation(
        metric,
        formula,
        version,
        _noop,
        inputs,
        mode=mode,
        reason="" if mode == "registered" else "тест ветви",
    )


def _loan(*, denominator: str = "debt_outstanding") -> MetricExpression:
    return MetricExpression(
        numerator_plus=("cfads",),
        denominator_plus=(denominator,),
        rate="discount_rate",
    )


def test_runtime_matrix_marks_llcr_and_plcr_plan_incomplete():
    load_implementations()
    metrics = load_coverage_document()["metrics"]
    rows = {(row.metric, row.implementation_version): row for row in runtime.runtime_matrix()}

    for metric, version in (("llcr", "llcr@1"), ("plcr", "plcr@1")):
        row = rows[(metric, version)]
        pinned = composition_concepts(metrics[metric])
        assert "debt_service" not in pinned
        assert "debt_service" in REGISTRY[(metric, metric)].inputs
        assert row.definition is True
        assert row.executor is True
        assert row.plan == "declared"
        assert row.plan != "generated"
        assert row.evidence == "evidence_not_supported"
        assert row.reason == "plan_incomplete"

    dscr = rows[("dscr", "dscr@1")]
    assert "debt_service" in composition_concepts(metrics["dscr"])
    assert dscr.plan == "declared"
    assert dscr.evidence == "evidence_available"
    assert dscr.reason == ""

    for metric in ("adscr", "dscr_min", "dscr_avg"):
        inherited = rows[(metric, f"{metric}@1")]
        assert inherited.plan == "declared"
        assert inherited.evidence == "evidence_available"
        assert inherited.reason != "plan_incomplete"

    npv = rows[("npv", "npv@1")]
    assert npv.plan == "declared"
    assert npv.evidence == "evidence_not_supported"
    assert npv.reason == "evidence_not_supported"

    nominal = rows[("llcr", "llcr.domrf@1")]
    assert nominal.plan == "declared"
    assert nominal.evidence == "evidence_not_supported"
    assert nominal.reason != "plan_incomplete"

    assert {row.plan for row in rows.values()} <= {"missing", "declared", "refused"}
    incomplete = {key for key, row in rows.items() if row.reason == "plan_incomplete"}
    assert incomplete == {("llcr", "llcr@1"), ("plcr", "plcr@1")}


def test_missing_definition_is_not_a_plan():
    row = runtime.runtime_row(
        "llcr",
        "llcr",
        None,
        _impl("llcr", "llcr", "llcr@1", ("cfads",)),
    )
    assert row.definition is False
    assert row.plan == "missing"
    assert row.plan != "generated"
    assert row.reason == "missing_definition"
    assert row.evidence == "evidence_not_supported"


def test_missing_executor_keeps_a_declared_formula():
    row = runtime.runtime_row("llcr", "llcr", _loan(), None)
    assert row.executor is False
    assert row.plan == "declared"
    assert row.plan != "generated"
    assert row.reason == "missing_executor"


def test_evidence_not_supported_is_not_the_plan():
    row = runtime.runtime_row(
        "npv",
        "npv",
        MetricExpression(numerator_plus=("project_fcf",), rate="discount_rate"),
        _impl("npv", "npv", "npv@1", ("project_fcf", "discount_rate")),
    )
    assert row.plan == "declared"
    assert row.evidence == "evidence_not_supported"
    assert row.reason == "evidence_not_supported"


def test_plan_incomplete_follows_branch_required_inputs():
    row = runtime.runtime_row(
        "llcr",
        "llcr",
        _loan(),
        _impl("llcr", "llcr", "llcr@1", ("cfads", "debt_outstanding", "discount_rate")),
    )
    assert row.plan == "declared"
    assert row.reason == "plan_incomplete"
    assert row.evidence == "evidence_not_supported"


def test_base_inheritance_resolves_required_inputs():
    child = MetricExpression(base="dscr")
    row = runtime.runtime_row(
        "adscr",
        "adscr",
        child,
        _impl("adscr", "adscr", "adscr@1", ("cfads", "debt_service")),
        expressions={
            "dscr": MetricExpression(
                numerator_plus=("cfads",),
                denominator_plus=("debt_service",),
            )
        },
    )
    assert row.plan == "declared"
    assert row.reason != "plan_incomplete"


def test_composed_executor_is_not_plan_incomplete():
    row = runtime.runtime_row(
        "llcr",
        "llcr",
        _loan(),
        _impl("llcr", "llcr", "llcr@1", ("debt_service",), mode="composed"),
    )
    assert row.plan == "declared"
    assert row.reason != "plan_incomplete"


def test_dynamic_executor_is_not_plan_incomplete():
    row = runtime.runtime_row(
        "llcr",
        "llcr.domrf",
        MetricExpression(
            numerator_plus=("cfo_statement", "cfi_statement", "financing_inflows"),
            denominator_plus=("credit_limit", "senior_interest_paid"),
        ),
        _impl("llcr", "llcr.domrf", "llcr.domrf@1", (), mode="dynamic"),
        windows={"llcr.domrf": "period"},
    )
    assert row.plan == "declared"
    assert row.reason != "plan_incomplete"


def test_refused_formula_shape_is_not_generated():
    row = runtime.runtime_row(
        "llcr",
        "llcr",
        _loan(denominator="other"),
        _impl("llcr", "llcr", "llcr@1", ("cfads", "debt_service")),
    )
    assert row.plan == "refused"
    assert row.plan != "generated"
    assert row.reason != "plan_incomplete"
    assert row.evidence == "evidence_not_supported"


def test_evaluation_matrix_leaves_llcr_and_plcr_integration_not_inventoried():
    import ast
    from pathlib import Path

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


def test_evaluation_inventory_names_existing_tests_and_fixtures():
    import importlib
    import subprocess
    import sys

    import tests.unit.evaluation_matrix as evaluation

    rows = evaluation.evaluation_matrix()
    modules: list[str] = []
    for row in rows:
        for ref in (*row.unit_refs, *row.golden_refs):
            if ref.module not in modules:
                modules.append(ref.module)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", *modules],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    collected = {line.strip() for line in proc.stdout.splitlines() if "::" in line}

    def present(refs: tuple) -> bool:
        return bool(refs) and all(ref.nodeid in collected for ref in refs)

    def fixtures(refs: tuple) -> bool:
        if not refs:
            return False
        for ref in refs:
            module = importlib.import_module(ref.module)
            if not hasattr(module, ref.name):
                return False
        return True

    for row in rows:
        assert row.integration == "not_inventoried"
        assert (row.unit == "covered") is present(row.unit_refs)
        assert (row.golden == "covered") is (present(row.golden_refs) and fixtures(row.golden_fixtures))
