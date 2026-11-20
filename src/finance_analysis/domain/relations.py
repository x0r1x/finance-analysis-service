"""Реестр типов отношений между понятиями.

Смысловая связь не даёт права подставить одно понятие вместо другого и не
складывается в метрику. Подстановка, агрегация и сверка включаются флагами
типа. Обратное ребро в данные не дописывается: у `related_to` одна сторона
не выводится из другой, `narrower_than` не появляется из `broader_than`.

`composed_of` — состав целого и сверка с тождеством. `calculated_from` —
зависимость формулы, без права считать по ней. `derived_from` — смысловое
происхождение. Формулы остаются в конфигах метрик.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from finance_analysis.domain.dimensions import ROLES

_ANY_ROLE = frozenset(ROLES)
_MEASURE = frozenset({"measure"})


@dataclass(frozen=True)
class RelationType:
    """Один тип отношения. Неактивный тип в данные каталога не принимается."""

    name: str
    title: str
    active: bool
    symmetric: bool
    transitive: bool
    inverse: str | None
    inverse_required: bool
    cycles_allowed: bool
    allows_substitution: bool
    participates_in_aggregation: bool
    participates_in_reconciliation: bool
    source_roles: frozenset[str]
    target_roles: frozenset[str]
    same_dimension: bool
    source_kind: str = "concept"
    target_kind: str = "concept"

    @property
    def direction(self) -> str:
        """`symmetric` читается в обе стороны. `directed` — только как записано."""

        return "symmetric" if self.symmetric else "directed"


def _spec(
    name: str,
    title: str,
    *,
    active: bool = True,
    symmetric: bool = False,
    transitive: bool = False,
    inverse: str | None = None,
    inverse_required: bool = False,
    cycles_allowed: bool = False,
    allows_substitution: bool = False,
    participates_in_aggregation: bool = False,
    participates_in_reconciliation: bool = False,
    source_roles: frozenset[str] = _ANY_ROLE,
    target_roles: frozenset[str] = _ANY_ROLE,
    same_dimension: bool = False,
) -> RelationType:
    return RelationType(
        name=name,
        title=title,
        active=active,
        symmetric=symmetric,
        transitive=transitive,
        inverse=inverse,
        inverse_required=inverse_required,
        cycles_allowed=cycles_allowed,
        allows_substitution=allows_substitution,
        participates_in_aggregation=participates_in_aggregation,
        participates_in_reconciliation=participates_in_reconciliation,
        source_roles=source_roles,
        target_roles=target_roles,
        same_dimension=same_dimension,
    )


RELATION_TYPES: dict[str, RelationType] = {
    spec.name: spec
    for spec in (
        _spec(
            "composed_of",
            "составляется из компонентов",
            participates_in_reconciliation=True,
            source_roles=_MEASURE,
            target_roles=_MEASURE,
            same_dimension=True,
        ),
        _spec(
            "calculated_from",
            "рассчитывается на основе",
        ),
        _spec(
            "derived_from",
            "производное понятие",
        ),
        _spec(
            "broader_than",
            "более широкое понятие",
            transitive=True,
            inverse="narrower_than",
        ),
        _spec(
            "narrower_than",
            "более узкое понятие",
            transitive=True,
            inverse="broader_than",
        ),
        _spec(
            "related_to",
            "общая смысловая связь",
            symmetric=True,
            inverse="related_to",
            cycles_allowed=True,
        ),
        _spec(
            "equivalent_to",
            "экономически эквивалентное понятие",
            active=False,
            symmetric=True,
            transitive=True,
            inverse="equivalent_to",
            cycles_allowed=True,
        ),
        _spec(
            "supersedes",
            "заменяет прежнее понятие",
            active=False,
            inverse="replaced_by",
        ),
        _spec(
            "replaced_by",
            "заменено другим понятием",
            active=False,
            inverse="supersedes",
        ),
        _spec(
            "contradicts",
            "противоречит",
            symmetric=True,
            inverse="contradicts",
            cycles_allowed=True,
        ),
        _spec(
            "requires",
            "требует наличия другого понятия",
        ),
    )
}

ACTIVE_RELATION_TYPES = frozenset(name for name, spec in RELATION_TYPES.items() if spec.active)
RESERVED_RELATION_TYPES = frozenset(name for name, spec in RELATION_TYPES.items() if not spec.active)

_USES = {
    "substitution": "allows_substitution",
    "aggregation": "participates_in_aggregation",
    "reconciliation": "participates_in_reconciliation",
}


def permits(type_name: str, use: str) -> bool:
    """Разрешает ли активный тип этот расчётный режим. Неизвестный режим — нет."""

    spec = RELATION_TYPES.get(type_name)
    field_name = _USES.get(use)
    if spec is None or field_name is None or not spec.active:
        return False
    return bool(getattr(spec, field_name))


def constraint_errors(
    nodes: Mapping[str, tuple[str, str]],
    edges: Sequence[tuple[str, str, str]],
    types: Mapping[str, RelationType] | None = None,
) -> list[str]:
    """Метки нарушений схемы. Узлы — id → (роль, размерность), рёбра — (источник, тип, цель).

    Здесь цель, роль, размерность, направление и обязательное обратное ребро.
    Циклы и опубликованное поле `broader` проверяются отдельно.
    """

    catalog = RELATION_TYPES if types is None else types
    bad: list[str] = []
    present: set[tuple[str, str, str]] = set()
    by_pair: dict[tuple[str, str], set[str]] = {}
    for source, kind, target in edges:
        spec = catalog.get(kind)
        if spec is None or not spec.active:
            continue
        present.add((source, kind, target))
        by_pair.setdefault((source, target), set()).add(kind)
        if target not in nodes:
            bad.append(f"missing:{target}")
            bad.append(f"отношение «{kind}»: понятие «{source}» ссылается на отсутствующее «{target}»")
            continue
        source_role, source_dim = nodes[source]
        target_role, target_dim = nodes[target]
        if source_role not in spec.source_roles:
            bad.extend(_role(kind, source, source_role, spec.source_roles, "источником"))
        if target_role not in spec.target_roles:
            bad.extend(_role(kind, target, target_role, spec.target_roles, "целью"))
        if spec.same_dimension and source_dim != target_dim:
            bad.append(f"dimension:{kind}")
            bad.append(
                f"отношение «{kind}»: у «{source}» размерность {source_dim}, у «{target}» — {target_dim}"
            )
    for source, target in sorted(by_pair):
        kinds = by_pair[(source, target)]
        for kind in sorted(kinds):
            inverse = catalog[kind].inverse
            if inverse and inverse != kind and inverse in kinds and kind < inverse:
                bad.append(f"direction:{kind}")
                bad.append(f"отношения «{kind}» и «{inverse}» записаны в одну сторону: «{source}» → «{target}»")
    for source, kind, target in sorted(present):
        spec = catalog[kind]
        inverse = spec.inverse
        if not spec.inverse_required or inverse is None:
            continue
        if (target, inverse, source) not in present:
            bad.append(f"inverse:{kind}")
            bad.append(
                f"для отношения «{kind}» «{source}» → «{target}» нет обязательного обратного «{inverse}»"
            )
    return bad


def _role(kind: str, concept: str, role: str, allowed: frozenset[str], place: str) -> list[str]:
    names = ", ".join(sorted(allowed))
    return [
        f"role:{kind}",
        f"понятие «{concept}» с ролью «{role}» не может быть {place} «{kind}»: допустимо {names}",
    ]
