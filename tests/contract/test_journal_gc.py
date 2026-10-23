"""Журнал с номерами, попытки, GC и derive_key (§9, тесты 0.21)."""

from __future__ import annotations

import asyncio
import os
import random
from datetime import UTC, datetime, timedelta
from multiprocessing import Queue, get_context

import pytest

from finance_analysis.adapters.storage.store import LocalStore
from finance_analysis.application.keys import head_key
from finance_analysis.application.semantic_guard import SemanticWriteGuard
from finance_analysis.domain.book import Actor
from finance_analysis.domain.errors import BindingConflict
from finance_analysis.domain.state import fold
from tests.conftest import JOB

pytestmark = pytest.mark.asyncio


def _append_many(root: str, job: str, prefix: str, count: int, skew_minutes: int, queue: Queue) -> None:
    async def _run() -> None:
        store = LocalStore(__import__("pathlib").Path(root))
        targets = frozenset(f"{prefix}-{index}" for index in range(count))
        guard = SemanticWriteGuard(store, targets=targets)
        actor = Actor(user_id="writer", client_id=prefix)
        for index in range(count):
            when = datetime.now(UTC) + timedelta(minutes=random.randint(-skew_minutes, skew_minutes))
            result = await guard.append(
                job,
                target=f"{prefix}-{index}",
                event_type="concept.set",
                value=index,
                actor=actor,
                expected_seq=None,
                request_id=f"{prefix}-{index}",
                at_utc=when,
            )
            if not result.accepted:
                raise RuntimeError(result.detail)
        queue.put(prefix)

    asyncio.run(_run())


async def test_journal_two_processes(tmp_path):
    root = tmp_path / "store"
    store = LocalStore(root)
    ctx = get_context("spawn")
    queue = ctx.Queue()
    procs = [
        ctx.Process(target=_append_many, args=(str(root), JOB, "p0", 1000, 5, queue)),
        ctx.Process(target=_append_many, args=(str(root), JOB, "p1", 1000, 5, queue)),
    ]
    for proc in procs:
        proc.start()
    for proc in procs:
        proc.join(120)
        assert proc.exitcode == 0
    guard = SemanticWriteGuard(store)
    events = await guard.read_all(JOB)
    assert len(events) == 2000
    seqs = [event["seq"] for event in events]
    assert seqs == list(range(1, 2001))
    folded = fold(events)
    assert len(folded) == 2000


def _one_decision(root: str, job: str, name: str, queue: Queue) -> None:
    async def _run() -> None:
        store = LocalStore(__import__("pathlib").Path(root))
        guard = SemanticWriteGuard(store, targets=frozenset({"same-row"}))
        try:
            result = await guard.append(
                job,
                target="same-row",
                event_type="concept.set",
                value=name,
                actor=Actor(user_id=name, client_id="c"),
                expected_seq=None,
                request_id=name,
            )
            if not result.accepted:
                raise RuntimeError(result.detail)
            queue.put("ok")
        except BindingConflict:
            queue.put("409")

    asyncio.run(_run())


async def test_same_expected_seq_one_conflict(tmp_path):
    root = tmp_path / "store"
    LocalStore(root)
    ctx = get_context("spawn")
    queue = ctx.Queue()
    procs = [ctx.Process(target=_one_decision, args=(str(root), JOB, f"u{i}", queue)) for i in range(2)]
    for proc in procs:
        proc.start()
    for proc in procs:
        proc.join(30)
        assert proc.exitcode == 0
    assert sorted(queue.get() for _ in procs) == ["409", "ok"]


async def test_attempts_and_gc(local_service):
    service = local_service
    actor = Actor(user_id="loader", client_id="t")
    first, second = await asyncio.gather(
        service.perform_load(JOB, actor=actor, fence=1),
        service.perform_load(JOB, actor=actor, fence=2),
    )
    assert first.build_key == second.build_key
    manifest = await service._manifest(JOB, first.build_key)
    referenced = []
    for rel, meta in manifest["files"].items():
        key = f"books/{JOB}/{first.build_key}/{rel}"
        body = await service.store.get(key)
        import hashlib

        assert hashlib.sha256(body).hexdigest() == meta["sha256"]
        referenced.append(key)
    orphan = f"books/{JOB}/{first.build_key}/a/01HZZZZZZZZZZZZZZZZZZZZZZZ/projection/orphan.parquet"
    await service.store.put(orphan, b"orphan")
    path = service.store.physical(orphan)
    old = (datetime.now(UTC) - timedelta(hours=3)).timestamp()
    os.utime(path, (old, old))
    report = await service.gc(now=datetime.now(UTC), max_age_s=1)
    assert report["removed"] >= 1
    for key in referenced:
        assert await service.store.stat(key) is not None
    assert await service.store.stat(head_key(JOB)) is not None
    assert await service.store.stat(orphan) is None


async def test_two_glossary_derive_keys(local_service):
    service = local_service
    actor = Actor()
    head = await service.perform_load(JOB, actor=actor, fence=1)
    import json

    from finance_analysis.adapters.builder.acl import parse_context, parse_graph
    from finance_analysis.application.project import project
    from tests.books import BUILDER_ROOT

    folder = BUILDER_ROOT / JOB
    snapshot = parse_graph(json.loads((folder / "graph.json").read_text()), parse_context(json.loads((folder / "context.json").read_text())))
    projected, _warnings = project(snapshot, model_id=JOB, build=head.build_key)
    first = await service.materialize_derived(JOB, glossary_version="g1", projected=projected)
    second = await service.materialize_derived(JOB, glossary_version="g2", projected=projected)
    assert first != second
    keys = [item.key async for item in service.store.list(f"books/{JOB}/{head.build_key}/derived")]
    assert any(f"/{first}/" in key for key in keys)
    assert any(f"/{second}/" in key for key in keys)


async def test_builder_flip_then_stable_and_unstable(settings, redis_runtime):
    from finance_analysis.adapters.builder.fixture import FixtureBuilder
    from finance_analysis.adapters.storage.parquet_io import PyarrowParquet
    from finance_analysis.adapters.storage.store import open_storage
    from finance_analysis.adapters.wren.query import WrenQuery
    from finance_analysis.application.metrics import BUILDER_INCONSISTENT
    from finance_analysis.application.service import FasService
    from finance_analysis.domain.errors import BuilderUnstable
    from tests.books import BUILDER_ROOT, job_id

    store = await open_storage(settings)
    builder = FixtureBuilder(BUILDER_ROOT)
    service = FasService(settings, store, PyarrowParquet(), builder, WrenQuery(settings), redis_runtime)
    summary, snapshot = await service.load_consistent(JOB, known_etag=None)
    assert summary.status == "succeeded"
    assert snapshot.rows
    builder.foreign_graph_from[JOB] = job_id("rvi")
    builder.foreign_graph_reads[JOB] = 5
    before = BUILDER_INCONSISTENT._value.get()
    with pytest.raises(BuilderUnstable):
        await service.load_consistent(JOB, known_etag=None)
    assert BUILDER_INCONSISTENT._value.get() == before + 1
