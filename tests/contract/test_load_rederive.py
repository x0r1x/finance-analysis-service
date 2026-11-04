"""304 builder не оставляет устаревшую свёртку, если сменился хеш входов."""

from __future__ import annotations

from dataclasses import replace

import pytest

from finance_analysis.domain.book import Actor
from tests.conftest import JOB

pytestmark = pytest.mark.asyncio


def _context_reads(service) -> int:
    return sum(1 for call in service.builder.calls if call == ("GET", "/context.json"))


async def test_same_builder_job_rederives_only_when_config_hash_changes(local_service):
    first = await local_service.ensure(JOB, Actor(), wait_sec=60)
    assert first.derive_key
    assert first.versions["model_types"] == local_service.model_types.version
    assert first.versions["sheet_roles"] == local_service.sheet_roles_version
    reads = _context_reads(local_service)
    reused = await local_service.ensure(JOB, Actor(), wait_sec=60)
    assert reused.build_key == first.build_key
    assert reused.derive_key == first.derive_key
    assert local_service.fold_runs == 0
    assert _context_reads(local_service) == reads

    local_service.model_types = replace(local_service.model_types, version="0" * 16)
    fresh = await local_service.ensure(JOB, Actor(), wait_sec=60)
    assert fresh.build_key == first.build_key
    assert fresh.derive_key != first.derive_key
    assert fresh.versions["model_types"] == "0" * 16
    assert local_service.fold_runs == 1
    assert _context_reads(local_service) == reads

    again = await local_service.perform_load(JOB, actor=Actor(), fence=fresh.fence)
    assert again.build_key == first.build_key
    assert again.derive_key == fresh.derive_key
    assert local_service.fold_runs == 1
