"""Единственный путь записи семантики (§5.12)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from finance_analysis.application.derived_store import DerivedWrite, write_derived
from finance_analysis.application.journal import Journal
from finance_analysis.domain.book import Actor
from finance_analysis.domain.errors import SemanticRejected
from finance_analysis.domain.validation.semantics import (
    Verdict,
    check_derived,
    check_event,
)

_SEAL = object()


def derived_seal() -> object:
    return _SEAL


@dataclass(frozen=True)
class WriteResult:
    accepted: bool
    duplicate: bool = False
    code: str | None = None
    detail: str = ""
    event: dict | None = None


class SemanticWriteGuard:
    def __init__(
        self,
        store,
        *,
        catalog: frozenset[str] | None = None,
        targets: frozenset[str] | None = None,
    ) -> None:
        self._store = store
        self._journal = Journal(store)
        self._catalog = catalog or frozenset()
        self._targets = targets or frozenset()

    async def read_all(self, job_id: str) -> list[dict]:
        return await self._journal.read_all(job_id)

    async def append(
        self,
        job_id: str,
        *,
        target: str,
        event_type: str,
        value,
        actor: Actor,
        expected_seq: int | None,
        request_id: str,
        at_utc: datetime | None = None,
        concept: str | None = None,
    ) -> WriteResult:
        verdict = check_event(
            event_type=event_type,
            target=target,
            concept=concept,
            catalog=self._catalog,
            targets=self._targets,
        )
        if not verdict.accepted:
            return WriteResult(False, code=verdict.code, detail=verdict.detail)
        event, duplicate = await self._journal.commit(
            job_id,
            target=target,
            event_type=event_type,
            value=value,
            actor=actor,
            expected_seq=expected_seq,
            request_id=request_id,
            at_utc=at_utc,
        )
        return WriteResult(True, duplicate=duplicate, event=event)

    def review_derived(self, tables: dict, *, row_keys: frozenset[str]) -> Verdict:
        return check_derived(tables, catalog=self._catalog, row_keys=row_keys)

    def authorize_derived(self, tables: dict, *, row_keys: frozenset[str]) -> DerivedWrite:
        verdict = self.review_derived(tables, row_keys=row_keys)
        if not verdict.accepted:
            raise SemanticRejected(verdict.code or "schema_invalid", verdict.detail)
        return DerivedWrite(tables, _SEAL)

    async def persist_derived(
        self,
        *,
        job_id: str,
        build: str,
        derive: str,
        attempt: str,
        tables: dict,
        parquet,
        row_keys: frozenset[str],
    ) -> dict:
        token = self.authorize_derived(tables, row_keys=row_keys)
        return await write_derived(
            self._store,
            parquet,
            token,
            job_id=job_id,
            build=build,
            derive=derive,
            attempt=attempt,
        )
