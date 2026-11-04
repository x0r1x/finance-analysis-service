"""Привязка строки к понятию: правила, признаки моделей, калибровка и NIL (§5.5, §5.6, §5.10.1)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from decimal import Decimal

from finance_analysis.domain.calibration import (
    Calibrator,
    Thresholds,
    heuristic_probability,
)
from finance_analysis.domain.candidates import Candidate, RowEvidence
from finance_analysis.domain.glossary import GlossaryPackage, label_scan, label_surface
from finance_analysis.domain.model_type import sheet_name_key
from finance_analysis.domain.references import blank_series, link_target, values_match

MATERIAL_SHARE = 0.05
_NOT_MONEY = frozenset({"%", "percent", "rate", "ratio", "x", "count", "years", "date"})
_MONEY = frozenset({"money", "price"})
MODEL_LABEL = "model:"
AGREE_SHARE = Decimal("0.8")
_HUMAN = frozenset({"concept.set", "concept.confirmed"})


@dataclass(frozen=True)
class SheetRoles:
    """Роли листа для каскада. Формы приходят из групп corporate.yaml, не копируются."""

    statement: tuple[str, ...]
    outputs: tuple[str, ...]
    assumptions: tuple[str, ...]


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
    roles: SheetRoles | None = None,
    periods: dict[str, dict[tuple[str, str], Decimal]] | None = None,
    links: list[dict] | None = None,
) -> dict[str, Assignment]:
    human, ignored, absent = _decisions(events)
    draft: list[tuple[dict, Assignment]] = []
    filtered: dict[str, list[dict]] = {}
    for row in rows:
        if row.get("kind") != "fact":
            continue
        item = _one(row, human, ignored, absent, glossary)
        missed = _statement_filtered(row, glossary, roles)
        if missed:
            filtered.setdefault(missed, []).append(row)
        found = (evidence or {}).get(row["binding_key"])
        if item.source == "inferred" and item.status == "unknown" and found is not None and not row.get("excluded"):
            item = decide(row, found, glossary, calibrator)
        elif found is not None and found.degraded:
            item = replace(item, evidence={**item.evidence, "degraded": list(found.degraded)})
        draft.append((row, item))
    _mark_references(draft, links, periods)
    _one_primary(draft, roles, periods, filtered)
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


def _one_primary(
    draft: list[tuple[dict, Assignment]],
    roles: SheetRoles | None = None,
    periods: dict | None = None,
    filtered: dict[str, list[dict]] | None = None,
) -> None:
    owners: dict[str, list[int]] = {}
    for index, (_row, item) in enumerate(draft):
        if item.is_primary and item.concept and item.status in {"bound", "bound_with_warning"}:
            owners.setdefault(item.concept, []).append(index)
    for indexes in list(owners.values()):
        if len(indexes) < 2:
            _veto_assumptions(draft, indexes, roles, filtered or {})
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
            _veto_assumptions(draft, indexes, roles, filtered or {})
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
        exact = [index for index in indexes if _exact_lexical(draft[index][1])]
        if len(exact) >= 2:
            for index in indexes:
                if index in exact:
                    continue
                row, item = draft[index]
                draft[index] = (row, replace(item, status="ambiguous", is_primary=False))
            marks = {
                str(draft[index][0].get("row_key")): {
                    "role": draft[index][1].evidence.get("role"),
                    "zero": periods is not None and blank_series(periods.get(str(draft[index][0].get("row_key")))),
                }
                for index in exact
            }
            winner, reason, tie, left = _cascade(
                [draft[index][0] for index in exact], roles, periods, marks
            )
            concept = draft[exact[0]][1].concept
            if winner is not None and _blocked_assumptions(winner, roles, concept, filtered or {}):
                winner, reason, tie = None, None, ["sheet_role"]
            if winner is not None and reason:
                chosen = next(index for index in exact if draft[index][0] is winner)
                _keep(draft, exact, chosen, reason)
                continue
            kept = [index for index in exact if any(draft[index][0] is row for row in left)]
            for index in exact:
                if index in kept:
                    continue
                row, item = draft[index]
                draft[index] = (row, replace(item, is_primary=False))
            _tie(draft, kept, tie)
            continue
        drop = confirmed or indexes
        for index in drop:
            row, item = draft[index]
            draft[index] = (row, replace(item, status="ambiguous", is_primary=False))


def _lexical(item: Assignment) -> bool:
    return bool(item.matched_label) and not str(item.matched_label).startswith(MODEL_LABEL)


def _exact_lexical(item: Assignment) -> bool:
    return _lexical(item) and not _abbrev_only(item)


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


_ROLE_RANK = {"statement": 0, "outputs": 1, "unranked": 2, "assumptions": 3}


def _statement_filtered(row: dict, glossary: GlossaryPackage, roles: SheetRoles | None) -> str | None:
    """Точная метка на листе формы, которую стадия 4 сняла единицей или знаком."""

    if roles is None or row.get("excluded") or _sheet_role(row, roles) != "statement":
        return None
    label = str(row.get("label") or "")
    found = glossary.resolve_match(label)
    if found is None:
        return None
    hit, strength = found
    if strength != "exact":
        return None
    if structure_pass(row, glossary.concepts[hit.concept], label=label):
        return None
    return hit.concept


def _sheet_role(row: dict, roles: SheetRoles) -> str:
    name = str(row.get("sheet") or "")
    if _named(name, roles.statement):
        return "statement"
    if _named(name, roles.outputs):
        return "outputs"
    if _named(name, roles.assumptions):
        return "assumptions"
    return "unranked"


def _named(name: str, aliases: tuple[str, ...]) -> bool:
    folded = sheet_name_key(name)
    return any(folded == sheet_name_key(alias) for alias in aliases)


def _mark_references(draft, links, periods) -> None:
    """Помечает строки, которые только повторяют другую строку того же понятия.

    Сначала берётся формула: одна ссылка на ячейку, в том числе на другой
    лист, и та же ссылка с умножением или делением на степень десяти.
    Затем строка без формулы, чьи периоды строго входят в периоды другого
    кандидата и чьи значения на них совпали. Более длинный ряд остаётся итогом.
    В `evidence` пишутся `role` со значением `reference` и `reference_of` с
    `row_key` источника. Статус строки здесь не меняется.
    """

    cells: dict[tuple[str, int], str] = {}
    for row, _item in draft:
        number = row.get("row_num")
        sheet = row.get("sheet")
        if isinstance(number, int) and not isinstance(number, bool) and sheet and row.get("row_key"):
            cells[(sheet_name_key(str(sheet)), number)] = str(row["row_key"])
    grouped: dict[str, list] = {}
    for link in links or []:
        key = link.get("row_key")
        if key:
            grouped.setdefault(str(key), []).append(link)
    targets: dict[str, str] = {}
    for row, _item in draft:
        target = link_target(row, grouped.get(str(row.get("row_key") or "")), cells)
        if target:
            targets[str(row["row_key"])] = target
    groups: dict[str, list] = {}
    for row, item in draft:
        if item.concept and item.is_primary and item.status in {"bound", "bound_with_warning"}:
            groups.setdefault(item.concept, []).append(row)
    for rows in groups.values():
        for row in rows:
            key = str(row["row_key"])
            if key in targets or row.get("formula") or row.get("has_formula"):
                continue
            target = _copy_target(row, rows, periods, targets)
            if target:
                targets[key] = target
    for index, (row, item) in enumerate(draft):
        target = targets.get(str(row.get("row_key") or ""))
        if not target:
            continue
        draft[index] = (
            row,
            replace(item, evidence={**item.evidence, "role": "reference", "reference_of": target}),
        )


def _copy_target(row, rows, periods, targets: dict[str, str]) -> str | None:
    """Возвращает источник вставленной копии или `None`.

    `row` — строка без формулы. `rows` — другие кандидаты того же понятия.
    `periods` — значения по периодам. Копией считается только ряд, чьи периоды
    строго входят в периоды другого ряда, а значения на них совпали. Более
    длинный ряд остаётся итогом. Одинаковый набор периодов копией не считается.
    """

    if not periods:
        return None
    own_key = str(row["row_key"])
    own = periods.get(own_key) or {}
    if blank_series(own):
        return None
    found = []
    for other in rows:
        other_key = str(other["row_key"])
        if other_key == own_key:
            continue
        source = periods.get(other_key) or {}
        if not values_match(source, own):
            continue
        if set(own) < set(source):
            found.append(other_key)
    if not found:
        return None
    plain = [key for key in found if key not in targets]
    chosen = min(plain or found)
    followed = targets.get(chosen)
    if followed and followed != own_key:
        return followed
    return chosen


def _cascade(rows: list[dict], roles: SheetRoles | None, periods: dict | None, marks: dict | None = None):
    """Оставшиеся строки, причина единственного победителя и причины ничьей.

    Сначала снимаются строки, у которых все значения нулевые или пустые,
    если рядом есть ненулевая строка. Затем снимаются ссылки `reference`,
    если осталась строка, которая не является ссылкой. Ненулевая ссылка
    поэтому побеждает пустую строку, а обычная строка побеждает ссылку.
    Дальше идут прежние шаги: роль листа, формула, итог и покрытие периодов.
    """

    current = list(rows)
    tie: list[str] = []
    steps = (
        ("zero", lambda items: _by_zero(items, marks)),
        ("reference", lambda items: _by_reference(items, marks)),
        ("sheet_role", lambda items: _by_role(items, roles)),
        ("formula", lambda items: _by_formula(items, roles)),
        ("aggregate", lambda items: _by_aggregate(items)),
        ("period_coverage", lambda items: _by_period(items, periods)),
    )
    for name, step in steps:
        nxt, ran = step(current)
        if not ran or len(current) < 2:
            continue
        if len(nxt) < len(current):
            current = nxt
            if len(current) == 1:
                return current[0], name, tie, current
            tie.append(name)
    return None, None, tie, current


def _by_zero(rows: list[dict], marks: dict | None):
    if not marks:
        return rows, False
    alive = [row for row in rows if not (marks.get(str(row.get("row_key"))) or {}).get("zero")]
    if alive and len(alive) < len(rows):
        return alive, True
    return rows, False


def _by_reference(rows: list[dict], marks: dict | None):
    if not marks:
        return rows, False
    plain = [row for row in rows if (marks.get(str(row.get("row_key"))) or {}).get("role") != "reference"]
    if plain and len(plain) < len(rows):
        return plain, True
    return rows, False


def _by_role(rows: list[dict], roles: SheetRoles | None):
    if roles is None:
        return rows, False
    best = min(_ROLE_RANK[_sheet_role(row, roles)] for row in rows)
    kept = []
    for row in rows:
        role = _sheet_role(row, roles)
        # Лист без роли остаётся рядом с формой: список алиасов неполный (CFS не «Cash flow»).
        if _ROLE_RANK[role] == best or (role == "unranked" and best == _ROLE_RANK["statement"]):
            kept.append(row)
    return kept, True


def _by_formula(rows: list[dict], roles: SheetRoles | None):
    if roles is None or not any(_sheet_role(row, roles) == "statement" for row in rows):
        return rows, False
    form = [row for row in rows if _sheet_role(row, roles) == "statement"]
    formulated = [row for row in form if row.get("has_formula")]
    if formulated:
        peers = [row for row in rows if _sheet_role(row, roles) == "unranked"]
        return formulated + peers, True
    return form, True


def _by_aggregate(rows: list[dict]):
    pool = [row for row in rows if row.get("aggregation") == "aggregate" or _is_parent(row, rows)]
    if not pool:
        return rows, False
    best = min(_indent(row) for row in pool)
    return [row for row in pool if _indent(row) == best], True


def _by_period(rows: list[dict], periods: dict | None):
    if not periods:
        return rows, False
    counted = []
    tally: dict[str, int] = {}
    for row in rows:
        series = periods.get(str(row.get("row_key") or "")) or {}
        for axis in {item for item, _period in series}:
            tally[axis] = tally.get(axis, 0) + 1
        counted.append((series, row))
    shared = [axis for axis, count in tally.items() if count >= 2]
    axis = shared[0] if len(shared) == 1 else None
    if axis is None and not shared:
        populated = [series for series, _row in counted if series]
        if len(populated) == 1 and len({item for item, _period in populated[0]}) == 1 and len(populated) < len(counted):
            axis = next(iter(populated[0]))[0]
    if axis is None:
        return rows, False
    counts = [(sum(1 for item_axis, _period in series if item_axis == axis), row) for series, row in counted]
    best = max(count for count, _row in counts)
    if all(best - count < 1 for count, _row in counts):
        return rows, False
    return [row for count, row in counts if best - count < 1], True


def _is_parent(row: dict, rows: list[dict]) -> bool:
    label = sheet_name_key(str(row.get("label") or ""))
    if not label:
        return False
    for other in rows:
        if other is row:
            continue
        if any(sheet_name_key(part) == label for part in _label_path(other)):
            return True
    return False


def _label_path(row: dict) -> tuple[str, ...]:
    raw = row.get("label_path")
    if isinstance(raw, (list, tuple)):
        return tuple(str(part) for part in raw)
    text = row.get("label_path_json")
    if not isinstance(text, str) or not text:
        return ()
    try:
        found = json.loads(text)
    except json.JSONDecodeError:
        return ()
    if not isinstance(found, list):
        return ()
    return tuple(str(part) for part in found)


def _indent(row: dict) -> int:
    value = row.get("indent")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return int(value)


def _blocked_assumptions(row: dict, roles: SheetRoles | None, concept: str | None, filtered: dict) -> bool:
    if roles is None or not concept or concept not in filtered:
        return False
    return _sheet_role(row, roles) == "assumptions"


def _veto_assumptions(draft, indexes, roles, filtered) -> None:
    if len(indexes) != 1:
        return
    index = indexes[0]
    row, item = draft[index]
    if item.source == "confirmed" or not item.is_primary:
        return
    if not _blocked_assumptions(row, roles, item.concept, filtered):
        return
    _tie(draft, [index], ["sheet_role"])


def _keep(draft, indexes, chosen: int, reason: str) -> None:
    for index in indexes:
        row, item = draft[index]
        if index == chosen:
            draft[index] = (row, replace(item, evidence={**item.evidence, "selection": reason}))
            continue
        draft[index] = (row, replace(item, is_primary=False))


def _tie(draft, indexes, reasons: list[str]) -> None:
    for index in indexes:
        row, item = draft[index]
        evidence = item.evidence
        if reasons and item.concept:
            evidence = {
                **item.evidence,
                "candidates": [
                    {
                        "concept": item.concept,
                        "reasons": list(reasons),
                        "structure_pass": True,
                        "match_strength": item.evidence.get("match_strength", "exact"),
                    }
                ],
            }
        draft[index] = (row, replace(item, status="ambiguous", is_primary=False, evidence=evidence))


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
