"""Неизменяемый результат разрешения метрики.

Типы не импортируют расчёт и резолвер: иначе цикл.
Идентичность — полный SHA-256 канонического тела. ``plan_id`` — первые 16 hex.
"""

from __future__ import annotations

import hashlib
import inspect
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from finance_analysis.domain.book import canonical_json

RESOLUTION_ENGINE_VERSION = "1"
PLAN_SCHEMA = "resolved_metric_plan@1.0"


def declared_resolution_dependencies() -> tuple[tuple[str, Any], ...]:
    """Внешние имена, которые движок читает. Имя — как в ``semantic_input``.

    Импорт ленивый: ``semantic_input`` сам импортирует этот модуль.
    Контрактный тест сверяет этот набор с каждым загруженным импортом модуля.
    Новая функция внутри модуля в набор не вносится: её исходник уже в штампе.
    """

    from finance_analysis.domain.binding_resolution import (
        declared_concept,
    )
    from finance_analysis.domain.binding_resolution import (
        select_primary as _select_primary,
    )
    from finance_analysis.domain.execution_contract import ExecutionContractError
    from finance_analysis.domain.free_cash_flow import _ambiguous_primary, _basis
    from finance_analysis.domain.metrics import (
        HUMAN_SOURCES,
        _primaries,
        choose_one_of,
        confirm_paid_interest,
        dscr_denominator_plan,
        interest_choice,
    )
    from finance_analysis.domain.model_type import MetricExpression, sheet_name_key

    named = (
        ("AppliedFallback", AppliedFallback),
        ("DiagnosticCandidate", DiagnosticCandidate),
        ("ExecutionControlInput", ExecutionControlInput),
        ("ExecutionContractError", ExecutionContractError),
        ("HUMAN_SOURCES", HUMAN_SOURCES),
        ("LineageRow", LineageRow),
        ("MetricExpression", MetricExpression),
        ("NeedsInput", NeedsInput),
        ("PlanWarning", PlanWarning),
        ("RejectedAlternative", RejectedAlternative),
        ("ResolvedInput", ResolvedInput),
        ("ResolvedMetricPlan", ResolvedMetricPlan),
        ("ShieldDecision", ShieldDecision),
        ("_ambiguous_primary", _ambiguous_primary),
        ("_basis", _basis),
        ("_primaries", _primaries),
        ("_select_primary", _select_primary),
        ("choose_one_of", choose_one_of),
        ("confirm_paid_interest", confirm_paid_interest),
        ("declared_concept", declared_concept),
        ("dscr_denominator_plan", dscr_denominator_plan),
        ("interest_choice", interest_choice),
        ("recover_row", recover_row),
        ("seal", seal),
        ("sheet_name_key", sheet_name_key),
    )
    return tuple(sorted(named))


def _dependency_source(obj: Any) -> str:
    if inspect.isfunction(obj) or inspect.isclass(obj):
        return inspect.getsource(obj)
    if isinstance(obj, (set, frozenset)):
        return repr(tuple(sorted(obj)))
    raise TypeError(type(obj))


def input_read_stamp() -> str:
    """16 hex версии движка, исходника модуля разрешения и объявленных зависимостей.

    Целый SMV сюда не входит. Новая функция в ``semantic_input`` меняет штамп
    без отдельной записи в список. Новый импорт, который модуль загружает и
    который не объявлен, контрактный тест не пропускает: без объявления сборка
    не сходится, и штамп такого пропуска не прячет.
    """

    import finance_analysis.domain.semantic_input as engine

    parts = [RESOLUTION_ENGINE_VERSION, inspect.getsource(engine)]
    parts.extend(f"{name}\n{_dependency_source(obj)}" for name, obj in declared_resolution_dependencies())
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class ResolvedInput:
    concept: str
    role: str
    source: str
    binding_key: str | None = None
    row_key: str | None = None
    missing: str | None = None
    ambiguous: bool = False
    confirmed: bool = True


@dataclass(frozen=True)
class DiagnosticCandidate:
    concept: str
    binding_key: str | None
    row_key: str | None
    reason: str = "ambiguous_primary_binding"


@dataclass(frozen=True)
class RejectedAlternative:
    reason: str
    concept: str
    binding_key: str | None = None
    row_key: str | None = None


@dataclass(frozen=True)
class AppliedFallback:
    slot: str
    replaced: str
    chosen: str
    warning_code: str | None = None


@dataclass(frozen=True)
class PlanWarning:
    code: str
    params: tuple[tuple[str, str], ...] = ()

    def as_dict(self) -> dict:
        return {"code": self.code, "params": dict(self.params)}


@dataclass(frozen=True)
class NeedsInput:
    kind: str
    reason: str
    subject: str

    def as_dict(self) -> dict:
        return {"kind": self.kind, "reason": self.reason, "subject": self.subject}


@dataclass(frozen=True)
class ShieldDecision:
    basis: str
    reason: str


@dataclass(frozen=True)
class LineageRow:
    """Порядок следа внутри процесса. В JSON контракта не входит.

    Значимые поля входят в хеш: строка без ``row_key`` не попадает ни в
    ``inputs``, ни в ``diagnostic``, и иначе два источника одного пропуска
    получали один ``content_sha256``. Порядок массива перед хешем сортируется.
    """

    concept: str
    source: str
    role: str
    row_key: str | None = None
    binding_key: str | None = None
    missing: str | None = None
    ambiguous: bool = False

    def as_origin(self) -> dict[str, str | bool | None]:
        body: dict[str, str | bool | None] = {
            "concept": self.concept,
            "source": self.source,
            "row_key": self.row_key,
        }
        if self.ambiguous:
            body["ambiguous"] = True
            body["confirmed"] = False
        return body


@dataclass(frozen=True)
class ExecutionControlInput:
    """Вспомогательный вход плана. Не слагаемое формулы.

    Роль — зачем расчёт читает строку: тестовый период или граница горизонта.
    Строка входит в хеш: смена привязки меняет план.
    https://www.w3.org/TR/prov-dm/#term-Plan
    """

    concept: str
    role: str
    binding_key: str | None = None
    row_key: str | None = None


@dataclass(frozen=True)
class ResolvedMetricPlan:
    schema: str
    plan_id: str
    content_sha256: str
    resolution_engine_version: str
    metric_id: str
    variant: str | None
    variant_source: str
    catalog_version: str | None
    semantic_model_version: str | None
    build_key: str | None
    model_id: str | None
    status: str
    inputs: tuple[ResolvedInput, ...]
    diagnostic: tuple[DiagnosticCandidate, ...]
    rejected: tuple[RejectedAlternative, ...]
    fallbacks: tuple[AppliedFallback, ...]
    warnings: tuple[PlanWarning, ...]
    needs_input: tuple[NeedsInput, ...]
    shield: ShieldDecision | None
    lineage: tuple[LineageRow, ...] = ()
    execution_control: tuple[ExecutionControlInput, ...] = ()
    # Ссылка на EffectiveMetricDefinition. В хеш плана не входит: стороны формулы здесь не живут.
    definition_hash: str | None = None


def recover_row(
    bindings: Sequence[Mapping[str, Any]], item: Any
) -> Mapping[str, Any] | None:
    """Строка, которую подтвердил план. Её же читает ``bindings_for_plan``.

    Есть ``binding_key`` — только он: пропавшая привязка не заменяется другой
    строкой с тем же ``row_key``. ``row_key`` читается, когда ``binding_key``
    нет, и только у строки без своего ключа.
    """

    binding_key = str(getattr(item, "binding_key", None) or "")
    if binding_key:
        for row in bindings:
            if str(row.get("binding_key") or "") == binding_key:
                return row
        return None
    row_key = getattr(item, "row_key", None) or None
    if not row_key:
        return None
    for row in bindings:
        if str(row.get("binding_key") or ""):
            continue
        if row.get("row_key") == row_key:
            return row
    return None


def bindings_for_plan(
    bindings: Sequence[Mapping[str, Any]],
    plan: Any | None,
) -> Sequence[Mapping[str, Any]]:
    """Строки калькулятора, у которого план уже есть.

    Понятие, о котором план говорит, берётся только из подтверждённого входа
    или вспомогательного входа. Кэш самой метрики и окно, которого план не
    называет, остаются.
    Без плана список тот же: это фасад старых тестов и golden.
    """

    if plan is None:
        return bindings
    from finance_analysis.domain.binding_resolution import declared_concept

    controls = tuple(
        item
        for item in (getattr(plan, "execution_control", ()) or ())
        if getattr(item, "binding_key", None) or getattr(item, "row_key", None)
    )
    owned = {item.concept for item in (*plan.inputs, *plan.diagnostic, *plan.rejected, *controls)}
    kept: list[Mapping[str, Any]] = []
    for row in bindings:
        if declared_concept(row) not in owned:
            kept.append(row)
            continue
        if any(recover_row((row,), item) is not None for item in (*plan.inputs, *controls)):
            kept.append(row)
    return kept


def bound_rows(plan: ResolvedMetricPlan, bindings: Sequence[Mapping[str, Any]]) -> dict[str, dict]:
    """Строки входов плана. Выбор не повторяет: ключ уже записан в плане."""

    found: dict[str, dict] = {}
    for item in plan.inputs:
        source = recover_row(bindings, item)
        if source is None:
            continue
        copy = dict(source)
        copy["effective_concept"] = item.concept
        found[item.concept] = copy
    return found


def content_digest(body: dict) -> str:
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ExecutionConfiguration:
    """Параметры прогона. Это не выбранные факты плана.

    ``profile`` — настройки, которые меняют выборку или число.
    Отпечаток входит в идентичность прогона и не в ``content_sha256`` плана.
    https://www.w3.org/TR/prov-dm/#term-Activity
    """

    basis: str = "period_end"
    marker_class: str | None = None
    explicit_phases: bool = False
    sign_convention: str = "outflow_negative"
    profile: tuple[tuple[str, str], ...] = ()

    def fingerprint(self) -> str:
        return content_digest(
            {
                "basis": self.basis,
                "explicit_phases": self.explicit_phases,
                "marker_class": self.marker_class or "",
                "profile": [list(item) for item in sorted(self.profile)],
                "sign_convention": self.sign_convention,
            }
        )


def run_identity(plan_content_sha256: str, configuration: ExecutionConfiguration) -> str:
    """Идентичность прогона: хеш плана и отпечаток параметров."""

    return content_digest({"configuration": configuration.fingerprint(), "plan": plan_content_sha256})


def _text(value: str | None) -> str:
    return value or ""


def _input_row(item: ResolvedInput) -> dict:
    return {
        "ambiguous": item.ambiguous,
        "binding_key": _text(item.binding_key),
        "concept": item.concept,
        "confirmed": item.confirmed,
        "missing": _text(item.missing),
        "role": item.role,
        "row_key": _text(item.row_key),
        "source": item.source,
    }


def _diagnostic_row(item: DiagnosticCandidate) -> dict:
    return {
        "binding_key": _text(item.binding_key),
        "concept": item.concept,
        "reason": item.reason,
        "row_key": _text(item.row_key),
    }


def _rejected_row(item: RejectedAlternative) -> dict:
    return {
        "binding_key": _text(item.binding_key),
        "concept": item.concept,
        "reason": item.reason,
        "row_key": _text(item.row_key),
    }


def _fallback_row(item: AppliedFallback) -> dict:
    return {
        "chosen": item.chosen,
        "replaced": item.replaced,
        "slot": item.slot,
        "warning_code": _text(item.warning_code),
    }


def _warning_row(item: PlanWarning) -> dict:
    return {"code": item.code, "params": list(item.params)}


def _need_row(item: NeedsInput) -> dict:
    return {"kind": item.kind, "reason": item.reason, "subject": item.subject}


def _control_row(item: ExecutionControlInput) -> dict:
    return {
        "binding_key": _text(item.binding_key),
        "concept": item.concept,
        "role": item.role,
        "row_key": _text(item.row_key),
    }


def _lineage_row(item: LineageRow) -> dict:
    return {
        "ambiguous": item.ambiguous,
        "binding_key": _text(item.binding_key),
        "concept": item.concept,
        "missing": _text(item.missing),
        "role": item.role,
        "row_key": _text(item.row_key),
        "source": item.source,
    }


def hashed_body(
    *,
    resolution_engine_version: str,
    metric_id: str,
    variant: str | None,
    variant_source: str,
    catalog_version: str | None,
    semantic_model_version: str | None = None,
    build_key: str | None,
    model_id: str | None,
    status: str,
    inputs: tuple[ResolvedInput, ...],
    diagnostic: tuple[DiagnosticCandidate, ...],
    rejected: tuple[RejectedAlternative, ...],
    fallbacks: tuple[AppliedFallback, ...],
    warnings: tuple[PlanWarning, ...],
    needs_input: tuple[NeedsInput, ...],
    shield: ShieldDecision | None,
    lineage: tuple[LineageRow, ...] = (),
    execution_control: tuple[ExecutionControlInput, ...] = (),
) -> dict:
    """Тело хеша. Массивы уже отсортированы: canonical_json ключи сортирует, списки нет."""

    return {
        "build_key": _text(build_key),
        "catalog_version": _text(catalog_version),
        "diagnostic": [
            _diagnostic_row(item)
            for item in sorted(
                diagnostic,
                key=lambda item: (item.concept, _text(item.binding_key), _text(item.row_key)),
            )
        ],
        "execution_control": [
            _control_row(item)
            for item in sorted(
                execution_control,
                key=lambda item: (item.concept, item.role, _text(item.binding_key), _text(item.row_key)),
            )
        ],
        "fallbacks": [
            _fallback_row(item)
            for item in sorted(
                fallbacks,
                key=lambda item: (item.slot, item.replaced, item.chosen, _text(item.warning_code)),
            )
        ],
        "input_read_stamp": input_read_stamp(),
        "lineage": [
            _lineage_row(item)
            for item in sorted(
                lineage,
                key=lambda item: (
                    item.concept,
                    item.source,
                    item.role,
                    _text(item.binding_key),
                    _text(item.row_key),
                    _text(item.missing),
                    item.ambiguous,
                ),
            )
        ],
        "inputs": [
            _input_row(item)
            for item in sorted(
                inputs,
                key=lambda item: (
                    item.concept,
                    item.role,
                    item.source,
                    _text(item.binding_key),
                    _text(item.row_key),
                ),
            )
        ],
        "metric_id": metric_id,
        "model_id": _text(model_id),
        "needs_input": [
            _need_row(item)
            for item in sorted(needs_input, key=lambda item: (item.kind, item.reason, item.subject))
        ],
        "rejected": [
            _rejected_row(item)
            for item in sorted(
                rejected,
                key=lambda item: (item.reason, item.concept, _text(item.binding_key), _text(item.row_key)),
            )
        ],
        "resolution_engine_version": resolution_engine_version,
        "semantic_model_version": _text(semantic_model_version),
        "shield": None
        if shield is None
        else {"basis": shield.basis, "reason": shield.reason},
        "status": status,
        "variant": _text(variant),
        "variant_source": variant_source,
        "warnings": [
            _warning_row(item)
            for item in sorted(warnings, key=lambda item: (item.code, item.params))
        ],
    }


def seal(
    *,
    metric_id: str,
    variant: str | None,
    variant_source: str,
    catalog_version: str | None,
    semantic_model_version: str | None,
    build_key: str | None,
    model_id: str | None,
    status: str,
    inputs: tuple[ResolvedInput, ...],
    diagnostic: tuple[DiagnosticCandidate, ...],
    rejected: tuple[RejectedAlternative, ...],
    fallbacks: tuple[AppliedFallback, ...],
    warnings: tuple[PlanWarning, ...],
    needs_input: tuple[NeedsInput, ...],
    shield: ShieldDecision | None,
    lineage: tuple[LineageRow, ...] = (),
    execution_control: tuple[ExecutionControlInput, ...] = (),
    resolution_engine_version: str = RESOLUTION_ENGINE_VERSION,
    definition_hash: str | None = None,
) -> ResolvedMetricPlan:
    digest = content_digest(
        hashed_body(
            resolution_engine_version=resolution_engine_version,
            metric_id=metric_id,
            variant=variant,
            variant_source=variant_source,
            catalog_version=catalog_version,
            semantic_model_version=semantic_model_version,
            build_key=build_key,
            model_id=model_id,
            status=status,
            inputs=inputs,
            diagnostic=diagnostic,
            rejected=rejected,
            fallbacks=fallbacks,
            warnings=warnings,
            needs_input=needs_input,
            shield=shield,
            lineage=lineage,
            execution_control=execution_control,
        )
    )
    return ResolvedMetricPlan(
        schema=PLAN_SCHEMA,
        plan_id=digest[:16],
        content_sha256=digest,
        resolution_engine_version=resolution_engine_version,
        metric_id=metric_id,
        variant=variant,
        variant_source=variant_source,
        catalog_version=catalog_version,
        semantic_model_version=semantic_model_version,
        build_key=build_key,
        model_id=model_id,
        status=status,
        inputs=inputs,
        diagnostic=diagnostic,
        rejected=rejected,
        fallbacks=fallbacks,
        warnings=warnings,
        needs_input=needs_input,
        shield=shield,
        lineage=lineage,
        execution_control=execution_control,
        definition_hash=definition_hash,
    )
