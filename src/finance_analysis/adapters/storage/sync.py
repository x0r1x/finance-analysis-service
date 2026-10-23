"""Копирование object store: fas storage sync (§4.1)."""

from __future__ import annotations

from finance_analysis.domain.errors import PreconditionFailed


async def sync_stores(source, destination) -> dict:
    copied = 0
    skipped = 0
    async for item in source.list(""):
        data = await source.get(item.key)
        try:
            await destination.put_if_absent(item.key, data)
            copied += 1
        except Exception as exc:
            from finance_analysis.domain.errors import AlreadyExists

            if not isinstance(exc, AlreadyExists):
                raise
            existing = await destination.get(item.key)
            if existing != data:
                raise PreconditionFailed(f"ключ {item.key} уже занят другим содержимым") from exc
            skipped += 1
    return {"copied": copied, "skipped": skipped}
