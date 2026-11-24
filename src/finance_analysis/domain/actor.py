"""Кто начал анализ и кто подтвердил входы этого расчёта.

Тип берётся из учётных данных. Тело запроса тип не повышает. Список
служебных субъектов — настройка развёртывания, умолчание `system`.
`user_id`, которого в списке нет, классифицируется как человек, даже
если оператор считает эту учётку служебной.
"""

from __future__ import annotations

from dataclasses import dataclass

from finance_analysis.domain.book import Actor

DEFAULT_SERVICE_SUBJECTS = frozenset({"system"})


@dataclass(frozen=True)
class ActorIdentity:
    actor_type: str
    actor_id: str
    claimed_diverged: bool = False


def classify_actor(
    actor: Actor,
    *,
    claimed_type: str | None = None,
    service_subjects: frozenset[str] | None = None,
) -> ActorIdentity:
    """`human` и `user_id`, когда пользователь не пуст, не `anonymous` и не в списке служб.

    Учётка, которую забыли внести в `FAS_SERVICE_SUBJECTS`, остаётся человеком.
    Иначе `service` и `client_id`. Заявленный тип, если он другой, только помечается.
    """

    subjects = DEFAULT_SERVICE_SUBJECTS if service_subjects is None else service_subjects
    user = actor.user_id.strip() if isinstance(actor.user_id, str) else ""
    if user and user != "anonymous" and user not in subjects:
        kind, ident = "human", user
    else:
        client = actor.client_id.strip() if isinstance(actor.client_id, str) else ""
        kind, ident = "service", client or "anonymous"
    claimed = claimed_type.strip() if isinstance(claimed_type, str) else ""
    return ActorIdentity(kind, ident, bool(claimed) and claimed != kind)


def trace_actor_fields(
    actor: Actor | None,
    bindings,
    state_seq: int | None,
    service_subjects: frozenset[str] | None = None,
    *,
    evidence=None,
) -> dict:
    """Кто начал анализ, и подтверждение только тех привязок, которые вошли в расчёт.

    `user_id` сюда не копируется. Поля пишутся один раз на след, не на ячейку.
    """

    identity = classify_actor(actor or Actor(), service_subjects=service_subjects)
    kind, key, inputs = confirmation_of(evidence, bindings)
    return {
        "actor_type": identity.actor_type,
        "actor_id": identity.actor_id,
        "confirmation_kind": kind,
        "binding_key": key,
        "state_seq": state_seq,
        "inputs": [dict(item) for item in inputs],
    }


def confirmation_of(evidence, bindings) -> tuple[str, str | None, tuple[dict, ...]]:
    """Источник подтверждения берётся у каждого входа этого доказательства.

    У факта без `binding_key` ключ восстанавливается по понятию, только когда
    привязка одна. Иначе вход остаётся в списке как `unresolved` и не пропадает.
    Один разрешённый вход оставляет свой `binding_key`. Несколько входов держат
    общий вид и отдельный источник у каждого.
    """

    from finance_analysis.domain.binding_resolution import declared_concept
    from finance_analysis.domain.metrics import HUMAN_SOURCES

    by_key = {}
    by_concept: dict[str, list[str]] = {}
    for row in bindings or []:
        if not isinstance(row, dict):
            continue
        key = row.get("binding_key")
        if not isinstance(key, str) or not key:
            continue
        by_key[key] = row
        concept = declared_concept(row)
        if concept and row.get("is_primary", True):
            by_concept.setdefault(concept, []).append(key)

    def described(key: str) -> dict:
        source = (by_key.get(key) or {}).get("source")
        if source in HUMAN_SOURCES:
            found = "human_confirmed"
        elif source == "auto_confirmed":
            found = "auto_confirmed"
        else:
            found = "inferred"
        return {"binding_key": key, "source": source, "confirmation_kind": found}

    inputs: list[dict] = []
    seen: set[str] = set()
    unresolved: set[str | None] = set()
    facts = (
        *(getattr(evidence, "fact_uses", ()) or ()),
        *(getattr(evidence, "fact_observations", ()) or ()),
    )
    for fact in facts:
        key = getattr(fact, "binding_key", None)
        if not isinstance(key, str) or not key:
            concept = getattr(fact, "concept", None)
            matches = by_concept.get(concept, []) if isinstance(concept, str) and concept else []
            key = matches[0] if len(matches) == 1 else None
        if isinstance(key, str) and key:
            if key not in seen:
                seen.add(key)
                inputs.append(described(key))
            continue
        concept = getattr(fact, "concept", None)
        marker = concept if isinstance(concept, str) and concept else None
        if marker in unresolved:
            continue
        unresolved.add(marker)
        inputs.append(
            {"binding_key": None, "source": None, "confirmation_kind": "unresolved", "concept": marker}
        )
    if any(item["confirmation_kind"] == "unresolved" for item in inputs):
        return "unresolved", None, tuple(inputs)
    if len(inputs) == 1:
        return inputs[0]["confirmation_kind"], inputs[0]["binding_key"], tuple(inputs)
    kinds = {item["confirmation_kind"] for item in inputs}
    if len(kinds) == 1:
        return inputs[0]["confirmation_kind"], None, tuple(inputs)
    return "inferred", None, tuple(inputs)
