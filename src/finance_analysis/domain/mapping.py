"""Привязка строки к понятию без модели (§5.5, §5.10.1)."""

from __future__ import annotations

from dataclasses import dataclass

from finance_analysis.domain.glossary import GlossaryPackage, normalize_label

MATERIAL_SHARE = 0.05
_HUMAN = frozenset({"concept.set", "concept.confirmed"})


@dataclass(frozen=True)
class Assignment:
    concept: str | None
    status: str
    source: str
    is_primary: bool
    matched_label: str | None
    importance: str


# shortcut: scope=profile и прецеденты графа dscr не смотрятся, точное совпадение метки и решение человека
def assign_rows(
    rows: list[dict],
    events: list[dict],
    glossary: GlossaryPackage,
    *,
    abs_by_row: dict[str, float] | None = None,
) -> dict[str, Assignment]:
    human, ignored, absent = _decisions(events)
    draft: list[tuple[dict, Assignment]] = []
    for row in rows:
        if row.get("kind") != "fact":
            continue
        draft.append((row, _one(row, human, ignored, absent, glossary)))
    _one_primary(draft)
    total = sum((abs_by_row or {}).values()) or 0
    assigned = {}
    for row, item in draft:
        importance = item.importance
        if item.status == "unknown" and total:
            share = (abs_by_row or {}).get(row["row_key"], 0) / total
            importance = "material" if share >= MATERIAL_SHARE else "peripheral"
        assigned[row["binding_key"]] = Assignment(
            item.concept, item.status, item.source, item.is_primary, item.matched_label, importance,
        )
    return assigned


def _one(row, human, ignored, absent, glossary: GlossaryPackage) -> Assignment:
    key = row["binding_key"]
    if key in ignored:
        return Assignment(None, "ignored", "confirmed", False, None, "normal")
    if key in human:
        concept = human[key]
        if concept in absent:
            return Assignment(concept, "unknown", "confirmed", False, None, "normal")
        return Assignment(concept, "bound", "confirmed", True, None, "normal")
    if row.get("excluded"):
        return Assignment(None, "not_applicable", "inferred", False, None, "normal")
    hit = glossary.resolve(str(row.get("label") or ""))
    if hit is None:
        return Assignment(None, "unknown", "inferred", False, None, "peripheral")
    concept = glossary.concepts[hit.concept]
    label = normalize_label(str(row.get("label") or ""))
    if concept.unit == "money" and "%" in str(row.get("label") or ""):
        return Assignment(None, "unknown", "inferred", False, None, "peripheral")
    if any(normalize_label(item) in label for item in concept.negative):
        return Assignment(None, "unknown", "inferred", False, None, "peripheral")
    warning = concept.expected_sign and row.get("sign") and row.get("sign") != concept.expected_sign
    status = "bound_with_warning" if warning else "bound"
    return Assignment(hit.concept, status, "inferred", True, hit.text, "normal")


def _one_primary(draft: list[tuple[dict, Assignment]]) -> None:
    owners: dict[str, list[int]] = {}
    for index, (_row, item) in enumerate(draft):
        if item.is_primary and item.concept and item.status in {"bound", "bound_with_warning"}:
            owners.setdefault(item.concept, []).append(index)
    for indexes in owners.values():
        if len(indexes) < 2:
            continue
        confirmed = [index for index in indexes if draft[index][1].source == "confirmed"]
        if len(confirmed) == 1:
            for index in indexes:
                if index in confirmed:
                    continue
                row, item = draft[index]
                draft[index] = (
                    row,
                    Assignment(item.concept, item.status, item.source, False, item.matched_label, item.importance),
                )
            continue
        drop = confirmed or indexes
        for index in drop:
            row, item = draft[index]
            draft[index] = (
                row,
                Assignment(item.concept, "ambiguous", item.source, False, item.matched_label, item.importance),
            )


def _decisions(events: list[dict]) -> tuple[dict[str, str], set[str], set[str]]:
    from finance_analysis.domain.state import fold

    human: dict[str, str] = {}
    ignored: set[str] = set()
    absent: set[str] = set()
    for _target, event in fold(events).items():
        kind = event.get("type")
        binding = str(event.get("binding_key") or _target)
        value = event.get("value")
        if kind in _HUMAN and isinstance(value, str) and binding != "book":
            human[binding] = value
        elif kind == "concept.ignored":
            ignored.add(binding)
        elif kind == "concept.absent" and isinstance(value, str):
            absent.add(value)
    return human, ignored, absent
