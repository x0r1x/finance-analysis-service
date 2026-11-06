"""Загрузка configs/model_types и формул метрик (§5.7)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from finance_analysis.application.catalog import catalog_file
from finance_analysis.domain.book import canonical_json
from finance_analysis.domain.ids import concept_id as check_concept_id
from finance_analysis.domain.model_type import (
    Composed,
    MetricExpression,
    MetricInputs,
    ModelTypeCatalog,
    RowFallback,
    Side,
    Signal,
    TypeSpec,
)
from finance_analysis.domain.validation.catalog_integrity import (
    CatalogIntegrityError,
    validate_catalog_integrity,
)
from finance_analysis.domain.validation.model_types import ModelTypeInvalid


def model_types_dir() -> Path:
    return catalog_file().parent.parent / "model_types"


def metrics_file() -> Path:
    return catalog_file().parent.parent / "metrics" / "coverage.yaml"


def _inputs(body: dict, refs: dict[str, MetricInputs], name: str) -> MetricInputs:
    base = body.get("base")
    if isinstance(base, str):
        if base not in refs:
            raise ModelTypeInvalid(f"{name}: base {base} не объявлен раньше")
        return refs[base]
    all_of: set[str] = set()
    one_of: set[str] = set()
    numerator = body.get("numerator") or []
    if isinstance(numerator, dict):
        all_of.update(_names(numerator, name))
    else:
        if isinstance(numerator, str):
            numerator = [numerator]
        if not isinstance(numerator, list):
            raise ModelTypeInvalid(f"{name}: numerator должен быть списком понятий")
        if len(numerator) > 1:
            one_of.update(str(item) for item in numerator)
        else:
            all_of.update(str(item) for item in numerator)
    denominator = body.get("denominator")
    if isinstance(denominator, dict):
        all_of.update(_names(denominator, name))
    elif isinstance(denominator, str):
        all_of.add(denominator)
    rate = body.get("rate")
    if isinstance(rate, str):
        all_of.add(rate)
    return MetricInputs(frozenset(all_of), frozenset(one_of))


def _names(side: dict, name: str) -> set[str]:
    if set(side) - {"plus", "minus"}:
        raise ModelTypeInvalid(f"{name}: у слагаемых только plus и minus")
    return {str(item) for item in (side.get("plus") or [])} | {str(item) for item in (side.get("minus") or [])}


def _side(raw: dict) -> Side:
    return Side(tuple(str(item) for item in raw.get("plus") or []), tuple(str(item) for item in raw.get("minus") or []))


def _composed(body: dict, name: str) -> Composed | None:
    numerator = body.get("numerator")
    if not isinstance(numerator, dict):
        return None
    window = body.get("window")
    denominator = body.get("denominator")
    if window not in {"LTM", "period"}:
        raise ModelTypeInvalid(f"{name}: окно LTM или period")
    if not isinstance(denominator, dict):
        raise ModelTypeInvalid(f"{name}: знаменатель — plus и minus")
    den = _side(denominator)
    if not den.plus and not den.minus:
        raise ModelTypeInvalid(f"{name}: знаменатель пуст")
    return Composed(_side(numerator), den, str(window))


def _expression(body: dict, name: str) -> MetricExpression:
    base = body.get("base")
    if isinstance(base, str):
        return MetricExpression(base=str(base), rate=str(body["rate"]) if isinstance(body.get("rate"), str) else None)
    rate = str(body["rate"]) if isinstance(body.get("rate"), str) else None
    numerator = body.get("numerator")
    denominator = body.get("denominator")
    one_of: set[str] = set()
    num_plus: tuple[str, ...] = ()
    num_minus: tuple[str, ...] = ()
    den_plus: tuple[str, ...] = ()
    den_minus: tuple[str, ...] = ()
    if isinstance(numerator, dict):
        num_plus = tuple(str(item) for item in numerator.get("plus") or [])
        num_minus = tuple(str(item) for item in numerator.get("minus") or [])
    elif isinstance(numerator, list):
        if len(numerator) > 1:
            one_of = {str(item) for item in numerator}
        elif numerator:
            num_plus = (str(numerator[0]),)
    elif isinstance(numerator, str):
        num_plus = (str(numerator),)
    if isinstance(denominator, dict):
        den_plus = tuple(str(item) for item in denominator.get("plus") or [])
        den_minus = tuple(str(item) for item in denominator.get("minus") or [])
    elif isinstance(denominator, list):
        den_plus = tuple(str(item) for item in denominator)
    elif isinstance(denominator, str):
        den_plus = (str(denominator),)
    return MetricExpression(
        numerator_plus=num_plus,
        numerator_minus=num_minus,
        denominator_plus=den_plus,
        denominator_minus=den_minus,
        one_of=frozenset(one_of),
        rate=rate,
        base=None,
    )


def load_metric_inputs(path: Path | None = None) -> dict[str, MetricInputs]:
    inputs, _variants, _composed_formulas, _bases, _rates, _expressions = load_metric_catalog(path)
    return inputs


def load_metric_catalog(
    path: Path | None = None,
) -> tuple[
    dict[str, MetricInputs],
    dict[str, dict[str, MetricInputs]],
    dict[str, Composed],
    dict[str, str],
    dict[str, str],
    dict[str, MetricExpression],
]:
    document = yaml.safe_load((path or metrics_file()).read_text(encoding="utf-8")) or {}
    raw = document.get("metrics") if isinstance(document, dict) else None
    if not isinstance(raw, dict) or not raw:
        raise ModelTypeInvalid("configs/metrics: нет metrics")
    inputs: dict[str, MetricInputs] = {}
    variants: dict[str, dict[str, MetricInputs]] = {}
    composed: dict[str, Composed] = {}
    bases: dict[str, str] = {}
    rates: dict[str, str] = {}
    expressions: dict[str, MetricExpression] = {}
    for name, body in raw.items():
        if not isinstance(body, dict):
            raise ModelTypeInvalid(f"{name}: формула метрики не объект")
        metric = str(name)
        if isinstance(body.get("base"), str):
            bases[metric] = str(body["base"])
        if isinstance(body.get("rate"), str):
            rates[metric] = str(body["rate"])
        inputs[metric] = _inputs(body, inputs, metric)
        expressions[metric] = _expression(body, metric)
        own = _composed(body, metric)
        if own is not None:
            composed[metric] = own
        raw_variants = body.get("variants") or {}
        if not isinstance(raw_variants, dict):
            raise ModelTypeInvalid(f"{metric}: variants должен быть объектом")
        found: dict[str, MetricInputs] = {}
        for variant, spec in raw_variants.items():
            if not isinstance(spec, dict):
                raise ModelTypeInvalid(f"{metric}.{variant}: вариант не объект")
            key = f"{metric}.{variant}"
            found[str(variant)] = _inputs(spec, inputs, key)
            expressions[key] = _expression(spec, key)
            if isinstance(spec.get("base"), str):
                bases[key] = str(spec["base"])
            item = _composed(spec, key)
            if item is not None:
                composed[key] = item
            if isinstance(spec.get("rate"), str):
                rates[key] = str(spec["rate"])
        if found:
            variants[metric] = found
    return inputs, variants, composed, bases, rates, expressions


def _signal(type_id: str, raw: dict) -> Signal:
    concepts = tuple(str(item) for item in raw.get("concepts") or [])
    groups = tuple(tuple(str(name) for name in group) for group in raw.get("groups") or [])
    absent = tuple(str(item) for item in raw.get("absent") or [])
    return Signal(str(raw["kind"]), float(raw["weight"]), concepts, groups, absent)


def _use(body) -> str:
    if isinstance(body, str):
        return body
    return str(body["use"])


def load_coverage_document(path: Path | None = None) -> dict:
    document = yaml.safe_load((path or metrics_file()).read_text(encoding="utf-8")) or {}
    if not isinstance(document, dict):
        raise ModelTypeInvalid("configs/metrics: документ должен быть объектом")
    return document


def load_row_fallbacks(path: Path | None = None) -> dict[str, RowFallback]:
    """Альтернативные идентификаторы строк. Не входят в таксономию понятий.

    `binding_key` и `matching.rule` хранятся как декларативные метаданные.
    Lookup — по id fallback в `interest_order` среди primaries.
    """

    document = load_coverage_document(path)
    raw = document.get("row_fallbacks") or {}
    if not isinstance(raw, dict):
        raise ModelTypeInvalid("configs/metrics: row_fallbacks должен быть объектом")
    found: dict[str, RowFallback] = {}
    for key, body in raw.items():
        name = check_concept_id(str(key))
        if not isinstance(body, dict):
            raise ModelTypeInvalid(f"row_fallbacks.{name}: объект")
        matching = body.get("matching") or {}
        if not isinstance(matching, dict):
            raise ModelTypeInvalid(f"row_fallbacks.{name}: matching должен быть объектом")
        canonical = body.get("canonical")
        binding_key = body.get("binding_key")
        rule = matching.get("rule")
        if not isinstance(canonical, str) or not canonical:
            raise ModelTypeInvalid(f"row_fallbacks.{name}: нужен canonical")
        if not isinstance(binding_key, str) or not binding_key:
            raise ModelTypeInvalid(f"row_fallbacks.{name}: нужен binding_key")
        if not isinstance(rule, str) or not rule:
            raise ModelTypeInvalid(f"row_fallbacks.{name}: нужен matching.rule")
        found[name] = RowFallback(
            id=name,
            canonical=check_concept_id(canonical),
            binding_key=check_concept_id(binding_key),
            matching_rule=str(rule),
        )
    return found


def load_interest_order(
    path: Path | None = None,
    *,
    concepts: frozenset[str] | None = None,
    fallbacks: dict[str, RowFallback] | None = None,
) -> dict[str, tuple[str, ...]]:
    """Порядок процентов из coverage.yaml. Имена — concept_id или row_fallback."""

    document = load_coverage_document(path)
    raw = document.get("interest_order") if isinstance(document, dict) else None
    if not isinstance(raw, dict) or not raw:
        raise ModelTypeInvalid("configs/metrics: нет interest_order")
    allowed = None
    if concepts is not None:
        names = set(concepts) | set(fallbacks or ())
        allowed = names
    order: dict[str, tuple[str, ...]] = {}
    for key, names_raw in raw.items():
        if not isinstance(names_raw, list) or not names_raw or any(not isinstance(item, str) for item in names_raw):
            raise ModelTypeInvalid(f"interest_order.{key}: список имён")
        cleaned = tuple(str(item) for item in names_raw)
        if allowed is not None:
            unknown = [item for item in cleaned if item not in allowed]
            if unknown:
                raise ModelTypeInvalid(
                    f"interest_order.{key}: неизвестные id: {', '.join(unknown)}"
                )
        order[str(key)] = cleaned
    return order


def load_model_types(path: Path | None = None, *, concepts: frozenset[str] | None = None) -> ModelTypeCatalog:
    folder = path or model_types_dir()
    common_path = folder / "_common.yaml"
    if not common_path.is_file():
        raise ModelTypeInvalid("нет configs/model_types/_common.yaml")
    common = yaml.safe_load(common_path.read_text(encoding="utf-8")) or {}
    if not isinstance(common, dict):
        raise ModelTypeInvalid("_common.yaml должен быть объектом")
    documents: dict[str, dict] = {}
    for file in sorted(folder.glob("*.yaml")):
        if file.name.startswith("_"):
            continue
        body = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
        if not isinstance(body, dict) or body.get("id") != file.stem:
            raise ModelTypeInvalid(f"{file.name}: id должен совпадать с именем файла")
        documents[file.stem] = body
    package = None
    if concepts is None:
        from finance_analysis.application.catalog import load_catalog

        package = load_catalog()
        concepts = package.ids
    metric_inputs, variant_inputs, composed, metric_bases, metric_rates, expressions = load_metric_catalog()
    row_fallbacks = load_row_fallbacks()
    interest_order = load_interest_order(concepts=concepts, fallbacks=row_fallbacks)
    _check_signal_concepts(documents, concepts)
    if package is None:
        from finance_analysis.application.catalog import load_catalog

        package = load_catalog()
    from finance_analysis.application.catalog import load_dimensions

    coverage = load_coverage_document()
    try:
        validate_catalog_integrity(
            concepts=concepts,
            concept_dimensions={name: item.dimension for name, item in package.concepts.items()},
            dimensions=load_dimensions(),
            model_documents=documents,
            metric_inputs=metric_inputs,
            variant_inputs=variant_inputs,
            metric_expressions=expressions,
            metric_bases=metric_bases,
            interest_order=interest_order,
            row_fallbacks=row_fallbacks,
            coverage_document=coverage,
        )
    except CatalogIntegrityError as exc:
        raise ModelTypeInvalid(str(exc)) from exc
    default = common.get("default_use")
    if default not in {"required", "optional", "not_applicable"}:
        raise ModelTypeInvalid("default_use: required, optional или not_applicable")
    compatible = _compatible(common.get("compatible"), documents)
    types = {type_id: _spec(type_id, body) for type_id, body in documents.items()}
    version = hashlib.sha256(
        canonical_json({"common": common, "types": documents}).encode("utf-8")
    ).hexdigest()[:16]
    return ModelTypeCatalog(
        types,
        str(default),
        version,
        concepts,
        metric_inputs,
        documents,
        compatible,
        composed,
        variant_inputs,
        interest_order,
        row_fallbacks,
        metric_bases,
        metric_rates,
        expressions,
    )


def _check_signal_concepts(documents: dict[str, dict], concepts: frozenset[str]) -> None:
    for type_id, body in documents.items():
        for signal in body.get("signals") or []:
            named = [*(signal.get("concepts") or []), *(signal.get("absent") or [])]
            unknown = [check_concept_id(str(name)) for name in named if str(name) not in concepts]
            if unknown:
                raise ModelTypeInvalid(f"{type_id}: понятие признака вне каталога: {', '.join(unknown)}")


def _compatible(raw, documents: dict[str, dict]) -> frozenset[frozenset[str]]:
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise ModelTypeInvalid("compatible должен быть списком пар")
    found: set[frozenset[str]] = set()
    for pair in raw:
        if not isinstance(pair, list) or len(pair) != 2 or any(item not in documents for item in pair):
            raise ModelTypeInvalid("compatible: обе стороны пары должны быть типами")
        found.add(frozenset(str(item) for item in pair))
    return frozenset(found)


def _spec(type_id: str, body: dict) -> TypeSpec:
    metrics: dict[str, str] = {}
    variants: dict[str, str] = {}
    for name, value in (body.get("metrics") or {}).items():
        metrics[str(name)] = _use(value)
        if isinstance(value, dict) and isinstance(value.get("variant"), str):
            variants[str(name)] = value["variant"]
    return TypeSpec(
        type_id,
        tuple(_signal(type_id, item) for item in body.get("signals") or []),
        frozenset(str(name) for name in body.get("required_concepts") or []),
        metrics,
        variants,
    )
