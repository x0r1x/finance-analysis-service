"""Покрытие тестами. Это не runtime-матрица и не модуль API.

Числа эталона остаются в тестах коэффициентов. Здесь только факт покрытия.
integration — not_inventoried, пока список интеграционных тестов не составлен.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EvaluationRow:
    metric: str
    unit: str
    golden: str
    integration: str
    evidence_assertions: str


def evaluation_matrix() -> tuple[EvaluationRow, ...]:
    """LLCR и PLCR. Источник — тесты, не каталог и не реестр.

    unit: ``tests/unit/test_cover_metrics.py`` вызывает оба расчёта.
    golden: ``test_llcr_catalog_matches_python_and_golden`` и
    ``test_plcr_catalog_matches_python_and_golden``.
    evidence_assertions: теста улики расчёта нет. Статус ``evidence_matrix``
    этим покрытием не считается.
    """

    return (
        EvaluationRow("llcr", "covered", "covered", "not_inventoried", "no_reference_test"),
        EvaluationRow("plcr", "covered", "covered", "not_inventoried", "no_reference_test"),
    )
