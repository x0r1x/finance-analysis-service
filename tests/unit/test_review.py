"""Регрессии по замечаниям ревью PR #1."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from finance_analysis.adapters.storage.store import LocalStore
from finance_analysis.adapters.wren.query import (
    EnginePool,
    EngineStartInterrupted,
    _apply_limits,
    _Slot,
)
from finance_analysis.application.semantic_guard import SemanticWriteGuard
from finance_analysis.application.service import Accepted
from finance_analysis.cli import _settings_for
from finance_analysis.domain.book import Actor
from finance_analysis.domain.errors import RequestInProgress
from finance_analysis.domain.periods import expand_ref
from finance_analysis.settings import Settings
from tests.conftest import JOB

ROOT = Path(__file__).resolve().parents[2]


def test_file_url_ignores_ambient_s3(monkeypatch):
    monkeypatch.setenv("FAS_S3_BUCKET", "bucket")
    monkeypatch.setenv("FAS_S3_ACCESS_KEY", "key")
    monkeypatch.setenv("FAS_S3_SECRET_KEY", "secret")
    monkeypatch.setenv("FAS_S3_ENDPOINT", "http://minio:9000")
    monkeypatch.setenv("FAS_READ_ONLY", "true")
    settings = _settings_for("file:///tmp/fas-backup")
    assert settings.s3_enabled is False
    assert settings.fas_read_only is False
    assert settings.fas_data_dir == "/tmp/fas-backup"
    remote = _settings_for("s3://bucket/prefix")
    assert remote.fas_read_only is False
    assert remote.fas_s3_bucket == "bucket"
    assert remote.fas_s3_endpoint == "http://minio:9000"
    assert remote.fas_s3_ssl is False


def test_s3_ssl_follows_endpoint():
    assert Settings(FAS_REDIS_URL="redis://unused").fas_s3_ssl is True
    assert Settings(FAS_REDIS_URL="redis://unused").fas_host == "127.0.0.1"
    assert Settings(FAS_REDIS_URL="redis://unused").fas_port == 8080
    plain = Settings(
        FAS_REDIS_URL="redis://unused",
        FAS_S3_ENDPOINT="http://127.0.0.1:9000",
        FAS_S3_BUCKET="finance-context",
        FAS_S3_ACCESS_KEY="minioadmin",
        FAS_S3_SECRET_KEY="minioadmin",
    )
    assert plain.fas_s3_ssl is False
    explicit = Settings(
        FAS_REDIS_URL="redis://unused",
        FAS_S3_ENDPOINT="https://s3.amazonaws.com",
        FAS_S3_BUCKET="finance-context",
        FAS_S3_ACCESS_KEY="key",
        FAS_S3_SECRET_KEY="secret",
        FAS_S3_SSL=True,
    )
    assert explicit.fas_s3_ssl is True
    https = Settings(
        _env_file=None,
        FAS_REDIS_URL="redis://unused",
        FAS_S3_ENDPOINT="https://minio.example:9000",
        FAS_S3_BUCKET="finance-context",
        FAS_S3_ACCESS_KEY="key",
        FAS_S3_SECRET_KEY="secret",
    )
    assert https.fas_s3_ssl is True
    bare = Settings(
        _env_file=None,
        FAS_REDIS_URL="redis://unused",
        FAS_S3_ENDPOINT="minio.example:9000",
        FAS_S3_BUCKET="finance-context",
        FAS_S3_ACCESS_KEY="key",
        FAS_S3_SECRET_KEY="secret",
    )
    assert bare.fas_s3_ssl is True


def test_container_rejects_loopback_redis():
    host = Settings(_env_file=None, FAS_REDIS_URL="redis://127.0.0.1:6379/1", FAS_IN_CONTAINER=False)
    assert host.fas_in_container is False
    for url in (
        "redis://127.0.0.1:6379/1",
        "redis://user:pass@localhost:6379/1",
        "redis://[::1]:6379/1",
    ):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, FAS_REDIS_URL=url, FAS_IN_CONTAINER=True)
    remote = Settings(_env_file=None, FAS_REDIS_URL="redis://redis:6379/1", FAS_IN_CONTAINER=True)
    assert remote.fas_redis_url == "redis://redis:6379/1"


def test_require_admin_token_fail_closed():
    """Prod perimeter: require flag without token refuses startup; with token loads."""

    ok = Settings(_env_file=None, FAS_REDIS_URL="redis://unused")
    assert ok.fas_require_admin_token is False
    assert ok.fas_admin_token is None
    with pytest.raises(ValidationError):
        Settings(_env_file=None, FAS_REDIS_URL="redis://unused", FAS_REQUIRE_ADMIN_TOKEN=True)
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            FAS_REDIS_URL="redis://unused",
            FAS_REQUIRE_ADMIN_TOKEN=True,
            FAS_ADMIN_TOKEN="   ",
        )
    locked = Settings(
        _env_file=None,
        FAS_REDIS_URL="redis://unused",
        FAS_REQUIRE_ADMIN_TOKEN=True,
        FAS_ADMIN_TOKEN="prod-secret",
    )
    assert locked.fas_require_admin_token is True
    assert locked.fas_admin_token == "prod-secret"


def test_s3_url_without_credentials_is_rejected(monkeypatch):
    for name in ("FAS_S3_BUCKET", "FAS_S3_ACCESS_KEY", "FAS_S3_SECRET_KEY", "FAS_S3_ENDPOINT"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValidationError):
        _settings_for("s3://bucket/prefix")


def test_duckdb_limits_must_be_positive():
    with pytest.raises(ValidationError):
        Settings(WREN_DUCKDB_MEMORY_MB=0)
    with pytest.raises(ValidationError):
        Settings(WREN_DUCKDB_THREADS=-1)


def test_required_duckdb_limit_failure_is_raised():
    class Conn:
        def execute(self, sql):
            raise RuntimeError(sql)

    class Engine:
        connection = Conn()

        def _get_connector(self):
            return self

    with pytest.raises(RuntimeError):
        _apply_limits(Engine(), Settings(WREN_DUCKDB_MEMORY_MB=256, WREN_DUCKDB_THREADS=1))


def test_expand_ref_caps_rectangle():
    cells, truncated = expand_ref("A1:B2", default_sheet="S", used_rows=100, used_cols=10)
    assert truncated is False
    assert cells == ["S!A1", "S!B1", "S!A2", "S!B2"]
    cells, truncated = expand_ref("A1:XFD1048576", default_sheet="S", used_rows=10, used_cols=3)
    assert truncated is True
    assert len(cells) == 30
    cells, truncated = expand_ref("A1:ZZ10000", default_sheet="S", used_rows=100_000, used_cols=100)
    assert truncated is True
    assert len(cells) == 50_000


def test_slo_requires_a_clean_run():
    import importlib.util

    path = ROOT / "scripts" / "k6" / "run_baseline.py"
    spec = importlib.util.spec_from_file_location("fas_k6_baseline", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    slo_met = module.slo_met

    clean = [{"exit_code": 0, "failed_rate": 0, "check_rate": 1, "p95_ms": 80}]
    assert slo_met(clean) is True
    assert slo_met([{**clean[0], "exit_code": 1}]) is False
    assert slo_met([{**clean[0], "failed_rate": 0.01}]) is False
    assert slo_met([{**clean[0], "check_rate": 0.5}]) is False
    assert slo_met([{**clean[0], "p95_ms": 800}]) is False


def test_k6_setup_waits_until_the_book_is_ready():
    for name in ("s1.js", "s2.js"):
        text = (ROOT / "scripts" / "k6" / name).read_text(encoding="utf-8")
        assert "status === 202" not in text.split("export default")[0]
        assert "operations/" in text
        assert 'r.status === 200' in text
    assert "checks:" in (ROOT / "scripts" / "k6" / "s1.js").read_text(encoding="utf-8")
    assert "checks:" in (ROOT / "scripts" / "k6" / "s2.js").read_text(encoding="utf-8")


def _guard(tmp_path):
    store = LocalStore(tmp_path / "store")
    return SemanticWriteGuard(store, catalog=frozenset({"revenue", "cost"}), targets=frozenset({"row-1"}))


async def test_replaced_value_is_appended_again(tmp_path):
    guard = _guard(tmp_path)
    actor = Actor()
    first = await guard.append(
        JOB,
        target="row-1",
        event_type="concept.set",
        value="revenue",
        actor=actor,
        expected_seq=None,
        request_id="a",
        concept="revenue",
    )
    second = await guard.append(
        JOB,
        target="row-1",
        event_type="concept.set",
        value="cost",
        actor=actor,
        expected_seq=first.event["seq"],
        request_id="b",
        concept="cost",
    )
    third = await guard.append(
        JOB,
        target="row-1",
        event_type="concept.set",
        value="revenue",
        actor=actor,
        expected_seq=second.event["seq"],
        request_id="c",
        concept="revenue",
    )
    assert third.duplicate is False
    assert third.event["seq"] == 3
    replay = await guard.append(
        JOB,
        target="row-1",
        event_type="concept.set",
        value="revenue",
        actor=actor,
        expected_seq=1,
        request_id="a",
        concept="revenue",
    )
    assert replay.duplicate is True
    assert replay.event["seq"] == 1
    assert len(await guard.read_all(JOB)) == 3


async def test_concurrent_retry_is_duplicate(tmp_path):
    guard = _guard(tmp_path)
    actor = Actor()

    async def once():
        return await guard.append(
            JOB,
            target="row-1",
            event_type="concept.set",
            value="revenue",
            actor=actor,
            expected_seq=None,
            request_id="same",
            concept="revenue",
        )

    results = await asyncio.gather(*[once() for _ in range(8)])
    assert all(item.accepted for item in results)
    assert sum(item.duplicate for item in results) == 7
    assert len(await guard.read_all(JOB)) == 1


async def test_cancelled_creator_does_not_stick_the_pool():
    pool = EnginePool(Settings(WREN_DUCKDB_MEMORY_MB=256, WREN_DUCKDB_THREADS=1))
    started = asyncio.Event()

    async def hang():
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(pool.lease(("book",), hang))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    async def ready():
        return _Slot(engine=None, mdl_json="{}")

    context = await asyncio.wait_for(pool.lease(("book",), ready), timeout=1)
    async with context:
        assert ("book",) in pool._slots


async def test_waiter_hears_a_retryable_error_when_creator_is_cancelled():
    pool = EnginePool(Settings(WREN_DUCKDB_MEMORY_MB=256, WREN_DUCKDB_THREADS=1))
    started = asyncio.Event()

    async def hang():
        started.set()
        await asyncio.Event().wait()

    creator = asyncio.create_task(pool.lease(("book",), hang))
    await started.wait()
    waiter = asyncio.create_task(pool.lease(("book",), hang))
    await asyncio.sleep(0.05)
    creator.cancel()
    with pytest.raises(asyncio.CancelledError):
        await creator
    with pytest.raises(EngineStartInterrupted):
        await asyncio.wait_for(waiter, timeout=1)


async def test_cancelled_queue_does_not_leak_waiters():
    pool = EnginePool(Settings(WREN_DUCKDB_MEMORY_MB=256, WREN_DUCKDB_THREADS=1))
    slot = _Slot(engine=None, mdl_json="{}")
    await slot.sem.acquire()
    pool._slots[("book",)] = [slot]

    async def ready():
        return _Slot(engine=None, mdl_json="{}")

    task = asyncio.create_task(pool.lease(("book",), ready))
    await asyncio.sleep(0.05)
    assert slot.waiters == 1
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert slot.waiters == 0
    slot.sem.release()


async def test_singleflight_preserves_accepted(redis_runtime):
    calls = 0

    async def factory():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.2)
        return Accepted({"id": "op"})

    first = asyncio.create_task(redis_runtime.singleflight("accepted", factory))
    await asyncio.sleep(0.05)
    second = asyncio.create_task(redis_runtime.singleflight("accepted", factory))
    left, right = await asyncio.gather(first, second)
    assert isinstance(left, Accepted)
    assert isinstance(right, Accepted)
    assert left.operation["id"] == right.operation["id"] == "op"
    assert calls == 1


async def test_failed_idempotency_key_is_released(redis_runtime):
    actor = Actor(user_id="u", client_id="c")
    assert await redis_runtime.idem_begin(actor, "POST", "/r", "k", b"{}") is None
    with pytest.raises(RequestInProgress):
        await redis_runtime.idem_begin(actor, "POST", "/r", "k", b"{}")
    await redis_runtime.idem_abort(actor, "POST", "/r", "k", b"{}")
    assert await redis_runtime.idem_begin(actor, "POST", "/r", "k", b"{}") is None
    await redis_runtime.idem_finish(actor, "POST", "/r", "k", b"{}", {"ok": True}, 200)
    await redis_runtime.idem_abort(actor, "POST", "/r", "k", b"{}")
    stored = await redis_runtime.idem_begin(actor, "POST", "/r", "k", b"{}")
    assert stored["status"] == "done"
    assert stored["response"] == {"ok": True}


async def test_ensure_keeps_the_book_lock_after_the_sync_wait(settings, local_service, redis_runtime):
    started = asyncio.Event()
    release = asyncio.Event()
    original = local_service.perform_load

    async def slow(job_id, **kwargs):
        started.set()
        await release.wait()
        return await original(job_id, **kwargs)

    local_service.perform_load = slow
    task = asyncio.create_task(local_service.ensure(JOB, Actor(), wait_sec=0.3))
    await asyncio.wait_for(started.wait(), timeout=30)
    result = await task
    assert isinstance(result, Accepted)
    assert await redis_runtime.held(f"book:{JOB}")
    release.set()
    for _ in range(200):
        if not await redis_runtime.held(f"book:{JOB}"):
            break
        await asyncio.sleep(0.1)
    else:
        raise AssertionError("замок книги остался занят после загрузки")
