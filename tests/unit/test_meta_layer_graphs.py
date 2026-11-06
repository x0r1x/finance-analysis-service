"""Фаза 4 метаслоя: три графа, edge id, трассировка metric→concept→cell."""

from __future__ import annotations

import pytest

from finance_analysis.application.keys import PROJECTION
from finance_analysis.domain.graphs import (
    MISSING_FACT_UNAVAILABLE,
    MISSING_METRIC_UNKNOWN,
    MISSING_NO_CELL,
    MISSING_NO_PRIMARY,
    MISSING_STALE,
    GraphTraceError,
    MetricTrace,
    TraceStep,
    assemble_metric_trace_response,
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


def _binding(
    *,
    binding_key: str = _BIND,
    concept: str = "ebitda",
    primary: bool = True,
    status: str = "bound",
    stale: bool = False,
    row_key: str = _ROW,
    build_key: str = _BUILD,
) -> dict:
    return {
        "model_id": _MODEL,
        "build_key": build_key,
        "binding_key": binding_key,
        "row_key": row_key,
        "concept": concept,
        "effective_concept": concept,
        "is_primary": primary,
        "status": status,
        "source": "glossary",
        "derive_key": "abcdefabcdefabcd",
        "state_seq": 1,
        "stale": stale,
    }


def _bindings(**kwargs) -> list[dict]:
    return [_binding(**kwargs)]


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


def _fact(*, cell_id: str = _CELL, period_id: str = "2024Y", build_key: str = _BUILD) -> dict:
    return {
        "model_id": _MODEL,
        "build_key": build_key,
        "row_key": _ROW,
        "cell_id": cell_id,
        "axis_id": "axis_time_1",
        "period_id": period_id,
        "value_status": "ok",
    }


def _facts() -> list[dict]:
    return [_fact()]


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
    assert trace.physical_lineage_complete is True
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
    body = assemble_metric_trace_response(trace)
    assert body["integrity"] == []
    assert body["physical_lineage_complete"] is True
    assert body["catalog_version"] == "deadbeefdeadbeef"


def test_missing_trace_no_cell_when_primary_without_facts() -> None:
    """Пустой fact_observation при доступном датасете → no_cell, не unavailable."""

    trace, findings = check_metric_physical_trace(
        "icr",
        inputs={"all_of": [], "one_of": ["ebitda"]},
        bindings=_bindings(),
        rows=_rows(),
        facts=[],
        facts_available=True,
    )
    step = trace.steps[0]
    assert step.binding_key == _BIND
    assert step.cell_ids == ()
    assert step.missing_trace == MISSING_NO_CELL
    assert findings == []
    validate_metric_trace_document(trace.as_dict())


def test_fact_dataset_unavailable_is_not_no_cell() -> None:
    trace, _ = check_metric_physical_trace(
        "icr",
        inputs={"all_of": [], "one_of": ["ebitda"]},
        bindings=_bindings(),
        rows=_rows(),
        facts=[],
        facts_available=False,
    )
    assert trace.steps == ()
    assert trace.missing_trace == MISSING_FACT_UNAVAILABLE
    validate_metric_trace_document(trace.as_dict())


def test_missing_graph_links_marks_lineage_incomplete() -> None:
    trace = trace_metric(
        "icr",
        inputs={"all_of": [], "one_of": ["ebitda"]},
        bindings=_bindings(),
        rows=_rows(),
        facts=_facts(),
        graph_links=[],
        graph_links_available=False,
    )
    assert trace.physical_lineage_complete is False
    assert trace.steps[0].cell_ids == (_CELL,)
    assert trace.steps[0].excel_links == ()
    validate_metric_trace_document(trace.as_dict())


def test_missing_trace_metric_unknown() -> None:
    trace = trace_metric("nope", inputs=None, bindings=_bindings())
    assert trace.missing_trace == MISSING_METRIC_UNKNOWN
    assert trace.steps == ()
    validate_metric_trace_document(trace.as_dict())


def test_bound_with_warning_traces() -> None:
    trace = trace_metric(
        "icr",
        inputs={"all_of": [], "one_of": ["ebitda"]},
        bindings=_bindings(status="bound_with_warning"),
        rows=_rows(),
        facts=_facts(),
    )
    assert trace.steps[0].binding_key == _BIND
    assert trace.steps[0].cell_ids == (_CELL,)


def test_stale_primary_is_not_used() -> None:
    trace = trace_metric(
        "icr",
        inputs={"all_of": [], "one_of": ["ebitda"]},
        bindings=_bindings(stale=True),
        rows=_rows(),
        facts=_facts(),
    )
    assert trace.steps[0].binding_key is None
    assert trace.steps[0].missing_trace == MISSING_STALE


def test_ambiguous_primary_is_deterministic() -> None:
    bindings = [
        _binding(binding_key="bk_z", concept="ebitda"),
        _binding(binding_key="bk_a", concept="ebitda"),
    ]
    trace = trace_metric(
        "icr",
        inputs={"all_of": [], "one_of": ["ebitda"]},
        bindings=bindings,
        rows=_rows(),
        facts=_facts(),
    )
    assert trace.steps[0].binding_key == "bk_a"
    assert any(item.reason == "ambiguous_primary_binding" for item in trace.integrity)
    body = assemble_metric_trace_response(trace)
    assert body["integrity"][0]["reason"] == "ambiguous_primary_binding"


def test_multiple_periods_return_all_cell_ids() -> None:
    facts = [_fact(cell_id="P&L!D12", period_id="2024Y"), _fact(cell_id="P&L!E12", period_id="2025Y")]
    trace = trace_metric(
        "icr",
        inputs={"all_of": [], "one_of": ["ebitda"]},
        bindings=_bindings(),
        rows=_rows(),
        facts=facts,
    )
    assert trace.steps[0].cell_ids == ("P&L!D12", "P&L!E12")


def test_foreign_build_facts_ignored() -> None:
    facts = [_fact(build_key="OTHERBUILDKEY00000000000000")]
    trace = trace_metric(
        "icr",
        inputs={"all_of": [], "one_of": ["ebitda"]},
        bindings=_bindings(),
        rows=_rows(),
        facts=facts,
        build_key=_BUILD,
        model_id=_MODEL,
    )
    assert trace.steps[0].missing_trace == MISSING_NO_CELL
    assert trace.steps[0].cell_ids == ()


def test_variant_uses_variant_inputs() -> None:
    trace = trace_metric(
        "dscr",
        inputs={"all_of": ["cfads", "debt_service"], "one_of": []},
        bindings=[
            _binding(binding_key="bk_cfads", concept="cfads", row_key="CFS|1|a"),
            _binding(binding_key="bk_ds", concept="debt_service", row_key="Debt|2|b"),
        ],
        rows=[
            {"model_id": _MODEL, "build_key": _BUILD, "row_key": "CFS|1|a", "binding_key": "bk_cfads"},
            {"model_id": _MODEL, "build_key": _BUILD, "row_key": "Debt|2|b", "binding_key": "bk_ds"},
        ],
        facts=[
            {
                "model_id": _MODEL,
                "build_key": _BUILD,
                "row_key": "CFS|1|a",
                "cell_id": "CFS!D10",
                "axis_id": "a",
                "period_id": "2024Y",
                "value_status": "ok",
            },
            {
                "model_id": _MODEL,
                "build_key": _BUILD,
                "row_key": "Debt|2|b",
                "cell_id": "Debt!D5",
                "axis_id": "a",
                "period_id": "2024Y",
                "value_status": "ok",
            },
        ],
        variant="pf",
    )
    assert {step.metric_edge_id for step in trace.steps} == {
        "metric:in:dscr.pf:all_of:cfads",
        "metric:in:dscr.pf:all_of:debt_service",
    }
    validate_metric_trace_document(trace.as_dict())


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
        integrity=(),
        physical_lineage_complete=True,
    )
    findings = validate_metric_traces([broken])
    assert len(findings) == 1
    assert findings[0].reason == "primary_binding_without_trace_or_reason"


def test_assemble_response_rejects_extra_properties() -> None:
    trace = trace_metric(
        "icr",
        inputs={"all_of": [], "one_of": ["ebitda"]},
        bindings=_bindings(),
        rows=_rows(),
        facts=_facts(),
    )
    body = assemble_metric_trace_response(trace)
    body["unexpected"] = True
    with pytest.raises(GraphTraceError):
        validate_metric_trace_document(body)


def test_projection_datasets_do_not_collapse_graphs() -> None:
    assert_graphs_not_collapsed(sorted(PROJECTION))
    assert "graph_links" in PROJECTION
    with pytest.raises(Exception, match="схлопывать"):
        assert_graphs_not_collapsed(["fact_observation", "unified_edges"])
