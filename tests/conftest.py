"""Общие фикстуры фазы 0."""

from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path

import pytest

from finance_analysis.adapters.builder.fixture import FixtureBuilder
from finance_analysis.adapters.redis.runtime import RedisRuntime, version_at_least
from finance_analysis.adapters.storage.parquet_io import PyarrowParquet
from finance_analysis.adapters.storage.store import S3Store, open_storage
from finance_analysis.adapters.wren.query import WrenQuery
from finance_analysis.application.service import FasService
from finance_analysis.settings import Settings
from tests.books import ALIASES, BUILDER_ROOT

JOB = ALIASES["packt"]
REDIS_SERVER = os.environ.get("FAS_REDIS_SERVER", "/tmp/redis-src/redis-8.6.7/src/redis-server")
REDIS_PORT = int(os.environ.get("FAS_TEST_REDIS_PORT", "6381"))
_STARTED_URL: str | None = None


def redis_url() -> str:
    explicit = os.environ.get("FAS_TEST_REDIS")
    if explicit:
        return explicit
    if _STARTED_URL:
        return _STARTED_URL
    return f"redis://127.0.0.1:{REDIS_PORT}/15"


def _redis_86(version: str | None) -> bool:
    return bool(version) and version_at_least(version, (8, 6, 5)) and not version_at_least(version, (8, 7, 0))


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except OSError:
        return False


class _ContractRedis:
    """Redis 8.6.x для контрактных тестов. Порт 6379 (часто 7.0.15) не используется."""

    def __init__(self) -> None:
        self.port = REDIS_PORT
        self.directory = Path("/tmp/fas-redis-contract")
        self.url = f"redis://127.0.0.1:{self.port}/15"
        self.proc: subprocess.Popen | None = None
        self.log_path = self.directory / "redis.log"

    def start(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        if _port_open(self.port):
            raise RuntimeError(f"порт {self.port} уже занят")
        log = open(self.log_path, "a", encoding="utf-8")  # noqa: SIM115 — живёт вместе с redis
        self.proc = subprocess.Popen(
            [
                REDIS_SERVER,
                "--port",
                str(self.port),
                "--bind",
                "127.0.0.1",
                "--dir",
                str(self.directory),
                "--appendonly",
                "no",
                "--save",
                "",
                "--protected-mode",
                "yes",
                "--daemonize",
                "no",
                "--logfile",
                str(self.log_path),
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        deadline = time.time() + 15
        while time.time() < deadline:
            if _port_open(self.port):
                return
            if self.proc.poll() is not None:
                raise RuntimeError(self.log_path.read_text(encoding="utf-8")[-2000:])
            time.sleep(0.05)
        raise RuntimeError("redis 8.6 не открыл порт")

    def kill(self) -> None:
        proc = self.proc
        if proc is None or proc.poll() is not None:
            self.proc = None
            return
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        self.proc = None


@pytest.fixture(scope="session")
def redis86_url():
    global _STARTED_URL
    explicit = os.environ.get("FAS_TEST_REDIS")
    if explicit:
        _STARTED_URL = explicit
        yield explicit
        return
    if not Path(REDIS_SERVER).is_file():
        pytest.skip("нет бинарника Redis 8.6.7 (FAS_REDIS_SERVER)")
    server = _ContractRedis()
    server.start()
    _STARTED_URL = server.url
    try:
        yield server.url
    finally:
        server.kill()


@pytest.fixture
def settings(tmp_path, redis86_url) -> Settings:
    return Settings(
        FAS_DATA_DIR=str(tmp_path / "data"),
        FAS_S3_PREFIX="fas",
        FAS_REDIS_URL=redis86_url,
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
async def redis_runtime(settings, redis86_url):
    del redis86_url
    runtime = RedisRuntime.connect(settings)
    version = await runtime.server_version()
    if not _redis_86(version):
        await runtime.close()
        pytest.fail(f"контрактные тесты требуют Redis 8.6.x, сейчас {version}")
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


@pytest.fixture
async def task_workers(settings, local_service, tmp_path):
    """Поднимает очереди Taskiq и два воркера на каталоге фикстур.

    Сервис теста начинает ставить задачи в эти очереди. Воркеры
    `fas:glossary` и `fas:interactive` читают тот же каталог данных и Redis,
    а книги берут из каталога фикстур. После теста процессы останавливаются,
    а соединение очереди закрывается.
    """

    from finance_analysis.adapters.queue.jobs import TaskiqJobs
    from finance_analysis.adapters.queue.names import GLOSSARY, INTERACTIVE
    from tests.chaos.harness import WorkerProc

    jobs = await TaskiqJobs.open(settings)
    await jobs.startup()
    local_service.jobs = jobs
    extra = {"FAS_FIXTURE_DIR": str(BUILDER_ROOT)}
    glossary = WorkerProc(settings, tmp_path, "glossary", queue=GLOSSARY, extra=extra)
    interactive = WorkerProc(settings, tmp_path, "interactive", queue=INTERACTIVE, extra=extra)
    try:
        glossary.wait_ready(40)
        interactive.wait_ready(40)
        yield jobs
    finally:
        glossary.stop()
        interactive.stop()
        local_service.jobs = None
        await jobs.shutdown()


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
        FAS_REDIS_URL=redis_url(),
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
    explicit = os.environ.get("FAS_TEST_MINIO")
    if explicit:
        yield explicit.rstrip("/")
        return
    if _port_open(9000):
        pytest.skip("порт 9000 занят, задайте FAS_TEST_MINIO")
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
