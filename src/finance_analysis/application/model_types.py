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
    MetricInputs,
    ModelTypeCatalog,
    Side,
    Signal,
    TypeSpec,
)
from finance_analysis.domain.validation.model_types import (
    ModelTypeInvalid,
    validate_model_types,
)


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


def load_metric_inputs(path: Path | None = None) -> dict[str, MetricInputs]:
    inputs, _variants, _composed_formulas = load_metric_catalog(path)
    return inputs


def load_metric_catalog(
    path: Path | None = None,
) -> tuple[dict[str, MetricInputs], dict[str, dict[str, MetricInputs]], dict[str, Composed]]:
    document = yaml.safe_load((path or metrics_file()).read_text(encoding="utf-8")) or {}
    raw = document.get("metrics") if isinstance(document, dict) else None
    if not isinstance(raw, dict) or not raw:
        raise ModelTypeInvalid("configs/metrics: нет metrics")
    inputs: dict[str, MetricInputs] = {}
    variants: dict[str, dict[str, MetricInputs]] = {}
    composed: dict[str, Composed] = {}
    for name, body in raw.items():
        if not isinstance(body, dict):
            raise ModelTypeInvalid(f"{name}: формула метрики не объект")
        metric = str(name)
        inputs[metric] = _inputs(body, inputs, metric)
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
            item = _composed(spec, key)
            if item is not None:
                composed[key] = item
        if found:
            variants[metric] = found
    return inputs, variants, composed


def _signal(type_id: str, raw: dict) -> Signal:
    concepts = tuple(str(item) for item in raw.get("concepts") or [])
    groups = tuple(tuple(str(name) for name in group) for group in raw.get("groups") or [])
    absent = tuple(str(item) for item in raw.get("absent") or [])
    return Signal(str(raw["kind"]), float(raw["weight"]), concepts, groups, absent)


def _use(body) -> str:
    if isinstance(body, str):
        return body
    return str(body["use"])


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
    if concepts is None:
        from finance_analysis.application.catalog import load_catalog

        concepts = load_catalog().ids
    metric_inputs, variant_inputs, composed = load_metric_catalog()
    _check_formula_concepts(metric_inputs, variant_inputs, concepts)
    _check_signal_concepts(documents, concepts)
    validate_model_types(
        documents,
        concepts=concepts,
        metric_inputs=metric_inputs,
        variant_inputs=variant_inputs,
    )
    default = common.get("default_use")
    if default not in {"required", "optional", "not_applicable"}:
        raise ModelTypeInvalid("default_use: required, optional или not_applicable")
    compatible = _compatible(common.get("compatible"), documents)
    types = {type_id: _spec(type_id, body) for type_id, body in documents.items()}
    version = hashlib.sha256(
        canonical_json({"common": common, "types": documents}).encode("utf-8")
    ).hexdigest()[:16]
    return ModelTypeCatalog(
        types, str(default), version, concepts, metric_inputs, documents, compatible, composed, variant_inputs
    )


def _check_formula_concepts(
    inputs: dict[str, MetricInputs],
    variants: dict[str, dict[str, MetricInputs]],
    concepts: frozenset[str],
) -> None:
    named = dict(inputs)
    for metric, specs in variants.items():
        for variant, spec in specs.items():
            named[f"{metric}.{variant}"] = spec
    for name, spec in named.items():
        unknown = sorted(check_concept_id(item) for item in spec.all_of | spec.one_of if item not in concepts)
        if unknown:
            raise ModelTypeInvalid(f"{name}: понятие вне каталога: {', '.join(unknown)}")


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
