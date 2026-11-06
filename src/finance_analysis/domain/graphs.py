"""Три графа метаслоя и трассировка metric → concept → binding → cell (фаза 4, G2).

Контракт: docs/meta-layer-graphs.md. Не пишет датасеты и не схлопывает графы
в одну таблицу рёбер. graph_links — только физический Excel-граф.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

_SCHEMA_PATH = Path(__file__).resolve().parent / "contracts" / "meta_layer_graphs.json"

_BOUND = frozenset({"bound", "bound_with_warning"})
MISSING_METRIC_UNKNOWN = "metric_unknown"
MISSING_NO_PRIMARY = "no_primary_binding"
MISSING_NO_CELL = "no_cell"
MISSING_CODES = frozenset({MISSING_METRIC_UNKNOWN, MISSING_NO_PRIMARY, MISSING_NO_CELL})


class GraphTraceError(ValueError):
    """Нарушение инварианта трассировки или контракта рёбер."""


@dataclass(frozen=True)
class ExcelLink:
    edge_id: str
    cell: str | None
    ref_cell: str | None
    formula_class: str | None = None
    truncated: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TraceStep:
    concept: str
    role: str
    metric_edge_id: str
    binding_key: str | None
    binding_edge_id: str | None
    row_key: str | None
    cell_ids: tuple[str, ...] = ()
    missing_trace: str | None = None
    excel_links: tuple[ExcelLink, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        body = asdict(self)
        body["cell_ids"] = list(self.cell_ids)
        body["excel_links"] = [link.as_dict() for link in self.excel_links]
        return body


@dataclass(frozen=True)
class MetricTrace:
    metric_id: str
    variant: str | None
    build_key: str | None
    model_id: str | None
    steps: tuple[TraceStep, ...] = ()
    missing_trace: str | None = None
    catalog_version: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "variant": self.variant,
            "build_key": self.build_key,
            "model_id": self.model_id,
            "catalog_version": self.catalog_version,
            "missing_trace": self.missing_trace,
            "steps": [step.as_dict() for step in self.steps],
        }


@dataclass(frozen=True)
class TraceIntegrityFinding:
    """Вход метрики с основной привязкой без физического следа и без явной причины."""

    metric_id: str
    concept: str
    binding_key: str
    reason: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def edge_digest(*parts: str) -> str:
    payload = "|".join(parts).encode()
    return hashlib.sha1(payload).hexdigest()[:16]


def physical_edge_id(model_id: str, build_key: str, cell: str | None, ref_cell: str | None) -> str:
    return f"excel:link:{edge_digest(model_id, build_key, cell or '', ref_cell or '')}"


def semantic_binding_edge_id(model_id: str, build_key: str, binding_key: str) -> str:
    return f"sem:bind:{edge_digest(model_id, build_key, binding_key)}"


def semantic_relation_edge_id(rel_type: str, source: str, target: str) -> str:
    return f"sem:rel:{rel_type}:{source}->{target}"


def metric_input_edge_id(metric_id: str, role: str, concept: str, *, variant: str | None = None) -> str:
    if role not in {"all_of", "one_of"}:
        raise GraphTraceError(f"unknown metric edge role: {role!r}")
    owner = f"{metric_id}.{variant}" if variant else metric_id
    return f"metric:in:{owner}:{role}:{concept}"


def metric_formula_edges(
    metric_id: str,
    *,
    all_of: Sequence[str] = (),
    one_of: Sequence[str] = (),
    variant: str | None = None,
) -> list[str]:
    """Стабильные id рёбер формульного графа для показателя (без книги)."""

    edges: list[str] = []
    for concept in all_of:
        edges.append(metric_input_edge_id(metric_id, "all_of", concept, variant=variant))
    for concept in one_of:
        edges.append(metric_input_edge_id(metric_id, "one_of", concept, variant=variant))
    return edges


def trace_metric(
    metric_id: str,
    *,
    inputs: Mapping[str, Sequence[str]] | None,
    bindings: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]] = (),
    facts: Sequence[Mapping[str, Any]] = (),
    graph_links: Sequence[Mapping[str, Any]] = (),
    variant: str | None = None,
    catalog_version: str | None = None,
    model_id: str | None = None,
    build_key: str | None = None,
) -> MetricTrace:
    """Собрать read-only трассировку metric → concept → binding_key → cell_id.

    ``inputs`` — ``{"all_of": [...], "one_of": [...]}`` из каталога. Если ``None``,
    показатель считается неизвестным → ``missing_trace=metric_unknown``.
    """

    resolved_model, resolved_build = _book_keys(bindings, rows, facts, model_id, build_key)
    if inputs is None:
        return MetricTrace(
            metric_id=metric_id,
            variant=variant,
            build_key=resolved_build,
            model_id=resolved_model,
            steps=(),
            missing_trace=MISSING_METRIC_UNKNOWN,
            catalog_version=catalog_version,
        )

    row_by_binding = _row_keys(rows, bindings)
    cells_by_row = _cells_by_row(facts)
    steps: list[TraceStep] = []
    for role in ("all_of", "one_of"):
        for concept in inputs.get(role) or ():
            steps.append(
                _step_for_concept(
                    metric_id=metric_id,
                    variant=variant,
                    concept=str(concept),
                    role=role,
                    bindings=bindings,
                    row_by_binding=row_by_binding,
                    cells_by_row=cells_by_row,
                    graph_links=graph_links,
                    model_id=resolved_model or "",
                    build_key=resolved_build or "",
                )
            )
    return MetricTrace(
        metric_id=metric_id,
        variant=variant,
        build_key=resolved_build,
        model_id=resolved_model,
        steps=tuple(steps),
        missing_trace=None,
        catalog_version=catalog_version,
    )


def validate_metric_traces(traces: Sequence[MetricTrace]) -> list[TraceIntegrityFinding]:
    """Целостность: вход с основной привязкой имеет cell_ids либо явный missing_trace."""

    findings: list[TraceIntegrityFinding] = []
    for trace in traces:
        for step in trace.steps:
            if step.binding_key is None:
                continue
            if step.cell_ids:
                if step.missing_trace is not None:
                    findings.append(
                        TraceIntegrityFinding(
                            metric_id=trace.metric_id,
                            concept=step.concept,
                            binding_key=step.binding_key,
                            reason="cell_ids_with_missing_trace",
                        )
                    )
                continue
            if step.missing_trace in MISSING_CODES:
                continue
            findings.append(
                TraceIntegrityFinding(
                    metric_id=trace.metric_id,
                    concept=step.concept,
                    binding_key=step.binding_key,
                    reason="primary_binding_without_trace_or_reason",
                )
            )
    return findings


def check_metric_physical_trace(
    metric_id: str,
    *,
    inputs: Mapping[str, Sequence[str]] | None,
    bindings: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]] = (),
    facts: Sequence[Mapping[str, Any]] = (),
    graph_links: Sequence[Mapping[str, Any]] = (),
    variant: str | None = None,
) -> tuple[MetricTrace, list[TraceIntegrityFinding]]:
    """Трассировка + проверка целостности физического следа для одного показателя."""

    trace = trace_metric(
        metric_id,
        inputs=inputs,
        bindings=bindings,
        rows=rows,
        facts=facts,
        graph_links=graph_links,
        variant=variant,
    )
    return trace, validate_metric_traces([trace])


def assert_graphs_not_collapsed(dataset_names: Sequence[str]) -> None:
    """Защита от миграции, смешивающей три графа в одну таблицу рёбер."""

    forbidden = {"graph_edges", "meta_edges", "unified_edges", "all_edges"}
    overlap = sorted(set(dataset_names) & forbidden)
    if overlap:
        raise GraphTraceError(
            "запрещено схлопывать три графа в один датасет рёбер: " + ", ".join(overlap)
        )


@lru_cache(maxsize=1)
def _trace_validator() -> Draft202012Validator:
    import json

    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    # Валидируем тело MetricTrace через $defs.metricTrace.
    root = {
        "$schema": schema["$schema"],
        "$defs": schema["$defs"],
        **schema["$defs"]["metricTrace"],
    }
    return Draft202012Validator(root)


def validate_metric_trace_document(body: Mapping[str, Any]) -> None:
    errors = sorted(_trace_validator().iter_errors(dict(body)), key=lambda err: list(err.path))
    if errors:
        raise GraphTraceError(errors[0].message)


def _step_for_concept(
    *,
    metric_id: str,
    variant: str | None,
    concept: str,
    role: str,
    bindings: Sequence[Mapping[str, Any]],
    row_by_binding: Mapping[str, str],
    cells_by_row: Mapping[str, tuple[str, ...]],
    graph_links: Sequence[Mapping[str, Any]],
    model_id: str,
    build_key: str,
) -> TraceStep:
    metric_edge = metric_input_edge_id(metric_id, role, concept, variant=variant)
    primary = _primary_binding(bindings, concept)
    if primary is None:
        return TraceStep(
            concept=concept,
            role=role,
            metric_edge_id=metric_edge,
            binding_key=None,
            binding_edge_id=None,
            row_key=None,
            cell_ids=(),
            missing_trace=MISSING_NO_PRIMARY,
            excel_links=(),
        )
    binding_key = str(primary["binding_key"])
    row_key = str(primary.get("row_key") or row_by_binding.get(binding_key) or "") or None
    cell_ids = cells_by_row.get(row_key or "", ())
    missing = None if cell_ids else MISSING_NO_CELL
    links = _excel_links_for_cells(graph_links, cell_ids, model_id=model_id, build_key=build_key)
    return TraceStep(
        concept=concept,
        role=role,
        metric_edge_id=metric_edge,
        binding_key=binding_key,
        binding_edge_id=semantic_binding_edge_id(model_id, build_key, binding_key),
        row_key=row_key,
        cell_ids=cell_ids,
        missing_trace=missing,
        excel_links=links,
    )


def _primary_binding(
    bindings: Sequence[Mapping[str, Any]], concept: str
) -> Mapping[str, Any] | None:
    matched = [
        row
        for row in bindings
        if row.get("is_primary")
        and row.get("status") in _BOUND
        and str(row.get("effective_concept") or row.get("concept") or "") == concept
    ]
    return matched[0] if matched else None


def _row_keys(
    rows: Sequence[Mapping[str, Any]], bindings: Sequence[Mapping[str, Any]]
) -> dict[str, str]:
    found: dict[str, str] = {}
    for row in rows:
        key = row.get("binding_key")
        row_key = row.get("row_key")
        if key and row_key:
            found[str(key)] = str(row_key)
    for row in bindings:
        key = row.get("binding_key")
        row_key = row.get("row_key")
        if key and row_key and str(key) not in found:
            found[str(key)] = str(row_key)
    return found


def _cells_by_row(facts: Sequence[Mapping[str, Any]]) -> dict[str, tuple[str, ...]]:
    buckets: dict[str, list[str]] = {}
    for fact in facts:
        row_key = fact.get("row_key")
        cell_id = fact.get("cell_id")
        if not row_key or not cell_id:
            continue
        buckets.setdefault(str(row_key), []).append(str(cell_id))
    return {key: tuple(dict.fromkeys(values)) for key, values in buckets.items()}


def _excel_links_for_cells(
    links: Sequence[Mapping[str, Any]],
    cell_ids: Sequence[str],
    *,
    model_id: str,
    build_key: str,
) -> tuple[ExcelLink, ...]:
    if not cell_ids or not links:
        return ()
    wanted = set(cell_ids)
    out: list[ExcelLink] = []
    seen: set[str] = set()
    for link in links:
        cell = link.get("cell")
        ref = link.get("ref_cell")
        cell_s = str(cell) if cell is not None else None
        ref_s = str(ref) if ref is not None else None
        if cell_s not in wanted and ref_s not in wanted:
            continue
        edge = physical_edge_id(model_id, build_key, cell_s, ref_s)
        if edge in seen:
            continue
        seen.add(edge)
        out.append(
            ExcelLink(
                edge_id=edge,
                cell=cell_s,
                ref_cell=ref_s,
                formula_class=(str(link["formula_class"]) if link.get("formula_class") is not None else None),
                truncated=bool(link.get("truncated")),
            )
        )
    return tuple(out)


def _book_keys(
    bindings: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
    facts: Sequence[Mapping[str, Any]],
    model_id: str | None,
    build_key: str | None,
) -> tuple[str | None, str | None]:
    if model_id and build_key:
        return model_id, build_key
    for source in (bindings, rows, facts):
        for row in source:
            mid = model_id or (str(row["model_id"]) if row.get("model_id") is not None else None)
            bkey = build_key or (str(row["build_key"]) if row.get("build_key") is not None else None)
            if mid and bkey:
                return mid, bkey
            model_id, build_key = mid, bkey
    return model_id, build_key
