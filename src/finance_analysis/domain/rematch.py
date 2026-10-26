"""Сопоставление привязки при сдвиге ключа (§5.3). Веса постоянные: оценивать m/u не на чем."""

from __future__ import annotations

import math

# shortcut: четыре константы вместо оценки Fellegi–Sunter, пока нет размеченного корпуса
WEIGHTS = {
    "label_path": 2.0,
    "neighbors": 1.0,
    "r1c1": 1.5,
    "numeric": 1.5,
}
REMATCH_MIN_WEIGHT = 3.0


def weight(features: dict[str, bool]) -> float:
    total = 0.0
    for name, matched in features.items():
        if matched:
            total += WEIGHTS[name]
    return total


def probability(features: dict[str, bool]) -> float:
    raw = weight(features)
    return 1 / (1 + math.pow(2, -raw))


def pair_status(candidates: list[tuple[str, float]]) -> tuple[str | None, bool]:
    """1:1. Ниже порога или две кандидатуры выше порога — stale, без выбора."""

    above = [item for item in candidates if item[1] >= REMATCH_MIN_WEIGHT]
    if len(above) == 1:
        return above[0][0], False
    return None, True
