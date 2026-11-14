"""Financial Model Catalog — показатель как сущность (фаза 3 метаслоя, G1).

Каталог читается поверх `configs/metrics` + таксономия + применимость
`model_types`. Формулы не выводятся из `composed_of`. Версия каталога входит
в `SemanticModelVersion.components.metrics.version`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

from finance_analysis.domain.book import canonical_json
from finance_analysis.domain.dimensions import DimensionCatalog
from finance_analysis.domain.model_type import (
    MetricExpression,
    MetricInputs,
    ModelTypeCatalog,
)

_SCHEMA_PATH = Path(__file__).resolve().parent / "contracts" / "financial_model_catalog.json"

INDICATOR_STATUSES = frozenset({"active", "deprecated"})
WINDOWS = frozenset({"LTM", "period"})
USES = frozenset({"required", "optional", "not_applicable"})


@dataclass(frozen=True)
class FormulaSide:
    plus: tuple[str, ...] = ()
    minus: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {"plus": list(self.plus), "minus": list(self.minus)}

    def empty(self) -> bool:
        return not self.plus and not self.minus


@dataclass(frozen=True)
class IndicatorFormula:
    """Декларативная структура формулы показателя (не исполняемый код)."""

    numerator: FormulaSide | None = None
    denominator: FormulaSide | None = None
    one_of: frozenset[str] = field(default_factory=frozenset)
    rate: str | tuple[str, ...] | None = None
    base: str | None = None
    terminal: str | None = None
    compare_with: str | None = None
    add_back: tuple[str, str] | None = None

    def as_dict(self) -> dict:
        body: dict = {}
        if self.base is not None:
            body["base"] = self.base
        if self.numerator is not None and not self.numerator.empty():
            body["numerator"] = self.numerator.as_dict()
        if self.denominator is not None and not self.denominator.empty():
            body["denominator"] = self.denominator.as_dict()
        if self.one_of:
            body["one_of"] = sorted(self.one_of)
        if isinstance(self.rate, tuple):
            body["rate"] = list(self.rate) if len(self.rate) > 1 else self.rate[0]
        elif self.rate is not None:
            body["rate"] = self.rate
        if self.terminal is not None:
            body["terminal"] = self.terminal
        if self.compare_with is not None:
            body["compare_with"] = self.compare_with
        if self.add_back is not None:
            body["add_back"] = {"concept": self.add_back[0], "tax_complement": self.add_back[1]}
        return body


@dataclass(frozen=True)
class IndicatorInputs:
    """Входы показателя с сохранением all_of / one_of."""

    all_of: frozenset[str] = field(default_factory=frozenset)
    one_of: frozenset[str] = field(default_factory=frozenset)

    @property
    def concepts(self) -> frozenset[str]:
        return self.all_of | self.one_of

    def as_dict(self) -> dict:
        return {"all_of": sorted(self.all_of), "one_of": sorted(self.one_of)}


@dataclass(frozen=True)
class ModelTypeUse:
    """Применимость показателя к типу модели + выбранный вариант формулы."""

    use: str
    variant: str | None = None

    def as_dict(self) -> dict:
        body = {"use": self.use}
        if self.variant is not None:
            body["variant"] = self.variant
        return body


@dataclass(frozen=True)
class IndicatorVariant:
    """Вариант показателя (например dscr.pf / dscr.corporate_covenant)."""

    id: str
    inputs: IndicatorInputs
    unit: str
    formula: IndicatorFormula
    window: str | None = None
    definition: str | None = None

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "definition": self.definition,
            "inputs": self.inputs.as_dict(),
            "input_concepts": sorted(self.inputs.concepts),
            "unit": self.unit,
            "window": self.window,
            "formula": self.formula.as_dict(),
        }


@dataclass(frozen=True)
class Indicator:
    """Публичная запись показателя финансовой модели.

    `inputs` — all_of / one_of concept_id таксономии (row_fallbacks сюда не входят).
    `formula` — декларативная структура числителя/знаменателя/ставки/base.
    `model_types` — применимость и выбранный variant по типу модели.
    `status` — active | deprecated.
    """

    id: str
    inputs: IndicatorInputs
    unit: str
    formula: IndicatorFormula
    definition: str | None = None
    window: str | None = None
    variants: dict[str, IndicatorVariant] = field(default_factory=dict)
    model_types: dict[str, ModelTypeUse] = field(default_factory=dict)
    status: str = "active"
    base: str | None = None

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "definition": self.definition,
            "inputs": self.inputs.as_dict(),
            "input_concepts": sorted(self.inputs.concepts),
            "unit": self.unit,
            "window": self.window,
            "formula": self.formula.as_dict(),
            "variants": {name: item.as_dict() for name, item in sorted(self.variants.items())},
            "model_types": {name: item.as_dict() for name, item in sorted(self.model_types.items())},
            "status": self.status,
            "base": self.base,
        }


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
                inputs=_structured_inputs(variant_inputs),
                unit=result_unit(
                    key, variant_expr, model_types.metric_expressions, concept_dimensions, dimensions
                ),
                formula=formula_from_expression(variant_expr),
                window=windows.get(key),
                definition=definitions.get(key),
            )
        status = statuses.get(metric_id) or "active"
        if status not in INDICATOR_STATUSES:
            raise ValueError(f"{metric_id}: status должен быть active или deprecated")
        window = windows.get(metric_id)
        if window is not None and window not in WINDOWS:
            raise ValueError(f"{metric_id}: окно LTM или period")
        base = model_types.metric_bases.get(metric_id)
        indicators[metric_id] = Indicator(
            id=metric_id,
            definition=definitions.get(metric_id),
            inputs=_structured_inputs(inputs),
            unit=unit,
            formula=formula_from_expression(expr),
            window=window,
            variants=variants,
            model_types=_applicability(model_types, metric_id),
            status=status,
            base=base,
        )
    version = catalog_version_for(indicators)
    catalog = FinancialModelCatalog(
        indicators=indicators,
        version=version,
        stamp=stamp,
        row_fallback_ids=frozenset(model_types.row_fallbacks),
    )
    validate_financial_catalog_integrity(catalog)
    return catalog


def formula_from_expression(expr: MetricExpression) -> IndicatorFormula:
    """Переносит декларативную структуру MetricExpression в публичную формулу."""

    rate = expr.rates if len(expr.rates) > 1 else expr.rate
    if expr.base and not _own_terms(expr):
        return IndicatorFormula(base=expr.base, rate=rate)
    numerator = FormulaSide(expr.numerator_plus, expr.numerator_minus)
    denominator = FormulaSide(expr.denominator_plus, expr.denominator_minus)
    return IndicatorFormula(
        numerator=None if numerator.empty() else numerator,
        denominator=None if denominator.empty() else denominator,
        one_of=frozenset(expr.one_of),
        rate=rate,
        terminal=expr.terminal,
        compare_with=expr.compare_with,
        add_back=expr.add_back,
        base=expr.base,
    )


def result_unit(
    name: str,
    expr: MetricExpression,
    expressions: Mapping[str, MetricExpression],
    concept_dimensions: Mapping[str, str],
    dimensions: DimensionCatalog,
) -> str:
    """Единица/размерность результата показателя (не входов)."""

    del dimensions  # размерности результата выводятся из структуры формулы
    resolved = _resolve(name, expr, expressions)
    num = [*resolved.numerator_plus, *resolved.numerator_minus]
    den = [*resolved.denominator_plus, *resolved.denominator_minus]
    if resolved.one_of or (num and den):
        return "ratio"
    if resolved.rate and num and not den:
        # NPV-подобные: результат в размерности числителя (обычно money).
        return _dim(name, num[0], concept_dimensions)
    if resolved.aggregate == "sum" and num and not den:
        return _dim(name, num[0], concept_dimensions)
    if name == "ncf" and num and not den:
        # Сумма трёх потоков. Ставку не вешаем: ветка IRR остаётся отношением.
        return "money"
    if resolved.compare_with and num and not den:
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
        or expr.rates
        or expr.terminal
        or expr.compare_with
        or expr.add_back
    )


def _structured_inputs(spec: MetricInputs) -> IndicatorInputs:
    return IndicatorInputs(all_of=frozenset(spec.all_of), one_of=frozenset(spec.one_of))


def _applicability(catalog: ModelTypeCatalog, metric_id: str) -> dict[str, ModelTypeUse]:
    found: dict[str, ModelTypeUse] = {}
    for type_id in sorted(catalog.types):
        use = catalog.use(type_id, metric_id)
        if use not in USES:
            raise ValueError(f"{metric_id}: неизвестный use у {type_id}: {use}")
        variant = catalog.types[type_id].variants.get(metric_id)
        found[type_id] = ModelTypeUse(use=use, variant=variant)
    return found


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
        _validate_inputs(metric_id, raw.get("inputs"))
        unit = raw.get("unit")
        if not isinstance(unit, str) or not unit:
            raise ValueError(f"{metric_id}: нужен unit")
        status = raw.get("status", "active")
        if status not in INDICATOR_STATUSES:
            raise ValueError(f"{metric_id}: status active|deprecated")
        window = raw.get("window")
        if window is not None and window not in WINDOWS:
            raise ValueError(f"{metric_id}: окно LTM или period")
        formula = raw.get("formula")
        if formula is not None and not isinstance(formula, Mapping):
            raise TypeError(f"{metric_id}: formula — объект")
        variants = raw.get("variants") or {}
        if not isinstance(variants, Mapping):
            raise TypeError(f"{metric_id}: variants — объект")
        for variant_id, variant in variants.items():
            if not isinstance(variant, Mapping):
                raise TypeError(f"{metric_id}.{variant_id}: вариант — объект")
            _validate_inputs(f"{metric_id}.{variant_id}", variant.get("inputs"))
            if "formula" in variant and not isinstance(variant.get("formula"), Mapping):
                raise TypeError(f"{metric_id}.{variant_id}: formula — объект")
        model_types = raw.get("model_types") or {}
        if not isinstance(model_types, Mapping):
            raise TypeError(f"{metric_id}: model_types — объект")
        for type_id, body in model_types.items():
            if not isinstance(body, Mapping):
                raise TypeError(f"{metric_id}.model_types.{type_id}: объект")
            use = body.get("use")
            if use not in USES:
                raise ValueError(f"{metric_id}.model_types.{type_id}: use required|optional|not_applicable")
            variant = body.get("variant")
            if variant is not None and (not isinstance(variant, str) or not variant):
                raise ValueError(f"{metric_id}.model_types.{type_id}: variant — непустая строка")


def _validate_inputs(owner: str, inputs: object) -> None:
    if not isinstance(inputs, Mapping):
        raise TypeError(f"{owner}: inputs — объект all_of/one_of")
    for key in ("all_of", "one_of"):
        values = inputs.get(key, [])
        if not isinstance(values, list) or any(not isinstance(item, str) or not item for item in values):
            raise ValueError(f"{owner}: inputs.{key} — список concept_id")


@lru_cache(maxsize=1)
def catalog_json_schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_catalog_schema(payload: Mapping) -> None:
    """Проверяет снимок каталога по JSON Schema Draft 2020-12. Блокирует публикацию."""

    Draft202012Validator.check_schema(catalog_json_schema())
    Draft202012Validator(catalog_json_schema()).validate(dict(payload))


def validate_financial_catalog_integrity(catalog: FinancialModelCatalog) -> None:
    """Схема + межполевые/ссылочные инварианты публичного каталога."""

    expected = catalog_version_for(catalog.indicators)
    if catalog.version != expected:
        raise ValueError(
            f"version каталога {catalog.version} не соответствует содержимому indicators {expected}"
        )
    payload = catalog.as_dict()
    validate_catalog_schema(payload)
    if payload.get("version") != catalog.version:
        raise ValueError("version снимка каталога не совпадает с FinancialModelCatalog.version")
    if payload.get("stamp") != catalog.stamp:
        raise ValueError("stamp снимка каталога не совпадает с FinancialModelCatalog.stamp")
    known = frozenset(catalog.indicators)
    for metric_id, item in catalog.indicators.items():
        if item.id != metric_id:
            raise ValueError(f"indicators[{metric_id}].id != ключ ({item.id})")
        _assert_input_concepts(metric_id, item.inputs, item.as_dict().get("input_concepts"))
        if item.base is not None and item.base not in known:
            raise ValueError(f"{metric_id}: base {item.base} вне каталога")
        if item.formula.base is not None and item.formula.base not in known:
            raise ValueError(f"{metric_id}: formula.base {item.formula.base} вне каталога")
        for type_id, use in item.model_types.items():
            if use.variant is not None and use.variant not in item.variants:
                raise ValueError(
                    f"{metric_id}.model_types.{type_id}: variant {use.variant} нет в variants"
                )
        for variant_id, variant in item.variants.items():
            if variant.id != variant_id:
                raise ValueError(f"{metric_id}.variants[{variant_id}].id != ключ ({variant.id})")
            _assert_input_concepts(
                f"{metric_id}.{variant_id}",
                variant.inputs,
                variant.as_dict().get("input_concepts"),
            )
            if variant.formula.base is not None and variant.formula.base not in known:
                raise ValueError(
                    f"{metric_id}.{variant_id}: formula.base {variant.formula.base} вне каталога"
                )


def _assert_input_concepts(owner: str, inputs: IndicatorInputs, flat: object) -> None:
    if not isinstance(flat, list):
        raise TypeError(f"{owner}: input_concepts — список")
    if frozenset(flat) != inputs.concepts:
        raise ValueError(f"{owner}: input_concepts != inputs.all_of ∪ inputs.one_of")
