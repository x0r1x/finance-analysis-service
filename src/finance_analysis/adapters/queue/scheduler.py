"""TaskiqScheduler: cron и отложенные повторы (§4.13.5)."""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
from datetime import timedelta
from pathlib import Path

from taskiq import TaskiqScheduler
from taskiq.cli.scheduler.run import SchedulerLoop
from taskiq.schedule_sources import LabelScheduleSource

from finance_analysis.adapters.queue.jobs import build_broker, open_schedule
from finance_analysis.adapters.queue.names import MAINTENANCE
from finance_analysis.adapters.redis.runtime import RedisRuntime, version_at_least
from finance_analysis.settings import Settings, load_settings


def build_scheduler(settings: Settings) -> TaskiqScheduler:
    if not settings.fas_redis_url:
        raise SystemExit("FAS_REDIS_URL не задан")
    schedule = open_schedule(settings.fas_redis_url)
    broker = build_broker(
        settings.fas_redis_url,
        settings,
        MAINTENANCE,
        schedule,
        schedules=True,
        exhausted=None,
    )
    return TaskiqScheduler(broker, sources=[LabelScheduleSource(broker), schedule])


async def serve(settings: Settings, *, update_interval: float, loop_interval: float, ready_path: str | None) -> None:
    locks = RedisRuntime.connect(settings)
    version = await locks.server_version()
    if not version_at_least(version):
        raise SystemExit(f"нужен Redis 8.6.5 или новее, сейчас {version}")
    scheduler = build_scheduler(settings)
    await scheduler.startup()
    if ready_path:
        Path(ready_path).write_text("1")
    loop = SchedulerLoop(scheduler)
    stop = asyncio.Event()
    current = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            current.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass

    runner = asyncio.create_task(
        loop.run(
            update_interval=timedelta(seconds=update_interval),
            loop_interval=timedelta(seconds=loop_interval),
            skip_first_run=False,
        )
    )
    stopper = asyncio.create_task(stop.wait())
    try:
        await asyncio.wait({runner, stopper}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        runner.cancel()
        stopper.cancel()
        await scheduler.shutdown()
        for source in scheduler.sources:
            await source.shutdown()
        await locks.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="fas-scheduler")
    parser.add_argument("--update-interval", type=float, default=1)
    parser.add_argument("--loop-interval", type=float, default=1)
    parser.add_argument("--ready-file", default=os.environ.get("FAS_SCHEDULER_READY"))
    args = parser.parse_args(argv)
    asyncio.run(
        serve(
            load_settings(),
            update_interval=args.update_interval,
            loop_interval=args.loop_interval,
            ready_path=args.ready_file,
        )
    )


if __name__ == "__main__":
    main()
