"""Метрики eval привязки (§5.6, §5.10.6). Без ввода-вывода.

Метка строки: понятие или NIL. Принятая привязка — статус bound/bound_with_warning.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

from finance_analysis.domain.calibration import brier, expected_calibration_error

NIL = "NIL"
ACCEPTED = frozenset({"bound", "bound_with_warning"})
# Общий abstain (не bind). Для NIL recall/precision — только unknown|ambiguous (см. eval/README).
ABSTAIN = frozenset({"unknown", "ambiguous", "not_applicable", "ignored"})
NIL_STATUSES = frozenset({"unknown", "ambiguous"})


@dataclass
class BookScore:
    job_id: str
    accepted: int = 0
    false: int = 0
    accepted_metric: int = 0
    false_metric: int = 0
    accepted_critical: int = 0
    false_critical: int = 0
    nil_total: int = 0
    nil_hit: int = 0
    nil_total_critical: int = 0
    nil_hit_critical: int = 0
    nil_predicted: int = 0
    nil_predicted_true: int = 0
    per_concept: dict[str, list[int]] = field(default_factory=lambda: defaultdict(lambda: [0, 0]))
    confidences: list[tuple[float, int]] = field(default_factory=list)


def score_book(
    job_id: str,
    bindings: list[dict],
    labels: dict[str, str],
    *,
    metric_concepts: frozenset[str],
    critical: frozenset[str] = frozenset(),
) -> BookScore:
    score = BookScore(job_id)
    for row in bindings:
        key = row["binding_key"]
        truth = labels.get(key)
        if truth is None:
            continue
        status = row.get("status")
        concept = row.get("effective_concept") or row.get("concept")
        is_critical = key in critical
        in_metric = truth in metric_concepts or (concept in metric_concepts if concept else False)
        if truth != NIL:
            hits = score.per_concept[truth]
            hits[1] += 1
            if status in ACCEPTED and concept == truth:
                hits[0] += 1
        if status in ACCEPTED:
            wrong = concept != truth
            score.accepted += 1
            score.false += int(wrong)
            if in_metric:
                score.accepted_metric += 1
                score.false_metric += int(wrong)
            if is_critical:
                score.accepted_critical += 1
                score.false_critical += int(wrong)
            if row.get("confidence") is not None:
                score.confidences.append((float(row["confidence"]), int(not wrong)))
        if truth == NIL:
            score.nil_total += 1
            hit = status in NIL_STATUSES
            score.nil_hit += int(hit)
            if is_critical:
                score.nil_total_critical += 1
                score.nil_hit_critical += int(hit)
        if status in NIL_STATUSES:
            score.nil_predicted += 1
            score.nil_predicted_true += int(truth == NIL)
    return score


def summarize(scores: list[BookScore], *, focus: frozenset[str]) -> dict:
    def rate(num: int, den: int) -> float | None:
        return None if den == 0 else round(num / den, 6)

    accepted = sum(item.accepted for item in scores)
    false = sum(item.false for item in scores)
    per_concept: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for item in scores:
        for concept, (hit, total) in item.per_concept.items():
            per_concept[concept][0] += hit
            per_concept[concept][1] += total
    confidences = [pair for item in scores for pair in item.confidences]
    p = np.array([c for c, _y in confidences], dtype=float)
    y = np.array([t for _c, t in confidences], dtype=float)
    nil_total = sum(item.nil_total for item in scores)
    nil_pred = sum(item.nil_predicted for item in scores)
    return {
        "books": len(scores),
        "accepted": accepted,
        "false_binding_rate": rate(false, accepted),
        "false_binding_rate_metric": rate(sum(i.false_metric for i in scores), sum(i.accepted_metric for i in scores)),
        "top1": {concept: rate(hit, total) for concept, (hit, total) in sorted(per_concept.items())},
        "top1_focus": {concept: rate(*per_concept[concept]) for concept in sorted(focus) if per_concept[concept][1]},
        "nil_recall": rate(sum(i.nil_hit for i in scores), nil_total),
        "nil_recall_critical": rate(sum(i.nil_hit_critical for i in scores), sum(i.nil_total_critical for i in scores)),
        "nil_precision": rate(sum(i.nil_predicted_true for i in scores), nil_pred),
        "ece": None if not len(p) else round(expected_calibration_error(p, y), 6),
        "brier": None if not len(p) else round(brier(p, y), 6),
    }


def targets_met(summary: dict, *, focus: frozenset[str]) -> dict:
    """Готово-когда фазы 2b (§12) [допущение]: top-1 ≥ 0.9, ECE < 0.05, ложные ≤ 2 %, NIL recall ≥ 0.9."""

    top1 = summary.get("top1_focus") or {}
    checks = {
        "top1_ge_0_9": bool(top1) and all((top1.get(c) or 0) >= 0.9 for c in focus if c in top1),
        "ece_lt_0_05": summary.get("ece") is not None and summary["ece"] < 0.05,
        "false_le_0_02": summary.get("false_binding_rate_metric") is not None and summary["false_binding_rate_metric"] <= 0.02,
        "nil_recall_critical_ge_0_9": summary.get("nil_recall_critical") is not None and summary["nil_recall_critical"] >= 0.9,
    }
    return {"checks": checks, "passed": all(checks.values())}
