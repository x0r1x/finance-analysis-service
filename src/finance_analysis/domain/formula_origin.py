"""Какие пометки формулы доходят до метрики.

Счётчики и не больше восьми прямых входов — для отчёта. Цепь без отсечения —
для API. На АШАН замыкание DSCR — сотни рядов; печать всех прячет коэффициент.
OAK ведёт по дереву одной формулы, PerfectXL показывает уникальные формулы,
ICAEW сокращает число формул, которые ревьюер читает.
"""

from __future__ import annotations

from collections import Counter, defaultdict, deque

from finance_analysis.domain.audit import AuditInput, Finding, severity_rank
from finance_analysis.domain.formula_shape import parse_cell
from finance_analysis.domain.model_type import MetricExpression

ORIGIN_CODES = frozenset(
    {
        "formula_pattern_break",
        "formula_segment",
        "cross_period_ref",
        "prior_column",
        "zero_addend",
        "literal_in_formula",
    }
)
DIRECT_DEPTH = 1
DIRECT_CAP = 8


def input_concepts(expressions: dict[str, MetricExpression], metric: str, seen: set[str] | None = None) -> tuple[str, ...]:
    """Входы базовой формулы. Варианты каталога сюда не входят."""

    if seen is None:
        seen = set()
    if metric in seen:
        return ()
    expr = expressions.get(metric)
    if expr is None:
        return ()
    seen.add(metric)
    if expr.base:
        return input_concepts(expressions, expr.base, seen)
    names: list[str] = []
    for name in (
        *expr.numerator_plus,
        *expr.numerator_minus,
        *expr.denominator_plus,
        *expr.denominator_minus,
        *sorted(expr.one_of),
        *expr.rates,
    ):
        if name not in names:
            names.append(name)
    if expr.compare_with and expr.compare_with not in names:
        names.append(expr.compare_with)
    return tuple(names)


def origin_view(data: AuditInput, findings: list[Finding], expressions: dict[str, MetricExpression]) -> dict:
    marked = [item for item in findings if item.code in ORIGIN_CODES]
    by_code: dict[str, Counter] = defaultdict(Counter)
    by_row: dict[str, list[Finding]] = defaultdict(list)
    for item in marked:
        by_code[item.code][item.severity] += 1
        for row_key in {loc.row_key for loc in item.locations if loc.row_key}:
            by_row[row_key].append(item)
    book = {
        code: {severity: count for severity, count in sorted(counts.items(), key=lambda pair: severity_rank(pair[0]))}
        for code, counts in sorted(by_code.items())
    }
    metrics = []
    chain = []
    wanted = data.applicable_metrics if data.applicable_metrics is not None else frozenset(expressions)
    inputs = _inputs_of(data)
    for metric in sorted(wanted & set(expressions)):
        seeds = _seeds(data, metric, input_concepts(expressions, metric))
        depth, via = _closure(seeds, inputs)
        counts: Counter = Counter()
        for row_key, distance in depth.items():
            for item in by_row.get(row_key, ()):
                counts[(item.code, item.severity)] += 1
                chain.append(
                    {
                        "metric": metric,
                        "code": item.code,
                        "severity": item.severity,
                        "fingerprint": item.fingerprint,
                        "depth": distance,
                        "via": via.get(row_key),
                        "cells": [loc.cell_id for loc in item.locations if loc.cell_id],
                    }
                )
        if not counts:
            continue
        direct = _direct(data, depth, by_row)
        metrics.append(
            {
                "metric": metric,
                "closure": len(depth),
                "counts": [
                    {"code": code, "severity": severity, "count": count}
                    for (code, severity), count in sorted(counts.items(), key=lambda pair: (severity_rank(pair[0][1]), pair[0][0]))
                ],
                "direct": direct,
            }
        )
    return {"book": book, "metrics": metrics, "chain": chain, "direct_cap": DIRECT_CAP}


def _seeds(data: AuditInput, metric: str, concepts: tuple[str, ...]) -> set[str]:
    names = {metric, *concepts}
    return {
        row["row_key"]
        for row in data.bindings
        if row.get("status") == "bound" and row.get("effective_concept") in names and row.get("row_key")
    }


def _inputs_of(data: AuditInput) -> dict[str, set[str]]:
    cell_row = {link.cell: link.row_key for link in data.link_cells.values() if link.row_key}
    by_address: dict[tuple[str, int], str] = {}
    for row in data.rows:
        sheet = row.get("sheet")
        number = row.get("row_num")
        if sheet and isinstance(number, int):
            by_address[(sheet, number)] = row["row_key"]
    edges: dict[str, set[str]] = defaultdict(set)
    for link in data.link_cells.values():
        source = link.row_key
        if not source:
            continue
        for ref in link.refs:
            target = cell_row.get(ref)
            if target is None:
                parsed = parse_cell(ref)
                if parsed and parsed[0]:
                    target = by_address.get((parsed[0], parsed[2]))
            if target and target != source:
                edges[source].add(target)
    return edges


def _closure(seeds: set[str], edges: dict[str, set[str]]) -> tuple[dict[str, int], dict[str, str | None]]:
    depth = {row: 0 for row in seeds}
    via: dict[str, str | None] = {row: None for row in seeds}
    queue = deque(seeds)
    while queue:
        current = queue.popleft()
        for nxt in edges.get(current, ()):
            if nxt in depth:
                continue
            depth[nxt] = depth[current] + 1
            via[nxt] = current
            queue.append(nxt)
    return depth, via


def _direct(data: AuditInput, depth: dict[str, int], by_row: dict[str, list[Finding]]) -> list[dict]:
    rows = [row for row, distance in depth.items() if distance <= DIRECT_DEPTH and by_row.get(row)]
    rows.sort(key=lambda row: (-max(severity_rank(item.severity) for item in by_row[row]), row))
    shown = []
    for row_key in rows[:DIRECT_CAP]:
        row = data.rows_by_key.get(row_key) or {}
        cells: dict[str, dict] = {}
        for item in by_row[row_key]:
            for loc in item.locations:
                if not loc.cell_id:
                    continue
                cell = cells.setdefault(loc.cell_id, {"cell_id": loc.cell_id, "period_id": loc.period_id, "codes": []})
                if item.code not in cell["codes"]:
                    cell["codes"].append(item.code)
        shown.append(
            {
                "row_key": row_key,
                "label": row.get("label"),
                "depth": depth[row_key],
                "cells": [cells[key] for key in sorted(cells)],
            }
        )
    return shown
