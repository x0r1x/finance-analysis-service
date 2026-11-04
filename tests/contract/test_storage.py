"""Один контракт ObjectStorePort для local и MinIO."""

from __future__ import annotations

import asyncio
import os
from multiprocessing import Queue, get_context

import pytest

from finance_analysis.adapters.storage.store import LocalStore, S3Store, open_storage
from finance_analysis.domain.errors import (
    AlreadyExists,
    DependencyUnavailable,
    InvalidId,
    NotFound,
    PreconditionFailed,
)
from finance_analysis.domain.ids import profile_id
from finance_analysis.settings import Settings

pytestmark = pytest.mark.asyncio


@pytest.fixture(params=["local", "s3"])
async def store(request, tmp_path):
    if request.param == "local":
        current = LocalStore(tmp_path / "store")
        await current.selftest()
        yield current
        return
    endpoint = request.getfixturevalue("minio_endpoint")
    current = S3Store(
        bucket="fas",
        prefix=f"c{os.getpid()}{tmp_path.name}",
        endpoint=endpoint,
        region="ap-northeast-1",
        access_key="minioadmin",
        secret_key="minioadmin",
    )
    await current.selftest()
    yield current
    await current.delete_prefix("")


async def test_put_get_stat_not_found(store):
    assert await store.stat("missing/object") is None
    with pytest.raises(NotFound):
        await store.get("missing/object")
    meta = await store.put("books/note", b"hello")
    assert await store.get("books/note") == b"hello"
    stat = await store.stat("books/note")
    assert stat is not None
    assert stat.etag == meta.etag
    assert stat.size == 5


async def test_conditional_writes(store):
    first = await store.put_if_absent("cas/head", b"v1")
    with pytest.raises(AlreadyExists):
        await store.put_if_absent("cas/head", b"v2")
    with pytest.raises(PreconditionFailed):
        await store.put_if_match("cas/head", b"nope", "deadbeef")
    updated = await store.put_if_match("cas/head", b"v2", first.etag)
    assert await store.get("cas/head") == b"v2"
    assert updated.etag != first.etag


async def test_list_skips_directories(store):
    await store.put("tree/a/file", b"1")
    await store.put("tree/b", b"2")
    keys = sorted([item.key async for item in store.list("tree")])
    assert keys == ["tree/a/file", "tree/b"]
    assert all(not key.endswith("/") for key in keys)


async def test_list_trailing_slash_is_a_directory_prefix(store):
    await store.put("books/job/_head.json", b"{}")
    await store.put("books/job/note", b"n")
    await store.put("notes/file", b"o")
    slashed = sorted([item.key async for item in store.list("books/")])
    plain = sorted([item.key async for item in store.list("books")])
    assert slashed == plain == ["books/job/_head.json", "books/job/note"]
    with pytest.raises(InvalidId):
        async for _item in store.list("books/../x/"):
            pass


async def test_reader_sees_complete_object(store):
    await store.put("atom/blob", b"alpha")
    seen = set()

    async def write() -> None:
        for payload in (b"alpha", b"beta-beta", b"gamma"):
            await store.put("atom/blob", payload)
            await asyncio.sleep(0)

    async def read() -> None:
        for _ in range(20):
            data = await store.get("atom/blob")
            seen.add(data)
            await asyncio.sleep(0)

    await asyncio.gather(write(), read())
    assert seen <= {b"alpha", b"beta-beta", b"gamma"}
    assert seen


def _cas_worker(root: str, token: str, payload: bytes, queue: Queue) -> None:
    async def _run() -> None:
        current = LocalStore(__import__("pathlib").Path(root))
        try:
            await current.put_if_match("head.json", payload, token)
            queue.put("ok")
        except PreconditionFailed:
            queue.put("412")

    asyncio.run(_run())


async def test_two_processes_one_cas(tmp_path):
    current = LocalStore(tmp_path / "cas")
    meta = await current.put_if_absent("head.json", b"base")
    ctx = get_context("spawn")
    queue = ctx.Queue()
    procs = [
        ctx.Process(target=_cas_worker, args=(str(current.root), meta.etag, f"p{i}".encode(), queue))
        for i in range(2)
    ]
    for proc in procs:
        proc.start()
    for proc in procs:
        proc.join(10)
    results = [queue.get(timeout=5) for _ in procs]
    assert sorted(results) == ["412", "ok"]
    body = await current.get("head.json")
    assert body in {b"p0", b"p1"}


async def test_path_escape(tmp_path):
    current = LocalStore(tmp_path / "root")
    with pytest.raises(InvalidId):
        await current.get("../outside")
    with pytest.raises(InvalidId):
        profile_id("../x")


async def test_selftest_failure_refuses_s3_start(monkeypatch, tmp_path):
    class Boom:
        backend = "s3"

        async def selftest(self) -> None:
            raise RuntimeError("If-Match не поддерживается")

    monkeypatch.setattr(
        "finance_analysis.adapters.storage.store.build_storage",
        lambda settings: Boom(),
    )
    settings = Settings(
        FAS_DATA_DIR=str(tmp_path),
        FAS_S3_BUCKET="fas",
        FAS_S3_ACCESS_KEY="k",
        FAS_S3_SECRET_KEY="s",
        FAS_S3_ENDPOINT="http://127.0.0.1:9",
        FAS_S3_REGION="ap-northeast-1",
        FAS_S3_SSL=False,
    )
    with pytest.raises(DependencyUnavailable):
        await open_storage(settings)


async def test_sync_roundtrip(tmp_path, minio_endpoint):
    from finance_analysis.adapters.storage.sync import sync_stores

    source = LocalStore(tmp_path / "src")
    await source.put("books/a", b"one")
    await source.put("books/b/c", b"two")
    destination = S3Store(
        bucket="fas",
        prefix=f"sync{tmp_path.name}",
        endpoint=minio_endpoint,
        region="ap-northeast-1",
        access_key="minioadmin",
        secret_key="minioadmin",
    )
    first = await sync_stores(source, destination)
    second = await sync_stores(source, destination)
    assert first["copied"] == 2
    assert second["copied"] == 0
    assert second["skipped"] == 2
    assert await destination.get("books/a") == b"one"
    await destination.delete_prefix("")


async def test_put_absent_publishes_complete_bytes(tmp_path):
    store = LocalStore(tmp_path / "store")
    payload = b"abc" * 1000
    meta = await store.put_if_absent("logs/1", payload)
    assert await store.get("logs/1") == payload
    assert meta.size == len(payload)
    with pytest.raises(AlreadyExists):
        await store.put_if_absent("logs/1", b"other")
    names = [path.name for path in (tmp_path / "store").rglob("*") if path.is_file()]
    assert names == ["1"]


async def test_put_absent_failure_leaves_no_object(tmp_path, monkeypatch):
    store = LocalStore(tmp_path / "store")

    def boom(fd, data):
        raise OSError("disk")

    monkeypatch.setattr(os, "write", boom)
    with pytest.raises(OSError):
        await store.put_if_absent("logs/1", b"hello")
    assert not (tmp_path / "store" / "logs" / "1").exists()


async def test_readonly_selftest_skips_writes(tmp_path):
    store = LocalStore(tmp_path / "ro", read_only=True)
    await store.selftest()
    files = [path for path in (tmp_path / "ro").rglob("*") if path.is_file()]
    assert files == []
