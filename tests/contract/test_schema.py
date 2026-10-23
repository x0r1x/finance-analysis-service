"""Контракт Parquet: имена, типы, zstd, один row group (§4.12)."""

from __future__ import annotations

import re

import pyarrow.parquet as pq
import pytest

from finance_analysis.adapters.storage.parquet_io import load_schema
from finance_analysis.domain.book import Actor
from tests.conftest import JOB

pytestmark = pytest.mark.asyncio
_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


async def test_projection_files_match_schemas(local_service):
    head = await local_service.perform_load(JOB, actor=Actor(), fence=1)
    prefix = f"books/{JOB}/{head.build_key}"
    keys = [item.key async for item in local_service.store.list(prefix)]
    parquet_keys = [key for key in keys if key.endswith(".parquet")]
    assert parquet_keys
    for key in parquet_keys:
        dataset = key.rsplit("/", 1)[-1].removesuffix(".parquet")
        doc = load_schema(dataset)
        path = local_service.store.physical(key)
        pf = pq.ParquetFile(path)
        assert pf.metadata.num_row_groups == 1
        assert pf.metadata.row_group(0).column(0).compression == "ZSTD"
        schema = pf.schema_arrow
        names = [field.name for field in schema]
        assert names == [column["name"] for column in doc["columns"]]
        assert all(_NAME.fullmatch(name) for name in names)
        meta = schema.metadata or {}
        assert meta[b"fas.schema"] == f"{dataset}@{doc['version']}".encode()
        assert meta[b"fas.build_key"] == head.build_key.encode()
