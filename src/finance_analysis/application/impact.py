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


def _cached(value, cell_id: str | None, facts: dict) -> object:
    if value is not None:
        return value
    fact = facts.get(cell_id or "")
    if not fact:
        return None
    if fact.get("value_raw") is not None:
        return fact["value_raw"]
    number = fact.get("value_dec") if fact.get("value_dec") is not None else fact.get("value")
    return None if number is None else str(number)


def _drivers(trace: dict, facts: dict) -> list[dict]:
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
                    "cached_value": _cached(node.get("cached_value"), node.get("node_id"), facts),
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
                        "cached_value": _cached(precedent.get("value"), precedent.get("cell_id"), facts),
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


def _outside(ref: str) -> bool:
    """Как ExternalRef: ссылка `[книга]Лист!A1`."""

    return ref.startswith("[") or "]" in ref.split("!", 1)[0]


def _external(trace: dict, link_cells: dict) -> tuple[list[dict], bool]:
    """Рёбра есть, а внешних ссылок нет — след их не классифицировал."""

    edges = [edge for item in trace.get("items") or [] for edge in item.get("edges") or []]
    found: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for cell in sorted(_cells_of(trace)):
        link = link_cells.get(cell)
        if link is None:
            continue
        for ref in link.refs:
            if _outside(ref) and (cell, ref) not in seen:
                seen.add((cell, ref))
                found.append({"cell_id": cell, "ref": ref})
    found.extend(edge for edge in edges if "external" in str(edge.get("kind") or "").lower())
    if found:
        return found, False
    if not edges:
        return [], trace.get("source") != "builder"
    return [], True


def _findings(findings: list[dict], cells: set[str]) -> list[str]:
    found = []
    for item in findings:
        locations = item.get("locations") or []
        if any((loc.get("cell_id") in cells) for loc in locations):
            found.append(item["fingerprint"])
    return found


def impact_view(trace: dict, link_cells: dict, findings: list[dict], origin: str, facts: dict | None = None) -> dict:
    cells = _cells_of(trace)
    values = facts or {}
    external, unclassified = _external(trace, link_cells)
    warnings = list(trace.get("warnings") or [])
    if unclassified:
        warnings.append({"code": "external_not_in_trace", "params": {}})
    return {
        "origin": origin,
        "direction": trace.get("direction"),
        "depth": trace.get("depth"),
        "source": trace.get("source"),
        "drivers": _drivers(trace, values),
        "hardcodes": _hardcodes(trace, link_cells),
        "external": external,
        "findings": _findings(findings, cells),
        "truncated": bool(trace.get("truncated")),
        "warnings": warnings,
    }
