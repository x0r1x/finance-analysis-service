"""Улика одного прохода коэффициента. Это не публичный след и не поле находки.

``evidence is None`` значит, что вызов вне объёма следа. Число сюда не считается
второй раз: штамп читает исходники уже названных функций, не весь модуль метрик.
"""

from __future__ import annotations

import hashlib
import inspect
from collections.abc import Mapping
from dataclasses import dataclass, replace
from decimal import Decimal
from functools import lru_cache
from typing import Any

from finance_analysis.domain.book import canonical_json

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
    node_id: str | None = None


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
    binding_key: str | None = None


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
    binding_key: str | None = None


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
    sums_additions: int = 0
    evidence_status: str = "evidence_available"
    published_read: str | None = None
    definition_version: str | None = None
    executor_id: str | None = None
    executor_version: str | None = None
    definition_source: str | None = None
    definition_ref: Mapping[str, Any] | None = None
    definition_hash: str | None = None
    branch_id: str | None = None
    actual_inputs: tuple[str, ...] = ()
    actual_fact_uses: tuple[str, ...] = ()
    actual_periods: tuple[str, ...] = ()
    actual_period_slots: tuple[tuple[str, str], ...] = ()
    profile_values: tuple[tuple[str, Any], ...] = ()
    parent_evidence_ids: tuple[str, ...] = ()
    parent_period_ids: tuple[str, ...] = ()
    calculation_origin: str | None = None
    evidence_id: str | None = None


def seal(evidence: CalculationEvidence) -> CalculationEvidence:
    """Идентификатор канонического тела улики. Поля, дописанные после freeze, входят в хеш.

    evidence_id identifies the canonical calculation evidence content, including
    the calculation implementation fingerprint. Identical evidence bodies share
    the same identifier. It is not a unique execution-attempt identifier.
    calculation_stamp is a fingerprint of the calculation path and constants,
    not a unique id of each run. Идентичность плана остаётся plan_content_sha256.

    https://csrc.nist.gov/publications/detail/fips/180/4/final
    """

    return replace(evidence, evidence_id=_identity(evidence))


def _identity(evidence: CalculationEvidence) -> str:
    """SHA-256 канонического тела. Версия исполнителя сюда не входит."""

    body = {
        "actual_fact_uses": list(evidence.actual_fact_uses),
        "actual_inputs": list(evidence.actual_inputs),
        "actual_period_slots": [list(pair) for pair in evidence.actual_period_slots],
        "actual_periods": list(evidence.actual_periods),
        "basis_sides": [_basis(item) for item in evidence.basis_sides],
        "branch_id": evidence.branch_id or "",
        "calculation_stamp": evidence.calculation_stamp,
        "definition_hash": evidence.definition_hash or "",
        "execution": evidence.execution_status,
        "fact_observations": [_observed(item) for item in evidence.fact_observations],
        "fact_uses": [_used_fact(item) for item in evidence.fact_uses],
        "implementation": evidence.implementation,
        "marker_class": evidence.marker_class or "",
        "metric": evidence.metric,
        "parent_evidence_ids": list(evidence.parent_evidence_ids),
        "parent_period_ids": list(evidence.parent_period_ids),
        "period_results": [_period_body(item) for item in evidence.period_results],
        "plan_hash": evidence.plan_content_sha256 or "",
        "profile_values": [[name, _plain(value)] for name, value in evidence.profile_values],
        "sign_convention": evidence.sign_convention,
    }
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def _basis(item: BasisSide) -> dict[str, str]:
    return {"concept": item.concept, "period_basis": item.period_basis, "source": item.source}


def _reading(item: FactUse | FactObservation) -> dict[str, Any]:
    """Сырое число и путь нормализации. Эффективное число одно, история чтения другая."""

    return {
        "axis_id": item.axis_id,
        "binding_key": item.binding_key or "",
        "cell_id": item.cell_id or "",
        "concept": item.concept,
        "effective_value": format(item.effective_value, "f"),
        "field": item.field,
        "normalization_source": item.normalization_source,
        "period_id": item.period_id,
        "period_index": "" if item.period_index is None else str(item.period_index),
        "raw_value": format(item.raw_value, "f"),
        "scale_applied": item.scale_applied,
        "scale_factor": "" if item.scale_factor is None else format(item.scale_factor, "f"),
        "scale_policy": item.scale_policy,
        "sheet": item.sheet,
        "timeline_id": item.timeline_id or "",
    }


def _used_fact(item: FactUse) -> dict[str, Any]:
    body = _reading(item)
    body["operand"] = item.operand
    body["result_axis_id"] = item.result_axis_id or ""
    body["result_period_id"] = item.result_period_id or ""
    return body


def _observed(item: FactObservation) -> dict[str, Any]:
    body = _reading(item)
    body["considered"] = item.considered or ""
    return body


def _period_body(item: PeriodResult) -> dict[str, Any]:
    return {
        "axis_id": item.axis_id or "",
        "denominator": _plain(item.denominator),
        "missing_concepts": [[label, list(subjects)] for label, subjects in item.missing_concepts],
        "node_id": item.node_id or "",
        "numerator": _plain(item.numerator),
        "period_id": item.period_id or "",
        "reason": item.reason or "",
        "status": item.status,
        "steps": [
            {
                "input_refs": list(step.input_refs),
                "operation": step.operation,
                "output_value": _plain(step.output_value),
                "parameters": _plain(step.parameters),
            }
            for step in item.steps
        ],
        "value": _plain(item.value),
        "window_missing": list(item.window_missing),
        "window_periods": list(item.window_periods),
    }


def _plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_plain(item) for item in value]
    return str(value)


def definition_fields(definition) -> dict[str, Any]:
    """Поля определения. Пустая версия остаётся пустой и не берётся у исполнителя."""

    if definition is None:
        return {}
    return {
        "definition_version": definition.definition_version,
        "definition_source": definition.definition_source,
        "definition_ref": definition.definition_ref,
        "definition_hash": definition.definition_hash,
        "executor_id": definition.executor_id,
        "executor_version": definition.executor_version,
    }


def trace_fields(trace) -> dict[str, Any]:
    """След выбранной ветви. Нет следа — поля не выдумываются."""

    if trace is None:
        return {}
    return {
        "branch_id": trace.branch_id,
        "actual_inputs": trace.actual_inputs,
        "actual_fact_uses": trace.actual_fact_uses,
        "actual_periods": trace.actual_periods,
        "actual_period_slots": trace.actual_period_slots,
        "profile_values": trace.profile_values,
    }


@dataclass(frozen=True)
class CalculationOutcome:
    result: dict
    evidence: CalculationEvidence | None
    trace: object | None = None


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
    bound_definition: Any = None

    def __post_init__(self) -> None:
        self.observations = [] if self.observations is None else self.observations
        self.fact_uses = [] if self.fact_uses is None else self.fact_uses
        self.notes = [] if self.notes is None else self.notes
        self.origins = {} if self.origins is None else self.origins
        self.periods = [] if self.periods is None else self.periods
        self.fallback = {} if self.fallback is None else self.fallback
        self.basis_sides = [] if self.basis_sides is None else self.basis_sides

    def freeze(
        self,
        execution: str,
        implementation: str,
        *,
        definition_version: str | None = None,
        executor_id: str | None = None,
        executor_version: str | None = None,
        definition_source: str | None = None,
        definition_ref: Mapping[str, Any] | None = None,
        definition_hash: str | None = None,
        branch_id: str | None = None,
        actual_inputs: tuple[str, ...] = (),
        actual_fact_uses: tuple[str, ...] = (),
        actual_periods: tuple[str, ...] = (),
        actual_period_slots: tuple[tuple[str, str], ...] = (),
        profile_values: tuple[tuple[str, Any], ...] = (),
        parent_evidence_ids: tuple[str, ...] = (),
        parent_period_ids: tuple[str, ...] = (),
        calculation_origin: str | None = None,
        evidence_status: str = "evidence_available",
        stamp: str | None = None,
    ) -> CalculationEvidence:
        stamped = calculation_stamp() if stamp is None else stamp
        uses = tuple(self.fact_uses or ())
        return seal(
            CalculationEvidence(
                metric=self.metric,
                execution_status=execution,
                implementation=implementation,
                calculation_stamp=stamped,
                plan_content_sha256=self.plan_content_sha256,
                sign_convention=self.sign_convention,
                marker_class=self.marker_class,
                explicit_phases=self.explicit_phases,
                sheet=self.sheet,
                fact_observations=tuple(self.observations or ()),
                fact_uses=uses,
                period_results=tuple(self.periods or ()),
                basis_sides=tuple(self.basis_sides or ()),
                sums_additions=self.sums_additions,
                evidence_status=evidence_status,
                definition_version=definition_version,
                executor_id=executor_id,
                executor_version=executor_version,
                definition_source=definition_source,
                definition_ref=definition_ref,
                definition_hash=definition_hash,
                branch_id=branch_id,
                actual_inputs=tuple(actual_inputs),
                actual_fact_uses=tuple(actual_fact_uses),
                actual_periods=tuple(actual_periods),
                actual_period_slots=tuple(actual_period_slots),
                profile_values=tuple(profile_values),
                parent_evidence_ids=tuple(parent_evidence_ids),
                parent_period_ids=tuple(parent_period_ids),
                calculation_origin=calculation_origin,
                evidence_id=None,
            )
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
        _definition_ltm,
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
        ("_definition_ltm", _definition_ltm),
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


def declared_composed_dependencies() -> tuple[tuple[str, Any], ...]:
    """Исходники составного исполнителя. Штамп покрытия от них не зависит."""

    from finance_analysis.domain.covenant import (
        _all_last,
        _chosen_keys,
        _definition_formula,
        _fold_side,
        _part,
        _rolls,
        _series_present,
        _span,
        _stock_choice,
        _term_fold,
        composed_ratio,
    )
    from finance_analysis.domain.cover_metrics import _as_date as _cover_as_date
    from finance_analysis.domain.cover_metrics import (
        _ctx,
        _ordered,
        _ratio,
        _window,
        grain_months,
    )
    from finance_analysis.domain.metrics import (
        _assume_sheet_units,
        _axes_of,
        _flow_basis,
        _payment,
        _sums,
        aligned_keys,
        quantize_ratio,
        unconfirmed_scale,
    )
    from finance_analysis.domain.period_basis import basis_of

    named = (
        ("_all_last", _all_last),
        ("_as_date", _cover_as_date),
        ("_ctx", _ctx),
        ("_definition_formula", _definition_formula),
        ("_ordered", _ordered),
        ("_assume_sheet_units", _assume_sheet_units),
        ("_axes_of", _axes_of),
        ("_chosen_keys", _chosen_keys),
        ("_flow_basis", _flow_basis),
        ("_fold_side", _fold_side),
        ("_part", _part),
        ("_payment", _payment),
        ("_ratio", _ratio),
        ("_rolls", _rolls),
        ("_series_present", _series_present),
        ("_span", _span),
        ("_stock_choice", _stock_choice),
        ("_sums", _sums),
        ("_term_fold", _term_fold),
        ("_window", _window),
        ("aligned_keys", aligned_keys),
        ("basis_of", basis_of),
        ("composed_ratio", composed_ratio),
        ("grain_months", grain_months),
        ("quantize_ratio", quantize_ratio),
        ("unconfirmed_scale", unconfirmed_scale),
    )
    return tuple(sorted(named))


def composed_calculation_sources() -> tuple[tuple[str, str], ...]:
    parts = [("composed", "1")]
    parts.extend((name, _dependency_source(obj)) for name, obj in declared_composed_dependencies())
    return tuple(parts)


@lru_cache(maxsize=1)
def composed_calculation_stamp() -> str:
    """16 hex исходников составной свёртки. ``composed_ratio@1`` этот хеш не заменяет."""

    text = "\n".join(f"{name}\n{source}" for name, source in composed_calculation_sources())
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
