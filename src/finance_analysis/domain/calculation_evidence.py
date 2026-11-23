"""Улика одного прохода коэффициента. Это не публичный след и не поле находки.

``evidence is None`` значит, что вызов вне объёма следа. Число сюда не считается
второй раз: штамп читает исходники уже названных функций, не весь модуль метрик.
"""

from __future__ import annotations

import hashlib
import inspect
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from typing import Any

CALCULATION_ENGINE_VERSION = "1"


@dataclass(frozen=True)
class TransformationStep:
    step_id: int
    operation: str
    input_refs: tuple[str, ...]
    output_value: Decimal | None
    parameters: Mapping[str, Any]


@dataclass(frozen=True)
class PeriodResult:
    axis_id: str | None
    period_id: str | None
    status: str
    reason: str | None
    value: Decimal | None
    numerator: Decimal | None
    denominator: Decimal | None
    steps: tuple[TransformationStep, ...]
    window_periods: tuple[str, ...] = ()
    window_missing: tuple[str, ...] = ()
    missing_concepts: tuple[tuple[str, tuple[str, ...]], ...] = ()


@dataclass(frozen=True)
class FactObservation:
    """Факт, прочитанный при сборке ряда. В операнд периода он ещё не входил."""

    concept: str
    cell_id: str | None
    axis_id: str
    period_id: str
    timeline_id: str | None
    period_index: int | None
    field: str
    sheet: bool
    raw_value: Decimal
    effective_value: Decimal
    scale_factor: Decimal | None
    scale_policy: str
    scale_applied: bool
    normalization_source: str
    considered: str | None = None


@dataclass(frozen=True)
class BasisSide:
    """Сторона проверки способа показа. Источник — header, formula или label."""

    concept: str
    period_basis: str
    source: str


@dataclass(frozen=True)
class FactUse:
    """Факт, который вошёл в операнд конкретного периода. Решение о масштабе лежит здесь, не в пустом шаге."""

    concept: str
    cell_id: str | None
    axis_id: str
    period_id: str
    timeline_id: str | None
    period_index: int | None
    field: str
    sheet: bool
    raw_value: Decimal
    effective_value: Decimal
    scale_factor: Decimal | None
    scale_policy: str
    scale_applied: bool
    normalization_source: str
    result_axis_id: str | None
    result_period_id: str | None
    operand: str


@dataclass(frozen=True)
class CalculationEvidence:
    metric: str
    execution_status: str
    implementation: str
    calculation_stamp: str
    plan_content_sha256: str | None
    sign_convention: str
    marker_class: str | None
    explicit_phases: bool
    sheet: bool
    fact_observations: tuple[FactObservation, ...]
    fact_uses: tuple[FactUse, ...]
    period_results: tuple[PeriodResult, ...]
    basis_sides: tuple[BasisSide, ...] = ()


@dataclass(frozen=True)
class CalculationOutcome:
    result: dict
    evidence: CalculationEvidence | None


@dataclass
class EvidenceBook:
    """Черновик одного прохода. В результат коэффициента не кладётся."""

    metric: str
    sign_convention: str
    marker_class: str | None
    explicit_phases: bool
    plan_content_sha256: str | None
    sheet: bool = False
    observations: list[FactObservation] | None = None
    fact_uses: list[FactUse] | None = None
    notes: list[dict] | None = None
    origins: dict | None = None
    periods: list[PeriodResult] | None = None
    fallback: dict | None = None
    basis_sides: list[BasisSide] | None = None
    sums_additions: int = 0

    def __post_init__(self) -> None:
        self.observations = [] if self.observations is None else self.observations
        self.fact_uses = [] if self.fact_uses is None else self.fact_uses
        self.notes = [] if self.notes is None else self.notes
        self.origins = {} if self.origins is None else self.origins
        self.periods = [] if self.periods is None else self.periods
        self.fallback = {} if self.fallback is None else self.fallback
        self.basis_sides = [] if self.basis_sides is None else self.basis_sides

    def freeze(self, execution: str, implementation: str) -> CalculationEvidence:
        return CalculationEvidence(
            metric=self.metric,
            execution_status=execution,
            implementation=implementation,
            calculation_stamp=calculation_stamp(),
            plan_content_sha256=self.plan_content_sha256,
            sign_convention=self.sign_convention,
            marker_class=self.marker_class,
            explicit_phases=self.explicit_phases,
            sheet=self.sheet,
            fact_observations=tuple(self.observations or ()),
            fact_uses=tuple(self.fact_uses or ()),
            period_results=tuple(self.periods or ()),
            basis_sides=tuple(self.basis_sides or ()),
        )


def _dependency_source(obj: Any) -> str:
    if inspect.isfunction(obj) or inspect.isclass(obj):
        return inspect.getsource(obj)
    return repr(obj)


def declared_calculation_dependencies() -> tuple[tuple[str, Any], ...]:
    """Имена, исходники которых входят в штамп числа. Весь ``metrics.py`` сюда не входит.

    Выбор входа (``choose_one_of`` и соседние функции) остаётся в штампе разрешения.
    ``_component_cells`` на число не влияет: адреса пишутся там, где факт входит в сумму.
    """

    from finance_analysis.domain.cover_metrics import (
        WINDOW_MONTHS,
        _dated,
        _month_last,
        _window,
        add_months,
    )
    from finance_analysis.domain.coverage import is_coverage_test_period
    from finance_analysis.domain.metrics import (
        RATIO,
        _as_date,
        _assume_sheet_units,
        _axes_of,
        _basis_message,
        _bound_name,
        _close,
        _dated_periods,
        _decimal,
        _explained,
        _figure_taken,
        _flow_basis,
        _home_period,
        _ltm_numerator,
        _noted,
        _numerator_misses_axis,
        _one_scale,
        _payment,
        _row,
        _scale,
        _scale_bundle,
        _scale_kind,
        _scale_policy,
        _stored_scale,
        _sums,
        aligned_keys,
        calculate_coverage,
        quantize_ratio,
        unconfirmed_scale,
    )
    from finance_analysis.domain.period_basis import _as_date as _period_as_date
    from finance_analysis.domain.period_basis import _year_of, basis_of, restate_series

    named = (
        ("RATIO", RATIO),
        ("RATIO_PRECISION", 38),
        ("RATIO_ROUNDING", "ROUND_HALF_EVEN"),
        ("WINDOW_MONTHS", WINDOW_MONTHS),
        ("_dated", _dated),
        ("_month_last", _month_last),
        ("add_months", add_months),
        ("_as_date", _as_date),
        ("_assume_sheet_units", _assume_sheet_units),
        ("_axes_of", _axes_of),
        ("_basis_message", _basis_message),
        ("_bound_name", _bound_name),
        ("_close", _close),
        ("_dated_periods", _dated_periods),
        ("_decimal", _decimal),
        ("_explained", _explained),
        ("_figure_taken", _figure_taken),
        ("_flow_basis", _flow_basis),
        ("_home_period", _home_period),
        ("_ltm_numerator", _ltm_numerator),
        ("_noted", _noted),
        ("_numerator_misses_axis", _numerator_misses_axis),
        ("_one_scale", _one_scale),
        ("_payment", _payment),
        ("_period_as_date", _period_as_date),
        ("_row", _row),
        ("_scale", _scale),
        ("_scale_bundle", _scale_bundle),
        ("_scale_kind", _scale_kind),
        ("_scale_policy", _scale_policy),
        ("_stored_scale", _stored_scale),
        ("_sums", _sums),
        ("_window", _window),
        ("_year_of", _year_of),
        ("aligned_keys", aligned_keys),
        ("basis_of", basis_of),
        ("calculate_coverage", calculate_coverage),
        ("is_coverage_test_period", is_coverage_test_period),
        ("quantize_ratio", quantize_ratio),
        ("restate_series", restate_series),
        ("unconfirmed_scale", unconfirmed_scale),
    )
    return tuple(sorted(named))


def calculation_sources() -> tuple[tuple[str, str], ...]:
    parts = [(CALCULATION_ENGINE_VERSION, CALCULATION_ENGINE_VERSION)]
    parts.extend((name, _dependency_source(obj)) for name, obj in declared_calculation_dependencies())
    return tuple(parts)


@lru_cache(maxsize=1)
def calculation_stamp() -> str:
    """16 hex исходников пути числа и констант кванта. Файла ``metrics.py`` в хеше нет."""

    text = "\n".join(f"{name}\n{source}" for name, source in calculation_sources())
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
