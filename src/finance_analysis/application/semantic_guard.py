"""Единственный путь записи семантики (§5.12)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from finance_analysis.application.derived_store import DerivedWrite, write_derived
from finance_analysis.application.journal import Journal
from finance_analysis.domain.book import Actor
from finance_analysis.domain.errors import SemanticRejected
from finance_analysis.domain.model_type import assignment_error
from finance_analysis.domain.phases import check_phase_order, check_phase_value
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
        model_types: frozenset[str] | None = None,
        max_labels: int = 3,
    ) -> None:
        self._store = store
        self._journal = Journal(store)
        self._catalog = catalog or frozenset()
        self._targets = targets or frozenset()
        self._model_types = model_types or frozenset()
        self._max_labels = max_labels

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
        known_targets: frozenset[str] | None = None,
        binding_key: str | None = None,
        supersedes: dict | None = None,
        question_id: str | None = None,
    ) -> WriteResult:
        verdict = check_event(
            event_type=event_type,
            target=target,
            concept=concept,
            catalog=self._catalog,
            targets=self._targets if known_targets is None else known_targets,
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
            binding_key=binding_key,
            supersedes=supersedes,
            question_id=question_id,
        )
        return WriteResult(True, duplicate=duplicate, event=event)

    async def write_decision(
        self,
        job_id: str,
        *,
        event_type: str,
        target: str,
        value,
        actor: Actor,
        expected_seq: int | None,
        request_id: str,
        concept: str | None = None,
        known_targets: frozenset[str] | None = None,
        phase_order: list[tuple[int, str]] | None = None,
        concept_taken: bool = False,
        binding_key: str | None = None,
        supersedes: dict | None = None,
        question_id: str | None = None,
    ) -> WriteResult:
        if event_type == "model_type.set":
            problem = assignment_error(value, known=self._model_types, max_labels=self._max_labels)
            if problem:
                return WriteResult(False, code=problem[0], detail=problem[1])
        if event_type == "phase.set":
            verdict = check_phase_value(value)
            if not verdict.accepted:
                return WriteResult(False, code=verdict.code, detail=verdict.detail)
            if phase_order is not None:
                verdict = check_phase_order(phase_order)
                if not verdict.accepted:
                    return WriteResult(False, code=verdict.code, detail=verdict.detail)
        if event_type in {"concept.set", "concept.confirmed"} and concept_taken and not supersedes:
            return WriteResult(False, code="supersede_required", detail="понятие уже привязано")
        return await self.append(
            job_id,
            target=target,
            event_type=event_type,
            value=value,
            actor=actor,
            expected_seq=expected_seq,
            request_id=request_id,
            concept=concept,
            known_targets=known_targets,
            binding_key=binding_key,
            supersedes=supersedes,
            question_id=question_id,
        )

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
