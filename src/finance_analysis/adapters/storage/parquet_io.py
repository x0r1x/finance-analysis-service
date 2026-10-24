"""Запись Parquet по schemas/*.json (§4.12)."""

from __future__ import annotations

import io
import json
import re
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path

import anyio
import pyarrow as pa
import pyarrow.parquet as pq

from finance_analysis.domain.book import FAS_VERSION
from finance_analysis.domain.errors import InvalidArgument

_SCHEMAS = Path(__file__).resolve().parent / "schemas"
_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_DECIMAL = re.compile(r"^decimal128\((\d+),(\d+)\)$")


def _arrow_type(spec: str) -> pa.DataType:
    if spec == "string":
        return pa.string()
    if spec == "bool":
        return pa.bool_()
    if spec == "int16":
        return pa.int16()
    if spec == "int32":
        return pa.int32()
    if spec == "int64":
        return pa.int64()
    if spec == "float32":
        return pa.float32()
    if spec == "float64":
        return pa.float64()
    if spec == "date32":
        return pa.date32()
    if spec == "timestamp(us, tz=UTC)":
        return pa.timestamp("us", tz="UTC")
    matched = _DECIMAL.fullmatch(spec)
    if matched:
        return pa.decimal128(int(matched.group(1)), int(matched.group(2)))
    raise InvalidArgument(f"неизвестный тип схемы {spec}")


@lru_cache(maxsize=32)
def load_schema(dataset: str) -> dict:
    path = _SCHEMAS / f"{dataset}.json"
    if not path.is_file():
        raise InvalidArgument(f"нет схемы {dataset}")
    return json.loads(path.read_text(encoding="utf-8"))


def arrow_schema(dataset: str, *, build_key: str, created_at: str) -> pa.Schema:
    doc = load_schema(dataset)
    fields = []
    for column in doc["columns"]:
        name = column["name"]
        if not _NAME.fullmatch(name):
            raise InvalidArgument(f"имя колонки {name!r} нарушает P2")
        fields.append(pa.field(name, _arrow_type(column["type"]), nullable=column["nullable"]))
    schema = pa.schema(fields)
    meta = {
        b"fas.schema": f"{dataset}@{doc['version']}".encode(),
        b"fas.writer": f"fas {FAS_VERSION}".encode(),
        b"fas.build_key": build_key.encode(),
        b"fas.created_at_utc": created_at.encode(),
    }
    return schema.with_metadata(meta)


def _fit(value, typ: pa.DataType):
    if value is None or value == "":
        return None
    if pa.types.is_decimal(typ):
        quantum = Decimal(1).scaleb(-typ.scale)
        try:
            dec = value if isinstance(value, Decimal) else Decimal(str(value))
            dec = dec.quantize(quantum, rounding=ROUND_HALF_EVEN)
        except (InvalidOperation, ValueError, TypeError):
            return None
        digits = len(dec.as_tuple().digits)
        if digits > typ.precision:
            return None
        return dec
    if pa.types.is_floating(typ):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if pa.types.is_integer(typ):
        return int(value)
    if pa.types.is_boolean(typ):
        return bool(value)
    if pa.types.is_timestamp(typ):
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=UTC)
            return value.astimezone(UTC)
        return None
    if pa.types.is_date(typ):
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return None
    if value is None:
        return None
    return str(value)


def _sort_key(dataset: str, row: dict):
    if dataset == "dim_period":
        return (row.get("axis_id") or "", row.get("period_index") or 0)
    if dataset == "fact_observation":
        return (row.get("row_key") or "", row.get("axis_id") or "", row.get("period_id") or "")
    if dataset in {"row_semantics", "bindings"}:
        return (row.get("row_key") or "",)
    if dataset == "period_semantics":
        return (row.get("axis_id") or "", row.get("period_id") or "")
    if dataset == "findings":
        return (row.get("code") or "", row.get("fingerprint") or "")
    return (row.get("row_key") or row.get("status") or "",)


def write_table(dataset: str, rows: list[dict], *, build_key: str) -> tuple[bytes, int]:
    created = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    schema = arrow_schema(dataset, build_key=build_key, created_at=created)
    ordered = sorted(rows, key=lambda row: _sort_key(dataset, row))
    columns: dict[str, list] = {field.name: [] for field in schema}
    for row in ordered:
        for field in schema:
            columns[field.name].append(_fit(row.get(field.name), field.type))
    table = pa.table(columns, schema=schema)
    buf = io.BytesIO()
    row_group = max(table.num_rows, 1)
    pq.write_table(
        table,
        buf,
        compression="zstd",
        coerce_timestamps="us",
        row_group_size=row_group,
    )
    return buf.getvalue(), table.num_rows


def read_table(payload: bytes) -> list[dict]:
    return pq.read_table(io.BytesIO(payload)).to_pylist()


class PyarrowParquet:
    async def write(self, dataset: str, rows: list[dict], *, build_key: str) -> tuple[bytes, int]:
        return await anyio.to_thread.run_sync(lambda: write_table(dataset, rows, build_key=build_key))

    async def read(self, payload: bytes) -> list[dict]:
        return await anyio.to_thread.run_sync(lambda: read_table(payload))
