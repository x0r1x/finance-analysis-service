"""Копирование object store: fas storage sync (§4.7)."""

from __future__ import annotations

import hashlib
import json

from finance_analysis.domain.errors import AlreadyExists


def sync_rank(key: str) -> tuple:
    """Порядок §4.7: examples, profiles, calibrators, сборки (manifest последним), журнал, _head."""
    if key.startswith("examples/"):
        return (0, "", 0, key)
    if key.startswith("profiles/"):
        return (1, "", 0, key)
    if key.startswith("calibrators/"):
        return (2, "", 0, key)
    if "/_state/log/" in key:
        return (4, "", 0, key)
    if key.endswith("/_head.json"):
        return (5, "", 0, key)
    parts = key.split("/")
    build_prefix = "/".join(parts[:3]) if len(parts) >= 3 else key
    manifest = 1 if key.endswith("/manifest.json") else 0
    return (3, build_prefix, manifest, key)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def _manifest_errors(destination, key: str, data: bytes) -> list[dict]:
    if not key.endswith("/manifest.json"):
        return []
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return [{"key": key, "error": "manifest не JSON"}]
    files = payload.get("files") or {}
    if not isinstance(files, dict):
        return [{"key": key, "error": "files не объект"}]
    prefix = key[: -len("manifest.json")]
    errors = []
    for rel, meta in files.items():
        if not isinstance(meta, dict) or "sha256" not in meta:
            continue
        full = f"{prefix}{rel}"
        try:
            body = await destination.get(full)
        except Exception as exc:  # noqa: BLE001 — ошибка чтения попадает в отчёт verify
            errors.append({"key": full, "error": str(exc)})
            continue
        digest = _sha256(body)
        if digest != meta["sha256"]:
            errors.append({"key": full, "expected": meta["sha256"], "actual": digest})
    return errors


async def sync_stores(source, destination, *, dry_run: bool = False, verify: bool = False) -> dict:
    items = [item async for item in source.list("")]
    items.sort(key=lambda item: sync_rank(item.key))
    total_bytes = sum(item.size for item in items)
    if dry_run:
        return {
            "dry_run": True,
            "objects": len(items),
            "bytes": total_bytes,
            "copied": 0,
            "skipped": 0,
            "conflicts": [],
            "verified": 0,
            "verify_errors": [],
        }
    copied = 0
    skipped = 0
    conflicts: list[dict] = []
    verify_errors: list[dict] = []
    verified = 0
    for item in items:
        data = await source.get(item.key)
        try:
            await destination.put_if_absent(item.key, data)
            copied += 1
        except AlreadyExists:
            existing = await destination.get(item.key)
            if existing != data:
                conflicts.append(
                    {"key": item.key, "source_sha256": _sha256(data), "destination_sha256": _sha256(existing)}
                )
            else:
                skipped += 1
            data = existing
        if verify:
            errors = await _manifest_errors(destination, item.key, data)
            if item.key.endswith("/manifest.json"):
                verified += 1
            verify_errors.extend(errors)
    return {
        "dry_run": False,
        "objects": len(items),
        "bytes": total_bytes,
        "copied": copied,
        "skipped": skipped,
        "conflicts": conflicts,
        "verified": verified,
        "verify_errors": verify_errors,
    }
