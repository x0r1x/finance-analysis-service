"""Загрузка Financial Model Catalog поверх configs/metrics + таксономии."""

from __future__ import annotations

from pathlib import Path

from finance_analysis.application.catalog import load_catalog, load_dimensions
from finance_analysis.application.model_types import (
    load_coverage_document,
    load_model_types,
)
from finance_analysis.domain.derive_fingerprint import configs_root
from finance_analysis.domain.financial_catalog import (
    INDICATOR_STATUSES,
    WINDOWS,
    FinancialModelCatalog,
    build_financial_catalog,
)
from finance_analysis.domain.model_type import ModelTypeCatalog
from finance_analysis.domain.semantic_model import stamp_path
from finance_analysis.domain.validation.model_types import ModelTypeInvalid


def load_financial_catalog(
    path: Path | None = None,
    *,
    concepts: frozenset[str] | None = None,
    model_types: ModelTypeCatalog | None = None,
) -> FinancialModelCatalog:
    """Загружает и валидирует каталог показателей (целостность — через load_model_types)."""

    catalog = model_types if model_types is not None else load_model_types(concepts=concepts)
    package = load_catalog()
    coverage = load_coverage_document(path)
    definitions, statuses, windows = _meta(coverage)
    stamp = stamp_path(configs_root(), "configs/metrics")[:16]
    return build_financial_catalog(
        model_types=catalog,
        concept_dimensions={name: item.dimension for name, item in package.concepts.items()},
        dimensions=load_dimensions(),
        stamp=stamp,
        definitions=definitions,
        statuses=statuses,
        windows=windows,
    )


def _meta(coverage: dict) -> tuple[dict[str, str | None], dict[str, str], dict[str, str | None]]:
    raw = coverage.get("metrics") or {}
    if not isinstance(raw, dict):
        raise ModelTypeInvalid("configs/metrics: metrics должен быть объектом")
    definitions: dict[str, str | None] = {}
    statuses: dict[str, str] = {}
    windows: dict[str, str | None] = {}
    for name, body in raw.items():
        metric = str(name)
        if not isinstance(body, dict):
            raise ModelTypeInvalid(f"{metric}: формула метрики не объект")
        _read_definition(definitions, metric, body)
        _read_status(statuses, metric, body)
        _read_window(windows, metric, body)
        variants = body.get("variants") or {}
        if variants is None:
            variants = {}
        if not isinstance(variants, dict):
            raise ModelTypeInvalid(f"{metric}.variants: объект")
        for variant, spec in variants.items():
            key = f"{metric}.{variant}"
            if not isinstance(spec, dict):
                raise ModelTypeInvalid(f"{key}: вариант не объект")
            _read_definition(definitions, key, spec)
            if "status" in spec:
                raise ModelTypeInvalid(f"{key}: status допустим только у показателя, не у варианта")
            _read_window(windows, key, spec)
    return definitions, statuses, windows


def _read_definition(target: dict[str, str | None], owner: str, body: dict) -> None:
    if "definition" not in body:
        return
    value = body.get("definition")
    if value is not None and not isinstance(value, str):
        raise ModelTypeInvalid(f"{owner}: definition должна быть строкой или null")
    target[owner] = value


def _read_status(target: dict[str, str], owner: str, body: dict) -> None:
    if "status" not in body:
        return
    value = body.get("status")
    if not isinstance(value, str):
        raise ModelTypeInvalid(f"{owner}: status должен быть строкой")
    if value not in INDICATOR_STATUSES:
        raise ModelTypeInvalid(f"{owner}: status active|deprecated")
    target[owner] = value


def _read_window(target: dict[str, str | None], owner: str, body: dict) -> None:
    if "window" not in body:
        return
    value = body.get("window")
    if value is not None and not isinstance(value, str):
        raise ModelTypeInvalid(f"{owner}: window должен быть строкой или null")
    if value is not None and value not in WINDOWS:
        raise ModelTypeInvalid(f"{owner}: окно LTM или period")
    target[owner] = value
