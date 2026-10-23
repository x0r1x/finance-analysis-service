"""Решающие chaos-тесты 0.22 (§9) на Redis 8.6.x."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import time
from contextlib import suppress
from pathlib import Path

import pytest
import redis.asyncio as redis_async

from finance_analysis.adapters.queue import runtime as runtime_mod
from finance_analysis.adapters.queue.jobs import TaskiqJobs
from finance_analysis.adapters.queue.names import CONSUMER_GROUP, GLOSSARY, INTERACTIVE
from finance_analysis.adapters.queue.runtime import WorkerRuntime
from finance_analysis.adapters.queue.tasks import reconcile_operations
from finance_analysis.adapters.redis.runtime import version_at_least
from finance_analysis.application.operations import read_op
from finance_analysis.domain.errors import RateLimited
from tests.chaos.conftest import _port_open
from tests.chaos.harness import (
    HOLD_WORKER,
    chaos_settings,
    start_scheduler,
    start_worker,
    starts,
    submit,
    wait_started,
    wait_status,
)

RESULTS: dict = {}
OOM_CGROUP = Path(
    "/sys/fs/cgroup/system.slice/pod-aoa72jkzlneujis4uljsxyt6oq-674d1c54/cursor-agent/fasoom2"
)


def record(name: str, payload: dict) -> None:
    RESULTS[name] = payload
    print(f"CHAOS {name} {json.dumps(payload, ensure_ascii=False)}")


@pytest.fixture(scope="module", autouse=True)
def _dump_results():
    yield
    Path("/tmp/fas-chaos-results.json").write_text(
        json.dumps(RESULTS, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


@pytest.fixture
async def chaos(tmp_path, redis86):
    settings = chaos_settings(tmp_path / "data", redis86.url)
    client = redis_async.Redis.from_url(redis86.url, socket_timeout=None)
    info = await client.info("server")
    version = info.get("redis_version") or info.get(b"redis_version")
    if isinstance(version, bytes):
        version = version.decode()
    if not version_at_least(str(version)):
        pytest.fail(f"нужен Redis >= 8.6.5, сейчас {version}")
    await client.flushall()
    jobs = await TaskiqJobs.open(settings)
    await jobs.startup()
    box = type("Chaos", (), {})()
    box.settings = settings
    box.redis = client
    box.jobs = jobs
    box.procs = []
    box.version = str(version)
    box.redis86 = redis86
    box.workdir = tmp_path
    RESULTS.setdefault("redis", {"version": str(version)})
    try:
        yield box
    finally:
        for proc in box.procs:
            proc.stop()
        with suppress(OSError, RuntimeError, redis_async.RedisError):
            await jobs.shutdown()
        with suppress(OSError, RuntimeError, redis_async.RedisError):
            await client.aclose()


def stop_all(chaos) -> None:
    for proc in chaos.procs:
        proc.stop()
    chaos.procs.clear()


def _oom_cgroup() -> Path | None:
    named = os.environ.get("FAS_TEST_OOM_CGROUP")
    if named and (Path(named) / "memory.max").is_file():
        return Path(named)
    if (OOM_CGROUP / "memory.max").is_file():
        return OOM_CGROUP
    try:
        here = Path("/proc/self/cgroup").read_text(encoding="utf-8").strip().split(":")[-1]
    except OSError:
        return None
    current = Path("/sys/fs/cgroup") / here.lstrip("/")
    for candidate in (current.parent / "fasoom2", current / "fasoom2"):
        if (candidate / "memory.max").is_file():
            return candidate
        try:
            candidate.mkdir(exist_ok=True)
        except OSError:
            continue
        if (candidate / "memory.max").is_file():
            return candidate
    return None


async def _kill_case(chaos, loaded: bool, label: str) -> dict:
    worker = start_worker(chaos, f"kill-{label}", max_async=1)
    operation = await submit(chaos, user=f"kill-{label}", stage="sleep", seconds=3)
    await wait_started(chaos.redis, operation["id"])
    extras = []
    if loaded:
        for index in range(2):
            extras.append(
                await submit(chaos, user=f"load-{label}-{index}", stage="sleep", seconds=0.05)
            )
    killed = time.time()
    os.kill(worker.proc.pid, signal.SIGKILL)
    worker.proc.wait(timeout=5)
    start_worker(chaos, f"kill-{label}-next", max_async=1)
    recovery = None
    deadline = time.time() + 30
    while time.time() < deadline:
        stamps = await starts(chaos.redis, operation["id"])
        if len(stamps) >= 2:
            recovery = stamps[1] - killed
            break
        await asyncio.sleep(0.05)
    assert recovery is not None and recovery <= 120, worker.tail()
    final = await wait_status(chaos.jobs.store, operation["id"], timeout=20)
    assert final["status"] == "succeeded", final
    parallel = await chaos.redis.get(f"fas:op:{operation['id']}:parallel")
    assert parallel is None
    execs = int(await chaos.redis.get(f"fas:exec:{operation['id']}") or 0)
    assert execs == 2
    for extra in extras:
        extra_final = await wait_status(chaos.jobs.store, extra["id"], timeout=20)
        assert extra_final["status"] == "succeeded", extra_final
    return {"recovery_sec": round(recovery, 3), "exec": execs, "parallel": 0, "loaded": loaded}


def _interactive_alive(chaos) -> bool:
    for item in chaos.procs:
        if "gloss" in item.log_path.name:
            continue
        if item.proc.poll() is None:
            return True
    return False


async def _poison(chaos, stage: str, extra: dict | None = None) -> dict:
    start_worker(chaos, f"gloss-{stage}", queue=GLOSSARY, max_async=2)
    neighbor = await submit(
        chaos,
        user=f"neighbor-{stage}",
        stage="sleep",
        seconds=0.2,
        queue=GLOSSARY,
    )
    operation = await submit(chaos, user=f"poison-{stage}", stage=stage, seconds=0)
    restarts = 0
    deadline = time.time() + 50
    final = None
    while time.time() < deadline:
        final = await read_op(chaos.jobs.store, operation["id"])
        if final.get("status") in {"succeeded", "failed", "cancelled"}:
            break
        if not _interactive_alive(chaos):
            restarts += 1
            if restarts > 8:
                break
            start_worker(chaos, f"poison-{stage}-{restarts}", max_async=1, extra=extra)
        await asyncio.sleep(0.1)
    assert final is not None and final["status"] == "failed", final
    assert (final.get("error") or {}).get("code") == "poison_task", final
    execs = int(await chaos.redis.get(f"fas:exec:{operation['id']}") or 0)
    attempt = int(await chaos.redis.get(f"fas:op:{operation['id']}:attempt") or 0)
    assert execs == 3, (execs, attempt, final)
    assert attempt == 4
    rows = await chaos.redis.xrange("fas:dlq", count=20)
    found = False
    for _msg_id, fields in rows:
        raw = fields.get(b"op_id", fields.get("op_id", b""))
        text = raw.decode() if isinstance(raw, bytes) else str(raw)
        if text == operation["id"]:
            found = True
    assert found, rows
    neighbor_final = await wait_status(chaos.jobs.store, neighbor["id"], timeout=20)
    assert neighbor_final["status"] == "succeeded", neighbor_final
    later = await submit(chaos, user=f"later-{stage}", stage="sleep", seconds=0.05)
    later_final = await wait_status(chaos.jobs.store, later["id"], timeout=20)
    assert later_final["status"] == "succeeded", later_final
    return {
        "exec": execs,
        "attempt": attempt,
        "dlq": len(rows),
        "restarts": restarts,
        "neighbor": neighbor_final["status"],
        "later": later_final["status"],
        "status": final["status"],
    }


async def test_01_kill_recovers_on_empty_and_loaded_queue(chaos):
    empty = await _kill_case(chaos, False, "empty")
    stop_all(chaos)
    loaded = await _kill_case(chaos, True, "loaded")
    record("1", {"empty": empty, "loaded": loaded, "redis": chaos.version})


async def test_02_sigkill_then_oom_goes_to_dlq(chaos):
    killed = await _poison(chaos, "kill")
    stop_all(chaos)
    cgroup = _oom_cgroup()
    assert cgroup is not None, "нет cgroup с memory.max"
    limit = cgroup / "memory.max"
    previous = limit.read_text(encoding="utf-8")
    try:
        limit.write_text("268435456")
        oom = await _poison(chaos, "oom", extra={"FAS_OOM_CGROUP": str(cgroup)})
    finally:
        limit.write_text(previous)
    record("2", {"sigkill": killed, "oom": oom})


async def test_03_live_task_runs_once(chaos):
    start_worker(chaos, "live-a", max_async=2)
    start_worker(chaos, "live-b", max_async=2)
    seconds = 7
    operation = await submit(chaos, user="live", stage="sleep", seconds=seconds)
    final = await wait_status(chaos.jobs.store, operation["id"], timeout=20)
    execs = int(await chaos.redis.get(f"fas:exec:{operation['id']}") or 0)
    parallel = await chaos.redis.get(f"fas:op:{operation['id']}:parallel")
    assert final["status"] == "succeeded", final
    assert execs == 1
    assert parallel is None
    record(
        "3",
        {
            "exec": execs,
            "parallel": 0,
            "sleep_sec": seconds,
            "idle_timeout_ms": chaos.settings.taskiq_idle_timeout_ms,
        },
    )


async def test_04_duckdb_timeout_and_cancel_release_cpu(chaos):
    start_worker(chaos, "duck-timeout", max_async=1)
    timed = await submit(
        chaos,
        user="duck-timeout",
        stage="duckdb",
        stage_args={"rounds": 10**12},
    )
    timed_final = await wait_status(chaos.jobs.store, timed["id"], timeout=30)
    timed_cpu = float((timed_final.get("result") or {}).get("cpu_release_sec") or -1)
    assert timed_final["status"] == "failed", timed_final
    assert 0 <= timed_cpu <= 5, timed_final
    stop_all(chaos)
    start_worker(
        chaos,
        "duck-cancel",
        max_async=1,
        extra={"HEAVY_STAGE_TIMEOUT_SEC": "30"},
    )
    cancelled = await submit(
        chaos,
        user="duck-cancel",
        stage="duckdb",
        stage_args={"rounds": 10**12},
    )
    deadline = time.time() + 20
    while time.time() < deadline:
        if await chaos.redis.get(f"fas:op:{cancelled['id']}:hb"):
            break
        await asyncio.sleep(0.05)
    else:
        raise AssertionError("нет heartbeat перед отменой")
    await asyncio.sleep(0.5)
    await chaos.redis.set(f"fas:op:{cancelled['id']}:cancel", "1")
    cancel_final = await wait_status(chaos.jobs.store, cancelled["id"], timeout=20)
    cancel_cpu = float((cancel_final.get("result") or {}).get("cpu_release_sec") or -1)
    assert cancel_final["status"] == "cancelled", cancel_final
    assert 0 <= cancel_cpu <= 5, cancel_final
    record(
        "4",
        {
            "timeout_status": timed_final["status"],
            "timeout_cpu_release_sec": round(timed_cpu, 3),
            "cancel_status": cancel_final["status"],
            "cancel_cpu_release_sec": round(cancel_cpu, 3),
        },
    )


async def test_05_interactive_fairness_and_latency(chaos):
    worker = start_worker(chaos, "fair", max_async=8)
    submitted = []
    operations = []
    for index in range(50):
        submitted.append(time.time())
        operations.append(await submit(chaos, user=f"u{index:02d}", stage="sleep", seconds=0.01))
    rss_kb = 0
    deltas = []
    for moment, operation in zip(submitted, operations, strict=True):
        deadline = time.time() + 20
        stamps: list[float] = []
        while time.time() < deadline:
            text = Path(f"/proc/{worker.proc.pid}/status").read_text(encoding="utf-8")
            for line in text.splitlines():
                if line.startswith("VmRSS:"):
                    rss_kb = max(rss_kb, int(line.split()[1]))
            stamps = await starts(chaos.redis, operation["id"])
            if stamps:
                break
            await asyncio.sleep(0.02)
        assert stamps, operation["id"]
        deltas.append(stamps[0] - moment)
    deltas.sort()
    p95 = deltas[int(0.95 * (len(deltas) - 1))]
    assert p95 <= 10, deltas
    assert rss_kb < 512 * 1024, rss_kb
    alice = []
    for _index in range(5):
        alice.append(await submit(chaos, user="alice", stage="sleep", seconds=0.35))
    bob = await submit(chaos, user="bob", stage="sleep", seconds=0.05)
    alice_starts = []
    for operation in alice:
        deadline = time.time() + 20
        stamps = []
        while time.time() < deadline and not stamps:
            stamps = await starts(chaos.redis, operation["id"])
            await asyncio.sleep(0.02)
        assert stamps, operation["id"]
        alice_starts.append(stamps[0])
    bob_deadline = time.time() + 20
    bob_stamps: list[float] = []
    while time.time() < bob_deadline and not bob_stamps:
        bob_stamps = await starts(chaos.redis, bob["id"])
        await asyncio.sleep(0.02)
    assert bob_stamps
    assert bob_stamps[0] < alice_starts[4]
    capped = 0
    with pytest.raises(RateLimited):
        for capped in range(21):
            await submit(chaos, user="capped", stage="sleep", seconds=0.01)
    assert capped == 20
    record(
        "5",
        {
            "users": 50,
            "p95_start_sec": round(p95, 3),
            "max_start_sec": round(deltas[-1], 3),
            "vm_rss_kb": rss_kb,
            "bob_before_alice_fifth_sec": round(alice_starts[4] - bob_stamps[0], 3),
            "rate_limit_at": 21,
        },
    )


async def test_06_locked_book_reschedule_is_once(chaos):
    job = "ab" * 32
    start_scheduler(chaos)
    start_worker(chaos, "book-lock", max_async=1)
    await chaos.redis.set(f"fas:lock:book:{job}", "held", px=180_000)
    operation = await submit(
        chaos,
        user="locker",
        stage="once",
        kind="book.load",
        job_id=job,
        needs_book_lock=True,
    )
    deadline = time.time() + 8
    scheduled = False
    while time.time() < deadline:
        keys = await chaos.redis.keys("fas:schedule:*")
        attempt = await chaos.redis.get(f"fas:op:{operation['id']}:attempt")
        if keys and attempt is None:
            scheduled = True
            break
        await asyncio.sleep(0.05)
    assert scheduled, "перестановка не попала в расписание"
    assert await chaos.redis.get(f"fas:op:{operation['id']}:attempt") is None
    await chaos.redis.delete(f"fas:lock:book:{job}")
    final = await wait_status(chaos.jobs.store, operation["id"], timeout=20)
    commits = int(await chaos.redis.get(f"fas:commit:{operation['id']}") or 0)
    attempt = int(await chaos.redis.get(f"fas:op:{operation['id']}:attempt") or 0)
    assert final["status"] == "succeeded", final
    assert commits == 1
    assert attempt == 1
    record("6", {"commits": commits, "attempt": attempt, "status": final["status"]})


async def test_07_reclaim_resumes_after_lock_ttl(chaos):
    operation = await submit(chaos, user="reclaim", stage="sleep", seconds=0.2)
    stolen = await chaos.redis.xreadgroup(
        CONSUMER_GROUP,
        "dead",
        {INTERACTIVE: ">"},
        count=10,
        block=1000,
    )
    assert stolen, "сообщение не попало в PEL"
    ready = chaos.workdir / "reclaim.ready"
    hold = start_worker(
        chaos,
        "hold",
        max_async=1,
        script=HOLD_WORKER,
        extra={"FAS_RECLAIM_READY": str(ready)},
    )
    deadline = time.time() + 15
    while time.time() < deadline and not ready.is_file():
        if hold.proc.poll() is not None:
            raise AssertionError(hold.tail())
        await asyncio.sleep(0.05)
    assert ready.is_file(), hold.tail()
    lock = f"fas:lock:reclaim:{INTERACTIVE}"
    assert int(await chaos.redis.pttl(lock)) > 0
    killed = time.time()
    os.kill(hold.proc.pid, signal.SIGKILL)
    hold.proc.wait(timeout=5)
    assert int(await chaos.redis.pttl(lock)) > 0
    start_worker(chaos, "reclaim-next", max_async=1, extra={"TASKIQ_IDLE_TIMEOUT_MS": "0"})
    stamps: list[float] = []
    deadline = time.time() + 15
    while time.time() < deadline:
        stamps = await starts(chaos.redis, operation["id"])
        if stamps:
            break
        await asyncio.sleep(0.05)
    assert stamps, "перехват не возобновился"
    waited = stamps[0] - killed
    assert waited >= 2, waited
    assert waited <= 10, waited
    final = await wait_status(chaos.jobs.store, operation["id"], timeout=15)
    assert final["status"] == "succeeded", final
    record("7", {"wait_after_kill_sec": round(waited, 3), "lock_ttl_sec": 3, "status": final["status"]})


async def test_08_redis_restart_keeps_operations(chaos):
    start_worker(chaos, "aof", max_async=4)
    operations = []
    for index in range(4):
        operations.append(
            await submit(
                chaos,
                user=f"aof-{index}",
                stage="marker",
                seconds=3,
                kind="book.load",
                idempotent=True,
            )
        )
    for operation in operations:
        await wait_started(chaos.redis, operation["id"])
    await asyncio.sleep(1.5)
    chaos.redis86.kill()
    await asyncio.sleep(0.4)
    # После подъёма Redis задачу забирает новый worker: сценарий проверяет AOF и сверку.
    stop_all(chaos)
    try:
        chaos.redis86.start()
        client = redis_async.Redis.from_url(chaos.redis86.url, socket_timeout=None)
        fresh = await TaskiqJobs.open(chaos.settings)
        await fresh.startup()
        start_worker(chaos, "aof-restart", max_async=4)
        chaos.settings.op_stale_sec = 3
        runtime_mod.RUNTIME = WorkerRuntime(
            settings=chaos.settings,
            redis=client,
            store=chaos.jobs.store,
            schedule=fresh.schedule,
            broker=fresh.brokers[INTERACTIVE],
            locks=None,
        )
        await asyncio.sleep(3.2)
        try:
            reconciled = await reconcile_operations()
        except (OSError, RuntimeError, redis_async.RedisError) as exc:
            reconciled = {"error": type(exc).__name__}
        counts = {"succeeded": 0, "failed": 0, "cancelled": 0, "running": 0}
        deadline = time.time() + 25
        while time.time() < deadline:
            counts = {"succeeded": 0, "failed": 0, "cancelled": 0, "running": 0}
            for operation in operations:
                body = await read_op(chaos.jobs.store, operation["id"])
                status = body.get("status") or "running"
                counts[status] = counts.get(status, 0) + 1
            if counts["running"] == 0:
                break
            await asyncio.sleep(0.2)
        record("8", {"counts": counts, "reconcile": reconciled, "ops": len(operations)})
        assert counts["running"] == 0, counts
        assert counts["succeeded"] + counts["failed"] + counts["cancelled"] == 4
    finally:
        runtime_mod.RUNTIME = None
        if not _port_open(chaos.redis86.port):
            chaos.redis86.start()
