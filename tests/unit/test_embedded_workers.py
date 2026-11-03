"""Children that ``fas-api`` starts when ``FAS_EMBEDDED_WORKERS`` is set."""

from __future__ import annotations

import os
import signal
import sys
import time
from collections.abc import Iterator

import pytest
from pydantic import ValidationError

from finance_analysis.adapters.queue import embedded
from finance_analysis.adapters.queue.embedded import (
    embedded_workers_ready,
    start_for_serve,
    stop_for_serve,
)
from finance_analysis.settings import Settings

_NAMES = ("interactive", "glossary", "batch", "maintenance", "scheduler")


@pytest.fixture(autouse=True)
def _stop_children() -> Iterator[None]:
    yield
    stop_for_serve(embedded._supervisor)


def _sleep_commands() -> list[tuple[str, list[str]]]:
    return [
        (name, [sys.executable, "-c", f"import time; time.sleep(60)  # {name}"]) for name in _NAMES
    ]


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "FAS_REDIS_URL": "redis://127.0.0.1:6379/15",
        "FAS_EMBEDDED_WORKERS": False,
        "FAS_EMBEDDED_RESTART_BACKOFF_SEC": 1.0,
        "SHUTDOWN_GRACE_SEC": 1,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _wait_until(predicate, timeout: float = 5) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_disabled_workers_do_not_spawn_and_backoff_rejects_zero() -> None:
    with pytest.raises(ValidationError):
        _settings(FAS_EMBEDDED_RESTART_BACKOFF_SEC=0)
    assert start_for_serve(_settings()) is None
    assert embedded_workers_ready() is None


def test_embedded_workers_start_and_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(embedded, "child_commands", _sleep_commands)
    workers = start_for_serve(_settings(FAS_EMBEDDED_WORKERS=True))
    assert workers is not None
    assert embedded_workers_ready() == {name: "up" for name in _NAMES}
    pids = workers.pids()
    assert all(pid is not None and _alive(pid) for pid in pids.values())
    stop_for_serve(workers)
    assert embedded_workers_ready() is None
    assert all(not _alive(pid) for pid in pids.values() if pid is not None)
    stop_for_serve(workers)


def test_a_killed_child_is_down_until_the_backoff_restarts_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(embedded, "child_commands", _sleep_commands)
    workers = start_for_serve(
        _settings(FAS_EMBEDDED_WORKERS=True, FAS_EMBEDDED_RESTART_BACKOFF_SEC=0.8)
    )
    assert workers is not None
    before = workers.pids()
    victim = "batch"
    old = before[victim]
    assert old is not None
    os.kill(old, signal.SIGKILL)
    assert _wait_until(lambda: workers.ready()[victim] == "down")
    assert workers.pids()[victim] in {None, old}
    assert _wait_until(
        lambda: workers.ready()[victim] == "up" and workers.pids()[victim] not in {None, old},
        timeout=5,
    )
    after = workers.pids()
    for name, pid in before.items():
        if name != victim:
            assert after[name] == pid
    stop_for_serve(workers)


def test_main_starts_children_before_uvicorn(monkeypatch: pytest.MonkeyPatch) -> None:
    import uvicorn

    monkeypatch.setattr(embedded, "child_commands", _sleep_commands)
    monkeypatch.setenv("FAS_EMBEDDED_WORKERS", "true")
    monkeypatch.setenv("FAS_REDIS_URL", "redis://127.0.0.1:6379/15")
    monkeypatch.setenv("SHUTDOWN_GRACE_SEC", "1")
    seen: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> None:
        del args
        seen["workers_kw"] = "workers" in kwargs
        seen["ready"] = embedded_workers_ready()

    monkeypatch.setattr(uvicorn, "run", fake_run)
    from finance_analysis.main import main

    main()
    assert seen["workers_kw"] is False
    assert seen["ready"] == {name: "up" for name in _NAMES}
    assert embedded_workers_ready() is None
