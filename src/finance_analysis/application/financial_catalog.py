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
    FinancialModelCatalog,
    build_financial_catalog,
)
from finance_analysis.domain.model_type import ModelTypeCatalog
from finance_analysis.domain.semantic_model import stamp_path


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
        return {}, {}, {}
    definitions: dict[str, str | None] = {}
    statuses: dict[str, str] = {}
    windows: dict[str, str | None] = {}
    for name, body in raw.items():
        if not isinstance(body, dict):
            continue
        metric = str(name)
        if "definition" in body:
            value = body.get("definition")
            definitions[metric] = None if value is None else str(value)
        if isinstance(body.get("status"), str):
            statuses[metric] = str(body["status"])
        if isinstance(body.get("window"), str):
            windows[metric] = str(body["window"])
        variants = body.get("variants") or {}
        if not isinstance(variants, dict):
            continue
        for variant, spec in variants.items():
            if not isinstance(spec, dict):
                continue
            key = f"{metric}.{variant}"
            if "definition" in spec:
                value = spec.get("definition")
                definitions[key] = None if value is None else str(value)
            if isinstance(spec.get("window"), str):
                windows[key] = str(spec["window"])
    return definitions, statuses, windows
