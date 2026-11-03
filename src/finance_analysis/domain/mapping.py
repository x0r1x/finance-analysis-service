"""Привязка строки к понятию: правила, признаки моделей, калибровка и NIL (§5.5, §5.6, §5.10.1)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal

from finance_analysis.domain.calibration import (
    Calibrator,
    Thresholds,
    heuristic_probability,
)
from finance_analysis.domain.candidates import Candidate, RowEvidence
from finance_analysis.domain.glossary import GlossaryPackage, label_scan, label_surface

MATERIAL_SHARE = 0.05
_NOT_MONEY = frozenset({"%", "percent", "rate", "ratio", "x", "count", "years", "date"})
_MONEY = frozenset({"money", "price"})
MODEL_LABEL = "model:"
AGREE_SHARE = Decimal("0.8")
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

    unit = str(row.get("unit_decision") or row.get("unit") or "").lower()
    if concept.unit == "money" and ("%" in label or unit in _NOT_MONEY):
        return False
    if concept.unit == "ratio" and unit in _MONEY:
        return False
    scanned = label_scan(label)
    return not any(label_scan(item) in scanned for item in concept.negative)


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
    # Модельная привязка тоже попадает в индекс меток: при правке понятия её найдёт glossary.remap.
    matched = f"{MODEL_LABEL}{top.concept}"
    evidence["label"] = {"id": matched, "kind": "model", "text": None}
    return Assignment(top.concept, status, "inferred", True, matched, "normal", top_p, evidence)


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
    found = lexical_hit(row, glossary)
    if found is None:
        return Assignment(None, "unknown", "inferred", False, None, "peripheral")
    hit, strength = found
    concept = glossary.concepts[hit.concept]
    warning = concept.expected_sign and row.get("sign") and row.get("sign") != concept.expected_sign
    status = "bound_with_warning" if warning else "bound"
    evidence = {
        "label": {"id": label_id(hit.concept, hit.kind, hit.text), "kind": hit.kind, "text": hit.text},
        "match_strength": strength,
    }
    return Assignment(hit.concept, status, "inferred", True, hit.text, "normal", None, evidence)


def lexical_hit(row: dict, glossary: GlossaryPackage):
    """Стадия 1: точная метка глоссария, если её не отсеяли % и отрицательные метки."""

    label = str(row.get("label") or "")
    found = glossary.resolve_match(label)
    if found is None:
        return None
    hit, _strength = found
    # Та же стадия 4, что у модельных кандидатов: единица (unit.set приоритетнее), % и negative.
    if not structure_pass(row, glossary.concepts[hit.concept], label=label):
        return None
    return found


def label_id(concept: str, kind: str, text: str) -> str:
    """Идентификатор метки для провенанса (§5.11.3): понятие, вид, исходный текст."""

    return f"{concept}/{kind}/{label_surface(text)}"


def _one_primary(draft: list[tuple[dict, Assignment]]) -> None:
    owners: dict[str, list[int]] = {}
    for index, (_row, item) in enumerate(draft):
        if item.is_primary and item.concept and item.status in {"bound", "bound_with_warning"}:
            owners.setdefault(item.concept, []).append(index)
    for indexes in list(owners.values()):
        if len(indexes) < 2:
            continue
        # Аббревиатура в скобке не спорит с телом той же метки (§5.5).
        weak = [index for index in indexes if _abbrev_only(draft[index][1])]
        strong = [index for index in indexes if index not in weak]
        if strong and weak:
            for index in weak:
                row, item = draft[index]
                draft[index] = (row, _abbrev_aside(item))
            indexes = strong
        if len(indexes) < 2:
            continue
        confirmed = [index for index in indexes if draft[index][1].source == "confirmed"]
        if not confirmed:
            # Точная метка глоссария сильнее кандидата модели того же понятия.
            lexical = [index for index in indexes if _lexical(draft[index][1])]
            if len(lexical) == 1:
                confirmed = lexical
        if len(confirmed) == 1:
            for index in indexes:
                if index in confirmed:
                    continue
                row, item = draft[index]
                if _lexical(item) or item.source == "confirmed":
                    draft[index] = (row, replace(item, is_primary=False))
                else:
                    draft[index] = (row, replace(item, status="ambiguous", is_primary=False))
            continue
        drop = confirmed or indexes
        for index in drop:
            row, item = draft[index]
            draft[index] = (row, replace(item, status="ambiguous", is_primary=False))


def _lexical(item: Assignment) -> bool:
    return bool(item.matched_label) and not str(item.matched_label).startswith(MODEL_LABEL)


def _abbrev_only(item: Assignment) -> bool:
    return item.evidence.get("match_strength") == "abbrev" and item.source != "confirmed"


def _abbrev_aside(item: Assignment) -> Assignment:
    """Слабая строка не bound и не ambiguous: остаётся кандидатом вопроса с пометкой."""

    evidence = {
        **item.evidence,
        "match_strength": "abbrev",
        "candidates": [
            {
                "concept": item.concept,
                "reasons": ["abbrev"],
                "match_strength": "abbrev",
                "structure_pass": True,
            }
        ],
    }
    return replace(item, concept=None, status="unknown", is_primary=False, matched_label=None, evidence=evidence)


def verify_numeric(
    assigned: dict[str, Assignment],
    rows: list[dict],
    values: dict[str, dict[tuple[str, str], Decimal]],
) -> dict[str, Assignment]:
    """Стадия 6: арифметика книги сошлась → source verified (§5.5).

    cfads / |debt_service| ≈ dscr и |debt_service| ≈ |interest| + |principal| по ≥ 80 % периодов
    с ненулевым обслуживанием долга. Меняется только source у inferred-привязок; статус и понятие — нет.
    """

    row_of = {row["binding_key"]: row["row_key"] for row in rows}
    primary: dict[str, list[str]] = {}
    for key, item in assigned.items():
        if item.is_primary and item.concept and item.status in {"bound", "bound_with_warning"}:
            primary.setdefault(item.concept, []).append(key)
    one = {concept: keys[0] for concept, keys in primary.items() if len(keys) == 1}

    def series(concept: str) -> dict[tuple[str, str], Decimal]:
        return values.get(row_of.get(one.get(concept, ""), ""), {})

    checks: list[tuple[str, tuple[str, ...]]] = []
    if {"cfads", "debt_service", "dscr"} <= set(one):
        cash, service, ratio = series("cfads"), series("debt_service"), series("dscr")
        pairs = [(cash[p] / abs(service[p]), abs(ratio[p])) for p in service if service[p] != 0 and p in cash and p in ratio]
        if _agree(pairs):
            checks.append(("dscr_identity", ("cfads", "debt_service")))
    if {"debt_service", "interest", "principal"} <= set(one):
        service, interest, principal = series("debt_service"), series("interest"), series("principal")
        pairs = [
            (abs(service[p]), abs(interest[p]) + abs(principal[p]))
            for p in service
            if service[p] != 0 and p in interest and p in principal
        ]
        if _agree(pairs):
            checks.append(("ds_composition", ("debt_service", "interest", "principal")))
    out = dict(assigned)
    for reason, concepts in checks:
        for concept in concepts:
            key = one[concept]
            item = out[key]
            if item.source not in {"inferred", "verified"}:
                continue
            evidence = {**item.evidence, "verified": sorted({*item.evidence.get("verified", []), reason})}
            out[key] = replace(item, source="verified", evidence=evidence)
    return out


def _agree(pairs: list[tuple[Decimal, Decimal]]) -> bool:
    if len(pairs) < 2:
        return False
    hits = sum(1 for left, right in pairs if abs(left - right) <= max(Decimal("0.005"), abs(right) * Decimal("0.005")))
    return Decimal(hits) / Decimal(len(pairs)) >= AGREE_SHARE


def absent_in_journal(events: list[dict]) -> frozenset[str]:
    """Понятия с действующей записью `concept.absent` в журнале книги (§5.10.5)."""

    return frozenset(_decisions(events)[2])


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
