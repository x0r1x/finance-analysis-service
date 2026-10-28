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
    Changed,
    GraphLink,
    NotModified,
    ReportNotReady,
    Summary,
    WorkbookSnapshot,
)
from finance_analysis.domain.deadline import Deadline


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

    async def read(self, payload: bytes) -> list[dict]: ...

    async def schema_tag(self, dataset: str) -> str: ...


class BuilderPort(Protocol):
    async def summary(self, job_id: str, etag: str | None) -> Summary | NotModified | ReportNotReady: ...

    async def head_summary(self, job_id: str, etag: str) -> NotModified | Changed | ReportNotReady: ...

    async def context(self, job_id: str) -> WorkbookSnapshot | ReportNotReady: ...

    async def graph(self, job_id: str) -> tuple[GraphLink, ...] | ReportNotReady: ...

    async def trace(self, job_id: str, origin: str, *, direction: str, depth: int) -> dict | ReportNotReady: ...

    async def breaker_state(self) -> str: ...


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


class JobQueuePort(Protocol):
    async def submit(self, kind: str, payload: dict, *, queue: str, actor: Actor) -> dict: ...


class OperationPort(Protocol):
    async def create(self, kind: str, job_id: str | None, actor: Actor, payload: dict) -> dict: ...

    async def get(self, op_id: str) -> dict: ...

    async def transition(self, op_id: str, status: str, **fields) -> dict: ...

    async def cancel(self, op_id: str, actor: Actor) -> dict: ...

    async def wait(self, op_id: str, wait_ms: int) -> dict: ...

    async def list(self, *, kind: str | None, job_id: str | None, status: str | None) -> AsyncIterator[dict]: ...


# --- модели (§10.3) и векторы (§10.4). Отказ стадии — ModelDegraded, анализ не падает. ---


class EmbedPort(Protocol):
    model: str

    async def embed(self, texts: list[str], *, deadline: Deadline) -> list[list[float]]: ...


class RerankPort(Protocol):
    model: str

    async def rerank(self, query: str, documents: list[str], *, deadline: Deadline, top_n: int) -> list[tuple[int, float]]: ...


class ChoiceModelPort(Protocol):
    model: str

    async def choose(self, state: str, questions: dict, *, deadline: Deadline) -> dict[str, dict]: ...


class LlmPort(Protocol):
    model: str

    async def complete(self, messages: list[dict], *, deadline: Deadline, max_tokens: int = 800) -> str: ...


class VectorIndexPort(Protocol):
    async def replace(self, vectors: list[list[float]], payloads: list[dict]) -> None: ...

    async def search(self, vectors: list[list[float]], k: int) -> list[list[tuple[float, dict]]]: ...

    async def size(self) -> int: ...


class ClusterPort(Protocol):
    async def cluster(self, vectors: list[list[float]], *, min_cluster_size: int) -> list[int]: ...


class BudgetPort(Protocol):
    async def take(self, key: str, limit: int, ttl: int) -> bool: ...


@dataclass
class Models:
    """Серверы моделей, каких нет — None; конвейер деградирует до lexical + structure + numeric."""

    embed: EmbedPort | None = None
    rerank: RerankPort | None = None
    clm: ChoiceModelPort | None = None
    llm: LlmPort | None = None
