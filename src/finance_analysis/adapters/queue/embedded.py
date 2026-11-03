"""Queue workers and the scheduler as children of ``fas-api``.

The children are the same ``fas-worker`` and ``fas-scheduler`` processes.
They are not tasks on the API event loop. ``/health/ready`` asks
:func:`embedded_workers_ready`, so a dead child cannot leave a silent API.
"""

from __future__ import annotations

import ctypes
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from finance_analysis.settings import Settings

_LOGGER = logging.getLogger("finance_analysis.queue")
_registry_lock = threading.Lock()
_PR_SET_PDEATHSIG = 1

_SLOTS = (
    ("interactive", "fas-worker", ["--queue", "fas:interactive", "--max-async-tasks", "8"]),
    ("glossary", "fas-worker", ["--queue", "fas:glossary", "--max-async-tasks", "4"]),
    ("batch", "fas-worker", ["--queue", "fas:batch", "--max-async-tasks", "2"]),
    ("maintenance", "fas-worker", ["--queue", "fas:maintenance", "--max-async-tasks", "1"]),
    ("scheduler", "fas-scheduler", []),
)


def child_commands() -> list[tuple[str, list[str]]]:
    """One argv per slot. Tests replace this function."""

    return [(name, _executable_argv(script, args)) for name, script, args in _SLOTS]


def arm_parent_death() -> None:
    """``SIGKILL`` this process when its parent dies.

    A parent that is already PID 1 is the container entrypoint, not a dead
    parent. ``PR_SET_PDEATHSIG`` is cleared on fork, so the child calls this
    itself. If the parent dies during the call, no signal is delivered.
    """

    if os.environ.get("FAS_EMBEDDED_CHILD") != "1" or sys.platform != "linux":
        return
    parent = os.getppid()
    if parent <= 1:
        return
    libc = ctypes.CDLL("libc.so.6", use_errno=True)
    libc.prctl.argtypes = (
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
    )
    libc.prctl.restype = ctypes.c_int
    if libc.prctl(_PR_SET_PDEATHSIG, signal.SIGKILL, 0, 0, 0) != 0:
        return
    if os.getppid() != parent:
        os._exit(1)


class EmbeddedWorkers:
    """Spawn the five FAS children and start a slot again after it exits."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._argv = dict(child_commands())
        self._slots: dict[str, subprocess.Popen[bytes] | None] = {name: None for name in self._argv}
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Spawn once, before the caller accepts traffic, then watch the slots."""

        for name in self._argv:
            self._spawn(name)
        self._thread = threading.Thread(target=self._supervise, name="embedded-workers", daemon=True)
        self._thread.start()

    def ready(self) -> dict[str, str]:
        with self._lock:
            slots = dict(self._slots)
        return {name: "up" if proc is not None and proc.poll() is None else "down" for name, proc in slots.items()}

    def pids(self) -> dict[str, int | None]:
        with self._lock:
            slots = dict(self._slots)
        found: dict[str, int | None] = {}
        for name, proc in slots.items():
            found[name] = None if proc is None or proc.poll() is not None else proc.pid
        return found

    def stop(self) -> None:
        """SIGTERM every child, wait the grace period, then SIGKILL the group."""

        self._stop.set()
        with self._lock:
            slots = dict(self._slots)
            for name in self._slots:
                self._slots[name] = None
        for proc in slots.values():
            if proc is not None:
                _shutdown_proc(proc, self.settings.shutdown_grace_sec)
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=self.settings.shutdown_grace_sec + self.settings.fas_embedded_restart_backoff_sec + 5)

    def _supervise(self) -> None:
        while not self._stop.is_set():
            restarted = False
            for name in self._argv:
                if self._stop.is_set():
                    return
                proc = self._current(name)
                if proc is not None and proc.poll() is None:
                    continue
                restarted = True
                code = None if proc is None else proc.returncode
                _LOGGER.warning("embedded child %s exited (%s); restarting", name, code)
                if self._stop.wait(self.settings.fas_embedded_restart_backoff_sec):
                    return
                self._spawn(name)
            if not restarted and self._stop.wait(0.2):
                return

    def _current(self, name: str) -> subprocess.Popen[bytes] | None:
        with self._lock:
            return self._slots.get(name)

    def _spawn(self, name: str) -> None:
        if self._stop.is_set():
            return
        try:
            proc = subprocess.Popen(
                self._argv[name],
                env=_child_env(),
                start_new_session=True,
            )
        except OSError as exc:
            _LOGGER.error("embedded child %s failed to start: %s", name, exc)
            return
        with self._lock:
            if self._stop.is_set():
                self._slots[name] = None
            else:
                self._slots[name] = proc
                _LOGGER.info("embedded child %s started pid=%s", name, proc.pid)
                return
        _shutdown_proc(proc, self.settings.shutdown_grace_sec)


_supervisor: EmbeddedWorkers | None = None


def start_for_serve(settings: Settings) -> EmbeddedWorkers | None:
    """Start the children when ``FAS_EMBEDDED_WORKERS`` is true."""

    global _supervisor
    if not settings.fas_embedded_workers:
        return None
    workers = EmbeddedWorkers(settings)
    with _registry_lock:
        _supervisor = workers
    workers.start()
    return workers


def stop_for_serve(workers: EmbeddedWorkers | None) -> None:
    """Stop the children this process started. A second call does nothing."""

    global _supervisor
    if workers is None:
        return
    workers.stop()
    with _registry_lock:
        if _supervisor is workers:
            _supervisor = None


def embedded_workers_ready() -> dict[str, str] | None:
    """None when this process is not supervising. Values are ``up`` or ``down``."""

    with _registry_lock:
        workers = _supervisor
    if workers is None:
        return None
    return workers.ready()


def _executable_argv(script: str, args: list[str]) -> list[str]:
    exe = Path(sys.executable).with_name(script)
    modules = {
        "fas-worker": "finance_analysis.adapters.queue.worker",
        "fas-scheduler": "finance_analysis.adapters.queue.scheduler",
    }
    if exe.is_file():
        return [str(exe), *args]
    return [sys.executable, "-m", modules[script], *args]


def _child_env() -> dict[str, str]:
    env = os.environ.copy()
    env["FAS_EMBEDDED_CHILD"] = "1"
    return env


def _shutdown_proc(proc: subprocess.Popen[bytes], grace_sec: float) -> None:
    if proc.poll() is not None:
        return
    _signal(proc.pid, signal.SIGTERM)
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        pass
    deadline = time.monotonic() + grace_sec
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            break
        time.sleep(0.05)
    if proc.poll() is None:
        _signal(proc.pid, signal.SIGKILL)
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        _LOGGER.error("embedded child pid=%s did not exit after SIGKILL", proc.pid)


def _signal(pid: int, sig: int) -> None:
    try:
        os.kill(pid, sig)
    except (ProcessLookupError, PermissionError):
        pass
