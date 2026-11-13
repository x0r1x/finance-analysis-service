"""Единый контракт целостности каталогов (§5.1, §5.7). Без ввода-вывода."""

from __future__ import annotations

from collections.abc import Mapping

from finance_analysis.domain.dimensions import DimensionCatalog
from finance_analysis.domain.model_type import (
    MetricExpression,
    MetricInputs,
    RowFallback,
)
from finance_analysis.domain.validation.model_types import (
    ModelTypeInvalid,
    validate_model_types,
)

# Слоты, которые реально читает код (metrics.py / covenant.py).
INTEREST_ORDER_SLOTS = frozenset({"icr", "icr_ebit", "corporate_covenant", "ocf_covenant", "pf"})
INTEREST_CANONICAL = "interest"
# Декларативные rule id. Рантайм по ним не диспатчит (выбор B).
MATCHING_RULES = frozenset({"interest_basis_paid"})

_COVERAGE_KEYS = frozenset({"row_fallbacks", "interest_order", "metrics", "tolerance"})
_FALLBACK_KEYS = frozenset({"canonical", "binding_key", "matching"})
_MATCHING_KEYS = frozenset({"rule"})
_METRIC_KEYS = frozenset(
    {"numerator", "denominator", "variants", "base", "rate", "window", "definition", "status"}
)
_SIDE_KEYS = frozenset({"plus", "minus"})


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
    metric_expressions: Mapping[str, MetricExpression],
    metric_bases: Mapping[str, str],
    interest_order: Mapping[str, tuple[str, ...]],
    row_fallbacks: Mapping[str, RowFallback],
    coverage_document: Mapping[str, object] | None = None,
) -> None:
    """Полный контракт: понятия, метрики, типы, единицы, порядок процентов, циклы, ключи."""

    if coverage_document is not None:
        _coverage_shape(coverage_document)
    _row_fallbacks(row_fallbacks, concepts)
    _metric_inputs(metric_inputs, variant_inputs, concepts, row_fallbacks)
    _interest_order(interest_order, concepts, row_fallbacks)
    _metric_dependency_cycles(metric_bases, metric_inputs, variant_inputs, metric_expressions)
    _units(metric_expressions, concept_dimensions, dimensions)
    try:
        validate_model_types(
            model_documents,
            concepts=concepts,
            metric_inputs=metric_inputs,
            variant_inputs=variant_inputs,
        )
    except ModelTypeInvalid as exc:
        raise CatalogIntegrityError(str(exc)) from exc


def _coverage_shape(document: Mapping[str, object]) -> None:
    unknown = sorted(set(document) - _COVERAGE_KEYS)
    if unknown:
        raise CatalogIntegrityError(f"configs/metrics: неизвестные ключи: {', '.join(unknown)}")
    fallbacks = document.get("row_fallbacks") or {}
    if not isinstance(fallbacks, dict):
        raise CatalogIntegrityError("row_fallbacks: объект")
    for name, body in fallbacks.items():
        if not isinstance(body, dict):
            raise CatalogIntegrityError(f"row_fallbacks.{name}: объект")
        bad = sorted(set(body) - _FALLBACK_KEYS)
        if bad:
            raise CatalogIntegrityError(f"row_fallbacks.{name}: неизвестные ключи: {', '.join(bad)}")
        matching = body.get("matching") or {}
        if not isinstance(matching, dict):
            raise CatalogIntegrityError(f"row_fallbacks.{name}.matching: объект")
        bad = sorted(set(matching) - _MATCHING_KEYS)
        if bad:
            raise CatalogIntegrityError(f"row_fallbacks.{name}.matching: неизвестные ключи: {', '.join(bad)}")
    order = document.get("interest_order") or {}
    if not isinstance(order, dict):
        raise CatalogIntegrityError("interest_order: объект")
    metrics = document.get("metrics") or {}
    if not isinstance(metrics, dict):
        raise CatalogIntegrityError("metrics: объект")
    for name, body in metrics.items():
        _metric_body_keys(str(name), body)


_BASE_EXCLUSIVE = frozenset({"numerator", "denominator", "rate"})


def _metric_body_keys(name: str, body: object, *, allow_variants: bool = True) -> None:
    if not isinstance(body, dict):
        raise CatalogIntegrityError(f"{name}: формула метрики не объект")
    bad = sorted(set(body) - _METRIC_KEYS)
    if bad:
        raise CatalogIntegrityError(f"{name}: неизвестные ключи: {', '.join(bad)}")
    if "base" in body:
        base = body.get("base")
        if not isinstance(base, str) or not base:
            raise CatalogIntegrityError(f"{name}: base — непустая строка")
        clash = sorted(key for key in _BASE_EXCLUSIVE if key in body)
        if clash:
            raise CatalogIntegrityError(
                f"{name}: base — самостоятельное наследование, нельзя вместе с {', '.join(clash)}"
            )
    for side_name in ("numerator", "denominator"):
        if side_name in body:
            _formula_term(name, side_name, body.get(side_name))
    if "rate" in body:
        rate = body.get("rate")
        if not isinstance(rate, str) or not rate:
            raise CatalogIntegrityError(f"{name}: rate — непустая строка")
    if "variants" in body:
        if not allow_variants:
            raise CatalogIntegrityError(f"{name}: вложенные variants не поддерживаются")
        variants = body.get("variants")
        if not isinstance(variants, dict):
            raise CatalogIntegrityError(f"{name}.variants: объект")
        for variant, spec in variants.items():
            _metric_body_keys(f"{name}.{variant}", spec, allow_variants=False)


def _formula_term(owner: str, field: str, value: object) -> None:
    """numerator/denominator: строка, список строк или непустой объект plus/minus."""

    if isinstance(value, str):
        if not value:
            raise CatalogIntegrityError(f"{owner}: {field} пустая строка")
        return
    if isinstance(value, list):
        if not value or any(not isinstance(item, str) or not item for item in value):
            raise CatalogIntegrityError(f"{owner}: {field} — непустой список строк")
        return
    if isinstance(value, dict):
        bad = sorted(set(value) - _SIDE_KEYS)
        if bad:
            raise CatalogIntegrityError(f"{owner}.{field}: неизвестные ключи: {', '.join(bad)}")
        total = 0
        for side in ("plus", "minus"):
            if side not in value:
                continue
            items = value.get(side)
            if not isinstance(items, list) or any(not isinstance(item, str) or not item for item in items):
                raise CatalogIntegrityError(f"{owner}.{field}.{side}: список строк")
            total += len(items)
        if total == 0:
            raise CatalogIntegrityError(f"{owner}: {field} пустой (нужен хотя бы один plus/minus)")
        return
    raise CatalogIntegrityError(f"{owner}: {field} — строка, список строк или объект plus/minus")


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
        if not item.binding_key:
            raise CatalogIntegrityError(f"row_fallbacks.{name}: нужен binding_key")
        if item.matching_rule not in MATCHING_RULES:
            raise CatalogIntegrityError(
                f"row_fallbacks.{name}: неизвестный matching.rule: {item.matching_rule}"
            )


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
) -> None:
    unknown_slots = sorted(set(order) - INTEREST_ORDER_SLOTS)
    if unknown_slots:
        raise CatalogIntegrityError(f"interest_order: неизвестные слоты: {', '.join(unknown_slots)}")
    missing = sorted(INTEREST_ORDER_SLOTS - set(order))
    if missing:
        raise CatalogIntegrityError(f"interest_order: нет слотов: {', '.join(missing)}")
    used_fallbacks: set[str] = set()
    for key, names in order.items():
        if not names:
            raise CatalogIntegrityError(f"interest_order.{key}: пустой список")
        if len(names) != len(set(names)):
            raise CatalogIntegrityError(f"interest_order.{key}: повторы кандидатов")
        for name in names:
            if name in concepts:
                if name != INTEREST_CANONICAL:
                    raise CatalogIntegrityError(
                        f"interest_order.{key}: понятие {name} не {INTEREST_CANONICAL}"
                    )
                continue
            if name in fallbacks:
                item = fallbacks[name]
                if item.canonical != INTEREST_CANONICAL:
                    raise CatalogIntegrityError(
                        f"interest_order.{key}: fallback {name} canonical не {INTEREST_CANONICAL}"
                    )
                used_fallbacks.add(name)
                continue
            raise CatalogIntegrityError(
                f"interest_order.{key}: {name} не concept_id и не row_fallback"
            )
    unused = sorted(set(fallbacks) - used_fallbacks)
    if unused:
        raise CatalogIntegrityError(f"row_fallbacks не используется: {', '.join(unused)}")


def _metric_dependency_cycles(
    bases: Mapping[str, str],
    inputs: dict[str, MetricInputs],
    variants: dict[str, dict[str, MetricInputs]],
    expressions: Mapping[str, MetricExpression],
) -> None:
    """Полный граф зависимостей: top-level base и base у вариантов (`metric_bases`)."""

    known = set(inputs) | set(expressions)
    for metric, specs in variants.items():
        known.update(f"{metric}.{variant}" for variant in specs)
    edges = dict(bases)
    for name, base in edges.items():
        if name not in known:
            raise CatalogIntegrityError(f"{name}: base у необъявленной метрики")
        if base not in known:
            raise CatalogIntegrityError(f"{name}: base {base} не объявлен")
    for start in edges:
        seen: set[str] = set()
        current = start
        while current in edges:
            if current in seen:
                raise CatalogIntegrityError(f"{start}: цикл зависимостей метрик")
            seen.add(current)
            current = edges[current]


def _units(
    expressions: Mapping[str, MetricExpression],
    concept_dimensions: Mapping[str, str],
    dimensions: DimensionCatalog,
) -> None:
    for name in sorted(expressions):
        expr = expressions[name]
        if expr.base and not _has_own_terms(expr):
            # Чистый base: единицы проверяются на разрешённой формуле.
            resolved = _resolve_expression(name, expressions)
            _expression_units(name, resolved, concept_dimensions, dimensions)
            continue
        _expression_units(name, expr, concept_dimensions, dimensions)


def _has_own_terms(expr: MetricExpression) -> bool:
    return bool(
        expr.numerator_plus
        or expr.numerator_minus
        or expr.denominator_plus
        or expr.denominator_minus
        or expr.one_of
        or expr.rate
    )


def _resolve_expression(name: str, expressions: Mapping[str, MetricExpression]) -> MetricExpression:
    expr = expressions[name]
    if not expr.base:
        return expr
    if any(
        (
            expr.numerator_plus,
            expr.numerator_minus,
            expr.denominator_plus,
            expr.denominator_minus,
            expr.one_of,
            expr.rate,
        )
    ):
        return expr
    base = expressions.get(expr.base)
    if base is None:
        raise CatalogIntegrityError(f"{name}: base {expr.base} без формулы")
    return _resolve_expression(expr.base, expressions)


def _expression_units(
    name: str,
    expr: MetricExpression,
    concept_dimensions: Mapping[str, str],
    dimensions: DimensionCatalog,
) -> None:
    if expr.rate is not None:
        rate_dim = _dimension(name, expr.rate, concept_dimensions)
        if rate_dim != "ratio":
            raise CatalogIntegrityError(f"{name}: rate {expr.rate} должен быть размерности ratio")
    num_terms = [*expr.numerator_plus, *expr.numerator_minus]
    den_terms = [*expr.denominator_plus, *expr.denominator_minus]
    if num_terms:
        num_dim = _terms_add(name, "numerator", num_terms, concept_dimensions, dimensions)
    else:
        num_dim = None
    if den_terms:
        den_dim = _terms_add(name, "denominator", den_terms, concept_dimensions, dimensions)
    else:
        den_dim = None
    if expr.one_of:
        if den_dim is None or len(den_terms) != 1:
            raise CatalogIntegrityError(f"{name}: one_of требует один знаменатель")
        for num in sorted(expr.one_of):
            alt = _dimension(name, num, concept_dimensions)
            _require_dimensionless(name, alt, den_dim, dimensions, num, den_terms[0])
        return
    if num_dim is None or den_dim is None:
        return
    _require_dimensionless(
        name,
        num_dim,
        den_dim,
        dimensions,
        "/".join(num_terms) or "numerator",
        "/".join(den_terms) or "denominator",
    )


def _terms_add(
    name: str,
    side_name: str,
    terms: list[str],
    concept_dimensions: Mapping[str, str],
    dimensions: DimensionCatalog,
) -> str:
    first = _dimension(name, terms[0], concept_dimensions)
    for item in terms[1:]:
        other = _dimension(name, item, concept_dimensions)
        if dimensions.combine("add", first, other) is None:
            raise CatalogIntegrityError(f"{name}: {side_name} единицы несовместимы ({terms[0]}, {item})")
    return first


def _require_dimensionless(
    name: str,
    num_dim: str,
    den_dim: str,
    dimensions: DimensionCatalog,
    left: str,
    right: str,
) -> None:
    ratio = dimensions.combine("ratio", num_dim, den_dim)
    if ratio is None or dict(ratio):
        raise CatalogIntegrityError(f"{name}: единицы {left}/{right} несовместимы")


def _dimension(owner: str, name: str, concept_dimensions: Mapping[str, str]) -> str:
    dim = concept_dimensions.get(name)
    if dim is None:
        raise CatalogIntegrityError(f"{owner}: нет размерности у {name}")
    return dim
