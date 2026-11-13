"""Привязка строки к понятию: правила, признаки моделей, калибровка и NIL (§5.5, §5.6, §5.10.1)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from decimal import Decimal

from finance_analysis.domain.calibration import (
    Calibrator,
    Thresholds,
    heuristic_probability,
)
from finance_analysis.domain.candidates import Candidate, RowEvidence
from finance_analysis.domain.components import component_records, scenario_of
from finance_analysis.domain.glossary import (
    GlossaryPackage,
    generic_case_label,
    label_scan,
    label_surface,
    stated_price_terms,
)
from finance_analysis.domain.model_type import sheet_name_key
from finance_analysis.domain.period_basis import (
    apply_block_titles,
    classify_period_basis,
    covered_months,
    grain_span,
)
from finance_analysis.domain.references import blank_series, link_target, values_match

MATERIAL_SHARE = 0.05
_NOT_MONEY = frozenset({"%", "percent", "rate", "ratio", "x", "count", "years", "date"})
_MONEY = frozenset({"money", "price"})
MODEL_LABEL = "model:"
AGREE_SHARE = Decimal("0.8")
_HUMAN = frozenset({"concept.set", "concept.confirmed"})
# Явная форма кода пояснений. Голое число соседней ячейки кодом не является.
_MARKED_LINE_CODE = re.compile(r"(?i)^ф\.\s*5\s*\(\s*740\s*\)$")


def marked_line_code(value: object) -> str | None:
    """Код строки только в форме «Ф. 5 (740)». Иначе код для сопоставления не определён."""

    if not isinstance(value, str):
        return None
    if not _MARKED_LINE_CODE.match(value.strip()):
        return None
    return "ф.5 (740)"


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
    calendar: dict | None = None,
    facts: list[dict] | None = None,
) -> dict[str, Assignment]:
    apply_block_titles(rows)
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
    _mark_references(draft, links, periods, roles)
    _mark_facets(draft, links)
    _mark_basis(draft, periods, calendar, links, facts)
    _one_primary(draft, roles, periods, filtered, calendar)
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
    if concept.sign_conflict(row.get("sign")):
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
    shared = _ambiguous_label(row, glossary)
    if shared is not None:
        return shared
    found = lexical_hit(row, glossary)
    if found is None:
        return Assignment(None, "unknown", "inferred", False, None, "peripheral")
    hit, strength = found
    concept = glossary.concepts[hit.concept]
    warning = concept.sign_conflict(row.get("sign"))
    status = "bound_with_warning" if warning else "bound"
    evidence = {
        "label": {"id": label_id(hit.concept, hit.kind, hit.text), "kind": hit.kind, "text": hit.text},
        "match_strength": strength,
    }
    code = marked_line_code(row.get("line_code"))
    if code:
        evidence["line_code"] = code
    if strength == "section_heading":
        evidence["match_provenance"] = "section_heading"
        evidence["section_heading"] = _nearest_heading(row)
    terms, source = _price_terms(row, strength)
    if terms and source:
        evidence["price_terms"] = terms
        evidence["price_terms_source"] = source
    return Assignment(hit.concept, status, "inferred", True, hit.text, "normal", None, evidence)


def _ambiguous_label(row: dict, glossary: GlossaryPackage) -> Assignment | None:
    """Метка нескольких понятий не выбирает одно. Кандидаты остаются в evidence."""

    label = str(row.get("label") or "")
    hits = glossary.ambiguous_hits(label)
    if len(hits) < 2:
        return None
    candidates = []
    for hit in hits:
        concept = glossary.concepts.get(hit.concept)
        if concept is None:
            continue
        candidates.append(
            {
                "concept": hit.concept,
                "reasons": ["ambiguous_label"],
                "structure_pass": structure_pass(row, concept, label=label),
                "lexical": True,
                "match_strength": "exact",
                "text": hit.text,
                "kind": hit.kind,
            }
        )
    if len(candidates) < 2:
        return None
    evidence = {"candidates": candidates, "match_strength": "ambiguous"}
    if not any(item["structure_pass"] for item in candidates):
        return Assignment(None, "unknown", "inferred", False, None, "peripheral", None, {**evidence, "nil": "structure_filtered"})
    return Assignment(None, "ambiguous", "inferred", False, None, "normal", None, evidence)


def lexical_hit(row: dict, glossary: GlossaryPackage):
    """Стадия 1: точная метка глоссария, если её не отсеяли % и отрицательные метки.

    Своя метка важнее заголовка. Заголовок смотрится, только когда метка сама
    не разобрана. Метка нескольких понятий заголовком не выбирается.
    """

    label = str(row.get("label") or "")
    found = glossary.resolve_match(label)
    if found is not None:
        hit, _strength = found
        # Та же стадия 4, что у модельных кандидатов: единица (unit.set приоритетнее), % и negative.
        if not structure_pass(row, glossary.concepts[hit.concept], label=label):
            return None
        return found
    code = marked_line_code(row.get("line_code"))
    if code and code != label:
        coded = glossary.resolve_match(code)
        if coded is not None:
            hit, _strength = coded
            if structure_pass(row, glossary.concepts[hit.concept], label=label):
                return coded
    return _heading_hit(row, glossary, label)


def _heading_hit(row: dict, glossary: GlossaryPackage, label: str):
    """Одно понятие ближайшего заголовка, если метка строки — общий кейс.

    Ближайший заголовок — последняя часть пути, иначе родитель. Предок дальше
    не читается. Заголовок должен дать ровно одно понятие точным совпадением.
    Аббревиатура и метка нескольких понятий строку не привязывают.
    """

    if len(glossary.ambiguous_hits(label)) >= 2 or not generic_case_label(label):
        return None
    heading = _nearest_heading(row)
    if not heading or glossary.ambiguous_hits(heading):
        return None
    found = glossary.resolve_match(heading)
    if found is None:
        return None
    hit, strength = found
    if strength != "exact":
        return None
    if not structure_pass(row, glossary.concepts[hit.concept], label=label):
        return None
    return hit, "section_heading"


def _nearest_heading(row: dict) -> str | None:
    """Последняя часть пути метки. Без пути — родитель. Дальше предки не идут."""

    path = _label_path(row)
    if path:
        text = path[-1].strip()
        return text or None
    parent = row.get("parent_label")
    if isinstance(parent, str) and parent.strip():
        return parent.strip()
    return None


def _price_terms(row: dict, strength: str) -> tuple[str | None, str | None]:
    """Основа цены строки. Своя метка сильнее заголовка, который дал понятие."""

    own = stated_price_terms(str(row.get("label") or ""))
    if own:
        return own, "label"
    if strength != "section_heading":
        return None, None
    via = stated_price_terms(_nearest_heading(row) or "")
    if via:
        return via, "section_heading"
    return None, None


def _terms_key(item: Assignment) -> str | None:
    terms = item.evidence.get("price_terms")
    if terms in {"real", "nominal"}:
        return str(terms)
    return None


def _via_heading(item: Assignment) -> bool:
    return item.evidence.get("match_provenance") == "section_heading"


def label_id(concept: str, kind: str, text: str) -> str:
    """Идентификатор метки для провенанса (§5.11.3): понятие, вид, исходный текст."""

    return f"{concept}/{kind}/{label_surface(text)}"


def _one_primary(
    draft: list[tuple[dict, Assignment]],
    roles: SheetRoles | None = None,
    periods: dict | None = None,
    filtered: dict[str, list[dict]] | None = None,
    calendar: dict | None = None,
) -> None:
    owners: dict[tuple[str, str | None], list[int]] = {}
    for index, (_row, item) in enumerate(draft):
        if item.is_primary and item.concept and item.status in {"bound", "bound_with_warning"}:
            # Разная основа цены — не одна величина. Пул основной строки у каждой свой.
            owners.setdefault((item.concept, _terms_key(item)), []).append(index)
    for indexes in list(owners.values()):
        headed = [index for index in indexes if _via_heading(draft[index][1])]
        labeled = [index for index in indexes if index not in headed]
        if labeled and headed:
            for index in headed:
                row, item = draft[index]
                draft[index] = (row, _drop_primary(item))
            indexes = labeled
        # Аббревиатура в скобке не спорит с телом той же метки (§5.5).
        # Её снимаем до частей и сценария, чтобы слабое совпадение не стало bound.
        if len(indexes) >= 2:
            weak = [index for index in indexes if _abbrev_only(draft[index][1])]
            strong = [index for index in indexes if index not in weak]
            if strong and weak:
                for index in weak:
                    row, item = draft[index]
                    draft[index] = (row, _abbrev_aside(item))
                indexes = strong
        indexes = _without_parts(draft, indexes)
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
                draft[index] = (row, _drop_primary(item, ambiguous=not _lexical(item) and item.source != "confirmed"))
            continue
        exact = [index for index in indexes if _exact_lexical(draft[index][1])]
        if len(exact) >= 2:
            for index in indexes:
                if index in exact:
                    continue
                row, item = draft[index]
                draft[index] = (row, _drop_primary(item, ambiguous=True))
            marks = {
                str(draft[index][0].get("row_key")): {
                    "role": draft[index][1].evidence.get("role"),
                    "zero": periods is not None and blank_series(periods.get(str(draft[index][0].get("row_key")))),
                }
                for index in exact
            }
            winner, reason, tie, left = _cascade(
                [draft[index][0] for index in exact], roles, periods, marks, calendar
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
                draft[index] = (row, _drop_primary(item))
            _tie(draft, kept, tie)
            continue
        drop = confirmed or indexes
        for index in drop:
            row, item = draft[index]
            draft[index] = (row, _drop_primary(item, ambiguous=True))
    _release_split_terms(draft)


def _release_split_terms(draft: list[tuple[dict, Assignment]]) -> None:
    """Две основы одного понятия не выбирают одну основную строку и не становятся ничьей.

    `draft` — пары строки и привязки. Если у понятия две основные строки с разной
    `price_terms`, обе остаются `bound`, но ни одна не основная. Выбор реальной
    цены вместо номинальной здесь не делается. В `evidence` пишется
    `selection: price_terms`. Строки одной основы этот шаг не трогает.
    """

    primaries: dict[str, list[int]] = {}
    for index, (_row, item) in enumerate(draft):
        if item.is_primary and item.concept and item.status in {"bound", "bound_with_warning"}:
            primaries.setdefault(item.concept, []).append(index)
    for indexes in primaries.values():
        if len(indexes) < 2:
            continue
        terms = {_terms_key(draft[index][1]) for index in indexes}
        if len(terms) < 2:
            continue
        for index in indexes:
            row, item = draft[index]
            draft[index] = (
                row,
                replace(item, is_primary=False, evidence={**item.evidence, "selection": "price_terms"}),
            )


def _drop_primary(item: Assignment, *, ambiguous: bool = False) -> Assignment:
    """Снимает признак основной строки у кандидата, которого человек не подтвердил.

    `item` — привязка строки. Если источник равен `confirmed`, метод возвращает
    ту же привязку: пересчёт не снимает `is_primary`. Иначе признак снимается.
    При `ambiguous` статус становится `ambiguous`. Метод ничего не записывает.
    """

    if item.source == "confirmed":
        return item
    if ambiguous:
        return replace(item, status="ambiguous", is_primary=False)
    return replace(item, is_primary=False)


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


def _mark_references(draft, links, periods, roles: SheetRoles | None) -> None:
    """Помечает строки, которые только повторяют другую строку того же понятия.

    Сначала берётся формула: одна ссылка на ячейку, в том числе на другой
    лист, и та же ссылка с умножением или делением на 1, 1000 или 1 000 000.
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
        key = row.get("row_key")
        if not key:
            continue
        target = link_target(row, grouped.get(str(key)), cells)
        if target:
            targets[str(key)] = target
    groups: dict[str, list] = {}
    for row, item in draft:
        if item.concept and item.is_primary and item.status in {"bound", "bound_with_warning"}:
            groups.setdefault(item.concept, []).append(row)
    for rows in groups.values():
        for row in rows:
            key = row.get("row_key")
            if not key:
                continue
            key = str(key)
            if key in targets or row.get("formula") or row.get("has_formula"):
                continue
            target = _copy_target(row, rows, periods, targets, roles)
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


def _mark_facets(draft, links) -> None:
    """Ставит роль component и сценарий до выбора основной строки.

    `draft` — пары строки и привязки. `links` — рёбра графа формул. Часть
    итога того же понятия теряет право быть единственным фактом: в `evidence`
    пишутся `role`, `member`, `component_of` и, если это доказала формула,
    `total_row`. Сценарий `alt` или `base` пишется каждой строке с понятием.
    Статус здесь не меняется.
    """

    concepts: dict[str, str] = {}
    skip: set[str] = set()
    for row, item in draft:
        key = str(row.get("row_key") or "")
        if not key:
            continue
        if item.evidence.get("role") == "reference" or _abbrev_only(item):
            skip.add(key)
            continue
        if item.concept and item.status in {"bound", "bound_with_warning", "ambiguous"}:
            concepts[key] = item.concept
    records = component_records(
        [row for row, _item in draft],
        concepts,
        links,
        skip=skip,
    )
    for index, (row, item) in enumerate(draft):
        evidence = dict(item.evidence)
        scenario = scenario_of(row)
        if item.concept or scenario == "alt":
            evidence["scenario"] = scenario
        extra = records.get(str(row.get("row_key") or ""))
        if extra and evidence.get("role") != "reference":
            evidence.update(extra)
        if evidence != item.evidence:
            draft[index] = (row, replace(item, evidence=evidence))


def _without_parts(draft, indexes: list[int]) -> list[int]:
    """Убирает части итога и сценарий alt из пула основной строки.

    `indexes` — кандидаты одного понятия, которые сейчас основные.
    Строка с ролью `component` или со сценарием `alt` теряет `is_primary`.
    Подтверждённая строка остаётся. Если подтверждена часть и итог того же
    понятия найден, в `evidence` добавляется предупреждение
    `component_over_total`. Статус не меняется. Если после отсечения осталась
    одна неподтверждённая строка, причина пишется в `selection`.
    """

    if not indexes:
        return indexes
    concept = draft[indexes[0]][1].concept
    total = _has_total(draft, concept)
    dropped_component = False
    dropped_scenario = False
    # Единственная квартальная часть остаётся в пуле, если итоги — только ytd.
    # Иначе каскад не видит period и оставляет нарастающий итог.
    rescue = _period_component(draft, indexes)
    kept: list[int] = []
    for index in indexes:
        row, item = draft[index]
        part = item.evidence.get("role") == "component"
        alt = item.evidence.get("scenario") == "alt"
        if index in rescue:
            kept.append(index)
            continue
        if not part and not alt:
            kept.append(index)
            continue
        if item.source == "confirmed":
            if part and total:
                warnings = [code for code in item.evidence.get("warnings") or [] if code != "component_over_total"]
                warnings.append("component_over_total")
                draft[index] = (row, replace(item, evidence={**item.evidence, "warnings": warnings}))
            kept.append(index)
            continue
        dropped_component = dropped_component or part
        dropped_scenario = dropped_scenario or alt
        draft[index] = (row, _drop_primary(item))
    if len(kept) == 1 and (dropped_component or dropped_scenario):
        row, item = draft[kept[0]]
        if item.source != "confirmed" and "selection" not in item.evidence:
            reason = "component" if dropped_component else "scenario"
            draft[kept[0]] = (row, replace(item, evidence={**item.evidence, "selection": reason}))
    return kept


def _period_component(draft, indexes: list[int]) -> set[int]:
    """Одна часть со способом `period`, если итог рядом только нарастающий.

    `draft` — пары строки и привязки. `indexes` — кандидаты одного понятия.
    Часть возвращается в пул, только когда она одна несёт способ `period`,
    а остальные итоги — `ytd`. Подтверждённый итог со способом `period` часть
    не возвращает. Пустой ответ оставляет прежнее отсечение частей.
    """

    def basis(index: int) -> str:
        return str(draft[index][0].get("period_basis") or "")

    def role(index: int) -> str:
        return str(draft[index][1].evidence.get("role") or "")

    parts = [index for index in indexes if role(index) == "component" and basis(index) == "period"]
    period_total = [
        index
        for index in indexes
        if role(index) not in {"component", "reference"} and basis(index) == "period"
    ]
    if len(parts) == 1 and not period_total:
        return {parts[0]}
    return set()


def _has_total(draft, concept: str | None) -> bool:
    """Есть ли у понятия итог, который не является частью или ссылкой."""

    if not concept:
        return False
    for _row, item in draft:
        if item.concept != concept or item.status not in {"bound", "bound_with_warning"}:
            continue
        if item.evidence.get("role") in {"component", "reference"}:
            continue
        return True
    return False


def _copy_target(row, rows, periods, targets: dict[str, str], roles: SheetRoles | None) -> str | None:
    """Возвращает источник вставленной копии или `None`.

    `row` — строка без формулы. `rows` — другие кандидаты того же понятия.
    `periods` — значения по периодам. Копией считается только ряд, чьи периоды
    строго входят в периоды другого ряда и чья роль листа не лучше роли
    источника. Строка формы поэтому не прячется за более длинным листом без
    роли. Более длинный ряд остаётся итогом. Одинаковый набор периодов копией
    не считается.
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
        if set(own) < set(source) and not _better_sheet(row, other, roles):
            found.append(other_key)
    if not found:
        return None
    plain = [key for key in found if key not in targets]
    chosen = min(plain or found)
    followed = targets.get(chosen)
    if followed and followed != own_key:
        return followed
    return chosen


def _better_sheet(copy: dict, source: dict, roles: SheetRoles | None) -> bool:
    """Строка-копия лежит на листе, который каскад предпочитает листу источника.

    `copy` и `source` — строки книги. `roles` — роли листов. Метод возвращает
    истину, если у копии роль лучше: форма лучше листа без роли, а лист без
    роли лучше допущений. Без ролей метод возвращает ложь.
    """

    if roles is None:
        return False
    return _ROLE_RANK[_sheet_role(copy, roles)] < _ROLE_RANK[_sheet_role(source, roles)]


def _cascade(
    rows: list[dict],
    roles: SheetRoles | None,
    periods: dict | None,
    marks: dict | None = None,
    calendar: dict | None = None,
):
    """Оставшиеся строки, причина единственного победителя и причины ничьей.

    Сначала снимается нулевая строка, но только если остаётся другой ненулевой
    итог. Единственный нулевой итог и нулевая строка рядом с одной ссылкой
    остаются. Затем снимаются ссылки `reference`, если осталась строка, которая
    не является ссылкой. Дальше идут роль листа, формула и итог. Способ показа
    снимает `ytd`, если рядом есть `period` или `unknown`. Затем покрытие
    сравнивает месяцы у строк одного зерна.
    """

    current = list(rows)
    tie: list[str] = []
    steps = (
        ("zero", lambda items: _by_zero(items, marks)),
        ("reference", lambda items: _by_reference(items, marks)),
        ("sheet_role", lambda items: _by_role(items, roles)),
        ("formula", lambda items: _by_formula(items, roles)),
        ("aggregate", lambda items: _by_aggregate(items)),
        ("period_basis", lambda items: _by_basis(items)),
        ("period_coverage", lambda items: _by_period(items, periods, calendar)),
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
    """Оставляет нулевую строку, если другого ненулевого итога нет.

    `rows` — кандидаты одного понятия. `marks` хранит `zero` и `role`.
    Строка-ссылка не заменяет итог. Метод возвращает оставшиеся строки и
    признак, что шаг применился. Если ненулевого итога нет, состав не меняется.
    """

    if not marks:
        return rows, False

    def mark(row: dict) -> dict:
        return marks.get(str(row.get("row_key"))) or {}

    base = [row for row in rows if mark(row).get("role") != "reference" and not mark(row).get("zero")]
    if not base:
        return rows, False
    alive = [row for row in rows if not mark(row).get("zero")]
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


def _by_basis(rows: list[dict]):
    """Снимает `ytd`, если рядом есть строка `period` или `unknown`.

    Строка `ltm` этим шагом не снимается. Без `ytd` или без более сильного
    способа показа состав кандидатов не меняется.
    """

    def basis(row: dict) -> str:
        return str(row.get("period_basis") or "unknown")

    if not any(basis(row) == "ytd" for row in rows):
        return rows, False
    if not any(basis(row) in {"period", "unknown"} for row in rows):
        return rows, False
    kept = [row for row in rows if basis(row) != "ytd"]
    return kept, len(kept) < len(rows)


def _by_period(rows: list[dict], periods: dict | None, calendar: dict | None = None):
    """Сравнивает число покрытых месяцев у строк одного зерна.

    Ось в сравнении не участвует: квартальные строки разных осей сравниваются.
    Восемь кварталов и шесть лет не сравниваются. Разница меньше одного периода
    этого зерна победителя не даёт. Совпадение значений шаг не читает, поэтому
    оно само по себе ничью не создаёт.
    """

    if not periods or not calendar:
        return rows, False
    scored = []
    for row in rows:
        series = periods.get(str(row.get("row_key") or "")) or {}
        grain, months = covered_months(series, calendar)
        scored.append((grain, months, row))
    drop: set[int] = set()
    groups: dict[str, list[tuple[int, dict]]] = {}
    for grain, months, row in scored:
        if grain:
            groups.setdefault(grain, []).append((months, row))
    for grain, items in groups.items():
        if len(items) < 2:
            continue
        span = grain_span(grain)
        if span is None:
            continue
        best = max(months for months, _row in items)
        for months, row in items:
            if best - months >= span:
                drop.add(id(row))
    if not drop:
        return rows, False
    return [row for row in rows if id(row) not in drop], True


def _mark_basis(
    draft,
    periods: dict | None,
    calendar: dict | None,
    links: list[dict] | None,
    facts: list[dict] | None = None,
) -> None:
    """Пишет способ показа в строку и в evidence. Fact-строка без ytd и ltm получает period."""

    for index, (row, item) in enumerate(draft):
        series = (periods or {}).get(str(row.get("row_key") or ""))
        basis, source = classify_period_basis(row, calendar=calendar, links=links, series=series, facts=facts)
        row["period_basis"] = basis
        row["period_basis_source"] = source
        evidence = {**item.evidence, "period_basis": basis, "period_basis_source": source}
        draft[index] = (row, replace(item, evidence=evidence))


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
        draft[index] = (row, _drop_primary(item))


def _tie(draft, indexes, reasons: list[str]) -> None:
    for index in indexes:
        row, item = draft[index]
        if item.source == "confirmed":
            continue
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
