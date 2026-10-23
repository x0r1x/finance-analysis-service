"""GC удаляет только недописанное и сверяет индекс `_builds/` (§4.10)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from finance_analysis.application.builds import index_document
from finance_analysis.domain.errors import AlreadyExists, InvalidId
from finance_analysis.domain.ids import job_id as check_job


def _age_ok(mtime: datetime | None, *, now: datetime, max_age_s: int) -> bool:
    if mtime is None:
        return False
    if mtime.tzinfo is None:
        mtime = mtime.replace(tzinfo=UTC)
    return (now - mtime).total_seconds() >= max_age_s


def _newest(metas) -> datetime | None:
    stamps = [item.mtime for item in metas if item and item.mtime]
    return max(stamps) if stamps else None


async def _referenced(store, job: str, job_keys: list[str]) -> tuple[dict[str, dict], set[str]]:
    manifests = [key for key in job_keys if key.count("/") == 3 and key.endswith("/manifest.json")]
    referenced: set[str] = set()
    builds: dict[str, dict] = {}
    for manifest_key in manifests:
        build = manifest_key.split("/")[2]
        payload = json.loads(await store.get(manifest_key))
        builds[build] = payload
        referenced.add(manifest_key)
        for rel in payload.get("files") or {}:
            referenced.add(f"books/{job}/{build}/{rel}")
    for done_key in job_keys:
        if not done_key.endswith("/_done.json") and not done_key.endswith("/result.json"):
            continue
        payload = json.loads(await store.get(done_key))
        referenced.add(done_key)
        build = done_key.split("/")[2]
        for rel in payload.get("files") or {}:
            if rel.startswith("books/"):
                referenced.add(rel)
            else:
                referenced.add(f"books/{job}/{build}/{rel}")
    return builds, referenced


def _protected(key: str) -> bool:
    return any(part in key for part in ("/_state/", "/_builds/", "/_reports/", "/_head.json"))


async def _delete_group(store, group_keys: list[str], *, now: datetime, max_age_s: int) -> tuple[int, int]:
    metas = []
    for key in group_keys:
        meta = await store.stat(key)
        if meta:
            metas.append(meta)
    if not metas:
        return 0, 0
    if _age_ok(_newest(metas), now=now, max_age_s=max_age_s):
        removed = 0
        for key in group_keys:
            removed += await store.delete_prefix(key)
        return removed, 0
    return 0, len(group_keys)


async def gc_incomplete(store, *, now: datetime | None = None, max_age_s: int = 3600, is_locked=None) -> dict:
    moment = now or datetime.now(UTC)
    removed = 0
    kept = 0
    repaired = 0
    orphan_index: list[str] = []
    keys = [item.key async for item in store.list("books")]
    jobs = {key.split("/")[1] for key in keys if key.startswith("books/") and len(key.split("/")) > 2}
    for job in sorted(jobs):
        try:
            check_job(job)
        except InvalidId:
            continue
        if is_locked and await is_locked(job):
            continue
        job_keys = [key for key in keys if key.startswith(f"books/{job}/")]
        builds, referenced = await _referenced(store, job, job_keys)
        removed_now, kept_now = await _sweep_attempts(
            store, job_keys, referenced, now=moment, max_age_s=max_age_s
        )
        removed += removed_now
        kept += kept_now
        removed_now, kept_now = await _sweep_unmarked(
            store,
            job,
            job_keys,
            segment="derived",
            now=moment,
            max_age_s=max_age_s,
        )
        removed += removed_now
        kept += kept_now
        removed_now, kept_now = await _sweep_unmarked(
            store,
            job,
            job_keys,
            segment="results",
            now=moment,
            max_age_s=max_age_s,
        )
        removed += removed_now
        kept += kept_now
        repaired += await _repair_index(store, job, job_keys, builds)
        orphan_index.extend(_orphan_index(job, job_keys, builds))
    return {"removed": removed, "kept": kept, "index_repaired": repaired, "index_without_manifest": orphan_index}


async def _sweep_attempts(store, job_keys, referenced, *, now, max_age_s) -> tuple[int, int]:
    candidates = [
        key
        for key in job_keys
        if "/a/" in key and key not in referenced and not _protected(key) and not key.endswith("/_done.json")
    ]
    grouped: dict[str, list[str]] = {}
    for key in candidates:
        head, _, _tail = key.partition("/a/")
        attempt = key[len(head) + 3 :].split("/", 1)[0]
        grouped.setdefault(f"{head}/a/{attempt}/", []).append(key)
    removed = kept = 0
    for group_keys in grouped.values():
        delta_removed, delta_kept = await _delete_group(store, group_keys, now=now, max_age_s=max_age_s)
        removed += delta_removed
        kept += delta_kept
    return removed, kept


def _unmarked_groups(job: str, job_keys: list[str], segment: str) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    marker = f"/{segment}/"
    for key in job_keys:
        if marker not in key or _protected(key):
            continue
        head, _, tail = key.partition(marker)
        folder = tail.split("/", 1)[0]
        grouped.setdefault(f"{head}{marker}{folder}/", []).append(key)
    unmarked = {}
    for prefix, group_keys in grouped.items():
        if any(key.endswith(("/_done.json", "/result.json")) for key in group_keys):
            continue
        unmarked[prefix] = group_keys
    return unmarked


async def _sweep_unmarked(store, job: str, job_keys, *, segment: str, now, max_age_s) -> tuple[int, int]:
    removed = kept = 0
    for group_keys in _unmarked_groups(job, job_keys, segment).values():
        delta_removed, delta_kept = await _delete_group(store, group_keys, now=now, max_age_s=max_age_s)
        removed += delta_removed
        kept += delta_kept
    return removed, kept


async def _repair_index(store, job: str, job_keys: list[str], builds: dict[str, dict]) -> int:
    present = {key for key in job_keys if "/_builds/" in key and key.endswith(".json")}
    repaired = 0
    previous = None
    for build, manifest in builds.items():
        index_key = f"books/{job}/_builds/{build}.json"
        if index_key in present:
            previous = build
            continue
        document = index_document(build, manifest, previous=previous, reason="initial")
        try:
            await store.put_if_absent(index_key, json.dumps(document, ensure_ascii=False).encode())
            repaired += 1
        except AlreadyExists:
            pass
        previous = build
    return repaired


def _orphan_index(job: str, job_keys: list[str], builds: dict[str, dict]) -> list[str]:
    orphans = []
    for key in job_keys:
        if "/_builds/" not in key or not key.endswith(".json"):
            continue
        build = key.rsplit("/", 1)[-1].removesuffix(".json")
        if build not in builds:
            orphans.append(key)
    return orphans
