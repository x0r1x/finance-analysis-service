"""Сборка брокера и постановка задач за JobQueuePort."""

from __future__ import annotations

import warnings

import redis.asyncio as redis_async
from taskiq_redis import RedisScheduleSource

from finance_analysis.adapters.queue.broker import FasStreamBroker
from finance_analysis.adapters.queue.names import INTERACTIVE, QUEUES
from finance_analysis.adapters.queue.retry import FasRetryMiddleware
from finance_analysis.adapters.queue.tasks import (
    RUN_TASK,
    fail_exhausted,
    register_tasks,
)
from finance_analysis.adapters.storage.store import open_storage
from finance_analysis.application.operations import create_op
from finance_analysis.domain.book import Actor
from finance_analysis.domain.errors import DependencyUnavailable, InvalidArgument
from finance_analysis.settings import Settings

from . import fairness


def open_schedule(url: str) -> RedisScheduleSource:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return RedisScheduleSource(url, prefix="fas:schedule")


def build_broker(
    url: str,
    settings: Settings,
    queue_name: str,
    schedule,
    *,
    schedules: bool,
    exhausted=None,
) -> FasStreamBroker:
    broker = FasStreamBroker(url, settings=settings, queue_name=queue_name)
    broker.add_middlewares(
        FasRetryMiddleware(settings=settings, schedule_source=schedule, on_exhausted=exhausted)
    )
    register_tasks(broker, schedules=schedules, cron=settings.gc_cron, settings=settings)
    return broker


class TaskiqJobs:
    """JobQueuePort на FasStreamBroker."""

    def __init__(self, settings: Settings, store, redis, schedule, brokers: dict[str, FasStreamBroker]) -> None:
        self.settings = settings
        self.store = store
        self.redis = redis
        self.schedule = schedule
        self.brokers = brokers

    @classmethod
    async def open(cls, settings: Settings) -> TaskiqJobs:
        if not settings.fas_redis_url:
            raise DependencyUnavailable("FAS_REDIS_URL не задан")
        store = await open_storage(settings)
        redis = redis_async.Redis.from_url(settings.fas_redis_url, socket_timeout=None)
        schedule = open_schedule(settings.fas_redis_url)
        brokers = {
            queue: build_broker(
                settings.fas_redis_url,
                settings,
                queue,
                schedule,
                schedules=False,
                exhausted=fail_exhausted,
            )
            for queue in QUEUES
        }
        return cls(settings, store, redis, schedule, brokers)

    async def startup(self) -> None:
        for broker in self.brokers.values():
            await broker.startup()

    async def shutdown(self) -> None:
        for broker in self.brokers.values():
            await broker.shutdown()
        await self.redis.aclose()
        await self.schedule.shutdown()

    async def submit(self, kind: str, payload: dict, *, queue: str, actor: Actor) -> dict:
        if queue not in QUEUES:
            raise InvalidArgument(f"неизвестная очередь {queue}")
        body = dict(payload)
        body["kind"] = kind
        body["queue"] = queue
        body["user_id"] = actor.user_id
        admitted = 1
        if queue == INTERACTIVE:
            admitted = await fairness.admit(self.redis, queue, actor.user_id, self.settings.user_max_queued)
        try:
            operation = await create_op(self.store, kind, body.get("job_id"), actor, body)
        except Exception:
            if queue == INTERACTIVE:
                await fairness.rollback(self.redis, queue, actor.user_id)
            raise
        body["op_id"] = operation["id"]
        try:
            await self.redis.publish(f"fas:op:{operation['id']}", "running")
        except redis_async.RedisError as exc:
            raise DependencyUnavailable("Redis недоступен") from exc
        if queue == INTERACTIVE and admitted > 1:
            await fairness.push_waiting(self.redis, queue, actor.user_id, body)
            return operation
        await self.kick(body)
        return operation

    async def kick(self, payload: dict) -> None:
        queue = payload.get("queue") or INTERACTIVE
        broker = self.brokers[queue]
        task = broker.find_task(RUN_TASK)
        await task.kicker().with_labels(queue_name=queue).kiq(payload)
