"""Единый контракт целостности каталогов (§5.1, §5.7). Без ввода-вывода."""

from __future__ import annotations

from collections.abc import Mapping

from finance_analysis.domain.dimensions import DimensionCatalog
from finance_analysis.domain.model_type import Composed, MetricInputs, RowFallback, Side
from finance_analysis.domain.validation.model_types import (
    ModelTypeInvalid,
    validate_model_types,
)

_COVERAGE_KEYS = frozenset({"row_fallbacks", "interest_order", "metrics", "tolerance"})


class CatalogIntegrityError(ValueError):
    """Каталоги понятий, метрик и типов не сходятся. Сервис с таким набором не стартует."""


def validate_catalog_integrity(
    *,
    concepts: frozenset[str],
    concept_dimensions: Mapping[str, str],
    dimensions: DimensionCatalog,
    model_documents: dict[str, dict],
    metric_inputs: dict[str, MetricInputs],
    variant_inputs: dict[str, dict[str, MetricInputs]],
    composed: dict[str, Composed],
    metric_bases: Mapping[str, str],
    metric_rates: Mapping[str, str],
    interest_order: Mapping[str, tuple[str, ...]],
    row_fallbacks: Mapping[str, RowFallback],
    coverage_keys: frozenset[str] | None = None,
) -> None:
    """Полный контракт: понятия, метрики, типы, единицы, связи порядка, циклы, неизвестные id."""

    _unknown_coverage_keys(coverage_keys)
    _row_fallbacks(row_fallbacks, concepts)
    _metric_inputs(metric_inputs, variant_inputs, concepts, row_fallbacks)
    _interest_order(interest_order, concepts, row_fallbacks, metric_inputs, variant_inputs)
    _metric_base_cycles(metric_bases, metric_inputs)
    _units(composed, metric_inputs, variant_inputs, metric_rates, concept_dimensions, dimensions)
    try:
        validate_model_types(
            model_documents,
            concepts=concepts,
            metric_inputs=metric_inputs,
            variant_inputs=variant_inputs,
        )
    except ModelTypeInvalid as exc:
        raise CatalogIntegrityError(str(exc)) from exc


def _unknown_coverage_keys(keys: frozenset[str] | None) -> None:
    if keys is None:
        return
    unknown = sorted(keys - _COVERAGE_KEYS)
    if unknown:
        raise CatalogIntegrityError(f"configs/metrics: неизвестные ключи: {', '.join(unknown)}")


def _row_fallbacks(fallbacks: Mapping[str, RowFallback], concepts: frozenset[str]) -> None:
    for name, item in fallbacks.items():
        if name != item.id:
            raise CatalogIntegrityError(f"row_fallbacks.{name}: id должен совпадать с ключом")
        if name in concepts:
            raise CatalogIntegrityError(f"row_fallbacks.{name}: совпадает с concept_id")
        if item.canonical not in concepts:
            raise CatalogIntegrityError(f"row_fallbacks.{name}: canonical вне каталога: {item.canonical}")
        if item.canonical == name:
            raise CatalogIntegrityError(f"row_fallbacks.{name}: canonical не должен совпадать с id")
        if not item.source_label:
            raise CatalogIntegrityError(f"row_fallbacks.{name}: нужен source_label")
        if not item.matching_rule:
            raise CatalogIntegrityError(f"row_fallbacks.{name}: нужен matching.rule")


def _metric_inputs(
    inputs: dict[str, MetricInputs],
    variants: dict[str, dict[str, MetricInputs]],
    concepts: frozenset[str],
    fallbacks: Mapping[str, RowFallback],
) -> None:
    named = dict(inputs)
    for metric, specs in variants.items():
        for variant, spec in specs.items():
            named[f"{metric}.{variant}"] = spec
    for name, spec in named.items():
        for item in sorted(spec.all_of | spec.one_of):
            if item in concepts:
                continue
            if item in fallbacks:
                raise CatalogIntegrityError(
                    f"{name}: вход метрики {item} объявлен как row_fallback, а не concept_id"
                )
            raise CatalogIntegrityError(f"{name}: понятие вне каталога: {item}")


def _interest_order(
    order: Mapping[str, tuple[str, ...]],
    concepts: frozenset[str],
    fallbacks: Mapping[str, RowFallback],
    inputs: dict[str, MetricInputs],
    variants: dict[str, dict[str, MetricInputs]],
) -> None:
    known_slots = set(inputs)
    for metric, specs in variants.items():
        known_slots.update(specs)
        known_slots.update(f"{metric}.{variant}" for variant in specs)
    used_fallbacks: set[str] = set()
    for key, names in order.items():
        if key not in known_slots:
            raise CatalogIntegrityError(f"interest_order.{key}: нет такой метрики или варианта")
        if not names:
            raise CatalogIntegrityError(f"interest_order.{key}: пустой список")
        for name in names:
            if name in concepts:
                continue
            if name in fallbacks:
                used_fallbacks.add(name)
                continue
            raise CatalogIntegrityError(
                f"interest_order.{key}: {name} не concept_id и не row_fallback"
            )
    unused = sorted(set(fallbacks) - used_fallbacks)
    if unused:
        raise CatalogIntegrityError(f"row_fallbacks не используется: {', '.join(unused)}")


def _metric_base_cycles(bases: Mapping[str, str], inputs: dict[str, MetricInputs]) -> None:
    for name, base in bases.items():
        if name not in inputs:
            raise CatalogIntegrityError(f"{name}: base у необъявленной метрики")
        if base not in inputs:
            raise CatalogIntegrityError(f"{name}: base {base} не объявлен")
    for start in bases:
        seen: set[str] = set()
        current = start
        while current in bases:
            if current in seen:
                raise CatalogIntegrityError(f"{start}: цикл base метрик")
            seen.add(current)
            current = bases[current]


def _units(
    composed: dict[str, Composed],
    inputs: dict[str, MetricInputs],
    variants: dict[str, dict[str, MetricInputs]],
    rates: Mapping[str, str],
    concept_dimensions: Mapping[str, str],
    dimensions: DimensionCatalog,
) -> None:
    for name, rate in rates.items():
        dim = concept_dimensions.get(rate)
        if dim is None:
            raise CatalogIntegrityError(f"{name}: rate {rate} вне каталога")
        if dim != "ratio":
            raise CatalogIntegrityError(f"{name}: rate {rate} должен быть размерности ratio")
    for name, formula in composed.items():
        num_dim = _side_units(name, "numerator", formula.numerator, concept_dimensions, dimensions)
        den_dim = _side_units(name, "denominator", formula.denominator, concept_dimensions, dimensions)
        ratio = dimensions.combine("ratio", num_dim, den_dim)
        # Коэффициент покрытия безразмерен: money/money → {}.
        if ratio is None or dict(ratio):
            raise CatalogIntegrityError(f"{name}: единицы числителя и знаменателя несовместимы")
    named: dict[str, MetricInputs] = dict(inputs)
    for metric, specs in variants.items():
        for variant, spec in specs.items():
            named[f"{metric}.{variant}"] = spec
    for name, spec in named.items():
        if name in composed or not spec.one_of:
            continue
        rate = rates.get(name) or rates.get(name.split(".", 1)[0])
        dens = spec.all_of - ({rate} if rate else set())
        if len(dens) != 1:
            continue
        den = next(iter(dens))
        den_dim = _dimension(name, den, concept_dimensions)
        for num in sorted(spec.one_of):
            num_dim = _dimension(name, num, concept_dimensions)
            if dimensions.combine("ratio", num_dim, den_dim) is None:
                raise CatalogIntegrityError(f"{name}: единицы {num}/{den} несовместимы")


def _side_units(
    name: str,
    side_name: str,
    side: Side,
    concept_dimensions: Mapping[str, str],
    dimensions: DimensionCatalog,
) -> str:
    terms = [*side.plus, *side.minus]
    if not terms:
        raise CatalogIntegrityError(f"{name}: {side_name} пуст")
    first = _dimension(name, terms[0], concept_dimensions)
    for item in terms[1:]:
        other = _dimension(name, item, concept_dimensions)
        if dimensions.combine("add", first, other) is None:
            raise CatalogIntegrityError(f"{name}: {side_name} единицы несовместимы ({terms[0]}, {item})")
    return first


def _dimension(owner: str, name: str, concept_dimensions: Mapping[str, str]) -> str:
    dim = concept_dimensions.get(name)
    if dim is None:
        raise CatalogIntegrityError(f"{owner}: нет размерности у {name}")
    return dim
