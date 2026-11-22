"""Какие пометки формулы доходят до метрики.

Счётчики и не больше восьми прямых входов — для отчёта. Цепь без отсечения —
для API. На АШАН замыкание DSCR — сотни рядов; печать всех прячет коэффициент.
OAK ведёт по дереву одной формулы, PerfectXL показывает уникальные формулы,
ICAEW сокращает число формул, которые ревьюер читает.

Семена — входы, которые расчёт реально взял: выбранный вариант, один член one_of,
текущая основная привязка и фактический запасной путь interest_order.
Подстановка 4123 (confirm_paid_interest) в семена не входит: это не вход формулы.
"""

from __future__ import annotations

from collections import Counter, defaultdict, deque

from finance_analysis.domain.audit import AuditInput, Finding, severity_rank
from finance_analysis.domain.formula_shape import parse_cell
from finance_analysis.domain.graphs import _select_primary
from finance_analysis.domain.metrics import interest_choice
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
# Тот же набор, что housing_cover._FAMILY: ADSCR и сводки наследуют housing, не ковенант.
_HOUSING = frozenset({"adscr", "dscr_min", "dscr_avg"})


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
        resolved = _resolved(data, expressions, metric, interest_order, row_fallbacks)
        seeds = {item["row_key"]: (item["concept"], item["source"]) for item in resolved}
        depth, via = _closure(set(seeds), edges)
        counts: Counter = Counter()
        for row_key, distance in depth.items():
            root = _root(via, row_key)
            concept, source = seeds.get(root, (None, None))
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
                        "input": concept,
                        "source": source,
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
                "inputs": resolved,
                "counts": [
                    {"code": code, "severity": severity, "count": count}
                    for (code, severity), count in sorted(counts.items(), key=lambda pair: (severity_rank(pair[0][1]), pair[0][0]))
                ],
                "direct": direct,
            }
        )
    truncated_links = sum(1 for link in data.link_cells.values() if link.truncated)
    # shortcut: пустой список связей выглядит полным. Книга без формул и отсутствующий graph_links здесь не различаются. Поднять, когда AuditInput получит graph_links_available, как trace_metric.
    # Обрезанный диапазон — та же неполнота физического графа, что physical_lineage_complete у trace_metric.
    complete = truncated_links == 0
    return {
        "book": book,
        "metrics": metrics,
        "chain": chain,
        "direct_cap": DIRECT_CAP,
        "physical_lineage_complete": complete,
        "truncated_links": truncated_links,
        "note": None if complete else f"цепь может быть неполной: обрезано ссылок {truncated_links}",
    }


def _variant_name(data: AuditInput, metric: str) -> str | None:
    named = data.dscr_variant
    if not named:
        return None
    if metric == "dscr":
        return named
    if metric in _HOUSING and named == "housing":
        return "housing"
    return None


def _active(data: AuditInput, expressions: dict[str, MetricExpression], metric: str) -> tuple[MetricExpression | None, str]:
    variant = _variant_name(data, metric)
    if variant:
        chosen = expressions.get(f"{metric}.{variant}")
        if chosen is not None and not chosen.base:
            return chosen, f"variant:{variant}"
    expr = expressions.get(metric)
    if expr is not None and expr.base:
        base = expressions.get(expr.base)
        if base is not None:
            return base, f"base:{expr.base}"
    return expr, "formula"


def _one_of(expr: MetricExpression, bindings: list[dict]) -> str | None:
    """Член one_of, который берёт расчёт. Оба числителя ICR — EBITDA."""

    present = [name for name in expr.one_of if _select_primary(bindings, name)[0] is not None]
    if "ebitda" in present:
        return "ebitda"
    if len(present) == 1:
        return present[0]
    return None


def _interest_slot(metric: str, variant: str | None) -> str | None:
    if metric in {"icr", "icr_ebit"}:
        return metric
    if metric == "dscr" and variant in {None, "pf", "corporate_covenant", "ocf_covenant"}:
        return "pf" if variant in {None, "pf"} else variant
    return None


def _interest_pick(bindings: list[dict], order, row_fallbacks: dict | None) -> str | None:
    primaries: dict = {}
    names = list(order)
    for name in names:
        row, _, _ = _select_primary(bindings, name)
        if row is not None:
            primaries[name] = row
        fallback = (row_fallbacks or {}).get(name)
        canonical = getattr(fallback, "canonical", None) if fallback is not None else ("interest" if name == "interest_paid" else None)
        if canonical and canonical not in primaries:
            canonical_row, _, _ = _select_primary(bindings, canonical)
            if canonical_row is not None:
                primaries[canonical] = canonical_row
    chosen, _warning = interest_choice(primaries, order, row_fallbacks=row_fallbacks)
    return chosen


def _specs(
    data: AuditInput,
    expressions: dict[str, MetricExpression],
    metric: str,
    interest_order: dict | None,
    row_fallbacks: dict | None,
) -> list[tuple[str, str]]:
    expr, source = _active(data, expressions, metric)
    if expr is None:
        return []
    specs: list[tuple[str, str]] = []

    def add(name: str | None, src: str) -> None:
        if name and all(item[0] != name for item in specs):
            specs.append((name, src))

    for name in (
        *expr.numerator_plus,
        *expr.numerator_minus,
        *expr.denominator_plus,
        *expr.denominator_minus,
        *expr.rates,
    ):
        add(name, source)
    add(expr.rate, source)
    add(expr.compare_with, source)
    if expr.add_back:
        add(expr.add_back[0], source)
        add(expr.add_back[1], source)
    chosen = _one_of(expr, data.bindings)
    if chosen:
        add(chosen, "one_of")
    return _fallbacks(data, metric, _variant_name(data, metric), specs, interest_order, row_fallbacks)


def _fallbacks(data, metric, variant, specs, interest_order, row_fallbacks) -> list[tuple[str, str]]:
    order = interest_order or {}
    names = [name for name, _src in specs]
    slot = _interest_slot(metric, variant)
    if "interest" in names and slot and order.get(slot) and _select_primary(data.bindings, "interest")[0] is None:
        chosen = _interest_pick(data.bindings, order[slot], row_fallbacks)
        if chosen and chosen != "interest":
            specs = [(chosen, "fallback") if name == "interest" else (name, src) for name, src in specs]
    if (
        metric == "dscr"
        and variant in {None, "pf"}
        and "debt_service" in names
        and _select_primary(data.bindings, "debt_service")[0] is None
        and order.get("pf")
    ):
        chosen = _interest_pick(data.bindings, order["pf"], row_fallbacks)
        if chosen and _select_primary(data.bindings, "principal")[0] is not None:
            specs = [item for item in specs if item[0] != "debt_service"]
            have = {name for name, _src in specs}
            if chosen not in have:
                specs.append((chosen, "fallback"))
            if "principal" not in have:
                specs.append(("principal", "fallback"))
    return specs


def _resolved(data, expressions, metric, interest_order, row_fallbacks) -> list[dict]:
    found = []
    for concept, source in _specs(data, expressions, metric, interest_order, row_fallbacks):
        primary, _missing, _ambiguous = _select_primary(data.bindings, concept)
        row_key = primary.get("row_key") if primary else None
        if not row_key:
            continue
        found.append({"concept": concept, "source": source, "row_key": row_key})
    return found


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
