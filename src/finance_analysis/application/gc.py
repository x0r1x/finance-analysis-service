"""GC удаляет только попытки без маркера (§4.10)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from finance_analysis.domain.errors import InvalidId
from finance_analysis.domain.ids import job_id as check_job


def _age_ok(mtime: datetime | None, *, now: datetime, max_age_s: int) -> bool:
    if mtime is None:
        return False
    if mtime.tzinfo is None:
        mtime = mtime.replace(tzinfo=UTC)
    return (now - mtime).total_seconds() >= max_age_s


async def gc_incomplete(store, *, now: datetime | None = None, max_age_s: int = 3600, is_locked=None) -> dict:
    moment = now or datetime.now(UTC)
    removed = 0
    kept = 0
    keys = [item.key async for item in store.list("books")]
    jobs = {key.split("/")[1] for key in keys if key.startswith("books/") and len(key.split("/")) > 2}
    for job in jobs:
        try:
            check_job(job)
        except InvalidId:
            continue
        if is_locked and await is_locked(job):
            continue
        manifests = [key for key in keys if key.startswith(f"books/{job}/") and key.endswith("/manifest.json")]
        referenced: set[str] = set()
        builds: set[str] = set()
        for manifest_key in manifests:
            build = manifest_key.split("/")[2]
            builds.add(build)
            payload = json.loads(await store.get(manifest_key))
            for rel in (payload.get("files") or {}):
                referenced.add(f"books/{job}/{build}/{rel}")
            referenced.add(manifest_key)
        done_keys = [
            key
            for key in keys
            if key.startswith(f"books/{job}/") and key.endswith("/_done.json")
        ]
        for done_key in done_keys:
            payload = json.loads(await store.get(done_key))
            build = done_key.split("/")[2]
            for rel in (payload.get("files") or {}):
                referenced.add(f"books/{job}/{build}/{rel}")
            referenced.add(done_key)
        protected_prefixes = ("/_state/", "/_builds/", "/_reports/", "/_head.json")
        candidates = [
            key
            for key in keys
            if key.startswith(f"books/{job}/")
            and "/a/" in key
            and key not in referenced
            and not any(part in key for part in protected_prefixes)
        ]
        grouped: dict[str, list[str]] = {}
        for key in candidates:
            # books/job/build/a/ULID/... or .../derived/derive/a/ULID/...
            marker = "/a/"
            head, _, _tail = key.partition(marker)
            attempt = key[len(head) + len(marker) :].split("/", 1)[0]
            group = f"{head}{marker}{attempt}/"
            grouped.setdefault(group, []).append(key)
        for group, group_keys in grouped.items():
            metas = []
            for key in group_keys:
                meta = await store.stat(key)
                if meta:
                    metas.append(meta)
            if not metas:
                continue
            newest = max((item.mtime for item in metas if item.mtime), default=None)
            if _age_ok(newest, now=moment, max_age_s=max_age_s):
                for key in group_keys:
                    removed += await store.delete_prefix(key)
            else:
                kept += len(group_keys)
    return {"removed": removed, "kept": kept}
