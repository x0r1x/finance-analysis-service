"""Общие фикстуры фазы 0."""

from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path

import pytest

from finance_analysis.adapters.builder.fixture import FixtureBuilder
from finance_analysis.adapters.redis.runtime import RedisRuntime
from finance_analysis.adapters.storage.parquet_io import PyarrowParquet
from finance_analysis.adapters.storage.store import S3Store, open_storage
from finance_analysis.adapters.wren.query import WrenQuery
from finance_analysis.application.service import FasService
from finance_analysis.settings import Settings
from tests.books import ALIASES, BUILDER_ROOT

JOB = ALIASES["packt"]
REDIS_URL = os.environ.get("FAS_TEST_REDIS", "redis://127.0.0.1:6379/15")


def _redis_up() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 6379), timeout=0.2):
            return True
    except OSError:
        return False


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        FAS_DATA_DIR=str(tmp_path / "data"),
        FAS_S3_PREFIX="fas",
        FAS_REDIS_URL=REDIS_URL,
        WREN_ENGINE_POOL=2,
        WREN_POOL_MEMORY_MB=512,
        WREN_DUCKDB_MEMORY_MB=256,
        WREN_DUCKDB_THREADS=1,
        WREN_THREADS=2,
        CPU_THREADS=2,
        SYNC_DEADLINE_MS=15000,
        LOAD_SYNC_SEC=60,
        RATE_USER_RPS=1000,
        RATE_CLIENT_RPS=1000,
        RATE_ANON_RPS=1000,
        RATE_USER_BURST=1000,
        USER_MAX_INFLIGHT=32,
        API_MAX_INFLIGHT=64,
    )


@pytest.fixture
async def redis_runtime(settings):
    if not _redis_up():
        pytest.skip("redis недоступен")
    runtime = RedisRuntime.connect(settings)
    await runtime.redis.flushdb()
    yield runtime
    await runtime.redis.flushdb()
    await runtime.close()


@pytest.fixture
def builder() -> FixtureBuilder:
    return FixtureBuilder(BUILDER_ROOT)


@pytest.fixture
async def local_service(settings, redis_runtime, builder):
    store = await open_storage(settings)
    service = FasService(
        settings,
        store,
        PyarrowParquet(),
        builder,
        WrenQuery(settings),
        redis_runtime,
    )
    yield service


def s3_settings(tmp_path, endpoint: str, bucket: str = "fas") -> Settings:
    return Settings(
        FAS_DATA_DIR=str(tmp_path / "data"),
        FAS_S3_BUCKET=bucket,
        FAS_S3_PREFIX="fas",
        FAS_S3_ENDPOINT=endpoint,
        FAS_S3_REGION="ap-northeast-1",
        FAS_S3_ACCESS_KEY="minioadmin",
        FAS_S3_SECRET_KEY="minioadmin",
        FAS_S3_SSL=False,
        FAS_REDIS_URL=REDIS_URL,
        WREN_ENGINE_POOL=2,
        WREN_POOL_MEMORY_MB=512,
        WREN_DUCKDB_MEMORY_MB=256,
        WREN_DUCKDB_THREADS=1,
        WREN_THREADS=2,
        CPU_THREADS=2,
        SYNC_DEADLINE_MS=15000,
        LOAD_SYNC_SEC=60,
        RATE_ANON_RPS=1000,
        RATE_USER_RPS=1000,
        RATE_USER_BURST=1000,
    )


@pytest.fixture(scope="session")
def minio_endpoint():
    binary = Path("/tmp/minio")
    if not binary.is_file():
        pytest.skip("бинарник MinIO не найден")
    data = Path("/tmp/fas-minio-data")
    data.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "MINIO_ROOT_USER": "minioadmin",
            "MINIO_ROOT_PASSWORD": "minioadmin",
            "MINIO_REGION": "ap-northeast-1",
            "MINIO_SITE_REGION": "ap-northeast-1",
        }
    )
    proc = subprocess.Popen(
        [str(binary), "server", str(data), "--address", "127.0.0.1:9000", "--console-address", "127.0.0.1:9001"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", 9000), timeout=0.2):
                break
        except OSError:
            if proc.poll() is not None:
                pytest.skip("MinIO завершился")
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.skip("MinIO не открыл порт")
    import boto3

    client = boto3.client(
        "s3",
        endpoint_url="http://127.0.0.1:9000",
        aws_access_key_id="minioadmin",
        aws_secret_access_key="minioadmin",
        region_name="ap-northeast-1",
    )
    buckets = {item["Name"] for item in client.list_buckets().get("Buckets", [])}
    if "fas" not in buckets:
        client.create_bucket(Bucket="fas", CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"})
    yield "http://127.0.0.1:9000"
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture
async def s3_store(minio_endpoint, tmp_path):
    settings = s3_settings(tmp_path, minio_endpoint, bucket=f"fas-{os.getpid()}")
    # общий бакет fas: префикс уникален на тест
    settings = settings.model_copy(update={"fas_s3_bucket": "fas", "fas_s3_prefix": f"t{os.getpid()}{id(tmp_path)}"})
    store = S3Store(
        bucket=settings.fas_s3_bucket,
        prefix=settings.fas_s3_prefix,
        endpoint=settings.fas_s3_endpoint,
        region=settings.fas_s3_region,
        access_key=settings.fas_s3_access_key or "",
        secret_key=settings.fas_s3_secret_key or "",
    )
    await store.selftest()
    yield store
    await store.delete_prefix("")
