"""Калибратор, temperature scaling, risk–coverage и bootstrap (§5.6, §5.10.6)."""

import numpy as np
import pytest

from finance_analysis.domain.calibration import (
    Calibrator,
    TrainingPair,
    apply_temperature,
    bootstrap_delta,
    expected_calibration_error,
    fit_isotonic,
    fit_platt,
    fit_temperature,
    group_folds,
    heuristic_probability,
    risk_coverage_threshold,
    train,
)
from finance_analysis.domain.candidates import Candidate


def _pairs(n_books: int = 6, per_book: int = 40, seed: int = 3) -> list[TrainingPair]:
    rng = np.random.default_rng(seed)
    out = []
    for book in range(n_books):
        for _ in range(per_book):
            label = int(rng.random() < 0.5)
            rank = 1 if label else int(rng.integers(2, 6))
            cos = float(np.clip(rng.normal(0.8 if label else 0.55, 0.08), 0, 1))
            candidate = Candidate("cfads", recall_cos=cos, rerank_rank=rank, rerank_gap=0.2 if label else -0.1)
            out.append(TrainingPair(f"b{book}", tuple(candidate.features()), label))
    return out


def test_platt_recovers_monotone_mapping():
    scores = np.linspace(-4, 4, 400)
    y = (np.random.default_rng(1).random(400) < 1 / (1 + np.exp(-2 * scores))).astype(float)
    a, b = fit_platt(scores, y)
    assert 1.2 < a < 3.0
    assert abs(b) < 0.6


def test_isotonic_is_monotone():
    xs, ys = fit_isotonic(np.array([0.1, 0.2, 0.3, 0.4, 0.5]), np.array([0, 1, 0, 1, 1]))
    assert list(ys) == sorted(ys)
    assert xs[0] == 0.1 and xs[-1] == 0.5


def test_group_folds_keep_book_together():
    groups = ["a", "a", "b", "b", "c", "d"]
    for train_idx, test_idx in group_folds(groups, 3):
        assert not {groups[i] for i in train_idx} & {groups[i] for i in test_idx}


def test_train_round_trips_and_is_calibrated():
    calibrator = train(_pairs(), seq=1, max_risk=0.05)
    assert calibrator.method == "platt"
    assert calibrator.version.startswith("c-0001:")
    assert calibrator.metrics["books"] == 6
    assert calibrator.metrics["ece"] < 0.1
    again = Calibrator.of(calibrator.as_dict())
    good = Candidate("cfads", recall_cos=0.85, rerank_rank=1, rerank_gap=0.2)
    bad = Candidate("cfads", recall_cos=0.5, rerank_rank=4, rerank_gap=-0.1)
    assert again.probability(good) > 0.8
    assert again.probability(bad) < 0.2
    assert again.probability(Candidate("cfads", structure_pass=False)) == 0.0


def test_train_needs_two_books_and_both_labels():
    with pytest.raises(ValueError):
        train([TrainingPair("a", (0.0,) * 8, 1)] * 20, seq=1)


def test_temperature_scaling_keeps_argmax():
    rows = [{"cfads": 0.99, "none": 0.01}, {"cfads": 0.98, "none": 0.02}, {"cfads": 0.97, "none": 0.03}, {"cfads": 0.99, "none": 0.01}]
    labels = ["cfads", "none", "none", "cfads"]
    temperature = fit_temperature(rows, labels)
    assert temperature > 1.0
    scaled = apply_temperature(rows[0], temperature)
    assert max(scaled, key=scaled.get) == "cfads"
    assert scaled["cfads"] < 0.99


def test_ece_and_risk_coverage():
    p = np.array([0.9, 0.8, 0.7, 0.4])
    correct = np.array([1, 1, 0, 0])
    assert expected_calibration_error(np.array([1.0, 0.0]), np.array([1.0, 0.0])) == 0.0
    threshold, coverage = risk_coverage_threshold(p, correct, max_risk=0.0)
    assert threshold == 0.8 and coverage == 0.5


def test_bootstrap_flags_clear_regression_only():
    before = [(0, 20)] * 10
    worse = [(5, 20)] * 10
    same = [(0, 20)] * 10
    _point, low, _high = bootstrap_delta(before, worse)
    assert low > 0
    _point, low, high = bootstrap_delta(before, same)
    assert low <= 0 <= high


def test_heuristic_prefers_lexical_and_top_rank():
    lexical = heuristic_probability(Candidate("x", lexical=True))
    ranked = heuristic_probability(Candidate("x", recall_cos=0.9, rerank_rank=1, rerank_gap=0.5))
    weak = heuristic_probability(Candidate("x", recall_cos=0.55, rerank_rank=4))
    assert lexical > ranked > weak
