"""Сигналы обучения глоссария, модель меток и решение glossary_mine (§5.11.1–5.11.3). Без ввода-вывода."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from finance_analysis.domain.glossary import normalize_label

# Уровни доверия §5.11.1 [допущение по весам].
WEIGHTS = {
    "human.confirmed": 1.0,
    "human.corrected": 1.0,
    "human.rejected": -1.0,
    "proposal.rejected": -1.0,
    "concept.ignored": -1.0,
    "lf.identity": 0.6,
    "lf.ratio_numerator": 0.6,
    "lf.rollforward": 0.3,
    "lf.sum_component": 0.4,
    "lf.unit_sign": -0.5,
}
STRONG = frozenset({"human.confirmed", "human.corrected"})
STRONG_AGAINST = frozenset({"human.rejected", "proposal.rejected", "concept.ignored"})
# Голос «компонент DS» — кандидат narrower, а не синоним: в майнинг синонимов не идёт.
NOT_SYNONYM = frozenset({"lf.sum_component"})


@dataclass(frozen=True)
class Vote:
    binding_key: str
    concept: str
    polarity: str  # "+" или "-"
    kind: str

    @property
    def weight(self) -> float:
        return abs(WEIGHTS[self.kind])


@dataclass
class LabelingInput:
    """Книга для LF: строки, значения по (ось, период), граф ссылок строк, текущие привязки."""

    rows: list[dict]
    values: dict[str, dict[tuple[str, str], Decimal]]
    precedents: dict[str, set[str]]
    bindings: dict[str, dict]
    concepts: dict
    identities: dict[str, list[str]] = field(default_factory=dict)

    def bound(self, concept: str, *, sources: frozenset[str] | None = None) -> str | None:
        """row_key основной строки понятия, если она одна."""

        found = [
            row["row_key"]
            for row in self.bindings.values()
            if row.get("effective_concept") == concept
            and row.get("is_primary")
            and row.get("status") in {"bound", "bound_with_warning"}
            and (sources is None or row.get("source") in sources)
        ]
        return found[0] if len(found) == 1 else None


def lexical_relation(label: str, known: list[str]) -> str:
    """hiddenLabel — опечатка/сокращение (расстояние ≤ 2, аббревиатура), иначе altLabel (§5.11.2 п. 4)."""

    norm = normalize_label(label).strip()
    for other in known:
        target = normalize_label(other).strip()
        if not target:
            continue
        if _distance(norm, target, limit=2) <= 2:
            return "hidden"
        words = [word for word in target.replace("-", " ").split() if word]
        initials = "".join(word[0] for word in words)
        if len(initials) >= 2 and norm.replace(".", "").replace(" ", "") == initials:
            return "hidden"
    return "alt"


def _distance(a: str, b: str, *, limit: int) -> int:
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        if min(current) > limit:
            return limit + 1
        previous = current
    return previous[-1]


@dataclass(frozen=True)
class MineThresholds:
    min_books: int = 3
    min_confirmations: int = 2
    min_profiles_global: int = 2


def mine(
    signals: list[dict],
    *,
    owned: dict[str, str],
    negatives: dict[str, set[str]],
    known_labels: dict[str, list[str]],
    lf_accuracy: dict[str, float] | None = None,
    thresholds: MineThresholds | None = None,
) -> list[dict]:
    """Агрегирует сигналы в кандидатов `label_norm → concept` (§5.11.3 п. 1).

    owned — нормализованная метка → понятие в активном глоссарии; negatives — понятие → отрицательные метки.
    Сигналы `model.*`/`inferred` сюда не попадают (риск 23). Книги одного профиля считаются одной.
    """

    accuracy = lf_accuracy or {}
    thresholds = thresholds or MineThresholds()
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for signal in dedupe(signals):
        kind = signal.get("kind")
        if kind not in WEIGHTS or kind in NOT_SYNONYM or not signal.get("concept"):
            continue
        grouped[(signal["label_norm"], signal["concept"])].append(signal)
    by_label: dict[str, set[str]] = defaultdict(set)
    for (label, concept), rows in grouped.items():
        if any(row.get("polarity") == "+" and row.get("kind") in STRONG for row in rows):
            by_label[label].add(concept)
    out = []
    for (label, concept), rows in sorted(grouped.items()):
        plus = [row for row in rows if row.get("polarity") == "+"]
        minus = [row for row in rows if row.get("polarity") == "-"]
        if not plus:
            continue
        independent = {(row.get("profile_id") or row["job_id"]) for row in plus if row.get("kind") in STRONG or row["kind"].startswith("lf.")}
        profiles = {row.get("profile_id") for row in plus if row.get("profile_id")}
        people = {row.get("actor") for row in plus if row.get("kind") in STRONG and row.get("actor")}
        lf_for = sum(1 for row in plus if row["kind"].startswith("lf."))
        lf_against = sum(1 for row in minus if row["kind"].startswith("lf."))
        conflicts = []
        if any(row.get("kind") in STRONG_AGAINST for row in minus) or lf_against:
            conflicts.append("negative_signal")
        current = owned.get(label)
        if current and current != concept:
            conflicts.append(f"owned_by:{current}")
        if label in {normalize_label(item) for item in negatives.get(concept, set())}:
            conflicts.append("in_negative")
        rivals = sorted(by_label.get(label, set()) - {concept})
        if rivals:
            conflicts.append("rivals:" + ",".join(rivals))
        if current == concept:
            continue
        votes = 0.0
        weight_sum = 0.0
        for row in rows:
            base = abs(WEIGHTS[row["kind"]]) * accuracy.get(row["kind"], 1.0)
            weight_sum += base
            votes += base if row.get("polarity") == "+" else 0.0
        p_weak = votes / weight_sum if weight_sum else None
        enough = len(independent) >= thresholds.min_books and len(people) >= thresholds.min_confirmations
        if conflicts:
            decision = "review"
        elif enough:
            decision = "auto"
        elif people or lf_for:
            decision = "review"
        else:
            decision = "hold"
        sample = next((row for row in plus if row.get("label_text")), plus[0])
        scope = "global" if len(profiles) >= thresholds.min_profiles_global else (
            f"profile:{min(profiles)}" if len(profiles) == 1 else "global"
        )
        out.append(
            {
                "label_norm": label,
                "label_text": sample.get("label_text"),
                "lang": sample.get("lang"),
                "concept": concept,
                "scope": scope,
                "label_kind": lexical_relation(sample.get("label_text") or label, known_labels.get(concept, [])),
                "books": len(independent),
                "profiles": len(profiles),
                "confirmations": len(people),
                "lf_for": lf_for,
                "lf_against": lf_against,
                "p_weak": None if p_weak is None else round(p_weak, 6),
                "conflicts": conflicts,
                "decision": decision,
            }
        )
    return out


def dedupe(signals: list[dict]) -> list[dict]:
    """Пересборка и ремап повторяют LF по той же строке: один голос на (книга, строка, вид, понятие, знак, кто)."""

    seen: dict[tuple, dict] = {}
    for row in sorted(signals, key=lambda item: str(item.get("signal_id") or "")):
        key = (row.get("job_id"), row.get("binding_key"), row.get("kind"), row.get("concept"), row.get("polarity"), row.get("actor"))
        if row.get("binding_key") is None:
            key = (*key, row.get("signal_id"))
        seen[key] = row
    return list(seen.values())


def lf_accuracy(signals: list[dict]) -> dict[str, float]:
    """Точность каждой LF на строках, где есть сигнал S (раз в сутки, §5.11.1)."""

    truth: dict[tuple[str, str], str] = {}
    for row in signals:
        if row.get("kind") in STRONG and row.get("polarity") == "+" and row.get("binding_key"):
            truth[(row["job_id"], row["binding_key"])] = row["concept"]
    hits: dict[str, list[int]] = defaultdict(list)
    for row in dedupe(signals):
        kind = str(row.get("kind") or "")
        if not kind.startswith("lf.") or not row.get("binding_key"):
            continue
        expected = truth.get((row["job_id"], row["binding_key"]))
        if expected is None:
            continue
        agree = (row["concept"] == expected) == (row.get("polarity") == "+")
        hits[kind].append(1 if agree else 0)
    return {kind: sum(values) / len(values) for kind, values in hits.items() if values}
