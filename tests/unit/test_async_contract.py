"""Async-контракт §4.14: порты, запрет sync-клиентов, event loop."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "src" / "finance_analysis"


def _calls(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            yield node


def test_ports_are_async():
    tree = ast.parse((ROOT / "application" / "ports.py").read_text(encoding="utf-8"))
    methods = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name != "__init__"
    ]
    assert methods
    sync = [node.name for node in methods if not isinstance(node, ast.AsyncFunctionDef)]
    assert sync == []


def test_no_sync_clients():
    banned = []
    for path in ROOT.rglob("*.py"):
        for node in _calls(path):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "Client"
                and isinstance(func.value, ast.Name)
                and func.value.id == "httpx"
            ):
                banned.append((path.name, node.lineno, "httpx.Client"))
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "Redis"
                and isinstance(func.value, ast.Name)
                and func.value.id == "redis"
            ):
                banned.append((path.name, node.lineno, "redis.Redis"))
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "Operator"
                and isinstance(func.value, ast.Name)
                and func.value.id == "opendal"
            ):
                banned.append((path.name, node.lineno, "opendal.Operator"))
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "sleep"
                and isinstance(func.value, ast.Name)
                and func.value.id == "time"
            ):
                banned.append((path.name, node.lineno, "time.sleep"))
    assert banned == []


@pytest.mark.asyncio
async def test_event_loop_not_blocked_on_health(settings, local_service, redis_runtime, monkeypatch):
    """Готовность уступает цикл, пока ping ждёт.

    Порог по настенным часам ловит опоздание планировщика на общем раннере, а не блокировку.
    Проба считает обороты цикла. ``asyncio.sleep`` всегда отдаёт ход:
    https://docs.python.org/3/library/asyncio-task.html#asyncio.sleep
    Сравнение зазора с порогом на общем раннере здесь не используется:
    https://docs.pytest.org/en/stable/explanation/flaky.html
    """

    import asyncio

    from httpx import ASGITransport, AsyncClient

    from finance_analysis.adapters.api.app import create_app
    from tests.conftest import JOB

    turns = 0
    stop = asyncio.Event()

    async def probe() -> None:
        nonlocal turns
        while not stop.is_set():
            turns += 1
            await asyncio.sleep(0)

    ping = redis_runtime.ping
    entered = False

    async def yielding_ping() -> bool:
        nonlocal entered
        entered = True
        before = turns
        await asyncio.sleep(0)
        if turns <= before:
            raise AssertionError("ping не отдал цикл")
        return await ping()

    monkeypatch.setattr(redis_runtime, "ping", yielding_ping)
    app = create_app(settings, service=local_service, support=redis_runtime)
    beat = asyncio.create_task(probe())
    await asyncio.sleep(0)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fas") as client:
            for path in ("/health/live", "/health/ready", "/v1/capabilities"):
                response = await client.get(path)
                assert response.status_code in {200, 503}
            loaded = await client.post(f"/v1/books/{JOB}:load")
            assert loaded.status_code in {200, 202}
    finally:
        stop.set()
        await beat
    assert entered
    assert turns > 1
