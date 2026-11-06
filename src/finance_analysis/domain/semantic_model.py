"""Публичный SemanticModelVersion (фаза 2 метаслоя, G4).

Агрегат согласованных определений: taxonomy, glossary, metrics, model_types,
units/dimensions, rules, schema. Не включает входы derive_key вроде state_seq,
профиля, калибратора и embed-моделей. derive_key не удаляется и не сливается.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

import yaml

from finance_analysis.domain.book import FAS_SCHEMA_VERSION, FAS_VERSION, canonical_json
from finance_analysis.domain.derive_fingerprint import configs_root

SMV_CONFIG_SOURCES = (
    "configs/concepts",
    "configs/metrics",
    "configs/model_types",
    "configs/dimensions.yaml",
)

HEAD_KEY = "semantic_models/_head.json"


def semantic_model_key(version: str) -> str:
    return f"semantic_models/{version}.json"


def stamp_path(root: Path, item: str) -> str:
    """sha256 объявленного файла или дерева; переводы строк → LF."""

    digest = hashlib.sha256()
    for path, body in _read(root, item):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(body)
        digest.update(b"\0")
    return digest.hexdigest()


def rules_stamp(versions: Mapping[str, str]) -> str:
    payload = {str(code): str(version) for code, version in sorted(versions.items())}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def semantic_model_components(
    *,
    glossary_version: str,
    taxonomy_id: str,
    taxonomy_stamp: str,
    metrics_stamp: str,
    model_types_version: str,
    dimensions_id: str,
    dimensions_stamp: str,
    rules_stamp_value: str,
    schema_version: str = FAS_SCHEMA_VERSION,
) -> dict:
    return {
        "taxonomy": {"id": taxonomy_id, "stamp": taxonomy_stamp},
        "glossary": glossary_version or "none",
        "metrics": metrics_stamp,
        "model_types": model_types_version,
        "dimensions": {"id": dimensions_id, "stamp": dimensions_stamp},
        "rules": rules_stamp_value,
        "schema": schema_version,
    }


def semantic_model_version_for(components: Mapping) -> str:
    """Воспроизводимый id: одинаковые components → одинаковый 16-hex."""

    return hashlib.sha256(canonical_json(dict(components)).encode("utf-8")).hexdigest()[:16]


def manifest_body(version: str, components: Mapping, *, created_at_utc: str) -> dict:
    return {
        "version": version,
        "components": dict(components),
        "fas_version": FAS_VERSION,
        "created_at_utc": created_at_utc,
    }


def head_body(version: str, *, updated_at_utc: str) -> dict:
    return {"active": version, "updated_at_utc": updated_at_utc}


def live_components(
    glossary_version: str,
    *,
    model_types_version: str,
    rules_versions: Mapping[str, str],
    schema_version: str = FAS_SCHEMA_VERSION,
    root: Path | None = None,
) -> dict:
    """Собирает components из текущего дерева конфигов и переданных версий."""

    configs = root if root is not None else configs_root()
    taxonomy_id, dimensions_id = _catalog_ids(configs)
    return semantic_model_components(
        glossary_version=glossary_version or "none",
        taxonomy_id=taxonomy_id,
        taxonomy_stamp=stamp_path(configs, "configs/concepts")[:16],
        metrics_stamp=stamp_path(configs, "configs/metrics")[:16],
        model_types_version=model_types_version,
        dimensions_id=dimensions_id,
        dimensions_stamp=stamp_path(configs, "configs/dimensions.yaml")[:16],
        rules_stamp_value=rules_stamp(rules_versions)[:16],
        schema_version=schema_version,
    )


def _catalog_ids(configs: Path) -> tuple[str, str]:
    concepts = yaml.safe_load((configs / "configs" / "concepts" / "core.yaml").read_text(encoding="utf-8")) or {}
    dimensions = yaml.safe_load((configs / "configs" / "dimensions.yaml").read_text(encoding="utf-8")) or {}
    taxonomy_id = str(concepts.get("taxonomy") or "none")
    dimensions_id = str(dimensions.get("taxonomy") or "none")
    return taxonomy_id, dimensions_id


def _read(root: Path, item: str) -> list[tuple[str, bytes]]:
    path = root / item
    if path.is_dir():
        files = sorted(file for file in path.rglob("*") if file.is_file() and "__pycache__" not in file.parts)
        if not files:
            raise FileNotFoundError(f"каталог SMV пуст: {item}")
        return [(file.relative_to(root).as_posix(), _lf(file.read_bytes())) for file in files]
    if not path.is_file():
        raise FileNotFoundError(f"файл SMV не найден: {item}")
    return [(item, _lf(path.read_bytes()))]


def _lf(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def dumps_manifest(body: dict) -> bytes:
    return json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")
