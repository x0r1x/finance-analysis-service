"""Покрытие тестами. Это не runtime-матрица и не модуль API.

Числа эталона остаются в тестах коэффициентов. Здесь только факт покрытия
и ссылки на тесты. integration — not_inventoried, пока список интеграционных
тестов не составлен.
"""

from __future__ import annotations

from dataclasses import dataclass

_COVER = "tests/unit/test_cover_metrics.py"
_GOLDEN = "tests/unit/test_metric_golden.py"
_FIXTURES = "tests.unit.test_cover_metrics"


@dataclass(frozen=True, slots=True)
class TestRef:
    module: str
    nodeid: str


@dataclass(frozen=True, slots=True)
class FixtureRef:
    module: str
    name: str


@dataclass(frozen=True, slots=True)
class EvaluationRow:
    metric: str
    unit: str
    golden: str
    integration: str
    evidence_assertions: str
    unit_refs: tuple[TestRef, ...]
    golden_refs: tuple[TestRef, ...]
    golden_fixtures: tuple[FixtureRef, ...]


def _ref(module: str, name: str) -> TestRef:
    return TestRef(module, f"{module}::{name}")


def evaluation_matrix() -> tuple[EvaluationRow, ...]:
    """LLCR и PLCR. Источник — тесты, не каталог и не реестр.

    evidence_assertions: теста улики расчёта нет. Статус ``evidence_matrix``
    этим покрытием не считается.
    """

    cover = (
        "test_llcr_with_one_scale_divides_the_sheet_figures",
        "test_llcr_reperformed_and_not_computed_in_final_period",
        "test_llcr_without_rate_asks_for_the_rate_cell",
        "test_llcr_period_start_basis_takes_the_current_period",
        "test_llcr_without_dates_discounts_by_grain_and_warns",
        "test_llcr_window_with_empty_cfads_is_missing_input",
        "test_llcr_rate_out_of_range_is_missing_input",
        "test_llcr_negative_balance_is_not_computed",
        "test_llcr_warns_that_dsra_is_not_included",
    )
    plcr = (
        "test_llcr_reperformed_and_not_computed_in_final_period",
        "test_llcr_rate_out_of_range_is_missing_input",
        "test_llcr_warns_that_dsra_is_not_included",
    )
    return (
        EvaluationRow(
            "llcr",
            "covered",
            "covered",
            "not_inventoried",
            "no_reference_test",
            tuple(_ref(_COVER, name) for name in cover),
            (_ref(_GOLDEN, "test_llcr_catalog_matches_python_and_golden"),),
            (FixtureRef(_FIXTURES, "LLCR_2025"),),
        ),
        EvaluationRow(
            "plcr",
            "covered",
            "covered",
            "not_inventoried",
            "no_reference_test",
            tuple(_ref(_COVER, name) for name in plcr),
            (_ref(_GOLDEN, "test_plcr_catalog_matches_python_and_golden"),),
            (FixtureRef(_FIXTURES, "PLCR_2025"),),
        ),
    )
