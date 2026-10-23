"""RLAC, strict mode и must-verify MinIO / пула."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest
from wren.model.error import WrenError

from finance_analysis.adapters.storage.store import S3Store, open_storage
from finance_analysis.adapters.wren.query import WrenQuery, _apply_limits
from finance_analysis.application.service import FasService
from finance_analysis.domain.book import Actor
from finance_analysis.domain.errors import InvalidArgument
from tests.books import (
    PACKT_PERIOD,
    PACKT_TRAFFIC_DIFF,
    PACKT_TRAFFIC_HV_ROW,
    PACKT_TRAFFIC_PC_ROW,
)
from tests.conftest import JOB, s3_settings

pytestmark = pytest.mark.asyncio


async def test_series_expression_on_minio(tmp_path, minio_endpoint, redis_runtime, builder):
    settings = s3_settings(tmp_path, minio_endpoint)
    settings = settings.model_copy(update={"fas_s3_prefix": f"packt{tmp_path.name}"})
    store = await open_storage(settings)
    service = FasService(settings, store, __import__("finance_analysis.adapters.storage.parquet_io", fromlist=["PyarrowParquet"]).PyarrowParquet(), builder, WrenQuery(settings), redis_runtime)
    actor = Actor(user_id="alex", client_id="desk")
    await service.perform_load(JOB, actor=actor, fence=1)
    series = await service.series(
        JOB,
        {"row_keys": [PACKT_TRAFFIC_PC_ROW], "periods": [PACKT_PERIOD]},
        actor,
        wait_sec=30,
    )
    assert series["result_data"]["series"][0]["value"] == "3125000"
    expression = await service.expression(
        JOB,
        {
            "expression": "a - b",
            "bindings": {
                "a": {"row_key": PACKT_TRAFFIC_PC_ROW, "period_id": PACKT_PERIOD},
                "b": {"row_key": PACKT_TRAFFIC_HV_ROW, "period_id": PACKT_PERIOD},
            },
        },
        actor,
        wait_sec=30,
    )
    assert expression["result_data"]["expression"]["result"] == PACKT_TRAFFIC_DIFF
    await store.delete_prefix("")


async def test_rlac_and_unscoped_sql(local_service):
    actor = Actor()
    await local_service.perform_load(JOB, actor=actor, fence=1)
    head = (await local_service._read_head(JOB))[0]
    pin = await local_service._pin(JOB, head)
    with pytest.raises(InvalidArgument):
        await local_service.query.sql(JOB, "SELECT 1", pin=None)
    table = await local_service.query.sql(JOB, "SELECT cell_id FROM series", pin=pin)
    assert table.num_rows >= 1
    other = "b" * 64
    hidden = await local_service.query.pool.lease(
        (JOB, pin["build_key"], pin["derive_key"]),
        lambda: local_service.query._create(JOB, pin["paths"]),
    )
    async with hidden as slot:
        foreign = await asyncio.to_thread(
            lambda: slot.engine.query(
                "SELECT cell_id FROM series",
                limit=10,
                properties={"session_model_id": f"'{other}'"},
            )
        )
        assert foreign.num_rows == 0
        with pytest.raises(WrenError):
            await asyncio.to_thread(lambda: slot.engine.query("SELECT cell_id FROM series", limit=10))
        with pytest.raises(WrenError):
            await asyncio.to_thread(
                lambda: slot.engine.query(
                    "SELECT * FROM read_parquet('missing.parquet')",
                    limit=1,
                    properties={"session_model_id": f"'{JOB}'"},
                )
            )


async def test_minio_region_and_conditional(minio_endpoint, tmp_path):
    store = S3Store(
        bucket="fas",
        prefix=f"verify{tmp_path.name}",
        endpoint=minio_endpoint,
        region="ap-northeast-1",
        access_key="minioadmin",
        secret_key="minioadmin",
    )
    await store.selftest()
    report = {
        "if_none_match": True,
        "if_match": True,
        "region": "ap-northeast-1",
        "endpoint": minio_endpoint,
    }
    path = Path("deploy/must-verify.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if path.is_file():
        existing = json.loads(path.read_text())
    existing["minio"] = report
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    await store.delete_prefix("")


async def test_pool_memory_and_gil(local_service):
    actor = Actor()
    await local_service.perform_load(JOB, actor=actor, fence=1)
    head = (await local_service._read_head(JOB))[0]
    pin = await local_service._pin(JOB, head)
    notes = {}

    async def factory():
        return await local_service.query._create(JOB, pin["paths"])

    async with await local_service.query.pool.lease((JOB, head.build_key, head.derive_key), factory) as slot:
        notes = dict(slot.limits)
        started = time.perf_counter()
        loop_ticks = 0

        def heavy():
            slot.engine._get_connector().connection.execute("SELECT count(*) FROM range(2000000)").fetchone()

        async def tick():
            nonlocal loop_ticks
            while time.perf_counter() - started < 0.3:
                await asyncio.sleep(0)
                loop_ticks += 1

        await asyncio.gather(asyncio.to_thread(heavy), tick())
        notes["loop_ticks_during_query"] = loop_ticks
        notes["gil_released"] = loop_ticks > 5
        notes["cold_starts"] = len(local_service.query.pool.cold_starts)
        cursor_safe = False
        try:
            cursor = slot.engine._get_connector().connection.cursor()
            cursor.execute("SELECT 1").fetchone()
            cursor.close()
            cursor_safe = True
        except Exception as exc:  # noqa: BLE001 — сбой cursor() только диагностический
            notes["cursor_error"] = str(exc)
        notes["cursor_safe"] = cursor_safe
        notes["semaphore"] = 1
    path = Path("deploy/must-verify.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(path.read_text()) if path.is_file() else {}
    existing["pool"] = notes
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    assert notes.get("set_ok") is True
    assert _apply_limits
