"""Проверка, что процесс входит в cgroup и memory.max его убивает.

Запуск: FAS_TEST_OOM_CGROUP=/path python tests/chaos/oom_probe.py
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path


def main() -> None:
    raw = os.environ.get("FAS_TEST_OOM_CGROUP") or ""
    cgroup = Path(raw)
    if not (cgroup / "memory.max").is_file():
        raise SystemExit(f"нет memory.max в {cgroup}")
    previous = (cgroup / "memory.max").read_text(encoding="utf-8")
    swap = cgroup / "memory.swap.max"
    previous_swap = swap.read_text(encoding="utf-8") if swap.is_file() else None
    try:
        (cgroup / "memory.max").write_text("67108864")
        if previous_swap is not None:
            swap.write_text("0")
        pid = os.fork()
        if pid == 0:
            procs = cgroup / "cgroup.procs"
            pid_text = str(os.getpid())
            try:
                procs.write_text(pid_text)
            except PermissionError:
                completed = subprocess.run(
                    ["sudo", "-n", "tee", str(procs)],
                    check=False,
                    input=pid_text + "\n",
                    text=True,
                    stdout=subprocess.DEVNULL,
                )
                if completed.returncode != 0:
                    print("enter failed: sudo tee", flush=True)
                    os._exit(2)
            except OSError as exc:
                print(f"enter failed: {exc}", flush=True)
                os._exit(2)
            blobs: list[bytearray] = []
            try:
                for _ in range(64):
                    blobs.append(bytearray(8 * 1024 * 1024))
            except MemoryError:
                os._exit(0)
            os._exit(3)
        deadline = time.time() + 8
        while time.time() < deadline:
            waited, status = os.waitpid(pid, os.WNOHANG)
            if waited:
                code = os.waitstatus_to_exitcode(status)
                print(f"oom child exit {code}")
                if code in {0, -9, 137}:
                    return
                raise SystemExit(1)
            time.sleep(0.1)
        os.kill(pid, 9)
        print("oom child still alive")
        raise SystemExit(1)
    finally:
        (cgroup / "memory.max").write_text(previous)
        if previous_swap is not None:
            swap.write_text(previous_swap)


if __name__ == "__main__":
    main()
