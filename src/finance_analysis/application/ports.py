"""Порты hexagonal (§4.14.2). Все методы асинхронные."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import pyarrow as pa

from finance_analysis.domain.book import (
    Actor,
    NotModified,
    Summary,
    WorkbookSnapshot,
)


@dataclass(frozen=True)
class ObjMeta:
    key: str
    size: int
    etag: str | None
    mtime: datetime | None


@dataclass(frozen=True)
class Fence:
    token: str
    fence: int


class ObjectStorePort(Protocol):
    url: str
    backend: str
    conditional_writes: str

    async def get(self, key: str) -> bytes: ...

    async def stat(self, key: str) -> ObjMeta | None: ...

    async def put(self, key: str, data: bytes) -> ObjMeta: ...

    async def put_if_absent(self, key: str, data: bytes) -> ObjMeta: ...

    async def put_if_match(self, key: str, data: bytes, token: str) -> ObjMeta: ...

    async def list(self, prefix: str) -> AsyncIterator[ObjMeta]: ...

    async def delete_prefix(self, prefix: str) -> int: ...

    async def selftest(self) -> None: ...


class ParquetPort(Protocol):
    async def write(self, dataset: str, rows: list[dict], *, build_key: str) -> tuple[bytes, int]: ...


class BuilderPort(Protocol):
    async def summary(self, job_id: str, etag: str | None) -> Summary | NotModified: ...

    async def context(self, job_id: str) -> tuple[WorkbookSnapshot, str | None, str]: ...

    async def graph(self, job_id: str) -> tuple[WorkbookSnapshot | None, str | None]: ...

    async def healthy(self) -> bool: ...


class SemanticQueryPort(Protocol):
    async def sql(self, job_id: str, sql: str, limit: int = 5000, pin: dict | None = None) -> pa.Table: ...

    async def cube(self, job_id: str, query: dict, pin: dict | None = None) -> pa.Table: ...

    async def mdl_for(self, job_id: str, head: dict, paths: dict[str, str]) -> dict: ...


class CachePort(Protocol):
    async def get(self, key: str) -> bytes | None: ...

    async def set(self, key: str, value: bytes, ttl: int) -> None: ...

    async def delete(self, key: str) -> None: ...


class LockPort(Protocol):
    async def lock(self, name: str, ttl_ms: int) -> AbstractAsyncContextManager[Fence]: ...

    async def held(self, name: str) -> bool: ...


class OperationPort(Protocol):
    async def create(self, kind: str, job_id: str | None, actor: Actor, payload: dict) -> dict: ...

    async def get(self, op_id: str) -> dict: ...

    async def transition(self, op_id: str, status: str, **fields) -> dict: ...

    async def cancel(self, op_id: str, actor: Actor) -> dict: ...

    async def wait(self, op_id: str, wait_ms: int) -> dict: ...

    async def list(self, *, kind: str | None, job_id: str | None, status: str | None) -> AsyncIterator[dict]: ...
