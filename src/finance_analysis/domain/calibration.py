"""Калибровка, порог NIL и метрики (§5.6, §5.10.1). Только NumPy, без ввода-вывода.

Калибратор хранится как JSON с числами, а не как pickle: версия проверяема и переносима.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field

import numpy as np

from finance_analysis.domain.candidates import FEATURES, Candidate, RowEvidence

ISOTONIC_MIN_PAIRS = 1000
NIL_FEATURES = ("top1_p", "nearest_concept_cos", "nearest_example_cos", "clm_none_prob")


@dataclass(frozen=True)
class Thresholds:
    """Стартовые пороги [допущение]; калибратор переопределяет их по risk–coverage."""

    accept: float = 0.6
    gap: float = 0.1
    weak_gap: float = 0.15
    tau_nil: float = 0.35
    delta_nil: float = 0.6
    clm_none: float = 0.55

    def as_dict(self) -> dict:
        return {
            "accept": self.accept,
            "gap": self.gap,
            "weak_gap": self.weak_gap,
            "tau_nil": self.tau_nil,
            "delta_nil": self.delta_nil,
            "clm_none": self.clm_none,
        }

    @classmethod
    def of(cls, raw: dict | None) -> Thresholds:
        base = cls()
        if not raw:
            return base
        return cls(**{key: float(raw.get(key, getattr(base, key))) for key in base.as_dict()})


def heuristic_probability(candidate: Candidate) -> float:
    """Правила фаз 0–2: без калибратора. Рейтинг reranker и косинусы дают оценку [допущение]."""

    if not candidate.structure_pass:
        return 0.0
    if candidate.lexical:
        return 0.95
    score = {1: 0.35, 2: 0.15, 3: 0.08}.get(candidate.rerank_rank or 0, 0.0)
    if candidate.rerank_rank == 1 and candidate.rerank_gap is not None:
        score += min(max(candidate.rerank_gap, 0.0), 1.0) * 0.15
    if candidate.recall_cos is not None:
        score += 0.35 * min(max((candidate.recall_cos - 0.5) / 0.5, 0.0), 1.0)
    if candidate.knn_cos is not None and candidate.knn_cos >= 0.85:
        score += 0.25 * (candidate.knn_cos - 0.85) / 0.15
    if candidate.clm_prob is not None:
        score = 0.5 * score + 0.5 * candidate.clm_prob
    return float(min(max(score, 0.0), 0.99))


@dataclass(frozen=True)
class Calibrator:
    version: str
    method: str
    scorer_w: tuple[float, ...]
    scorer_b: float
    platt: tuple[float, float] | None = None
    isotonic: tuple[tuple[float, ...], tuple[float, ...]] | None = None
    temperature: float = 1.0
    nil_w: tuple[float, ...] | None = None
    nil_b: float = 0.0
    thresholds: Thresholds = field(default_factory=Thresholds)
    metrics: dict = field(default_factory=dict, compare=False)

    def probability(self, candidate: Candidate) -> float:
        if not candidate.structure_pass:
            return 0.0
        score = float(np.dot(self.scorer_w, candidate.features()) + self.scorer_b)
        return float(self.calibrate_score(score))

    def calibrate_score(self, score: float) -> float:
        if self.isotonic is not None:
            xs, ys = self.isotonic
            return float(np.interp(score, xs, ys))
        a, b = self.platt or (1.0, 0.0)
        return _sigmoid(a * score + b)

    def nil_probability(self, evidence: RowEvidence, top1_p: float) -> float | None:
        if self.nil_w is None:
            return None
        x = nil_features(evidence, top1_p)
        return _sigmoid(float(np.dot(self.nil_w, x) + self.nil_b))

    def as_dict(self) -> dict:
        return {
            "version": self.version,
            "method": self.method,
            "features": list(FEATURES),
            "scorer": {"w": list(self.scorer_w), "b": self.scorer_b},
            "platt": None if self.platt is None else {"a": self.platt[0], "b": self.platt[1]},
            "isotonic": None if self.isotonic is None else {"x": list(self.isotonic[0]), "y": list(self.isotonic[1])},
            "temperature": self.temperature,
            "nil": None if self.nil_w is None else {"features": list(NIL_FEATURES), "w": list(self.nil_w), "b": self.nil_b},
            "thresholds": self.thresholds.as_dict(),
            "metrics": self.metrics,
        }

    @classmethod
    def of(cls, raw: dict) -> Calibrator:
        if list(raw.get("features") or FEATURES) != list(FEATURES):
            raise ValueError("признаки калибратора не совпадают с конвейером")
        platt = raw.get("platt")
        iso = raw.get("isotonic")
        nil = raw.get("nil")
        return cls(
            version=str(raw["version"]),
            method=str(raw.get("method") or "platt"),
            scorer_w=tuple(float(x) for x in raw["scorer"]["w"]),
            scorer_b=float(raw["scorer"]["b"]),
            platt=None if not platt else (float(platt["a"]), float(platt["b"])),
            isotonic=None if not iso else (tuple(map(float, iso["x"])), tuple(map(float, iso["y"]))),
            temperature=float(raw.get("temperature") or 1.0),
            nil_w=None if not nil else tuple(float(x) for x in nil["w"]),
            nil_b=0.0 if not nil else float(nil["b"]),
            thresholds=Thresholds.of(raw.get("thresholds")),
            metrics=dict(raw.get("metrics") or {}),
        )


def nil_features(evidence: RowEvidence, top1_p: float) -> list[float]:
    return [
        float(top1_p),
        float(evidence.nearest_concept_cos or 0.0),
        float(evidence.nearest_example_cos or 0.0),
        float(evidence.clm_none_prob or 0.0),
    ]


def calibrator_version(seq: int, body: dict) -> str:
    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:12]
    return f"c-{seq:04d}:{digest}"


# --- обучение -------------------------------------------------------------------------


def _sigmoid(value):
    return 1.0 / (1.0 + np.exp(-np.clip(value, -40, 40)))


def fit_logistic(x: np.ndarray, y: np.ndarray, *, l2: float = 1.0, iterations: int = 60) -> tuple[np.ndarray, float]:
    """Логистическая регрессия Ньютоном (IRLS) с L2 на весах, свободный член без штрафа."""

    rows, cols = x.shape
    design = np.hstack([x, np.ones((rows, 1))])
    beta = np.zeros(cols + 1)
    penalty = np.eye(cols + 1) * l2
    penalty[-1, -1] = 0.0
    for _ in range(iterations):
        p = _sigmoid(design @ beta)
        grad = design.T @ (p - y) + penalty @ beta
        weight = p * (1 - p) + 1e-9
        hess = (design * weight[:, None]).T @ design + penalty
        step = np.linalg.solve(hess, grad)
        beta -= step
        if float(np.max(np.abs(step))) < 1e-8:
            break
    return beta[:-1], float(beta[-1])


def fit_platt(scores: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    w, b = fit_logistic(scores.reshape(-1, 1), y, l2=1e-6)
    return float(w[0]), b


def fit_isotonic(scores: np.ndarray, y: np.ndarray) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Pool adjacent violators. Возвращает узлы для np.interp."""

    order = np.argsort(scores, kind="mergesort")
    xs = scores[order].astype(float)
    ys = y[order].astype(float)
    blocks: list[list[float]] = []  # [sum_y, count, x_min, x_max]
    for xv, yv in zip(xs, ys, strict=True):
        blocks.append([yv, 1.0, xv, xv])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            last = blocks.pop()
            prev = blocks[-1]
            prev[0] += last[0]
            prev[1] += last[1]
            prev[3] = last[3]
    knots_x: list[float] = []
    knots_y: list[float] = []
    for total, count, lo, hi in blocks:
        value = total / count
        knots_x.extend([lo, hi])
        knots_y.extend([value, value])
    return tuple(knots_x), tuple(knots_y)


def fit_temperature(probabilities: list[dict[str, float]], chosen: list[str]) -> float:
    """Temperature scaling вероятностей CLM: один параметр, accuracy не меняется (Guo et al. 2017)."""

    pairs = [(row, label) for row, label in zip(probabilities, chosen, strict=True) if label in row and len(row) > 1]
    if not pairs:
        return 1.0

    def nll(temp: float) -> float:
        total = 0.0
        for row, label in pairs:
            logits = {key: math.log(max(value, 1e-9)) / temp for key, value in row.items()}
            top = max(logits.values())
            norm = top + math.log(sum(math.exp(v - top) for v in logits.values()))
            total -= logits[label] - norm
        return total

    lo, hi = math.log(0.05), math.log(20.0)
    golden = (math.sqrt(5) - 1) / 2
    a, b = lo, hi
    c, d = b - golden * (b - a), a + golden * (b - a)
    for _ in range(60):
        if nll(math.exp(c)) < nll(math.exp(d)):
            b = d
        else:
            a = c
        c, d = b - golden * (b - a), a + golden * (b - a)
    return float(math.exp((a + b) / 2))


def apply_temperature(probabilities: dict[str, float], temperature: float) -> dict[str, float]:
    if not probabilities or temperature == 1.0:
        return dict(probabilities)
    logits = {key: math.log(max(float(value), 1e-9)) / temperature for key, value in probabilities.items()}
    top = max(logits.values())
    exp = {key: math.exp(value - top) for key, value in logits.items()}
    total = sum(exp.values())
    return {key: value / total for key, value in exp.items()}


def expected_calibration_error(p: np.ndarray, y: np.ndarray, *, bins: int = 10) -> float:
    if len(p) == 0:
        return 0.0
    edges = np.linspace(0.0, 1.0, bins + 1)
    total = 0.0
    for index in range(bins):
        lo, hi = edges[index], edges[index + 1]
        mask = (p >= lo) & ((p < hi) if index < bins - 1 else (p <= hi))
        if not mask.any():
            continue
        total += abs(float(p[mask].mean()) - float(y[mask].mean())) * float(mask.sum())
    return total / len(p)


def brier(p: np.ndarray, y: np.ndarray) -> float:
    if len(p) == 0:
        return 0.0
    return float(np.mean((p - y) ** 2))


def risk_coverage_threshold(p: np.ndarray, correct: np.ndarray, *, max_risk: float) -> tuple[float, float]:
    """Наименьший порог, при котором ошибка среди принятых ≤ max_risk; возвращает (порог, покрытие)."""

    if len(p) == 0:
        return 1.0, 0.0
    order = np.argsort(-p, kind="mergesort")
    sorted_p = p[order]
    wrong = np.cumsum(1 - correct[order])
    accepted = np.arange(1, len(p) + 1)
    risk = wrong / accepted
    ok = np.where(risk <= max_risk)[0]
    if len(ok) == 0:
        return 1.0, 0.0
    last = int(ok[-1])
    return float(sorted_p[last]), float((last + 1) / len(p))


def group_folds(groups: list[str], k: int) -> list[tuple[np.ndarray, np.ndarray]]:
    """K-fold по книгам: одна книга целиком в одной части, чтобы не было утечки внутри книги."""

    unique = sorted(set(groups))
    k = max(2, min(k, len(unique)))
    fold_of = {name: index % k for index, name in enumerate(unique)}
    labels = np.array([fold_of[name] for name in groups])
    folds = []
    for fold in range(k):
        test = np.where(labels == fold)[0]
        train = np.where(labels != fold)[0]
        if len(test) and len(train):
            folds.append((train, test))
    return folds


@dataclass(frozen=True)
class TrainingPair:
    group: str
    features: tuple[float, ...]
    label: int


def train(
    pairs: list[TrainingPair],
    *,
    seq: int,
    max_risk: float = 0.02,
    nil_pairs: list[TrainingPair] | None = None,
    clm: tuple[list[dict[str, float]], list[str]] | None = None,
    folds: int = 5,
) -> Calibrator:
    """Скорер на признаках + Platt (или isotonic при > ~1000 пар) на out-of-fold скорах по книгам."""

    if len(pairs) < 10 or len({pair.label for pair in pairs}) < 2:
        raise ValueError("мало размеченных пар для калибратора")
    x = np.array([pair.features for pair in pairs], dtype=float)
    y = np.array([pair.label for pair in pairs], dtype=float)
    groups = [pair.group for pair in pairs]
    oof = np.zeros(len(pairs))
    splits = group_folds(groups, folds)
    if not splits:
        raise ValueError("для калибратора нужны пары минимум из двух книг")
    for train_idx, test_idx in splits:
        w, b = fit_logistic(x[train_idx], y[train_idx])
        oof[test_idx] = x[test_idx] @ w + b
    w, b = fit_logistic(x, y)
    method = "isotonic" if len(pairs) > ISOTONIC_MIN_PAIRS else "platt"
    platt = iso = None
    if method == "isotonic":
        iso = fit_isotonic(oof, y)
        calibrated = np.interp(oof, iso[0], iso[1])
    else:
        platt = fit_platt(oof, y)
        calibrated = _sigmoid(platt[0] * oof + platt[1])
    accept, coverage = risk_coverage_threshold(calibrated, y, max_risk=max_risk)
    nil_w = None
    nil_b = 0.0
    if nil_pairs and len({pair.label for pair in nil_pairs}) == 2:
        nx = np.array([pair.features for pair in nil_pairs], dtype=float)
        ny = np.array([pair.label for pair in nil_pairs], dtype=float)
        weights, nil_b = fit_logistic(nx, ny)
        nil_w = tuple(float(v) for v in weights)
    temperature = fit_temperature(*clm) if clm else 1.0
    metrics = {
        "pairs": len(pairs),
        "books": len(set(groups)),
        "ece": round(expected_calibration_error(calibrated, y), 6),
        "brier": round(brier(calibrated, y), 6),
        "coverage_at_risk": round(coverage, 6),
        "max_risk": max_risk,
    }
    thresholds = Thresholds(accept=max(0.5, min(accept, 0.99)))
    body = {
        "method": method,
        "w": [float(v) for v in w],
        "b": b,
        "platt": platt,
        "iso": iso,
        "nil": nil_w,
        "t": temperature,
    }
    return Calibrator(
        version=calibrator_version(seq, body),
        method=method,
        scorer_w=tuple(float(v) for v in w),
        scorer_b=b,
        platt=platt,
        isotonic=iso,
        temperature=temperature,
        nil_w=nil_w,
        nil_b=nil_b,
        thresholds=thresholds,
        metrics=metrics,
    )


def bootstrap_delta(
    before: list[tuple[int, int]],
    after: list[tuple[int, int]],
    *,
    iterations: int = 1000,
    seed: int = 7,
) -> tuple[float, float, float]:
    """Δ доли ложных привязок (after − before) с 95 % интервалом, bootstrap по книгам.

    before/after — по книге (ложных, принятых), в одном порядке книг.
    """

    if not before:
        return 0.0, 0.0, 0.0
    a = np.array(before, dtype=float)
    b = np.array(after, dtype=float)

    def rate(rows: np.ndarray) -> float:
        accepted = rows[:, 1].sum()
        return float(rows[:, 0].sum() / accepted) if accepted else 0.0

    point = rate(b) - rate(a)
    rng = np.random.default_rng(seed)
    deltas = []
    for _ in range(iterations):
        pick = rng.integers(0, len(a), len(a))
        deltas.append(rate(b[pick]) - rate(a[pick]))
    low, high = np.percentile(deltas, [2.5, 97.5])
    return point, float(low), float(high)
