"""Первый операционный год (§5.4). Флаги таймлайна не читаются."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from finance_analysis.domain.phases import split_phase_target

DEBT_SERVICE = "debt_service"
_BOUND = frozenset({"bound", "bound_with_warning"})


def _decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError, ArithmeticError):
        return None


def _explicit_phases(events: list[dict], axis_id: str) -> bool:
    for event in events:
        if event.get("type") != "phase.set":
            continue
        parsed = split_phase_target(str(event.get("target") or ""))
        if parsed and parsed[0] == axis_id:
            return True
    return False


def resolve_operational_year(
    periods: list[dict],
    semantics: list[dict],
    bindings: list[dict],
    facts: list[dict],
    *,
    events: list[dict] | None = None,
) -> dict:
    """(axis_id, period_id) канонической оси таймлайна либо needs_input по debt_service."""

    journal = events or []
    phase_of = {(row["axis_id"], row["period_id"]): row.get("phase") for row in semantics}
    located = {
        (row["axis_id"], row["period_id"]): row
        for row in periods
        if row.get("axis_kind") == "time"
    }
    canonical = [
        row
        for row in periods
        if row.get("axis_kind") == "time"
        and row.get("timeline_id")
        and row["axis_id"] == row["timeline_id"]
    ]
    canonical.sort(key=lambda row: (row["axis_id"], int(row["period_index"])))
    if not canonical:
        return _needs_debt()
    timeline_id = canonical[0]["timeline_id"]
    axis_id = canonical[0]["axis_id"]
    timeline = [row for row in canonical if row["axis_id"] == axis_id]
    explicit = _explicit_phases(journal, axis_id) or any(phase_of.get((row["axis_id"], row["period_id"])) for row in timeline)
    if explicit:
        picked = next(
            (row for row in timeline if phase_of.get((row["axis_id"], row["period_id"])) == "operation"),
            None,
        )
        if picked is None:
            return {"periods": [], "needs_input": [], "basis": "phase_decision"}
        return {"periods": [_ref(picked, "phase_decision")], "needs_input": [], "basis": "phase_decision"}

    primary = _primary_row(bindings)
    if primary is None:
        return _needs_debt()
    if primary == "ambiguous":
        return _needs_debt()
    totals = _debt_by_index(facts, located, timeline_id, primary)
    picked = next((row for row in timeline if totals.get(int(row["period_index"]), Decimal(0)) != 0), None)
    if picked is None:
        return {"periods": [], "needs_input": [], "basis": "nonzero_debt_service"}
    return {
        "periods": [_ref(picked, "nonzero_debt_service")],
        "needs_input": [],
        "basis": "nonzero_debt_service",
    }


def _needs_debt() -> dict:
    return {
        "periods": [],
        "needs_input": [{"kind": "concept", "reason": "concept_unknown", "subject": DEBT_SERVICE}],
    }


def _primary_row(bindings: list[dict]) -> str | None:
    """row_key основной строки, None если не привязана, 'ambiguous' если привязка неоднозначна."""

    rows = []
    ambiguous = False
    for row in bindings:
        concept = row.get("effective_concept") or row.get("concept")
        if concept != DEBT_SERVICE:
            continue
        status = row.get("status")
        if status == "ambiguous":
            ambiguous = True
        if row.get("is_primary") and status in _BOUND:
            key = row.get("row_key")
            if key:
                rows.append(key)
    unique = set(rows)
    if ambiguous or len(unique) > 1:
        return "ambiguous"
    if len(unique) == 1:
        return next(iter(unique))
    return None


def _debt_by_index(facts, located, timeline_id: str, row_key: str) -> dict[int, Decimal]:
    totals: dict[int, Decimal] = {}
    for fact in facts:
        if fact.get("row_key") != row_key:
            continue
        period = located.get((fact.get("axis_id"), fact.get("period_id")))
        if period is None:
            continue
        owner = period.get("timeline_id") or period.get("axis_id")
        if owner != timeline_id:
            continue
        number = _decimal(fact.get("value_dec"))
        if number is None:
            continue
        index = int(period["period_index"])
        totals[index] = totals.get(index, Decimal(0)) + number
    return totals


def _ref(period: dict, basis: str) -> dict:
    year = period.get("calendar_year")
    body = {
        "axis_id": period["axis_id"],
        "period_id": period["period_id"],
        "period_key": period["period_id"],
        "period_key_base": period.get("period_key_base"),
        "period_marker": period.get("period_marker"),
        "calendar_year": year,
        "basis": basis,
    }
    if year is None:
        body["reason"] = "no_calendar_anchor"
    return body
