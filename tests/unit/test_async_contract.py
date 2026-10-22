"""Async-контракт §4.14: порты, запрет sync-клиентов, event loop."""

from __future__ import annotations

import ast
import asyncio
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
            if isinstance(func, ast.Attribute) and func.attr == "Client":
                if isinstance(func.value, ast.Name) and func.value.id == "httpx":
                    banned.append((path.name, node.lineno, "httpx.Client"))
            if isinstance(func, ast.Attribute) and func.attr == "Redis":
                if isinstance(func.value, ast.Name) and func.value.id == "redis":
                    banned.append((path.name, node.lineno, "redis.Redis"))
            if isinstance(func, ast.Attribute) and func.attr == "Operator":
                if isinstance(func.value, ast.Name) and func.value.id == "opendal":
                    banned.append((path.name, node.lineno, "opendal.Operator"))
            if isinstance(func, ast.Attribute) and func.attr == "sleep":
                if isinstance(func.value, ast.Name) and func.value.id == "time":
                    banned.append((path.name, node.lineno, "time.sleep"))
    assert banned == []


@pytest.mark.asyncio
async def test_event_loop_not_blocked_on_health(settings, local_service, redis_runtime):
    from httpx import ASGITransport, AsyncClient

    from finance_analysis.adapters.api.app import create_app

    app = create_app(settings, service=local_service, support=redis_runtime)
    loop = asyncio.get_running_loop()
    loop.set_debug(True)
    slow = []

    def handler(loop, context):
        message = context.get("message", "")
        if "Executing" in message and "took" in message:
            slow.append(message)

    previous = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: handler(_loop, context) or None)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fas") as client:
            for path in ("/health/live", "/health/ready", "/v1/capabilities"):
                response = await client.get(path)
                assert response.status_code in {200, 503}
            loaded = await client.post(f"/v1/books/{'a'*64}:load")
            assert loaded.status_code in {200, 202}
    finally:
        loop.set_exception_handler(previous)
        loop.set_debug(False)
    assert slow == []
