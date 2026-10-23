"""Тяжёлая стадия в отдельном процессе с жёстким завершением (§4.14.3)."""

from __future__ import annotations

import asyncio
import multiprocessing
import signal
import time
from collections.abc import Callable


def _die_with_parent() -> None:
    import ctypes

    libc = ctypes.CDLL("libc.so.6", use_errno=True)
    if libc.prctl(1, signal.SIGKILL) != 0:
        return
    if __import__("os").getppid() == 1:
        raise SystemExit(1)


def _limit_memory(memory_mb: int) -> None:
    import resource

    limit = int(memory_mb) * 1024 * 1024
    if limit <= 0:
        return
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))


def _duckdb_scan(args: dict, conn) -> None:
    import threading

    import duckdb

    connection = duckdb.connect()
    stop = threading.Event()

    def _watch() -> None:
        while not stop.is_set():
            if conn.poll(0.05):
                message = conn.recv()
                if isinstance(message, dict) and message.get("cmd") == "interrupt":
                    connection.interrupt()
                    return

    threading.Thread(target=_watch, daemon=True).start()
    try:
        rounds = int(args.get("rounds") or 10**12)
        connection.execute("SELECT sum(hash(i::VARCHAR)) FROM range(?) t(i)", [rounds])
        conn.send({"ok": True, "status": "succeeded"})
    finally:
        stop.set()
        connection.close()


def _isolated_entry(stage: str, args: dict, conn) -> None:
    try:
        _die_with_parent()
        _limit_memory(int(args.get("memory_mb") or 4096))
        if stage == "duckdb_scan":
            _duckdb_scan(args, conn)
        else:
            conn.send({"ok": False, "status": "failed", "error": f"неизвестная стадия {stage}"})
    except Exception as exc:  # noqa: BLE001 — ошибка стадии уходит родителю
        try:
            conn.send({"ok": False, "status": "failed", "error": str(exc)})
        except (OSError, BrokenPipeError, EOFError):
            return
    finally:
        conn.close()


async def _wait_dead(proc: multiprocessing.Process, timeout: float) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while proc.is_alive() and loop.time() < deadline:
        await asyncio.sleep(0.02)
    await asyncio.to_thread(proc.join, 0.1)


async def _kill(proc: multiprocessing.Process, parent, *, grace: float, status: str) -> dict:
    started = time.monotonic()
    try:
        parent.send({"cmd": "interrupt"})
    except (OSError, BrokenPipeError):
        pass
    if proc.is_alive():
        proc.terminate()
        await _wait_dead(proc, grace)
    if proc.is_alive():
        proc.kill()
        await _wait_dead(proc, 1)
    return {
        "ok": False,
        "status": status,
        "cpu_release_sec": time.monotonic() - started,
        "exitcode": proc.exitcode,
    }


async def run_isolated(
    stage: str,
    args: dict,
    timeout: float,
    *,
    grace: float,
    memory_mb: int,
    cancelled: Callable[[], bool] | None = None,
) -> dict:
    ctx = multiprocessing.get_context("spawn")
    parent, child = ctx.Pipe(duplex=True)
    proc = ctx.Process(target=_isolated_entry, args=(stage, {**args, "memory_mb": memory_mb}, child))
    proc.start()
    child.close()
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    try:
        while proc.is_alive():
            if parent.poll():
                result = parent.recv()
                await _wait_dead(proc, 1)
                if isinstance(result, dict):
                    return result
                return {"ok": False, "status": "failed", "error": "пустой результат стадии"}
            if cancelled and cancelled():
                return await _kill(proc, parent, grace=grace, status="cancelled")
            if loop.time() >= deadline:
                return await _kill(proc, parent, grace=grace, status="failed")
            await asyncio.sleep(0.05)
        if parent.poll():
            result = parent.recv()
            if isinstance(result, dict):
                return result
        return {"ok": False, "status": "failed", "error": "процесс стадии завершился", "exitcode": proc.exitcode}
    finally:
        if proc.is_alive():
            proc.kill()
            proc.join(1)
        parent.close()
