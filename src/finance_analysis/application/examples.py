"""Кросс-книжные примеры `examples/{embed_model}/` и kNN по ним (§4.5, §5.11.5).

Файлы не удаляются (§4.10): слияние пишет `part-*.parquet` и список поглощённых файлов
в `_merged.json`; читатель пропускает поглощённые.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime

import numpy as np
from ulid import ULID

from finance_analysis.domain.errors import AlreadyExists, NotFound, PreconditionFailed

LIVE_KINDS = frozenset({"confirmed", "set"})


def pack_vector(vector: list[float] | tuple[float, ...] | None) -> bytes | None:
    if not vector:
        return None
    return np.asarray(vector, dtype="<f4").tobytes()


def unpack_vector(raw: bytes | None) -> list[float] | None:
    if not raw:
        return None
    return np.frombuffer(raw, dtype="<f4").astype(float).tolist()


class AppendOnlyParquet:
    """Мелкие файлы с ULID + дневное слияние в part-*. Общий код examples/, unmapped/, signals/."""

    def __init__(self, store, parquet, *, dataset: str, prefix: str, sort_key: str) -> None:
        self.store = store
        self.parquet = parquet
        self.dataset = dataset
        self.prefix = prefix.rstrip("/") + "/"
        self.sort_key = sort_key

    async def append(self, rows: list[dict], *, sub: str = "") -> str | None:
        if not rows:
            return None
        payload, _count = await self.parquet.write(self.dataset, rows, build_key="")
        key = f"{self.prefix}{sub}{ULID()}.parquet"
        await self.store.put_if_absent(key, payload)
        return key

    async def _merged(self) -> tuple[set[str], str | None]:
        key = f"{self.prefix}_merged.json"
        try:
            raw = await self.store.get(key)
        except NotFound:
            return set(), None
        meta = await self.store.stat(key)
        return set(json.loads(raw).get("consumed") or []), None if meta is None else meta.etag

    async def keys(self) -> list[str]:
        consumed, _etag = await self._merged()
        found = []
        async for item in self.store.list(self.prefix):
            if item.key.endswith(".parquet") and item.key not in consumed:
                found.append(item.key)
        return sorted(found)

    async def rows(self) -> list[dict]:
        out: list[dict] = []
        for key in await self.keys():
            out.extend(await self.parquet.read(await self.store.get(key)))
        return out

    async def merge(self) -> dict:
        consumed, etag = await self._merged()
        small = [key for key in await self.keys() if not key.rsplit("/", 1)[-1].startswith("part-")]
        if len(small) < 2:
            return {"merged": 0}
        rows: list[dict] = []
        for key in small:
            rows.extend(await self.parquet.read(await self.store.get(key)))
        rows.sort(key=lambda row: str(row.get(self.sort_key) or ""))
        payload, _count = await self.parquet.write(self.dataset, rows, build_key="")
        part = f"{self.prefix}part-{ULID()}.parquet"
        await self.store.put_if_absent(part, payload)
        body = json.dumps({"consumed": sorted(consumed | set(small))}).encode()
        key = f"{self.prefix}_merged.json"
        try:
            if etag is None:
                await self.store.put_if_absent(key, body)
            else:
                await self.store.put_if_match(key, body, etag)
        except (AlreadyExists, PreconditionFailed):
            # Другой процесс слил раньше: наш part дублирует строки, читатель берёт последнюю по seq.
            return {"merged": 0, "conflict": True}
        return {"merged": len(small), "part": part}


class ExampleStore:
    def __init__(self, store, parquet, index, *, model: str, refresh_sec: float = 60) -> None:
        self.model = model or "none"
        self.files = AppendOnlyParquet(store, parquet, dataset="examples", prefix=f"examples/{self.model}/", sort_key="example_id")
        self._index = index
        self._refresh_sec = refresh_sec
        self._loaded_at = 0.0
        self._keys: tuple[str, ...] = ()

    async def append(self, rows: list[dict]) -> None:
        now = datetime.now(UTC)
        prepared = []
        for row in rows:
            prepared.append(
                {
                    "example_id": str(ULID()),
                    "embed_model": self.model,
                    "at_utc": now,
                    **row,
                    "embedding_f32": pack_vector(row.get("embedding")),
                }
            )
        await self.files.append(prepared)
        self._loaded_at = 0.0

    async def all_rows(self) -> list[dict]:
        return await self.files.rows()

    async def active(self) -> list[dict]:
        """Последняя запись по (книга, строка). Заменённые и отклонённые в kNN не идут (§5.10.5)."""

        latest: dict[tuple[str, str], dict] = {}
        for row in await self.files.rows():
            key = (row["job_id"], row["binding_key"])
            current = latest.get(key)
            if current is None or (int(row["seq"]), row["example_id"]) > (int(current["seq"]), current["example_id"]):
                latest[key] = row
        return [row for row in latest.values() if row.get("kind") in LIVE_KINDS and row.get("concept")]

    async def refresh(self, *, force: bool = False) -> int:
        if self._index is None:
            return 0
        if not force and time.monotonic() - self._loaded_at < self._refresh_sec:
            return await self._index.size()
        keys = tuple(await self.files.keys())
        if keys == self._keys and not force and self._loaded_at:
            self._loaded_at = time.monotonic()
            return await self._index.size()
        rows = [row for row in await self.active() if row.get("embedding_f32")]
        vectors = [unpack_vector(row["embedding_f32"]) for row in rows]
        payloads = [
            {
                "concept": row["concept"],
                "job_id": row["job_id"],
                "binding_key": row["binding_key"],
                **({"path_text": row["path_text"]} if row.get("path_text") else {}),
            }
            for row in rows
        ]
        await self._index.replace(vectors, payloads)
        self._keys = keys
        self._loaded_at = time.monotonic()
        return len(rows)

    async def search(self, vectors: list[list[float]], k: int) -> list[list[tuple[float, dict]]]:
        if self._index is None:
            return [[] for _ in vectors]
        await self.refresh()
        return await self._index.search(vectors, k)

    async def merge(self) -> dict:
        return await self.files.merge()
