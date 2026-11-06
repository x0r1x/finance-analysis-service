"""Published Parquet contract для внешнего DataMesh (фаза 5, G5).

Документ: docs/published-parquet-contract.md.
Индекс: domain/contracts/published_parquet.json.

Чистая проверка обещаний: чтение только по маркеру, паритет schemas/*.json,
аддитивная эволюция в пределах MAJOR. Без Iceberg/Hive writers.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

_CONTRACT_PATH = Path(__file__).resolve().parent / "contracts" / "published_parquet.json"
_SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "adapters" / "storage" / "schemas"
_VERSION = re.compile(r"^(\d+)\.(\d+)$")
_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_ALLOWED_TYPES = frozenset(
    {
        "string",
        "bool",
        "int16",
        "int32",
        "int64",
        "float32",
        "float64",
        "date32",
        "timestamp(us, tz=UTC)",
        # embedding_f32: сырой float32 vector (examples/unmapped); не list/struct Parquet
        "binary",
    }
)
_DECIMAL = re.compile(r"^decimal128\(\d+,\d+\)$")

CONTRACT_LABEL_PREFIX = "published_parquet@"


class PublishedParquetError(ValueError):
    """Нарушение внешнего контракта Parquet / DataMesh."""


@lru_cache(maxsize=1)
def load_published_contract() -> dict[str, Any]:
    return json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))


def contract_version() -> str:
    return str(load_published_contract()["contract_version"])


def contract_label() -> str:
    return f"{CONTRACT_LABEL_PREFIX}{contract_version()}"


def load_dataset_schema(dataset: str) -> dict[str, Any]:
    path = _SCHEMAS_DIR / f"{dataset}.json"
    if not path.is_file():
        raise PublishedParquetError(f"нет схемы {dataset}")
    return json.loads(path.read_text(encoding="utf-8"))


def marker_files(marker: Mapping[str, Any] | None, *, files_field: str = "files") -> dict[str, dict[str, Any]]:
    """Файлы зафиксированной сборки — только из маркера.

    Отсутствие маркера или поля files → пустой набор (читать нечего).
    List-before-marker не поддерживается: листинг префикса сюда не передаётся.
    """

    if marker is None:
        return {}
    raw = marker.get(files_field)
    if not isinstance(raw, Mapping):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for rel, meta in raw.items():
        if not isinstance(rel, str) or not rel:
            raise PublishedParquetError(f"пустой путь в маркере: {rel!r}")
        if not isinstance(meta, Mapping):
            raise PublishedParquetError(f"метаданные файла {rel!r} должны быть объектом")
        out[rel] = dict(meta)
    return out


def is_committed_readable(marker: Mapping[str, Any] | None, *, files_field: str = "files") -> bool:
    """True только если маркер присутствует и перечисляет хотя бы один файл."""

    return bool(marker_files(marker, files_field=files_field))


def refuse_list_before_marker(
    *,
    marker: Mapping[str, Any] | None,
    listed_keys: Sequence[str],
    files_field: str = "files",
) -> tuple[str, ...]:
    """Ключи листинга вне маркера — вне контракта чтения (list-before-marker).

    При отсутствии маркера весь листинг считается отказанным.
    """

    committed = set(marker_files(marker, files_field=files_field))
    if marker is None:
        return tuple(sorted(listed_keys))
    return tuple(sorted(key for key in listed_keys if key not in committed))


def parse_schema_version(version: str) -> tuple[int, int]:
    matched = _VERSION.fullmatch(version)
    if not matched:
        raise PublishedParquetError(f"версия схемы не MAJOR.MINOR: {version!r}")
    return int(matched.group(1)), int(matched.group(2))


def _type_ok(spec: str) -> bool:
    return spec in _ALLOWED_TYPES or bool(_DECIMAL.fullmatch(spec))


def check_schema_document(doc: Mapping[str, Any]) -> list[str]:
    """Проверки P1/P2 и базовой согласованности since/version."""

    errors: list[str] = []
    dataset = doc.get("dataset")
    version = doc.get("version")
    columns = doc.get("columns")
    if not isinstance(dataset, str) or not dataset:
        errors.append("нет dataset")
        return errors
    if not isinstance(version, str):
        errors.append(f"{dataset}: нет version")
        return errors
    try:
        major, minor = parse_schema_version(version)
    except PublishedParquetError as exc:
        errors.append(f"{dataset}: {exc}")
        return errors
    if not isinstance(columns, list) or not columns:
        errors.append(f"{dataset}: пустые columns")
        return errors

    for index, column in enumerate(columns):
        if not isinstance(column, Mapping):
            errors.append(f"{dataset}: колонка[{index}] не объект")
            continue
        name = column.get("name")
        if not isinstance(name, str) or not _NAME.fullmatch(name):
            errors.append(f"{dataset}: имя колонки[{index}] нарушает P2: {name!r}")
        typ = column.get("type")
        if not isinstance(typ, str) or not _type_ok(typ):
            errors.append(f"{dataset}.{name}: тип вне P1: {typ!r}")
        since = column.get("since")
        if not isinstance(since, str):
            errors.append(f"{dataset}.{name}: нет since")
            continue
        try:
            since_major, since_minor = parse_schema_version(since)
        except PublishedParquetError as exc:
            errors.append(f"{dataset}.{name}: {exc}")
            continue
        if since_major != major:
            errors.append(f"{dataset}.{name}: since {since} major ≠ schema version {version}")
        if since_minor > minor:
            errors.append(f"{dataset}.{name}: since {since} новее version {version}")
    return errors


def check_additive_evolution(doc: Mapping[str, Any]) -> list[str]:
    """P6: в пределах MAJOR новая колонка (since minor > 0) — nullable.

    Полный «только в конец» проверяется на синтетических документах в тестах:
    исторические схемы могут иметь вставку перед хвостовыми полями той же MAJOR.
    """

    errors = check_schema_document(doc)
    dataset = doc.get("dataset")
    columns = doc.get("columns")
    if not isinstance(columns, list):
        return errors
    for column in columns:
        if not isinstance(column, Mapping):
            continue
        since = column.get("since")
        if not isinstance(since, str):
            continue
        try:
            _major, since_minor = parse_schema_version(since)
        except PublishedParquetError:
            continue
        if since_minor > 0 and column.get("nullable") is not True:
            name = column.get("name")
            errors.append(
                f"{dataset}.{name}: аддитивная колонка since={since} должна быть nullable (P6)"
            )
    return errors


def assert_columns_append_only(doc: Mapping[str, Any]) -> None:
    """Строгий P6 для нового изменения схемы: since non-decreasing, *.0 только префиксом."""

    columns = doc.get("columns")
    if not isinstance(columns, list):
        raise PublishedParquetError("нет columns")
    minors: list[int] = []
    for column in columns:
        since = column["since"]
        _major, since_minor = parse_schema_version(since)
        minors.append(since_minor)
    if minors != sorted(minors):
        raise PublishedParquetError("since minor не монотонен — колонки не append-only")
    first_additive = next((i for i, value in enumerate(minors) if value > 0), len(minors))
    if any(value == 0 for value in minors[first_additive:]):
        raise PublishedParquetError("колонка since=*.0 после аддитивных")


def published_dataset_names() -> frozenset[str]:
    return frozenset(item["name"] for item in load_published_contract()["datasets"])


def schema_file_names() -> frozenset[str]:
    return frozenset(path.stem for path in _SCHEMAS_DIR.glob("*.json"))


def check_index_matches_schemas() -> list[str]:
    """Индекс ↔ schemas/*.json: те же имена; required_keys ⊆ колонки схемы."""

    errors: list[str] = []
    contract = load_published_contract()
    indexed = published_dataset_names()
    on_disk = schema_file_names()
    if indexed != on_disk:
        missing = sorted(on_disk - indexed)
        extra = sorted(indexed - on_disk)
        if missing:
            errors.append(f"в индексе нет схем: {missing}")
        if extra:
            errors.append(f"в индексе лишние датасеты без schemas/*.json: {extra}")

    aligns = contract.get("aligns_with") or {}
    sections = aligns.get("design_sections") or []
    if "4.11" not in sections or "4.12" not in sections:
        errors.append("aligns_with.design_sections должен включать 4.11 и 4.12")

    for item in contract["datasets"]:
        name = item["name"]
        if name not in on_disk:
            continue
        doc = load_dataset_schema(name)
        col_names = {column["name"] for column in doc["columns"]}
        for key in item["required_keys"]:
            if key not in col_names:
                errors.append(f"{name}: required_key {key!r} отсутствует в schema")
        errors.extend(check_additive_evolution(doc))
    return errors


def check_no_forbidden_writers(
    *,
    dependency_names: Sequence[str],
    source_text_blobs: Sequence[str] = (),
) -> list[str]:
    """Нет зависимостей/символов Iceberg/Hive/Delta writers."""

    forbidden = [str(item).lower() for item in load_published_contract()["forbidden_writers"]]
    errors: list[str] = []
    deps_lower = {name.lower() for name in dependency_names}
    for needle in forbidden:
        if needle in deps_lower:
            errors.append(f"запрещённая зависимость: {needle}")
        for blob in source_text_blobs:
            if needle in blob.lower():
                errors.append(f"запрещённый символ {needle!r} в исходниках")
                break
    return errors


def assert_published_contract() -> None:
    """Падает, если индекс, схемы или эволюция нарушают контракт."""

    errors = check_index_matches_schemas()
    if errors:
        raise PublishedParquetError("; ".join(errors))
