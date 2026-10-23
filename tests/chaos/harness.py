"""Запуск worker/scheduler и ожидание операций для chaos-тестов."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from finance_analysis.adapters.queue.names import INTERACTIVE
from finance_analysis.application.operations import read_op
from finance_analysis.domain.book import Actor
from finance_analysis.settings import Settings

HOLD_WORKER = str(Path(__file__).with_name("hold_worker.py"))
ROOT = Path(__file__).resolve().parents[2]
TERMINAL = {"succeeded", "failed", "cancelled"}


def chaos_settings(data_dir: Path, url: str, **overrides) -> Settings:
    fields = {
        "FAS_DATA_DIR": str(data_dir),
        "FAS_REDIS_URL": url,
        "FAS_READ_ONLY": False,
        "TASKIQ_IDLE_TIMEOUT_MS": 2000,
        "TASKIQ_LEASE_REFRESH_SEC": 0.4,
        "TASKIQ_RECLAIM_INTERVAL_SEC": 0.4,
        "TASKIQ_RECLAIM_LOCK_SEC": 3,
        "OP_HEARTBEAT_SEC": 0.4,
        "OP_STALE_SEC": 120,
        "TASK_RETRY_MAX": 2,
        "TASK_RETRY_BASE_SEC": 0.2,
        "TASK_RETRY_MAX_DELAY_SEC": 0.2,
        "HEAVY_STAGE_TIMEOUT_SEC": 2,
        "HEAVY_STAGE_KILL_GRACE_SEC": 1,
        "HEAVY_STAGE_MEMORY_MB": 8192,
        "USER_MAX_QUEUED": 20,
        "LOCK_TTL_MS": 60_000,
    }
    fields.update(overrides)
    return Settings(**fields)


def worker_env(settings: Settings, extra: dict | None = None) -> dict:
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("FAS_S3"):
            env.pop(key, None)
    dumped = settings.model_dump(by_alias=True)
    for key, value in dumped.items():
        if value is None:
            env.pop(key, None)
            continue
        if isinstance(value, bool):
            env[key] = "true" if value else "false"
        else:
            env[key] = str(value)
    if extra:
        env.update({key: str(value) for key, value in extra.items()})
    env["PYTHONUNBUFFERED"] = "1"
    return env


class WorkerProc:
    def __init__(
        self,
        settings: Settings,
        workdir: Path,
        name: str,
        *,
        queue: str = INTERACTIVE,
        max_async: int = 1,
        extra: dict | None = None,
        script: str | None = None,
    ) -> None:
        self.ready = workdir / f"{name}.ready"
        self.log_path = workdir / f"{name}.log"
        self.log = open(self.log_path, "w", encoding="utf-8")  # noqa: SIM115
        env = worker_env(settings, extra)
        env["FAS_WORKER_READY"] = str(self.ready)
        if script:
            cmd = [sys.executable, script]
        else:
            cmd = [sys.executable, "-m", "finance_analysis.adapters.queue.worker"]
        cmd.extend(
            [
                "--queue",
                queue,
                "--max-async-tasks",
                str(max_async),
                "--ready-file",
                str(self.ready),
            ]
        )
        self.proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=self.log,
            stderr=subprocess.STDOUT,
            cwd=str(ROOT),
        )

    def wait_ready(self, timeout: float = 25) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.ready.is_file() and self.ready.read_text(encoding="utf-8").strip():
                return
            if self.proc.poll() is not None:
                raise RuntimeError(self.tail() or f"worker завершился с {self.proc.returncode}")
            time.sleep(0.05)
        raise TimeoutError(self.tail() or "worker не записал ready")

    def stop(self) -> None:
        if self.proc.poll() is None:
            try:
                os.kill(self.proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        if not self.log.closed:
            self.log.close()

    def tail(self) -> str:
        try:
            return self.log_path.read_text(encoding="utf-8")[-4000:]
        except OSError:
            return ""


class SchedulerProc:
    def __init__(self, settings: Settings, workdir: Path, name: str) -> None:
        self.ready = workdir / f"{name}.ready"
        self.log_path = workdir / f"{name}.log"
        self.log = open(self.log_path, "w", encoding="utf-8")  # noqa: SIM115
        env = worker_env(settings)
        env["FAS_SCHEDULER_READY"] = str(self.ready)
        self.proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "finance_analysis.adapters.queue.scheduler",
                "--update-interval",
                "1",
                "--loop-interval",
                "1",
                "--ready-file",
                str(self.ready),
            ],
            env=env,
            stdout=self.log,
            stderr=subprocess.STDOUT,
            cwd=str(ROOT),
        )

    def wait_ready(self, timeout: float = 25) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.ready.is_file():
                return
            if self.proc.poll() is not None:
                raise RuntimeError(self.tail() or "scheduler завершился")
            time.sleep(0.05)
        raise TimeoutError(self.tail() or "scheduler не записал ready")

    def stop(self) -> None:
        if self.proc.poll() is None:
            try:
                os.kill(self.proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.kill(self.proc.pid, signal.SIGKILL)
                self.proc.wait(timeout=5)
        if not self.log.closed:
            self.log.close()

    def tail(self) -> str:
        try:
            return self.log_path.read_text(encoding="utf-8")[-4000:]
        except OSError:
            return ""


def start_worker(chaos, name: str, **kwargs) -> WorkerProc:
    proc = WorkerProc(chaos.settings, chaos.workdir, name, **kwargs)
    chaos.procs.append(proc)
    proc.wait_ready()
    return proc


def start_scheduler(chaos, name: str = "scheduler") -> SchedulerProc:
    proc = SchedulerProc(chaos.settings, chaos.workdir, name)
    chaos.procs.append(proc)
    proc.wait_ready()
    return proc


async def submit(
    chaos,
    *,
    user: str,
    stage: str,
    seconds: float = 0,
    queue: str = INTERACTIVE,
    kind: str = "probe",
    **payload,
):
    body = {"stage": stage, "stage_args": {"seconds": seconds}, **payload}
    actor = Actor(user_id=user, client_id="chaos")
    return await chaos.jobs.submit(kind, body, queue=queue, actor=actor)


async def starts(redis, op_id: str) -> list[float]:
    raw = await redis.lrange(f"fas:start:{op_id}", 0, -1)
    values = []
    for item in raw:
        text = item.decode() if isinstance(item, bytes) else str(item)
        values.append(float(text))
    return values


async def wait_started(redis, op_id: str, timeout: float = 20) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if await starts(redis, op_id):
            return
        await asyncio_sleep()
    raise AssertionError(f"{op_id} не стартовала")


async def wait_status(store, op_id: str, timeout: float = 30) -> dict:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = await read_op(store, op_id)
        if last.get("status") in TERMINAL:
            return last
        await asyncio_sleep()
    raise AssertionError(last)


async def asyncio_sleep() -> None:
    import asyncio

    await asyncio.sleep(0.05)
