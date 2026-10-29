"""Структурный impact из уже посчитанного trace. Формулы Excel не пересчитываются (§6.5)."""

from __future__ import annotations


def _cells_of(trace: dict) -> set[str]:
    found: set[str] = set()
    for item in trace.get("items") or []:
        for key in ("cell_id", "origin"):
            if item.get(key):
                found.add(item[key])
        for node in item.get("nodes") or []:
            if node.get("node_id"):
                found.add(node["node_id"])
        for precedent in item.get("precedents") or []:
            if isinstance(precedent, dict) and precedent.get("cell_id"):
                found.add(precedent["cell_id"])
    return found


def _drivers(trace: dict) -> list[dict]:
    found = []
    for item in trace.get("items") or []:
        for node in item.get("nodes") or []:
            if int(node.get("depth") or 0) <= 0:
                continue
            found.append(
                {
                    "node_id": node.get("node_id"),
                    "row_key": node.get("row_key"),
                    "formula": node.get("formula"),
                    "cached_value": node.get("cached_value"),
                    "depth": node.get("depth"),
                }
            )
        for precedent in item.get("precedents") or []:
            if isinstance(precedent, dict):
                found.append(
                    {
                        "node_id": precedent.get("cell_id"),
                        "row_key": precedent.get("row_key"),
                        "formula": None,
                        "cached_value": precedent.get("value"),
                        "depth": 1,
                    }
                )
    return found


def _hardcodes(trace: dict, link_cells: dict) -> list[dict]:
    found = []
    seen: set[str] = set()
    for cell in sorted(_cells_of(trace)):
        link = link_cells.get(cell)
        if link is None:
            continue
        klass = link.formula_class or ""
        bare = bool(link.formula) and not link.refs
        if "hardcoded" not in klass and not bare:
            continue
        seen.add(cell)
        found.append({"cell_id": cell, "formula": link.formula, "formula_class": link.formula_class})
    for item in trace.get("items") or []:
        cell = item.get("cell_id")
        if not cell or cell in seen:
            continue
        klass = item.get("formula_class") or ""
        if "hardcoded" in klass or (item.get("formula") and not item.get("precedents")):
            found.append({"cell_id": cell, "formula": item.get("formula"), "formula_class": item.get("formula_class")})
    return found


def _external(trace: dict) -> tuple[list[dict], bool]:
    """Пустой kind у всех рёбер — след не классифицировал внешние ссылки."""

    edges = [edge for item in trace.get("items") or [] for edge in item.get("edges") or []]
    if not edges:
        return [], trace.get("source") != "builder"
    if all(edge.get("kind") is None for edge in edges):
        return [], True
    return [edge for edge in edges if "external" in str(edge.get("kind") or "").lower()], False


def _findings(findings: list[dict], cells: set[str]) -> list[str]:
    found = []
    for item in findings:
        locations = item.get("locations") or []
        if any((loc.get("cell_id") in cells) for loc in locations):
            found.append(item["fingerprint"])
    return found


def impact_view(trace: dict, link_cells: dict, findings: list[dict], origin: str) -> dict:
    cells = _cells_of(trace)
    external, unclassified = _external(trace)
    warnings = list(trace.get("warnings") or [])
    if unclassified:
        warnings.append({"code": "external_not_in_trace", "params": {}})
    return {
        "origin": origin,
        "direction": trace.get("direction"),
        "depth": trace.get("depth"),
        "source": trace.get("source"),
        "drivers": _drivers(trace),
        "hardcodes": _hardcodes(trace, link_cells),
        "external": external,
        "findings": _findings(findings, cells),
        "truncated": bool(trace.get("truncated")),
        "warnings": warnings,
    }
