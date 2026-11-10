"""Published Parquet contract для внешнего DataMesh (фаза 5, G5).

Документ: docs/published-parquet-contract.md.
Индекс: domain/contracts/published_parquet.json.

Чистая проверка обещаний: чтение только по маркеру, паритет schemas/*.json,
аддитивная эволюция в пределах MAJOR (append-only), P5-ключи.
Без Iceberg/Hive writers.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path, PurePosixPath
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
        # embedding_f32 only: raw float32 little-endian vector (see design §4.12 P1)
        "binary",
    }
)
_DECIMAL = re.compile(r"^decimal128\(\d+,\d+\)$")
_MARKER_FILE_FIELDS = ("sha256", "rows", "schema")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SCHEMA_TAG = re.compile(r"^[a-z][a-z0-9_]*@\d+\.\d+$")

CONTRACT_LABEL_PREFIX = "published_parquet@"

# P5 baseline keys by published group (docs/published-parquet-contract.md §2).
_P5_BASE: dict[str, frozenset[str]] = {
    "projection": frozenset({"model_id", "build_key"}),
    "derived": frozenset({"model_id", "build_key", "state_seq", "derive_key"}),
    "results": frozenset({"model_id", "build_key", "analysis_id", "state_seq"}),
}
_P5_EXTRA: dict[str, frozenset[str]] = {
    "bindings": frozenset({"glossary_version"}),
}


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


def _validate_rel_path(rel: str) -> None:
    if not rel or rel.startswith("/") or rel.endswith("/"):
        raise PublishedParquetError(f"недопустимый путь в маркере: {rel!r}")
    parts = PurePosixPath(rel).parts
    if ".." in parts or any(part == "" for part in parts):
        raise PublishedParquetError(f"недопустимый путь в маркере: {rel!r}")


def _validate_file_meta(rel: str, meta: Mapping[str, Any]) -> dict[str, Any]:
    missing = [field for field in _MARKER_FILE_FIELDS if field not in meta]
    if missing:
        raise PublishedParquetError(f"маркер {rel!r}: нет полей {missing}")
    sha = meta["sha256"]
    rows = meta["rows"]
    schema = meta["schema"]
    if not isinstance(sha, str) or not _SHA256.fullmatch(sha):
        raise PublishedParquetError(f"маркер {rel!r}: sha256 должен быть 64 hex")
    if not isinstance(rows, int) or isinstance(rows, bool) or rows < 0:
        raise PublishedParquetError(f"маркер {rel!r}: rows должен быть int ≥ 0")
    if not isinstance(schema, str) or not _SCHEMA_TAG.fullmatch(schema):
        raise PublishedParquetError(f"маркер {rel!r}: schema должен быть dataset@MAJOR.MINOR")
    return {"sha256": sha, "rows": rows, "schema": schema, **{k: v for k, v in meta.items() if k not in _MARKER_FILE_FIELDS}}


def parse_marker_files(
    marker: Mapping[str, Any] | None,
    *,
    files_field: str = "files",
) -> dict[str, dict[str, Any]]:
    """Разобрать маркер: обязательны sha256, rows, schema; пути без ``..``.

    Отсутствие маркера или поля files → пустой набор (читать нечего).
    Неполный meta → PublishedParquetError (маркер не считается commit-ом).
    """

    if marker is None:
        return {}
    raw = marker.get(files_field)
    if not isinstance(raw, Mapping):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for rel, meta in raw.items():
        if not isinstance(rel, str):
            raise PublishedParquetError(f"пустой путь в маркере: {rel!r}")
        _validate_rel_path(rel)
        if not isinstance(meta, Mapping):
            raise PublishedParquetError(f"метаданные файла {rel!r} должны быть объектом")
        out[rel] = _validate_file_meta(rel, meta)
    return out


def marker_files(marker: Mapping[str, Any] | None, *, files_field: str = "files") -> dict[str, dict[str, Any]]:
    """Синоним parse_marker_files (P7)."""

    return parse_marker_files(marker, files_field=files_field)


def is_committed_readable(marker: Mapping[str, Any] | None, *, files_field: str = "files") -> bool:
    """True только если маркер валиден (P7) и перечисляет хотя бы один файл."""

    try:
        return bool(parse_marker_files(marker, files_field=files_field))
    except PublishedParquetError:
        return False


def refuse_list_before_marker(
    *,
    marker: Mapping[str, Any] | None,
    listed_keys: Sequence[str],
    files_field: str = "files",
) -> tuple[str, ...]:
    """Ключи листинга вне маркера — вне контракта чтения (list-before-marker)."""

    try:
        committed = set(parse_marker_files(marker, files_field=files_field))
    except PublishedParquetError:
        return tuple(sorted(listed_keys))
    if marker is None:
        return tuple(sorted(listed_keys))
    return tuple(sorted(key for key in listed_keys if key not in committed))


def verify_committed_files(
    marker: Mapping[str, Any] | None,
    payloads: Mapping[str, bytes],
    *,
    files_field: str = "files",
    allowed_prefixes: Sequence[str] = (),
) -> list[str]:
    """Сверить sha256 (/ rows / schema footer при Parquet) с payload'ами из store.

    Не полный DataMesh reader: только инварианты commit-маркера против байтов.
    ``allowed_prefixes`` — если задан, каждый rel должен начинаться с одного из них.
    """

    errors: list[str] = []
    try:
        files = parse_marker_files(marker, files_field=files_field)
    except PublishedParquetError as exc:
        return [str(exc)]
    for rel, meta in files.items():
        if allowed_prefixes and not any(rel.startswith(prefix) for prefix in allowed_prefixes):
            errors.append(f"{rel}: путь вне allowed_prefixes {list(allowed_prefixes)}")
        payload = payloads.get(rel)
        if payload is None:
            errors.append(f"{rel}: нет payload")
            continue
        digest = hashlib.sha256(payload).hexdigest()
        if digest != meta["sha256"]:
            errors.append(f"{rel}: sha256 mismatch")
        if rel.endswith(".parquet"):
            try:
                import io

                import pyarrow.parquet as pq

                pf = pq.ParquetFile(io.BytesIO(payload))
                if pf.metadata.num_rows != meta["rows"]:
                    errors.append(f"{rel}: rows {pf.metadata.num_rows} ≠ marker {meta['rows']}")
                footer = pf.schema_arrow.metadata or {}
                tag = footer.get(b"fas.schema", b"").decode()
                if tag != meta["schema"]:
                    errors.append(f"{rel}: fas.schema {tag!r} ≠ marker {meta['schema']!r}")
            except Exception as exc:  # noqa: BLE001 — контрактный отчёт
                errors.append(f"{rel}: не удалось прочитать parquet: {exc}")
    return errors


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
        if typ == "binary" and name != "embedding_f32":
            errors.append(f"{dataset}.{name}: binary разрешён только для embedding_f32")
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
    """P6: nullable для since minor > 0 + append-only порядок колонок."""

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
    try:
        assert_columns_append_only(doc)
    except PublishedParquetError as exc:
        errors.append(f"{dataset}: {exc}")
    return errors


def assert_columns_append_only(doc: Mapping[str, Any]) -> None:
    """Строгий P6: since minor non-decreasing; *.0 только префиксом перед аддитивными."""

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


def p5_required_keys(group: str, dataset: str) -> frozenset[str]:
    base = _P5_BASE.get(group, frozenset())
    return base | _P5_EXTRA.get(dataset, frozenset())


def check_p5_required_keys() -> list[str]:
    """Индекс required_keys ⊇ P5 baseline из published contract §2 / design P5."""

    errors: list[str] = []
    for item in load_published_contract()["datasets"]:
        expected = p5_required_keys(item["group"], item["name"])
        if not expected:
            continue
        declared = set(item["required_keys"])
        missing = sorted(expected - declared)
        if missing:
            errors.append(f"{item['name']}: в индексе нет P5-ключей {missing}")
        doc = load_dataset_schema(item["name"])
        col_names = {column["name"] for column in doc["columns"]}
        absent = sorted(expected - col_names)
        if absent:
            errors.append(f"{item['name']}: P5-ключи отсутствуют в schema: {absent}")
    return errors


def published_dataset_names() -> frozenset[str]:
    return frozenset(item["name"] for item in load_published_contract()["datasets"])


def schema_file_names() -> frozenset[str]:
    return frozenset(path.stem for path in _SCHEMAS_DIR.glob("*.json"))


def check_index_matches_schemas() -> list[str]:
    """Индекс ↔ schemas/*.json: имена, required_keys, P5, additive/append-only."""

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

    errors.extend(check_p5_required_keys())

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
    """Падает, если индекс, схемы, P5 или append-only нарушают контракт."""

    errors = check_index_matches_schemas()
    if errors:
        raise PublishedParquetError("; ".join(errors))
