"""Перенос local → MinIO даёт те же ответы API, что и исходная книга."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from finance_analysis.adapters.api.app import create_app
from finance_analysis.adapters.storage.parquet_io import PyarrowParquet
from finance_analysis.adapters.storage.store import open_storage
from finance_analysis.adapters.storage.sync import sync_stores
from finance_analysis.adapters.wren.query import WrenQuery
from finance_analysis.application.service import FasService
from finance_analysis.domain.book import Actor
from tests.books import (
    PACKT_PERIOD,
    PACKT_REVENUE_CELL,
    PACKT_REVENUE_ROW,
    PACKT_REVENUE_VALUE,
    PACKT_TRAFFIC_DIFF,
    PACKT_TRAFFIC_HV_ROW,
    PACKT_TRAFFIC_PC_ROW,
)
from tests.conftest import JOB, s3_settings

pytestmark = pytest.mark.asyncio


def _stable(body):
    if isinstance(body, dict):
        return {key: _stable(value) for key, value in body.items() if key != "analysis_id"}
    if isinstance(body, list):
        return [_stable(value) for value in body]
    return body


async def _answers(app) -> dict:
    headers = {"X-User-Id": "alex", "X-Client-Id": "desk"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fas") as client:
        book = await client.get(f"/v1/books/{JOB}", headers=headers)
        series = await client.post(
            f"/v1/books/{JOB}/series",
            headers=headers,
            json={"row_keys": [PACKT_REVENUE_ROW], "periods": [PACKT_PERIOD]},
        )
        expression = await client.post(
            f"/v1/books/{JOB}/expression",
            headers=headers,
            json={
                "expression": "a - b",
                "bindings": {
                    "a": {"row_key": PACKT_TRAFFIC_PC_ROW, "period_id": PACKT_PERIOD},
                    "b": {"row_key": PACKT_TRAFFIC_HV_ROW, "period_id": PACKT_PERIOD},
                },
            },
        )
    assert book.status_code == 200, book.text
    assert series.status_code == 200, series.text
    assert expression.status_code == 200, expression.text
    return {"book": book.json(), "series": series.json(), "expression": expression.json()}


async def test_sync_local_to_minio_matches_api(tmp_path, minio_endpoint, redis_runtime, builder, settings):
    local_store = await open_storage(settings)
    local = FasService(
        settings,
        local_store,
        PyarrowParquet(),
        builder,
        WrenQuery(settings),
        redis_runtime,
    )
    await local.perform_load(JOB, actor=Actor(user_id="alex", client_id="desk"), fence=1)
    remote_settings = s3_settings(tmp_path, minio_endpoint)
    remote_settings = remote_settings.model_copy(
        update={"fas_s3_prefix": f"sync{tmp_path.name}"}
    )
    destination = await open_storage(remote_settings)
    try:
        report = await sync_stores(local_store, destination, verify=True)
        assert report["copied"] > 0
        assert report["conflicts"] == []
        assert report["verify_errors"] == []
        remote = FasService(
            remote_settings,
            destination,
            PyarrowParquet(),
            builder,
            WrenQuery(remote_settings),
            redis_runtime,
        )
        left = await _answers(create_app(settings, service=local, support=redis_runtime))
        right = await _answers(create_app(remote_settings, service=remote, support=redis_runtime))
        assert left["book"]["build_key"] == right["book"]["build_key"]
        assert left["book"]["state_seq"] == right["book"]["state_seq"]
        assert left["book"]["builder_ref"] == right["book"]["builder_ref"]
        assert left["book"]["build_count"] == right["book"]["build_count"]
        assert _stable(left["book"]) == _stable(right["book"])
        assert _stable(left["series"]) == _stable(right["series"])
        assert _stable(left["expression"]) == _stable(right["expression"])
        rows = right["series"]["result_data"]["series"]
        assert rows[0]["value"] == PACKT_REVENUE_VALUE
        assert rows[0]["cell_id"] == PACKT_REVENUE_CELL
        assert right["expression"]["result_data"]["expression"]["result"] == PACKT_TRAFFIC_DIFF
        manifest = f"books/{JOB}/{left['book']['build_key']}/manifest.json"
        assert await local_store.get(manifest) == await destination.get(manifest)
    finally:
        await destination.delete_prefix("")
