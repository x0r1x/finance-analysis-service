"""Сумма привязанных строк долга, включая забалансовые. Без каталога и без деления."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

_METRIC = "debt_incl_off_balance"
_BOUND = frozenset({"bound", "bound_with_warning"})
_VALUED = frozenset({"cached", "zero_explicit"})
# Только эти источники отменяют `concept.absent`, как у `_primaries`.
_HUMAN = frozenset({"confirmed", "profile"})


def debt_incl_off_balance(
    *,
    components: tuple[str, ...],
    facts: list[dict],
    bindings: list[dict],
    periods: list[dict],
    absent: frozenset[str] = frozenset(),
) -> dict:
    """Сумма signed `normalized_value` по каждой привязанной строке слагаемого.

    `periods` не участвует в арифметике: вызывающий передаёт тот же набор, что и
    в другие метрики. Ключ строки результата — `(axis_id, period_id)` факта.
    """

    _ = periods
    bound_rows = _bound_rows(components, bindings, absent)
    if not bound_rows:
        return {
            "metric": _METRIC,
            "rows": [],
            "needs_input": [{"kind": "concept", "reason": "concept_unknown", "subject": _METRIC}],
            "warnings": [],
            "status": "missing_input",
        }
    present = list(dict.fromkeys(concept for concept in components if concept in bound_rows))
    complete, warnings = _by_period(facts, bound_rows, present)
    rows = [_row(key, amounts, present) for key, amounts in complete]
    missing = [concept for concept in components if concept not in bound_rows]
    if missing:
        warnings.append({"code": "component_absent", "params": {"concepts": missing}})
    status = "not_computed" if not rows and warnings else "succeeded"
    return {"metric": _METRIC, "rows": rows, "needs_input": [], "warnings": warnings, "status": status}


def _bound_rows(components: tuple[str, ...], bindings: list[dict], absent: frozenset[str]) -> dict[str, list[str]]:
    wanted = set(components)
    found: dict[str, list[str]] = {}
    for binding in bindings:
        concept = binding.get("effective_concept")
        if concept not in wanted or binding.get("status") not in _BOUND:
            continue
        if concept in absent and binding.get("source") not in _HUMAN:
            continue
        rows = found.setdefault(concept, [])
        row_key = binding.get("row_key")
        if row_key is not None and row_key not in rows:
            rows.append(row_key)
    return found


def _by_period(
    facts: list[dict],
    bound_rows: dict[str, list[str]],
    present: list[str],
) -> tuple[list[tuple[tuple, dict[str, Decimal]]], list[dict]]:
    row_concepts: dict[str, list[str]] = {}
    for concept in present:
        for row_key in bound_rows[concept]:
            concepts = row_concepts.setdefault(row_key, [])
            if concept not in concepts:
                concepts.append(concept)
    totals: dict[tuple, dict[str, Decimal]] = {}
    gaps: dict[tuple, set[str]] = {}
    for fact in facts:
        concepts = row_concepts.get(fact.get("row_key"))
        if not concepts:
            continue
        key = (fact.get("axis_id"), fact.get("period_id"))
        bucket = totals.setdefault(key, {})
        gapped = gaps.setdefault(key, set())
        number = _usable(fact)
        if number is None:
            for concept in concepts:
                gapped.add(concept)
                bucket.pop(concept, None)
            continue
        for concept in concepts:
            if concept in gapped:
                continue
            bucket[concept] = bucket.get(concept, Decimal(0)) + number
    complete: list[tuple[tuple, dict[str, Decimal]]] = []
    warnings: list[dict] = []
    for key, bucket in totals.items():
        holes = [concept for concept in present if concept not in bucket]
        if holes:
            for concept in holes:
                warnings.append(
                    {
                        "code": "component_gap",
                        "params": {"concept": concept, "axis_id": key[0], "period_id": key[1]},
                    }
                )
            continue
        complete.append((key, bucket))
    return complete, warnings


def _usable(fact: dict) -> Decimal | None:
    status = fact.get("value_status")
    if status is not None and status not in _VALUED:
        return None
    return _decimal(fact.get("normalized_value"))


def _row(key: tuple, amounts: dict[str, Decimal], present: list[str]) -> dict:
    shown: dict[str, str] = {}
    total = Decimal(0)
    for concept in present:
        part = amounts[concept]
        shown[concept] = str(part)
        total += part
    return {
        "period_id": key[1],
        "axis_id": key[0],
        "value": str(total),
        "status": "computed",
        "components": shown,
    }


def _decimal(value) -> Decimal | None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not number.is_finite():
        return None
    return number
