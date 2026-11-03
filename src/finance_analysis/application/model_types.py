"""Загрузка configs/model_types и формул метрик (§5.7)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from finance_analysis.application.catalog import catalog_file
from finance_analysis.domain.book import canonical_json
from finance_analysis.domain.ids import concept_id as check_concept_id
from finance_analysis.domain.model_type import (
    MetricInputs,
    ModelTypeCatalog,
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
    if isinstance(numerator, str):
        numerator = [numerator]
    if not isinstance(numerator, list):
        raise ModelTypeInvalid(f"{name}: numerator должен быть списком понятий")
    if len(numerator) > 1:
        one_of.update(str(item) for item in numerator)
    else:
        all_of.update(str(item) for item in numerator)
    for key in ("denominator", "rate"):
        value = body.get(key)
        if isinstance(value, str):
            all_of.add(value)
    return MetricInputs(frozenset(all_of), frozenset(one_of))


def load_metric_inputs(path: Path | None = None) -> dict[str, MetricInputs]:
    document = yaml.safe_load((path or metrics_file()).read_text(encoding="utf-8")) or {}
    raw = document.get("metrics") if isinstance(document, dict) else None
    if not isinstance(raw, dict) or not raw:
        raise ModelTypeInvalid("configs/metrics: нет metrics")
    found: dict[str, MetricInputs] = {}
    for name, body in raw.items():
        if not isinstance(body, dict):
            raise ModelTypeInvalid(f"{name}: формула метрики не объект")
        found[str(name)] = _inputs(body, found, str(name))
    return found


def _signal(type_id: str, raw: dict) -> Signal:
    concepts = tuple(str(item) for item in raw.get("concepts") or [])
    groups = tuple(tuple(str(name) for name in group) for group in raw.get("groups") or [])
    return Signal(str(raw["kind"]), float(raw["weight"]), concepts, groups)


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
    metric_inputs = load_metric_inputs()
    _check_signal_concepts(documents, concepts)
    validate_model_types(documents, concepts=concepts, metric_inputs=metric_inputs)
    default = common.get("default_use")
    if default not in {"required", "optional", "not_applicable"}:
        raise ModelTypeInvalid("default_use: required, optional или not_applicable")
    compatible = _compatible(common.get("compatible"), documents)
    types = {type_id: _spec(type_id, body) for type_id, body in documents.items()}
    version = hashlib.sha256(
        canonical_json({"common": common, "types": documents}).encode("utf-8")
    ).hexdigest()[:16]
    return ModelTypeCatalog(types, str(default), version, concepts, metric_inputs, documents, compatible)


def _check_signal_concepts(documents: dict[str, dict], concepts: frozenset[str]) -> None:
    for type_id, body in documents.items():
        for signal in body.get("signals") or []:
            unknown = [check_concept_id(str(name)) for name in signal.get("concepts") or [] if str(name) not in concepts]
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
    metrics = {str(name): _use(value) for name, value in (body.get("metrics") or {}).items()}
    return TypeSpec(
        type_id,
        tuple(_signal(type_id, item) for item in body.get("signals") or []),
        frozenset(str(name) for name in body.get("required_concepts") or []),
        metrics,
    )
