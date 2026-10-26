"""Знак, природа и исключение строки (§5.4). Фазу отсюда не ставим."""

from __future__ import annotations

from finance_analysis.domain.glossary import normalize_label

_EXCLUDED_KINDS = frozenset({"helper", "flag", "index"})


def exclusion(row: dict, *, empty_series: bool) -> tuple[bool, str | None]:
    if row.get("kind") in _EXCLUDED_KINDS:
        return True, row["kind"]
    if row.get("hidden"):
        return True, "hidden"
    if row.get("check_row"):
        return True, "check_row"
    if empty_series:
        return True, "empty_series"
    return False, None


def infer_row(row: dict, flows: dict) -> dict:
    label = normalize_label(str(row.get("label") or ""))
    sign = _flow(label, flows)
    nature = "flow" if sign else None
    aggregation = "aggregate" if any(token in label for token in ("total", "итого", "всего")) else None
    return {"sign": sign, "nature": nature, "aggregation": aggregation, "source": "inferred"}


def _flow(label: str, flows: dict) -> str | None:
    for direction in ("outflow", "inflow"):
        for token in flows.get(direction) or ():
            if normalize_label(token) and normalize_label(token) in label:
                return direction
    return None


def empty_series(row_key: str, facts: list[dict] | None) -> bool:
    if facts is None or row_key is None:
        return False
    own = [fact for fact in facts if fact.get("row_key") == row_key]
    if not own:
        return True
    return all(fact.get("value_status") in {None, "empty", "not_applicable"} for fact in own)
