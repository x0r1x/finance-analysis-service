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


_BLOCKING = {
    ("time", "sleep"): "time.sleep",
    ("httpx", "Client"): "httpx.Client",
    ("redis", "Redis"): "redis.Redis",
    ("opendal", "Operator"): "opendal.Operator",
}


def _named(path: Path, name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    assert len(found) == 1, name
    return found[0]


def _statement_calls(node):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
        return
    if isinstance(node, ast.Call):
        yield node
    for child in ast.iter_child_nodes(node):
        yield from _statement_calls(child)


def _blocking(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return _BLOCKING.get((func.value.id, func.attr))
    return None


def _first_await(fn):
    found = [
        node
        for stmt in fn.body
        for node in ast.walk(stmt)
        if isinstance(node, ast.Await)
    ]
    if not found:
        return None
    return min(found, key=lambda node: (node.lineno, node.col_offset))


def _blocking_in(fn) -> list[str]:
    blocked = []
    for stmt in fn.body:
        for node in _statement_calls(stmt):
            name = _blocking(node)
            if name is not None:
                blocked.append(f"{name}:{node.lineno}")
    return blocked


def _before_await(fn) -> list[str]:
    """Вызовы, которые исполняются до первой приостановки.

    У ``await`` аргумент считается раньше, чем корутина отдаёт цикл:
    https://docs.python.org/3/reference/expressions.html#await
    """

    first = _first_await(fn)
    blocked = []
    for stmt in fn.body:
        for node in _statement_calls(stmt):
            if first is not None and (node.lineno, node.col_offset) >= (first.lineno, first.col_offset):
                continue
            name = _blocking(node)
            if name is not None:
                blocked.append(f"{name}:{node.lineno}")
    return blocked


def test_health_ready_does_not_block_before_ping():
    """Обработчик готовности не вызывает sync-клиент до ping.

    Проба внутри подменённого ping не видит ``time.sleep`` выше по обработчику.
    Порог по настенным часам здесь не используется:
    https://docs.pytest.org/en/stable/explanation/flaky.html
    ``time.sleep`` блокирует поток: https://docs.python.org/3/library/time.html#time.sleep
    """

    live = _named(ROOT / "adapters" / "api" / "app.py", "live")
    route = _named(ROOT / "adapters" / "api" / "app.py", "ready")
    service = _named(ROOT / "application" / "service.py", "ready")
    assert isinstance(live, ast.AsyncFunctionDef)
    assert isinstance(route, ast.AsyncFunctionDef)
    assert isinstance(service, ast.AsyncFunctionDef)
    route_await = _first_await(route)
    service_await = _first_await(service)
    assert route_await is not None and isinstance(route_await.value, ast.Call)
    assert isinstance(route_await.value.func, ast.Attribute)
    assert route_await.value.func.attr == "ready"
    assert service_await is not None and isinstance(service_await.value, ast.Call)
    assert isinstance(service_await.value.func, ast.Attribute)
    assert service_await.value.func.attr == "ping"
    assert _blocking_in(live) == []
    assert _blocking_in(route) == []
    assert _blocking_in(service) == []
    assert _before_await(live) == []
    assert _before_await(route) == []
    assert _before_await(service) == []


@pytest.mark.asyncio
async def test_ready_ping_yields_to_one_waiter(settings, local_service, redis_runtime, monkeypatch):
    """Ping готовности будит одну задачу. Это уступка ping, не весь путь /health.

    Ждущий стоит на Event и не крутится, пока идёт запрос:
    https://docs.python.org/3/library/asyncio-sync.html#asyncio.Event
    """

    import asyncio

    from httpx import ASGITransport, AsyncClient

    from finance_analysis.adapters.api.app import create_app

    release = asyncio.Event()
    parked = asyncio.Event()
    resumed = asyncio.Event()

    async def waiter() -> None:
        parked.set()
        await release.wait()
        resumed.set()

    ping = redis_runtime.ping

    async def yielding_ping() -> bool:
        release.set()
        await resumed.wait()
        return await ping()

    monkeypatch.setattr(redis_runtime, "ping", yielding_ping)
    app = create_app(settings, service=local_service, support=redis_runtime)
    task = asyncio.create_task(waiter())
    await parked.wait()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fas") as client:
            response = await client.get("/health/ready")
        assert response.status_code in {200, 503}
        assert release.is_set()
        assert resumed.is_set()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
