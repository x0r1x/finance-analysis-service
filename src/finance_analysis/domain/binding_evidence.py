"""Пометки амортизации на привязке. Зерно периода книги их не заменяет."""

from __future__ import annotations

_DEPRECIATION = frozenset({"depreciation_notes", "depreciation_rou"})
_VALUE_BASIS = frozenset({"period", "ytd", "annual"})


def depreciation_evidence_error(concept: str, evidence: dict | None) -> str | None:
    """includes_rou — только bool на depreciation_notes и только с источником.

    value_basis — period, ytd или annual, и только у амортизации.
    """

    if not evidence:
        return None
    if "includes_rou" in evidence:
        if concept != "depreciation_notes":
            return "includes_rou только у depreciation_notes"
        if not isinstance(evidence.get("includes_rou"), bool):
            return "includes_rou — да или нет"
        source = evidence.get("includes_rou_source")
        if evidence.get("includes_rou") is True and (not isinstance(source, str) or not source.strip()):
            return "includes_rou требует источник подтверждения"
    elif evidence.get("includes_rou_source"):
        return "includes_rou_source без includes_rou"
    if "value_basis" in evidence:
        if concept not in _DEPRECIATION:
            return "value_basis только у амортизации"
        if evidence.get("value_basis") not in _VALUE_BASIS:
            return "value_basis — period, ytd или annual"
    return None


def stamped_depreciation_evidence(evidence: dict, event: dict) -> dict:
    """Переносит пометку в привязку и пишет происхождение в журнал привязки."""

    kept: dict = {}
    if "value_basis" in evidence:
        kept["value_basis"] = evidence["value_basis"]
    if "includes_rou" not in evidence:
        return kept
    kept["includes_rou"] = evidence["includes_rou"]
    kept["includes_rou_source"] = evidence.get("includes_rou_source")
    kept["includes_rou_provenance"] = {
        "seq": event.get("seq"),
        "actor": event.get("actor"),
        "at_utc": event.get("at_utc"),
        "source": evidence.get("includes_rou_source"),
    }
    return kept
