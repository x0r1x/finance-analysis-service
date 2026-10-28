"""Процесс worker-а одной очереди (§4.13.5)."""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
from pathlib import Path

from taskiq.acks import AcknowledgeType
from taskiq.receiver import Receiver

from finance_analysis.adapters.queue import runtime as runtime_mod
from finance_analysis.adapters.queue.jobs import build_broker, open_schedule
from finance_analysis.adapters.queue.retry import FasRetryMiddleware
from finance_analysis.adapters.queue.runtime import WorkerRuntime
from finance_analysis.adapters.queue.tasks import fail_exhausted, register_tasks
from finance_analysis.adapters.redis.runtime import RedisRuntime, version_at_least
from finance_analysis.adapters.storage.store import open_storage
from finance_analysis.settings import Settings, load_settings


async def serve(
    settings: Settings,
    *,
    queue: str,
    max_async_tasks: int,
    ready_path: str | None,
    broker_cls=None,
) -> None:
    if not settings.fas_redis_url:
        raise SystemExit("FAS_REDIS_URL не задан")
    locks = RedisRuntime.connect(settings)
    version = await locks.server_version()
    if not version_at_least(version):
        raise SystemExit(f"нужен Redis 8.6.5 или новее, сейчас {version}")
    schedule = open_schedule(settings.fas_redis_url)
    if broker_cls is None:
        broker = build_broker(
            settings.fas_redis_url,
            settings,
            queue,
            schedule,
            schedules=False,
            exhausted=fail_exhausted,
        )
    else:
        broker = broker_cls(settings.fas_redis_url, settings=settings, queue_name=queue)
        broker.add_middlewares(
            FasRetryMiddleware(settings=settings, schedule_source=schedule, on_exhausted=fail_exhausted)
        )
        register_tasks(broker, schedules=False, cron=settings.gc_cron, settings=settings)
    store = await open_storage(settings)
    runtime_mod.RUNTIME = WorkerRuntime(
        settings=settings,
        redis=locks.redis,
        store=store,
        schedule=schedule,
        broker=broker,
        locks=locks,
    )
    await broker.startup()
    if ready_path:
        Path(ready_path).write_text(broker.consumer_name)
    receiver = Receiver(
        broker,
        max_async_tasks=max_async_tasks,
        max_prefetch=0,
        ack_type=AcknowledgeType.WHEN_EXECUTED,
        run_startup=False,
    )
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass
    try:
        await receiver.listen(stop)
    finally:
        await broker.shutdown()
        await schedule.shutdown()
        await locks.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="fas-worker")
    parser.add_argument("--queue", required=True)
    parser.add_argument("--max-async-tasks", type=int, default=8)
    parser.add_argument("--ready-file", default=os.environ.get("FAS_WORKER_READY"))
    args = parser.parse_args(argv)
    asyncio.run(
        serve(
            load_settings(),
            queue=args.queue,
            max_async_tasks=args.max_async_tasks,
            ready_path=args.ready_file,
        )
    )


if __name__ == "__main__":
    main()
