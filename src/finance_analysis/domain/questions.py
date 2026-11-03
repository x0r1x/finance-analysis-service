"""Пакет вопросов книги: один вопрос на понятие (§5.10.5). Без ввода-вывода."""

from __future__ import annotations

import json
from collections.abc import Mapping

from finance_analysis.domain.book import question_digest
from finance_analysis.domain.mapping import absent_in_journal
from finance_analysis.domain.metrics import _primaries, absent_concepts
from finance_analysis.domain.model_type import (
    ModelTypeCatalog,
    concept_metrics,
    open_concepts,
)

_HEX = frozenset("0123456789abcdef")
_CONCEPT_EVENTS = frozenset(
    {"concept.set", "concept.confirmed", "concept.rejected", "concept.absent"}
)
_BIND = frozenset({"concept.set", "concept.confirmed"})


def question_id_problem(event_type: str, value, job_id: str, given) -> str | None:
    """None — question_id можно писать. Нет поля — тоже можно."""

    if given is None:
        return None
    if (
        not isinstance(given, str)
        or len(given) != 40
        or any(char not in _HEX for char in given)
    ):
        return "question_id должен быть sha1"
    expected = _expected_question_id(event_type, value, job_id)
    if expected is not None and given != expected:
        return "question_id не совпадает с вопросом"
    return None


def _expected_question_id(event_type: str, value, job_id: str) -> str | None:
    if event_type in _CONCEPT_EVENTS and isinstance(value, str):
        return question_digest("concept", value, job_id)
    if event_type == "model_type.set":
        return question_digest("model_type", "book", job_id)
    return None


def rejected_pairs(events: list[dict]) -> frozenset[tuple[str, str]]:
    """Пары (binding_key, понятие), которые человек отклонил и потом не подтвердил."""

    rejected: set[tuple[str, str]] = set()
    for event in sorted(events, key=lambda item: int(item.get("seq") or 0)):
        kind = event.get("type")
        binding = str(event.get("binding_key") or event.get("target") or "")
        value = event.get("value")
        if not binding or binding == "book" or not isinstance(value, str):
            continue
        if kind == "concept.rejected":
            rejected.add((binding, value))
        elif kind in _BIND:
            rejected.discard((binding, value))
    return frozenset(rejected)


def concept_questions(
    *,
    job_id: str,
    bindings: list[dict],
    rows: list[dict],
    events: list[dict],
    catalog: ModelTypeCatalog,
    labels: tuple[str, ...],
    concepts: Mapping[str, object],
    limit: int,
) -> list[dict]:
    """Открытые вопросы по понятиям. Строка без такого понятия в пакет не входит."""

    absent = frozenset(absent_concepts(bindings, absent_in_journal(events)))
    # Выведенная основная строка после concept.absent не закрывает one_of: ICR её не использует.
    bound = frozenset(_primaries(bindings, absent))
    rejected = rejected_pairs(events)
    by_key = {row["binding_key"]: row for row in rows if row.get("binding_key")}
    questions = []
    for concept in open_concepts(catalog, labels, bound=bound, absent=absent):
        candidates, ambiguous = _candidates(bindings, by_key, concept, rejected, limit)
        questions.append(
            {
                "question_id": question_digest("concept", concept, job_id),
                "kind": "concept",
                "subject": concept,
                "scope": job_id,
                "reason": "ambiguous" if ambiguous else "concept_unknown",
                "needed_by": list(
                    concept_metrics(catalog, labels, concept, bound=bound)
                ),
                "expects": _expects(concepts.get(concept)),
                "status": "open",
                "candidates": candidates,
            }
        )
    return questions


def _expects(spec: object) -> dict:
    kind = getattr(spec, "kind", None)
    unit = getattr(spec, "unit", None)
    return {"measure": unit, "shape": "scalar" if kind == "parameter" else "series"}


def _candidates(
    bindings: list[dict],
    by_key: dict[str, dict],
    concept: str,
    rejected: frozenset[tuple[str, str]],
    limit: int,
) -> tuple[list[dict], bool]:
    found: list[tuple[float, str, dict]] = []
    for row in bindings:
        if (
            row.get("status") not in {"unknown", "ambiguous"}
            or row.get("source") == "confirmed"
        ):
            continue
        key = row.get("binding_key")
        if not isinstance(key, str) or (key, concept) in rejected:
            continue
        hit = _hit(row, _evidence(row.get("evidence_json")), concept)
        if hit is None:
            continue
        score = _score(hit, row)
        dim = by_key.get(key) or {}
        # Строка с этим effective_concept выше слабого кандидата модели: у лексики p нет.
        tier = 1 if row.get("effective_concept") == concept else 0
        found.append(
            (
                tier,
                score,
                key,
                {
                    "binding_key": key,
                    "row_ref": row.get("row_key") or dim.get("row_key") or "",
                    "sheet": dim.get("sheet") or "",
                    "label": _label(row, dim),
                    "score": score,
                    "reasons": list(hit.get("reasons") or []),
                    "_status": row.get("status"),
                },
            )
        )
    found.sort(key=lambda item: (-item[0], -item[1], item[2]))
    ambiguous = any(item[3]["_status"] == "ambiguous" for item in found)
    chosen = found[:limit] if limit > 0 else []
    candidates = []
    for _tier, _score_value, _key, body in chosen:
        body.pop("_status")
        candidates.append(body)
    return candidates, ambiguous


def _hit(row: dict, evidence: dict, concept: str) -> dict | None:
    items = [
        item
        for item in evidence.get("candidates") or []
        if isinstance(item, dict)
        and item.get("concept") == concept
        and item.get("structure_pass", True)
    ]
    if row.get("effective_concept") == concept:
        return items[0] if items else {}
    return items[0] if items else None


def _score(hit: dict, row: dict) -> float:
    raw = hit.get("p", row.get("confidence"))
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return 0.0
    return float(raw)


def _label(row: dict, dim: dict) -> str:
    if dim.get("label"):
        return str(dim["label"])
    text = str(row.get("label_path_text") or "")
    if " › " in text:
        return text.rsplit(" › ", 1)[-1]
    return text


def _evidence(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw:
        return {}
    try:
        found = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return found if isinstance(found, dict) else {}
