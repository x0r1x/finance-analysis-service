"""Проверка, что процесс входит в cgroup и memory.max его убивает.

Запуск: FAS_TEST_OOM_CGROUP=/path python tests/chaos/oom_probe.py

Лимит ставится после входа. Иначе ядро режет процесс ещё при миграции,
и systemd останавливает службу, внутри которой живёт job.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

_LIMIT = "67108864"


def _write(path: Path, text: str) -> None:
    payload = text if text.endswith("\n") else f"{text}\n"
    try:
        path.write_text(payload)
    except OSError:
        completed = subprocess.run(
            ["sudo", "-n", "tee", str(path)],
            check=False,
            input=payload,
            text=True,
            stdout=subprocess.DEVNULL,
        )
        if completed.returncode != 0:
            print(f"write failed: {path}", flush=True)
            os._exit(2)


def _child(cgroup: Path) -> None:
    os.setsid()
    _write(cgroup / "cgroup.procs", str(os.getpid()))
    print(Path("/proc/self/cgroup").read_text(encoding="utf-8").strip(), flush=True)
    group = cgroup / "memory.oom.group"
    if group.is_file():
        _write(group, "0")
    swap = cgroup / "memory.swap.max"
    if swap.is_file():
        _write(swap, "0")
    _write(cgroup / "memory.max", _LIMIT)
    blobs: list[bytearray] = []
    try:
        for _ in range(64):
            blobs.append(bytearray(8 * 1024 * 1024))
    except MemoryError:
        os._exit(0)
    os._exit(3)


def main() -> None:
    raw = os.environ.get("FAS_TEST_OOM_CGROUP") or ""
    cgroup = Path(raw)
    if not (cgroup / "memory.max").is_file():
        raise SystemExit(f"нет memory.max в {cgroup}")
    previous = (cgroup / "memory.max").read_text(encoding="utf-8")
    swap = cgroup / "memory.swap.max"
    previous_swap = swap.read_text(encoding="utf-8") if swap.is_file() else None
    pid = os.fork()
    if pid == 0:
        try:
            _child(cgroup)
        except OSError as exc:
            print(f"enter failed: {exc}", flush=True)
            os._exit(2)
    try:
        deadline = time.time() + 8
        while time.time() < deadline:
            waited, status = os.waitpid(pid, os.WNOHANG)
            if waited:
                code = os.waitstatus_to_exitcode(status)
                print(f"oom child exit {code}", flush=True)
                if code in {0, -9, 137}:
                    return
                raise SystemExit(1)
            time.sleep(0.1)
        os.kill(pid, 9)
        print("oom child still alive", flush=True)
        raise SystemExit(1)
    finally:
        (cgroup / "memory.max").write_text(previous)
        if previous_swap is not None:
            swap.write_text(previous_swap)


if __name__ == "__main__":
    main()
