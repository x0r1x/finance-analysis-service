"""Привязка строки к понятию: правила, признаки моделей, калибровка и NIL (§5.5, §5.6, §5.10.1)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from finance_analysis.domain.calibration import (
    Calibrator,
    Thresholds,
    heuristic_probability,
)
from finance_analysis.domain.candidates import Candidate, RowEvidence
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
    confidence: float | None = None
    evidence: dict = field(default_factory=dict, compare=False)


# shortcut: scope=profile и прецеденты графа dscr не смотрятся (стадии 0 и 5–6)
def assign_rows(
    rows: list[dict],
    events: list[dict],
    glossary: GlossaryPackage,
    *,
    abs_by_row: dict[str, float] | None = None,
    evidence: dict[str, RowEvidence] | None = None,
    calibrator: Calibrator | None = None,
) -> dict[str, Assignment]:
    human, ignored, absent = _decisions(events)
    draft: list[tuple[dict, Assignment]] = []
    for row in rows:
        if row.get("kind") != "fact":
            continue
        item = _one(row, human, ignored, absent, glossary)
        found = (evidence or {}).get(row["binding_key"])
        if item.source == "inferred" and item.status == "unknown" and found is not None and not row.get("excluded"):
            item = decide(row, found, glossary, calibrator)
        elif found is not None and found.degraded:
            item = replace(item, evidence={**item.evidence, "degraded": list(found.degraded)})
        draft.append((row, item))
    _one_primary(draft)
    total = sum((abs_by_row or {}).values()) or 0
    assigned = {}
    for row, item in draft:
        importance = item.importance
        if item.status == "unknown" and total:
            share = (abs_by_row or {}).get(row["row_key"], 0) / total
            importance = "material" if share >= MATERIAL_SHARE else "peripheral"
        assigned[row["binding_key"]] = replace(item, importance=importance)
    return assigned


def structure_pass(row: dict, concept, *, label: str) -> bool:
    """Стадия 4: единица, отсев %-строк и отрицательных меток понятия."""

    unit = str(row.get("unit") or "").lower()
    if concept.unit == "money" and ("%" in label or unit in {"%", "percent", "rate", "ratio", "x"}):
        return False
    if concept.unit == "ratio" and unit in {"money", "price"}:
        return False
    norm = normalize_label(label)
    return not any(normalize_label(item) in norm for item in concept.negative)


def decide(
    row: dict,
    found: RowEvidence,
    glossary: GlossaryPackage,
    calibrator: Calibrator | None,
) -> Assignment:
    """Стадии 4, 7b и 9: структура, вероятность, NIL. source всегда inferred (§5.5)."""

    thresholds = calibrator.thresholds if calibrator else Thresholds()
    label = str(row.get("label") or "")
    scored: list[tuple[float, Candidate]] = []
    for item in found.candidates:
        concept = glossary.concepts.get(item.concept)
        if concept is None:
            continue
        passed = item.structure_pass and structure_pass(row, concept, label=label)
        candidate = replace(item, structure_pass=passed)
        p = calibrator.probability(candidate) if calibrator else heuristic_probability(candidate)
        scored.append((p, candidate))
    scored.sort(key=lambda pair: (-pair[0], pair[1].concept))
    evidence = {
        **found.as_dict(),
        "candidates": [{**candidate.as_dict(), "p": round(p, 6)} for p, candidate in scored],
        "calibrator_version": calibrator.version if calibrator else "none",
    }
    alive = [(p, candidate) for p, candidate in scored if candidate.structure_pass]
    if not alive:
        reason = "structure_filtered" if scored else "no_candidates"
        return Assignment(None, "unknown", "inferred", False, None, "peripheral", None, {**evidence, "nil": reason})
    top_p, top = alive[0]
    second_p = alive[1][0] if len(alive) > 1 else 0.0
    if found.clm_choice == "none" and (found.clm_none_prob or 0.0) >= thresholds.clm_none:
        return Assignment(None, "unknown", "inferred", False, None, "peripheral", top_p, {**evidence, "nil": "clm_none"})
    nil_p = calibrator.nil_probability(found, top_p) if calibrator else None
    if nil_p is not None:
        if nil_p >= 0.5:
            return Assignment(None, "unknown", "inferred", False, None, "peripheral", top_p, {**evidence, "nil": "classifier", "nil_p": round(nil_p, 6)})
    else:
        nearest = max(found.nearest_concept_cos or 0.0, found.nearest_example_cos or 0.0)
        if top_p < thresholds.tau_nil and nearest < thresholds.delta_nil:
            return Assignment(None, "unknown", "inferred", False, None, "peripheral", top_p, {**evidence, "nil": "threshold"})
    gap = top_p - second_p
    if top_p < thresholds.accept or gap < thresholds.gap:
        return Assignment(top.concept, "ambiguous", "inferred", False, None, "normal", top_p, evidence)
    concept = glossary.concepts[top.concept]
    warnings = []
    if concept.expected_sign and row.get("sign") and row.get("sign") != concept.expected_sign:
        warnings.append("sign")
    if gap < thresholds.weak_gap:
        warnings.append("weak_gap")
    status = "bound_with_warning" if warnings else "bound"
    if warnings:
        evidence["warnings"] = warnings
    return Assignment(top.concept, status, "inferred", True, None, "normal", top_p, evidence)


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
    hit = lexical_hit(row, glossary)
    if hit is None:
        return Assignment(None, "unknown", "inferred", False, None, "peripheral")
    concept = glossary.concepts[hit.concept]
    warning = concept.expected_sign and row.get("sign") and row.get("sign") != concept.expected_sign
    status = "bound_with_warning" if warning else "bound"
    evidence = {"label": {"id": label_id(hit.concept, hit.kind, hit.text), "kind": hit.kind, "text": hit.text}}
    return Assignment(hit.concept, status, "inferred", True, hit.text, "normal", None, evidence)


def lexical_hit(row: dict, glossary: GlossaryPackage):
    """Стадия 1: точная метка глоссария, если её не отсеяли % и отрицательные метки."""

    hit = glossary.resolve(str(row.get("label") or ""))
    if hit is None:
        return None
    concept = glossary.concepts[hit.concept]
    label = normalize_label(str(row.get("label") or ""))
    if concept.unit == "money" and "%" in str(row.get("label") or ""):
        return None
    if any(normalize_label(item) in label for item in concept.negative):
        return None
    return hit


def label_id(concept: str, kind: str, text: str) -> str:
    """Идентификатор метки для провенанса (§5.11.3): понятие, вид, нормализованный текст."""

    return f"{concept}/{kind}/{normalize_label(text)}"


def _one_primary(draft: list[tuple[dict, Assignment]]) -> None:
    owners: dict[str, list[int]] = {}
    for index, (_row, item) in enumerate(draft):
        if item.is_primary and item.concept and item.status in {"bound", "bound_with_warning"}:
            owners.setdefault(item.concept, []).append(index)
    for indexes in owners.values():
        if len(indexes) < 2:
            continue
        confirmed = [index for index in indexes if draft[index][1].source == "confirmed"]
        if not confirmed:
            # Точная метка глоссария сильнее кандидата модели того же понятия.
            lexical = [index for index in indexes if draft[index][1].matched_label]
            if len(lexical) == 1:
                confirmed = lexical
        if len(confirmed) == 1:
            for index in indexes:
                if index in confirmed:
                    continue
                row, item = draft[index]
                if item.matched_label or item.source == "confirmed":
                    draft[index] = (row, replace(item, is_primary=False))
                else:
                    draft[index] = (row, replace(item, status="ambiguous", is_primary=False))
            continue
        drop = confirmed or indexes
        for index in drop:
            row, item = draft[index]
            draft[index] = (row, replace(item, status="ambiguous", is_primary=False))


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
