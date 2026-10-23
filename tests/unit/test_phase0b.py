"""Фаза 0b: sync, GC, индекс, jitter, справедливость."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from finance_analysis.adapters.queue.retry import full_jitter
from finance_analysis.adapters.redis.runtime import version_at_least
from finance_analysis.adapters.storage.store import LocalStore
from finance_analysis.adapters.storage.sync import sync_rank, sync_stores
from finance_analysis.application.gc import gc_incomplete
from finance_analysis.domain.ids import job_id as check_job
from tests.conftest import JOB


def test_redis_version_floor():
    assert version_at_least("8.6.5")
    assert version_at_least("8.6.7")
    assert version_at_least("8.10.0")
    assert not version_at_least("8.6.4")
    assert not version_at_least("7.0.15")
    assert not version_at_least(None)


def test_retry_delay_is_full_jitter():
    delays = [full_jitter(5, 300, 1) for _ in range(40)]
    assert min(delays) >= 0
    assert max(delays) <= 5
    assert len({round(item, 5) for item in delays}) > 1
    later = [full_jitter(5, 12, 4) for _ in range(20)]
    assert max(later) <= 12


def test_sync_rank_puts_manifest_and_head_last():
    keys = [
        "books/j/_head.json",
        "books/j/bbbbbbbbbbbbbbbb/manifest.json",
        "books/j/bbbbbbbbbbbbbbbb/a/01ARZ3NDEKTSV4RRFFQ69G5FAV/projection/fact_observation.parquet",
        "examples/a.parquet",
        "profiles/p/v/000001.yaml",
        "calibrators/c.parquet",
        "books/j/_state/log/00000000000000000001.json",
    ]
    ordered = sorted(keys, key=sync_rank)
    assert ordered[0].startswith("examples/")
    assert ordered[1].startswith("profiles/")
    assert ordered[2].startswith("calibrators/")
    assert ordered[-2].endswith("/_state/log/00000000000000000001.json") or "/_state/log/" in ordered[-2]
    assert ordered[-1].endswith("/_head.json")
    manifest_at = next(i for i, key in enumerate(ordered) if key.endswith("/manifest.json"))
    data_at = next(i for i, key in enumerate(ordered) if key.endswith(".parquet") and "/a/" in key)
    assert data_at < manifest_at


async def test_sync_dry_run_verify_and_conflict(tmp_path):
    source = LocalStore(tmp_path / "src")
    destination = LocalStore(tmp_path / "dst")
    await source.put("examples/a", b"a")
    await source.put("books/j/_head.json", b"head")
    manifest = {
        "files": {"a/01ARZ3NDEKTSV4RRFFQ69G5FAV/projection/fact_observation.parquet": {"sha256": "abc"}},
    }
    body = b"parquet"
    import hashlib

    manifest["files"]["a/01ARZ3NDEKTSV4RRFFQ69G5FAV/projection/fact_observation.parquet"]["sha256"] = hashlib.sha256(
        body
    ).hexdigest()
    await source.put("books/j/bbbbbbbbbbbbbbbb/a/01ARZ3NDEKTSV4RRFFQ69G5FAV/projection/fact_observation.parquet", body)
    await source.put("books/j/bbbbbbbbbbbbbbbb/manifest.json", json.dumps(manifest).encode())
    plan = await sync_stores(source, destination, dry_run=True)
    assert plan["objects"] == 4
    assert plan["bytes"] > 0
    assert plan["copied"] == 0
    assert [item.key async for item in destination.list("")] == []
    order: list[str] = []
    original = destination.put_if_absent

    async def tracking(key, data):
        order.append(key)
        return await original(key, data)

    destination.put_if_absent = tracking
    report = await sync_stores(source, destination, verify=True)
    assert report["copied"] == 4
    assert report["verify_errors"] == []
    assert report["verified"] == 1
    assert order[0].startswith("examples/")
    assert order[-1].endswith("_head.json")
    await destination.put("examples/a", b"other")
    again = await sync_stores(source, destination)
    assert again["conflicts"]
    assert again["conflicts"][0]["key"] == "examples/a"
    assert await destination.get("examples/a") == b"other"


async def test_gc_keeps_committed_and_repairs_index(tmp_path):
    store = LocalStore(tmp_path / "store")
    job = JOB
    check_job(job)
    build = "abcdefabcdefabcd"
    attempt = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
    data_key = f"books/{job}/{build}/a/{attempt}/projection/fact_observation.parquet"
    manifest_key = f"books/{job}/{build}/manifest.json"
    head_key = f"books/{job}/_head.json"
    orphan = f"books/{job}/{build}/a/01HZZZZZZZZZZZZZZZZZZZZZZZ/projection/orphan.parquet"
    derived = f"books/{job}/{build}/derived/abcdefabcdefabce/_done.json"
    dangling = f"books/{job}/{build}/derived/abcdefabcdefabcf/a/{attempt}/bindings.parquet"
    result = f"books/{job}/{build}/results/01ARZ3NDEKTSV4RRFFQ69G5FAV/partial.parquet"
    index_orphan = f"books/{job}/_builds/1234567890abcdef.json"
    manifest = {
        "build_key": build,
        "loaded_at": "2026-10-21T00:00:00Z",
        "fas_schema_version": "1.0",
        "builder_ref": {"job_id": job},
        "files": {f"a/{attempt}/projection/fact_observation.parquet": {"sha256": "x", "rows": 3, "bytes": 4}},
    }
    await store.put(data_key, b"data")
    await store.put(manifest_key, json.dumps(manifest).encode())
    await store.put(head_key, b"{}")
    await store.put(orphan, b"orphan")
    await store.put(derived, json.dumps({"derive_key": "abcdefabcdefabce", "files": {}}).encode())
    await store.put(dangling, b"old")
    await store.put(result, b"partial")
    await store.put(index_orphan, b"{}")
    old = (datetime.now(UTC) - timedelta(hours=3)).timestamp()
    for key in (orphan, dangling, result):
        import os

        os.utime(store.physical(key), (old, old))
    report = await gc_incomplete(store, now=datetime.now(UTC), max_age_s=3600)
    assert await store.stat(data_key)
    assert await store.stat(manifest_key)
    assert await store.stat(head_key)
    assert await store.stat(derived)
    assert await store.stat(index_orphan)
    assert await store.stat(orphan) is None
    assert await store.stat(dangling) is None
    assert await store.stat(result) is None
    index = json.loads(await store.get(f"books/{job}/_builds/{build}.json"))
    assert index["build_key"] == build
    assert report["index_repaired"] == 1
    assert index_orphan in report["index_without_manifest"]
    assert report["removed"] >= 1


async def test_interactive_fairness_limit(redis_runtime):
    from finance_analysis.adapters.queue.fairness import admit, complete, push_waiting
    from finance_analysis.domain.errors import RateLimited

    redis = redis_runtime.redis
    user = "fair-user"
    queue = "fas:interactive"
    first = await admit(redis, queue, user, 2)
    second = await admit(redis, queue, user, 2)
    assert (first, second) == (1, 2)
    with pytest.raises(RateLimited):
        await admit(redis, queue, user, 2)
    await push_waiting(redis, queue, user, {"op_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV", "queue": queue, "user_id": user})
    nxt = await complete(redis, queue, user)
    assert nxt["op_id"] == "01ARZ3NDEKTSV4RRFFQ69G5FAV"
    assert await complete(redis, queue, user) is None
    await redis.delete(f"fas:fair:n:{queue}:{user}", f"fas:fair:wait:{queue}:{user}")
