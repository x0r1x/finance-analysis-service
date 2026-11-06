"""Фаза 4 метаслоя: три графа, edge id, трассировка metric→concept→cell."""

from __future__ import annotations

import pytest

from finance_analysis.application.keys import PROJECTION
from finance_analysis.domain.graphs import (
    MISSING_METRIC_UNKNOWN,
    MISSING_NO_CELL,
    MISSING_NO_PRIMARY,
    MetricTrace,
    TraceStep,
    assert_graphs_not_collapsed,
    check_metric_physical_trace,
    metric_formula_edges,
    metric_input_edge_id,
    physical_edge_id,
    semantic_binding_edge_id,
    semantic_relation_edge_id,
    trace_metric,
    validate_metric_trace_document,
    validate_metric_traces,
)

_MODEL = "job_golden_book"
_BUILD = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
_ROW = "P&L|12|blk1"
_BIND = "bk_ebitda_primary"
_CELL = "P&L!D12"


def _inputs() -> dict:
    return {"all_of": ["interest"], "one_of": ["ebitda", "ebit"]}


def _bindings(*, primary: bool = True, concept: str = "ebitda") -> list[dict]:
    return [
        {
            "model_id": _MODEL,
            "build_key": _BUILD,
            "binding_key": _BIND,
            "row_key": _ROW,
            "concept": concept,
            "effective_concept": concept,
            "is_primary": primary,
            "status": "bound",
            "source": "glossary",
            "derive_key": "abcdefabcdefabcd",
            "state_seq": 1,
            "stale": False,
        }
    ]


def _rows() -> list[dict]:
    return [
        {
            "model_id": _MODEL,
            "build_key": _BUILD,
            "row_key": _ROW,
            "binding_key": _BIND,
            "sheet": "P&L",
        }
    ]


def _facts() -> list[dict]:
    return [
        {
            "model_id": _MODEL,
            "build_key": _BUILD,
            "row_key": _ROW,
            "cell_id": _CELL,
            "axis_id": "axis_time_1",
            "period_id": "2024Y",
            "value_status": "ok",
        }
    ]


def _links() -> list[dict]:
    return [
        {
            "model_id": _MODEL,
            "build_key": _BUILD,
            "cell": _CELL,
            "ref_cell": "P&L!C12",
            "formula_class": "ref",
            "truncated": False,
            "row_key": _ROW,
        }
    ]


def test_edge_ids_stable_and_namespaced() -> None:
    excel_a = physical_edge_id(_MODEL, _BUILD, _CELL, "P&L!C12")
    excel_b = physical_edge_id(_MODEL, _BUILD, _CELL, "P&L!C12")
    assert excel_a == excel_b
    assert excel_a.startswith("excel:link:")
    bind = semantic_binding_edge_id(_MODEL, _BUILD, _BIND)
    assert bind.startswith("sem:bind:")
    rel = semantic_relation_edge_id("composed_of", "debt_service", "interest")
    assert rel == "sem:rel:composed_of:debt_service->interest"
    metric = metric_input_edge_id("icr", "one_of", "ebitda")
    assert metric == "metric:in:icr:one_of:ebitda"
    assert metric_formula_edges("icr", all_of=["interest"], one_of=["ebitda"]) == [
        "metric:in:icr:all_of:interest",
        "metric:in:icr:one_of:ebitda",
    ]


def test_trace_metric_to_cell_on_golden_book() -> None:
    trace = trace_metric(
        "icr",
        inputs=_inputs(),
        bindings=_bindings(),
        rows=_rows(),
        facts=_facts(),
        graph_links=_links(),
        catalog_version="deadbeefdeadbeef",
    )
    assert trace.missing_trace is None
    assert trace.model_id == _MODEL
    assert trace.build_key == _BUILD
    ebitda = next(step for step in trace.steps if step.concept == "ebitda")
    assert ebitda.metric_edge_id == "metric:in:icr:one_of:ebitda"
    assert ebitda.binding_key == _BIND
    assert ebitda.binding_edge_id == semantic_binding_edge_id(_MODEL, _BUILD, _BIND)
    assert ebitda.row_key == _ROW
    assert ebitda.cell_ids == (_CELL,)
    assert ebitda.missing_trace is None
    assert ebitda.excel_links[0].edge_id == physical_edge_id(_MODEL, _BUILD, _CELL, "P&L!C12")
    interest = next(step for step in trace.steps if step.concept == "interest")
    assert interest.missing_trace == MISSING_NO_PRIMARY
    assert interest.cell_ids == ()
    validate_metric_trace_document(trace.as_dict())
    assert validate_metric_traces([trace]) == []


def test_missing_trace_no_cell_when_primary_without_facts() -> None:
    trace, findings = check_metric_physical_trace(
        "icr",
        inputs={"all_of": [], "one_of": ["ebitda"]},
        bindings=_bindings(),
        rows=_rows(),
        facts=[],
    )
    step = trace.steps[0]
    assert step.binding_key == _BIND
    assert step.cell_ids == ()
    assert step.missing_trace == MISSING_NO_CELL
    assert findings == []


def test_missing_trace_metric_unknown() -> None:
    trace = trace_metric("nope", inputs=None, bindings=_bindings())
    assert trace.missing_trace == MISSING_METRIC_UNKNOWN
    assert trace.steps == ()


def test_integrity_flags_silent_gap() -> None:
    """Инвариант сборщика: нельзя иметь primary binding без cells и без missing_trace."""

    broken = MetricTrace(
        metric_id="icr",
        variant=None,
        build_key=_BUILD,
        model_id=_MODEL,
        steps=(
            TraceStep(
                concept="ebitda",
                role="one_of",
                metric_edge_id="metric:in:icr:one_of:ebitda",
                binding_key=_BIND,
                binding_edge_id=semantic_binding_edge_id(_MODEL, _BUILD, _BIND),
                row_key=_ROW,
                cell_ids=(),
                missing_trace=None,
            ),
        ),
    )
    findings = validate_metric_traces([broken])
    assert len(findings) == 1
    assert findings[0].reason == "primary_binding_without_trace_or_reason"


def test_projection_datasets_do_not_collapse_graphs() -> None:
    assert_graphs_not_collapsed(sorted(PROJECTION))
    assert "graph_links" in PROJECTION
    with pytest.raises(Exception, match="схлопывать"):
        assert_graphs_not_collapsed(["fact_observation", "unified_edges"])
