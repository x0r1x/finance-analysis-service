"""Запись derived/. Импортирует только SemanticWriteGuard."""

from __future__ import annotations

from typing import Any

from finance_analysis.application import keys
from finance_analysis.domain.book import sha256_bytes
from finance_analysis.domain.errors import AlreadyExists


class DerivedWrite:
    """Разрешение на запись. Собрать его можно только внутри guard."""

    def __init__(self, tables: dict, seal: object) -> None:
        from finance_analysis.application.semantic_guard import derived_seal

        if seal is not derived_seal():
            raise TypeError("DerivedWrite выпускает только SemanticWriteGuard")
        self.tables = tables


async def write_derived(
    store,
    parquet,
    token: DerivedWrite,
    *,
    job_id: str,
    build: str,
    derive: str,
    attempt: str,
) -> dict:
    if not isinstance(token, DerivedWrite):
        raise TypeError("запись derived принимает только разрешение guard")
    files: dict[str, Any] = {}
    for dataset, rows in token.tables.items():
        payload, count = await parquet.write(dataset, rows, build_key=build)
        rel = f"derived/{derive}/a/{attempt}/{dataset}.parquet"
        key = keys.derived_file(job_id, build, derive, attempt, dataset)
        try:
            await store.put_if_absent(key, payload)
        except AlreadyExists:
            pass
        files[rel] = {"sha256": sha256_bytes(payload), "rows": count, "schema": await parquet.schema_tag(dataset)}
    return files
