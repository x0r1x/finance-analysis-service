"""Financial Model Catalog — показатель как сущность (фаза 3 метаслоя, G1).

Каталог читается поверх `configs/metrics` + таксономия + применимость
`model_types`. Формулы не выводятся из `composed_of`. Версия каталога входит
в `SemanticModelVersion.components.metrics.version`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from finance_analysis.domain.book import canonical_json
from finance_analysis.domain.dimensions import DimensionCatalog
from finance_analysis.domain.model_type import (
    MetricExpression,
    MetricInputs,
    ModelTypeCatalog,
)

INDICATOR_STATUSES = frozenset({"active", "deprecated"})
WINDOWS = frozenset({"LTM", "period"})


@dataclass(frozen=True)
class IndicatorVariant:
    """Вариант показателя (например dscr.pf / dscr.corporate_covenant)."""

    id: str
    inputs: frozenset[str]
    unit: str
    window: str | None = None
    definition: str | None = None


@dataclass(frozen=True)
class Indicator:
    """Публичная запись показателя финансового модели.

    `inputs` — только concept_id таксономии (row_fallbacks сюда не входят).
    `model_types` — применимость по типу: required / optional / not_applicable.
    `status` — active | deprecated.
    """

    id: str
    inputs: frozenset[str]
    unit: str
    definition: str | None = None
    window: str | None = None
    variants: dict[str, IndicatorVariant] = field(default_factory=dict)
    model_types: dict[str, str] = field(default_factory=dict)
    status: str = "active"
    base: str | None = None

    def as_dict(self) -> dict:
        body = {
            "id": self.id,
            "definition": self.definition,
            "inputs": sorted(self.inputs),
            "unit": self.unit,
            "window": self.window,
            "variants": {
                name: {
                    "id": item.id,
                    "definition": item.definition,
                    "inputs": sorted(item.inputs),
                    "unit": item.unit,
                    "window": item.window,
                }
                for name, item in sorted(self.variants.items())
            },
            "model_types": dict(sorted(self.model_types.items())),
            "status": self.status,
            "base": self.base,
        }
        return body


@dataclass(frozen=True)
class FinancialModelCatalog:
    """Версионируемый каталог показателей."""

    indicators: dict[str, Indicator]
    version: str
    stamp: str
    row_fallback_ids: frozenset[str] = field(default_factory=frozenset)

    def get(self, metric_id: str) -> Indicator | None:
        return self.indicators.get(metric_id)

    def as_dict(self) -> dict:
        return {
            "version": self.version,
            "stamp": self.stamp,
            "indicators": {name: item.as_dict() for name, item in sorted(self.indicators.items())},
            "row_fallbacks": sorted(self.row_fallback_ids),
        }


def catalog_version_for(indicators: Mapping[str, Indicator]) -> str:
    """Воспроизводимый id каталога: одинаковые записи → одинаковый 16-hex."""

    payload = {name: item.as_dict() for name, item in sorted(indicators.items())}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:16]


def build_financial_catalog(
    *,
    model_types: ModelTypeCatalog,
    concept_dimensions: Mapping[str, str],
    dimensions: DimensionCatalog,
    stamp: str,
    definitions: Mapping[str, str | None] | None = None,
    statuses: Mapping[str, str] | None = None,
    windows: Mapping[str, str | None] | None = None,
) -> FinancialModelCatalog:
    """Собирает каталог из уже загруженного ModelTypeCatalog + размерностей."""

    definitions = definitions or {}
    statuses = statuses or {}
    windows = windows or {}
    indicators: dict[str, Indicator] = {}
    for metric_id, inputs in sorted(model_types.metric_inputs.items()):
        expr = model_types.metric_expressions.get(metric_id) or MetricExpression()
        unit = result_unit(metric_id, expr, model_types.metric_expressions, concept_dimensions, dimensions)
        variant_specs = model_types.variant_inputs.get(metric_id) or {}
        variants: dict[str, IndicatorVariant] = {}
        for variant_id, variant_inputs in sorted(variant_specs.items()):
            key = f"{metric_id}.{variant_id}"
            variant_expr = model_types.metric_expressions.get(key) or MetricExpression()
            variants[variant_id] = IndicatorVariant(
                id=variant_id,
                inputs=_concept_inputs(variant_inputs),
                unit=result_unit(key, variant_expr, model_types.metric_expressions, concept_dimensions, dimensions),
                window=windows.get(key),
                definition=definitions.get(key),
            )
        status = statuses.get(metric_id) or "active"
        if status not in INDICATOR_STATUSES:
            raise ValueError(f"{metric_id}: status должен быть active или deprecated")
        window = windows.get(metric_id)
        if window is not None and window not in WINDOWS:
            raise ValueError(f"{metric_id}: окно LTM или period")
        indicators[metric_id] = Indicator(
            id=metric_id,
            definition=definitions.get(metric_id),
            inputs=_concept_inputs(inputs),
            unit=unit,
            window=window,
            variants=variants,
            model_types=_applicability(model_types, metric_id),
            status=status,
            base=model_types.metric_bases.get(metric_id),
        )
    version = catalog_version_for(indicators)
    return FinancialModelCatalog(
        indicators=indicators,
        version=version,
        stamp=stamp,
        row_fallback_ids=frozenset(model_types.row_fallbacks),
    )


def result_unit(
    name: str,
    expr: MetricExpression,
    expressions: Mapping[str, MetricExpression],
    concept_dimensions: Mapping[str, str],
    dimensions: DimensionCatalog,
) -> str:
    """Единица/размерность результата показателя (не входов)."""

    resolved = _resolve(name, expr, expressions)
    num = [*resolved.numerator_plus, *resolved.numerator_minus]
    den = [*resolved.denominator_plus, *resolved.denominator_minus]
    if resolved.one_of or (num and den):
        return "ratio"
    if resolved.rate and num and not den:
        # NPV-подобные: результат в размерности числителя (обычно money).
        return _dim(name, num[0], concept_dimensions)
    if num and not den:
        # IRR и сходные потоковые показатели без знаменателя → ratio.
        return "ratio"
    if resolved.rate and not num and not den:
        return "ratio"
    return "ratio"


def _resolve(
    name: str,
    expr: MetricExpression,
    expressions: Mapping[str, MetricExpression],
) -> MetricExpression:
    if expr.base and not _own_terms(expr):
        base = expressions.get(expr.base)
        if base is None:
            raise ValueError(f"{name}: base {expr.base} без формулы")
        return _resolve(expr.base, base, expressions)
    return expr


def _own_terms(expr: MetricExpression) -> bool:
    return bool(
        expr.numerator_plus
        or expr.numerator_minus
        or expr.denominator_plus
        or expr.denominator_minus
        or expr.one_of
        or expr.rate
    )


def _concept_inputs(spec: MetricInputs) -> frozenset[str]:
    return frozenset(spec.all_of | spec.one_of)


def _applicability(catalog: ModelTypeCatalog, metric_id: str) -> dict[str, str]:
    return {type_id: catalog.use(type_id, metric_id) for type_id in sorted(catalog.types)}


def _dim(owner: str, name: str, concept_dimensions: Mapping[str, str]) -> str:
    dim = concept_dimensions.get(name)
    if dim is None:
        raise ValueError(f"{owner}: нет размерности у {name}")
    return dim


def validate_indicator_records(records: Sequence[Mapping]) -> None:
    """Проверяет список записей каталога на контракт схемы (без I/O)."""

    seen: set[str] = set()
    for raw in records:
        if not isinstance(raw, Mapping):
            raise TypeError("запись показателя должна быть объектом")
        metric_id = raw.get("id")
        if not isinstance(metric_id, str) or not metric_id:
            raise ValueError("показатель: нужен непустой id")
        if metric_id in seen:
            raise ValueError(f"дубликат показателя: {metric_id}")
        seen.add(metric_id)
        inputs = raw.get("inputs")
        if not isinstance(inputs, list) or any(not isinstance(item, str) or not item for item in inputs):
            raise ValueError(f"{metric_id}: inputs — список concept_id")
        unit = raw.get("unit")
        if not isinstance(unit, str) or not unit:
            raise ValueError(f"{metric_id}: нужен unit")
        status = raw.get("status", "active")
        if status not in INDICATOR_STATUSES:
            raise ValueError(f"{metric_id}: status active|deprecated")
        window = raw.get("window")
        if window is not None and window not in WINDOWS:
            raise ValueError(f"{metric_id}: окно LTM или period")
        variants = raw.get("variants") or {}
        if not isinstance(variants, Mapping):
            raise TypeError(f"{metric_id}: variants — объект")
        model_types = raw.get("model_types") or {}
        if not isinstance(model_types, Mapping):
            raise TypeError(f"{metric_id}: model_types — объект")
