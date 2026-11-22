"""Какие пометки формулы доходят до метрики.

Счётчики и не больше восьми прямых входов — для отчёта. Цепь без отсечения —
для API. На АШАН замыкание DSCR — сотни рядов; печать всех прячет коэффициент.
OAK ведёт по дереву одной формулы, PerfectXL показывает уникальные формулы,
ICAEW сокращает число формул, которые ревьюер читает.

Семена берёт resolve_semantic_inputs: выбранный вариант, один член one_of,
не-stale основная привязка, фактический запасной путь и та же подстановка
4123, что у расчёта. Щит FCFF добавляет interest_paid тем же базисом;
источник такого входа — paid_interest.
"""

from __future__ import annotations

from collections import Counter, defaultdict, deque

from finance_analysis.domain.audit import AuditInput, Finding, severity_rank
from finance_analysis.domain.formula_shape import parse_cell
from finance_analysis.domain.model_type import MetricExpression
from finance_analysis.domain.semantic_input import (
    FormulaChain,
    FormulaOrigin,
    lineage_completeness,
    resolve_semantic_inputs,
)

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


def origin_view(
    data: AuditInput,
    findings: list[Finding],
    expressions: dict[str, MetricExpression],
    *,
    interest_order: dict | None = None,
    row_fallbacks: dict | None = None,
) -> dict:
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
    catalog = {name for name in expressions if "." not in name}
    wanted = data.applicable_metrics if data.applicable_metrics is not None else catalog
    edges = _inputs_of(data)
    for metric in sorted(wanted & catalog):
        resolved = resolve_semantic_inputs(
            metric,
            data.bindings,
            expressions,
            dscr_variant=data.dscr_variant,
            interest_order=interest_order,
            row_fallbacks=row_fallbacks,
            absent=data.absent,
            facts=data.facts,
            links=data.links,
            statement_sheets=data.statement_sheets,
        )
        if not resolved:
            continue
        seeded = tuple(item for item in resolved if item.row_key)
        seeds = {item.row_key: item for item in seeded if item.row_key}
        depth, via = _closure(set(seeds), edges)
        counts: Counter = Counter()
        links: list[FormulaChain] = []
        for row_key, distance in depth.items():
            root = _root(via, row_key)
            seed = seeds.get(root)
            for item in by_row.get(row_key, ()):
                counts[(item.code, item.severity)] += 1
                links.append(
                    FormulaChain(
                        metric=metric,
                        code=item.code,
                        severity=item.severity,
                        fingerprint=item.fingerprint,
                        depth=distance,
                        via=via.get(row_key),
                        input=seed.concept if seed else None,
                        source=seed.source if seed else None,
                        cells=tuple(loc.cell_id for loc in item.locations if loc.cell_id),
                        confirmed=not seed.ambiguous if seed else True,
                    )
                )
        if not counts:
            continue
        ordered = tuple(
            sorted(counts.items(), key=lambda pair: (severity_rank(pair[0][1]), pair[0][0]))
        )
        origin = FormulaOrigin(
            metric=metric,
            closure=len(depth),
            inputs=seeded,
            counts=tuple((code, severity, count) for (code, severity), count in ordered),
            direct=tuple(_direct(data, depth, by_row)),
        )
        metrics.append(origin.as_dict())
        chain.extend(link.as_dict() for link in links)
    status = lineage_completeness(
        graph_links_available=data.graph_links_available,
        truncated_links=sum(1 for link in data.link_cells.values() if link.truncated),
    )
    return {
        "book": book,
        "metrics": metrics,
        "chain": chain,
        "direct_cap": DIRECT_CAP,
        "physical_lineage_complete": status.physical_lineage_complete,
        "truncated_links": status.truncated_links,
        "note": status.note,
    }


def _root(via: dict[str, str | None], row_key: str) -> str:
    seen = set()
    current = row_key
    while via.get(current) and current not in seen:
        seen.add(current)
        current = via[current]
    return current


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
