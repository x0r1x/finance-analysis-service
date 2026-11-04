"""Закрытый подбор сопоставления не переписывает книгу."""

from __future__ import annotations

import pytest

from finance_analysis.adapters.queue import learning_tasks
from finance_analysis.adapters.queue import runtime as runtime_mod
from finance_analysis.adapters.queue.runtime import WorkerRuntime
from finance_analysis.adapters.queue.tasks import _run_locked, _service_stage
from finance_analysis.domain.book import Actor
from tests.conftest import JOB

pytestmark = pytest.mark.asyncio


async def test_closed_mapping_infer_skips_the_write(local_service, redis_runtime, monkeypatch):
    await local_service.perform_load(JOB, actor=Actor(), fence=1)
    head, _token = await local_service._read_head(JOB)
    build_key, derive_key = head.build_key, head.derive_key

    async def _mine():
        return local_service

    monkeypatch.setattr(learning_tasks, "_mine_service", _mine)
    failed = await local_service.create_op(
        "mapping.infer",
        JOB,
        Actor(user_id="alex"),
        {"stage": "mapping.infer", "stage_args": {"job_id": JOB}, "job_id": JOB},
    )
    await local_service.finish_op(
        failed["id"],
        "failed",
        error={"code": "dependency_unavailable", "title": "Нет heartbeat операции"},
    )
    staged = await _service_stage("mapping.infer", {"job_id": JOB}, failed["id"])
    assert staged["status"] == "skipped"
    assert (await local_service.get_op(failed["id"]))["status"] == "failed"

    runtime_mod.RUNTIME = WorkerRuntime(
        settings=local_service.settings,
        redis=redis_runtime.redis,
        store=local_service.store,
        schedule=None,
        broker=None,
        locks=redis_runtime,
    )
    try:
        played = await _run_locked(
            runtime_mod.RUNTIME,
            {"op_id": failed["id"], "stage": "mapping.infer", "stage_args": {"job_id": JOB}},
        )
    finally:
        runtime_mod.RUNTIME = None
    assert played["status"] == "skipped"
    assert (await local_service.get_op(failed["id"]))["status"] == "failed"

    cancelled = await local_service.create_op(
        "mapping.infer",
        JOB,
        Actor(user_id="alex"),
        {"stage": "mapping.infer", "stage_args": {"job_id": JOB}, "job_id": JOB},
    )
    await local_service.cancel_op(cancelled["id"], Actor(user_id="alex"))
    skipped = await _service_stage("mapping.infer", {"job_id": JOB}, cancelled["id"])
    assert skipped["status"] == "skipped"
    assert (await local_service.get_op(cancelled["id"]))["status"] == "cancelled"

    fresh, _token = await local_service._read_head(JOB)
    assert fresh.build_key == build_key
    assert fresh.derive_key == derive_key
