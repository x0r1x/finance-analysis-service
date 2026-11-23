"""Кто подтвердил привязку: человек или служба. Тип берётся из учётных данных.

Тело запроса тип не повышает. Список служебных субъектов — настройка
развёртывания, умолчание `system`.
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
    """`human` и `user_id`, когда пользователь не пуст, не `anonymous` и не служебный.

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
) -> dict:
    """Один набор на след, не на ячейку. `user_id` сюда не копируется."""

    identity = classify_actor(actor or Actor(), service_subjects=service_subjects)
    kind, key = confirmation_of(bindings)
    return {
        "actor_type": identity.actor_type,
        "actor_id": identity.actor_id,
        "confirmation_kind": kind,
        "binding_key": key,
        "state_seq": state_seq,
    }


def confirmation_of(bindings) -> tuple[str, str | None]:
    """Человеческий источник важнее служебного, служебный — важнее вывода."""

    from finance_analysis.domain.metrics import HUMAN_SOURCES

    human_key = None
    auto_key = None
    for row in bindings or []:
        if not isinstance(row, dict):
            continue
        source = row.get("source")
        key = row.get("binding_key")
        if not isinstance(key, str):
            continue
        if source in HUMAN_SOURCES and human_key is None:
            human_key = key
        elif source == "auto_confirmed" and auto_key is None:
            auto_key = key
    if human_key is not None:
        return "human_confirmed", human_key
    if auto_key is not None:
        return "auto_confirmed", auto_key
    return "inferred", None
