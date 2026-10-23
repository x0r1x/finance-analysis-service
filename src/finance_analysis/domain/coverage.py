"""Окно тестовых периодов DSCR, LLCR и ADSCR (§5.7).

Полный расчёт коэффициентов — следующие фазы. Здесь только правило окна.
"""

from __future__ import annotations

TEST_PERIODS = "nonzero_debt_service"

# Окно по умолчанию одно и то же.
COVERAGE_TEST_PERIODS = {
    "dscr": TEST_PERIODS,
    "llcr": TEST_PERIODS,
    "adscr": TEST_PERIODS,
}


def is_coverage_test_period(
    *,
    debt_service_nonzero: bool,
    phase: str | None,
    explicit_phases: bool,
) -> bool:
    """Тестовый период: debt_service ≠ 0; при явных фазах ещё и phase = operation."""

    if not debt_service_nonzero:
        return False
    return phase == "operation" or not explicit_phases
