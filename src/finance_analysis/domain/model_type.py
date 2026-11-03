"""Тип модели и применимость метрик (§5.5 стадия 0, §5.7). Без ввода-вывода."""

from __future__ import annotations

from dataclasses import dataclass

_USES = {"required": 2, "optional": 1, "not_applicable": 0}
# Уверенное противоречие профилю: чужой тип выше 0.8, указанный ниже 0.2.
CONFLICT_HIGH = 0.8
CONFLICT_LOW = 0.2


@dataclass(frozen=True)
class Signal:
    kind: str
    weight: float
    concepts: tuple[str, ...] = ()
    groups: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class TypeSpec:
    id: str
    signals: tuple[Signal, ...]
    required_concepts: frozenset[str]
    metrics: dict[str, str]
    variants: dict[str, str]


@dataclass(frozen=True)
class MetricInputs:
    all_of: frozenset[str]
    one_of: frozenset[str]


@dataclass(frozen=True)
class Side:
    plus: tuple[str, ...]
    minus: tuple[str, ...]


@dataclass(frozen=True)
class Composed:
    """Числитель и знаменатель из понятий каталога и окно `LTM` или `period`."""

    numerator: Side
    denominator: Side
    window: str


@dataclass(frozen=True)
class ModelTypeCatalog:
    types: dict[str, TypeSpec]
    default_use: str
    version: str
    concepts: frozenset[str]
    metric_inputs: dict[str, MetricInputs]
    documents: dict[str, dict]
    compatible: frozenset[frozenset[str]]
    composed: dict[str, Composed]
    variant_inputs: dict[str, dict[str, MetricInputs]]

    @property
    def ids(self) -> frozenset[str]:
        return frozenset(self.types)

    def use(self, type_id: str, metric: str) -> str:
        spec = self.types[type_id]
        if metric in spec.metrics:
            return spec.metrics[metric]
        if "*" in spec.metrics:
            return spec.metrics["*"]
        return self.default_use


@dataclass(frozen=True)
class Scored:
    type_id: str
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class Inference:
    confident: bool
    reason: str | None
    labels: tuple[str, ...]
    primary: str | None
    candidates: tuple[Scored, ...]
    scores: dict[str, float]


@dataclass(frozen=True)
class Effective:
    labels: tuple[str, ...]
    primary: str | None
    source: str
    reason: str | None
    seq: int | None
    profile_version: str | None
    score: float | None
    scores: dict[str, float]
    candidates: tuple[Scored, ...]

    def as_dict(self) -> dict:
        return {
            "labels": list(self.labels),
            "primary": self.primary,
            "source": self.source,
            "score": self.score,
            "scores": dict(self.scores),
            "seq": self.seq,
            "profile_version": self.profile_version,
            "reason": self.reason,
            "candidates": [
                {"label": item.type_id, "score": item.score, "reasons": list(item.reasons)} for item in self.candidates
            ],
        }


def _sheet_hit(name: str, group: tuple[str, ...]) -> bool:
    folded = name.casefold().strip()
    return any(folded == alias.casefold().strip() for alias in group)


def _fired(signal: Signal, *, bound: frozenset[str], sheets: frozenset[str]) -> bool:
    if signal.kind == "concepts_bound_all":
        return bool(signal.concepts) and all(name in bound for name in signal.concepts)
    if signal.kind == "concepts_bound_any":
        return bool(signal.concepts) and any(name in bound for name in signal.concepts)
    if signal.kind == "concepts_absent_all":
        return bool(signal.concepts) and all(name not in bound for name in signal.concepts)
    if signal.kind == "sheets_any":
        return bool(signal.groups) and all(any(_sheet_hit(name, group) for name in sheets) for group in signal.groups)
    return False


def _score(spec: TypeSpec, *, bound: frozenset[str], sheets: frozenset[str]) -> Scored:
    total = sum(item.weight for item in spec.signals)
    if total <= 0:
        return Scored(spec.id, 0.0, ())
    got = 0.0
    reasons: list[str] = []
    for signal in spec.signals:
        if _fired(signal, bound=bound, sheets=sheets):
            got += signal.weight
            reasons.append(signal.kind)
    return Scored(spec.id, got / total, tuple(reasons))


def infer(
    catalog: ModelTypeCatalog,
    *,
    bound: frozenset[str],
    sheets: frozenset[str],
    accept: float,
    gap: float,
) -> Inference:
    """Score каждого типа в [0, 1]. `other` не голосует: его ставит человек."""

    ranked = sorted(
        (_score(spec, bound=bound, sheets=sheets) for spec in catalog.types.values() if spec.id != "other"),
        key=lambda item: (-item.score, item.type_id),
    )
    scores = {item.type_id: item.score for item in ranked}
    if not ranked:
        return Inference(False, "unknown", (), None, (), scores)
    leader, second = ranked[0], ranked[1] if len(ranked) > 1 else None
    accepted = tuple(item for item in ranked if item.score >= accept)
    gap_ok = second is None or leader.score - second.score >= gap
    pair = frozenset({leader.type_id, second.type_id}) if second is not None else frozenset()
    hybrid = second is not None and second.score >= accept and pair in catalog.compatible
    if accepted and (gap_ok or hybrid):
        labels = [leader.type_id]
        if hybrid and second is not None:
            labels.append(second.type_id)
        return Inference(True, None, tuple(labels), leader.type_id, accepted, scores)
    reason = "ambiguous" if accepted else "unknown"
    candidates = accepted if accepted else tuple(ranked)
    top = candidates[0].type_id if candidates else None
    return Inference(False, reason, (), top, candidates, scores)


def contradicts_signals(scores: dict[str, float], stated: str) -> bool:
    stated_score = scores.get(stated, 0.0)
    return stated_score < CONFLICT_LOW and any(score > CONFLICT_HIGH for name, score in scores.items() if name != stated)


def _from_value(value: dict, *, source: str, scores: dict[str, float], profile_version: str | None) -> Effective:
    primary = str(value["primary"])
    return Effective(
        labels=tuple(value["labels"]),
        primary=primary,
        source=source,
        reason=None,
        seq=value.get("seq") if isinstance(value.get("seq"), int) else None,
        profile_version=profile_version,
        score=scores.get(primary),
        scores=scores,
        candidates=(),
    )


def effective(
    inference: Inference,
    *,
    confirmed: dict | None,
    profile_default: dict | None,
    profile_version: str | None,
) -> Effective:
    """confirmed книги > уверенный inferred > профиль. Сильный конфликт с профилем — вопрос."""

    if confirmed:
        return _from_value(confirmed, source="confirmed", scores=inference.scores, profile_version=profile_version)
    if profile_default and contradicts_signals(inference.scores, str(profile_default.get("primary") or "")):
        names = [item.type_id for item in inference.candidates]
        stated = str(profile_default.get("primary") or "")
        for name in (*inference.labels, stated):
            if name and name not in names:
                names.append(name)
        candidates = list(inference.candidates)
        if stated and all(item.type_id != stated for item in candidates):
            candidates.append(Scored(stated, float(inference.scores.get(stated, 0.0)), ()))
        return Effective(
            labels=tuple(names),
            primary=inference.primary,
            source="unresolved",
            reason="profile_conflict",
            seq=None,
            profile_version=profile_version,
            score=inference.scores.get(inference.primary) if inference.primary else None,
            scores=inference.scores,
            candidates=tuple(candidates),
        )
    if inference.confident and inference.primary:
        return Effective(
            labels=inference.labels,
            primary=inference.primary,
            source="inferred",
            reason=None,
            seq=None,
            profile_version=profile_version,
            score=inference.scores.get(inference.primary),
            scores=inference.scores,
            candidates=inference.candidates,
        )
    if profile_default:
        return _from_value(profile_default, source="profile", scores=inference.scores, profile_version=profile_version)
    return Effective(
        labels=tuple(item.type_id for item in inference.candidates),
        primary=inference.primary,
        source="unresolved",
        reason=inference.reason or "unknown",
        seq=None,
        profile_version=profile_version,
        score=inference.scores.get(inference.primary) if inference.primary else None,
        scores=inference.scores,
        candidates=inference.candidates,
    )


def applicability(catalog: ModelTypeCatalog, labels: tuple[str, ...], metric: str) -> str:
    """Максимум required > optional > not_applicable. Пустой набор — все типы каталога."""

    chosen = labels or tuple(catalog.types)
    best = "not_applicable"
    for type_id in chosen:
        if type_id not in catalog.types:
            continue
        use = catalog.use(type_id, metric)
        if _USES[use] > _USES[best]:
            best = use
    return best


def assignment_error(value, *, known: frozenset[str], max_labels: int) -> tuple[str, str] | None:
    """Ошибка схемы model_type. None — значение можно записать."""

    if not isinstance(value, dict) or set(value) - {"labels", "primary"} or _number(value):
        return "schema_invalid", "model_type: только labels и primary, без чисел"
    labels = value.get("labels")
    primary = value.get("primary")
    if (
        not isinstance(labels, list)
        or not labels
        or len(labels) != len(set(labels))
        or any(not isinstance(item, str) for item in labels)
    ):
        return "schema_invalid", "labels: непустой список меток без повторов"
    if any(item not in known for item in labels):
        return "schema_invalid", "неизвестная метка типа"
    if not isinstance(primary, str) or primary not in labels:
        return "schema_invalid", "primary должен входить в labels"
    if len(labels) > max_labels:
        return "schema_invalid", "слишком много меток типа"
    return None


def _number(value) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, dict):
        return any(_number(item) for item in value.values())
    if isinstance(value, list):
        return any(_number(item) for item in value)
    return False


def asks_for(users: tuple[str, ...], catalog: ModelTypeCatalog, labels: tuple[str, ...]) -> bool:
    """Вопрос по понятию нужен, только если хотя бы одна метрика-потребитель required."""

    return any(applicability(catalog, labels, metric) == "required" for metric in users)


def applicable_metrics(catalog: ModelTypeCatalog, labels: tuple[str, ...], metrics: tuple[str, ...]) -> frozenset[str]:
    return frozenset(metric for metric in metrics if applicability(catalog, labels, metric) != "not_applicable")


def confirmed_variants(catalog: ModelTypeCatalog, verdict: Effective) -> dict[str, str]:
    """Варианты формул уверенного primary. Пока тип не уверен, считается базовая формула."""

    if verdict.source == "unresolved" or not verdict.primary or verdict.primary not in catalog.types:
        return {}
    return dict(catalog.types[verdict.primary].variants)


def decision_labels(verdict: Effective) -> tuple[str, ...]:
    """Метки, по которым считается применимость: подтверждённые или объединение кандидатов."""

    if verdict.source == "unresolved":
        return verdict.labels
    if verdict.primary:
        return verdict.labels or (verdict.primary,)
    return verdict.labels


def open_concepts(
    catalog: ModelTypeCatalog,
    labels: tuple[str, ...],
    *,
    bound: frozenset[str],
    absent: frozenset[str],
) -> tuple[str, ...]:
    """Понятия открытых вопросов: входы required-метрик без привязки и без concept.absent.

    `one_of` спрашивается целиком, пока ни один член не привязан. Необязательная
    метрика и `not_applicable` вопросов не дают. Если у обязательной метрики
    один общий вариант, спрашиваются его входы, а не базовая формула.
    """

    asked: list[str] = []
    seen: set[str] = set()
    for metric in catalog.metric_inputs:
        spec = _required_inputs(catalog, labels, metric)
        if spec is None:
            continue
        group = sorted(spec.all_of)
        if spec.one_of and not (spec.one_of & bound):
            group = [*group, *sorted(spec.one_of)]
        for concept in group:
            if concept in seen or concept in bound or concept in absent:
                continue
            seen.add(concept)
            asked.append(concept)
    return tuple(asked)


def concept_metrics(
    catalog: ModelTypeCatalog,
    labels: tuple[str, ...],
    concept: str,
    *,
    bound: frozenset[str],
) -> tuple[str, ...]:
    """required-метрики, которым ещё нужен этот вход (`needed_by` вопроса)."""

    found: list[str] = []
    for metric in catalog.metric_inputs:
        spec = _required_inputs(catalog, labels, metric)
        if spec is None:
            continue
        if concept in spec.all_of or (concept in spec.one_of and not (spec.one_of & bound)):
            found.append(metric)
    return tuple(found)


def _required_inputs(catalog: ModelTypeCatalog, labels: tuple[str, ...], metric: str) -> MetricInputs | None:
    """Входы required-метрики. Вариант берётся, если все такие метки называют один и тот же."""

    if applicability(catalog, labels, metric) != "required":
        return None
    base = catalog.metric_inputs[metric]
    chosen: list[MetricInputs] = []
    for type_id in labels or tuple(catalog.types):
        if type_id not in catalog.types or catalog.use(type_id, metric) != "required":
            continue
        variant = catalog.types[type_id].variants.get(metric)
        override = catalog.variant_inputs.get(metric, {}).get(variant) if variant else None
        chosen.append(override or base)
    if not chosen or any(item != chosen[0] for item in chosen[1:]):
        return base
    return chosen[0]
