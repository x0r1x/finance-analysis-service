"""Redis 8.6.7 для chaos-тестов 0.22. Системный Redis на 6379 не трогаем."""

from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import time
from pathlib import Path

import pytest

REDIS_SERVER = os.environ.get("FAS_REDIS_SERVER", "/tmp/redis-src/redis-8.6.7/src/redis-server")
REDIS_PORT = 6380
REDIS_DIR = Path("/tmp/fas-redis-86")


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except OSError:
        return False


class Redis86:
    def __init__(self) -> None:
        self.port = REDIS_PORT
        self.directory = REDIS_DIR
        self.url = f"redis://127.0.0.1:{REDIS_PORT}/0"
        self.proc: subprocess.Popen | None = None
        self.log_path = REDIS_DIR / "redis.log"

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
                "yes",
                "--appendfsync",
                "everysec",
                "--maxmemory-policy",
                "noeviction",
                "--protected-mode",
                "yes",
                "--daemonize",
                "no",
                "--logfile",
                str(self.log_path),
                "--save",
                "",
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        deadline = time.time() + 15
        while time.time() < deadline:
            if _port_open(self.port):
                return
            if self.proc.poll() is not None:
                raise RuntimeError(self.tail())
            time.sleep(0.05)
        raise RuntimeError(self.tail() or "redis 8.6.7 не открыл порт")

    def kill(self) -> None:
        proc = self.proc
        if proc is None or proc.poll() is not None:
            self.proc = None
            return
        os.kill(proc.pid, signal.SIGKILL)
        proc.wait(timeout=5)
        self.proc = None

    def tail(self) -> str:
        try:
            return self.log_path.read_text(encoding="utf-8")[-4000:]
        except OSError:
            return ""


@pytest.fixture(scope="session")
def redis86():
    if not Path(REDIS_SERVER).is_file():
        pytest.skip("нет бинарника Redis 8.6.7")
    if REDIS_DIR.exists():
        shutil.rmtree(REDIS_DIR)
    server = Redis86()
    server.start()
    yield server
    server.kill()
