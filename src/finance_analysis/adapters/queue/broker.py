"""FasStreamBroker: аренда, перехват по таймеру, лок с таймаутом (§4.13.5)."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable

from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError, ResponseError
from taskiq import AckableMessage
from taskiq_redis import RedisStreamBroker

from finance_analysis.adapters.queue.names import CONSUMER_GROUP

_RELEASE = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
else
  return 0
end
"""


def _text(value) -> str:
    if isinstance(value, bytes):
        return value.decode()
    return str(value)


def _rows(claimed) -> list:
    if not claimed:
        return []
    if isinstance(claimed, (list, tuple)) and len(claimed) >= 2 and isinstance(claimed[1], list):
        return claimed[1]
    if isinstance(claimed, list) and claimed and isinstance(claimed[0], (list, tuple)):
        return claimed
    return []


class FasStreamBroker(RedisStreamBroker):
    """Свой listen поверх Redis Streams. Подтверждение делает worker после выполнения."""

    def __init__(self, url: str, *, settings, queue_name: str, **connection_kwargs) -> None:
        super().__init__(
            url,
            queue_name=queue_name,
            consumer_group_name=CONSUMER_GROUP,
            maxlen=settings.taskiq_stream_maxlen,
            approximate=True,
            idle_timeout=settings.taskiq_idle_timeout_ms,
            unacknowledged_lock_timeout=settings.taskiq_reclaim_lock_sec,
            xread_count=1,
            xread_block=500,
            **connection_kwargs,
        )
        self._settings = settings
        self._owned: set[str] = set()
        self._inbox: asyncio.Queue[AckableMessage] = asyncio.Queue()
        self.stream_depth = 0

    def reclaim_lock_key(self) -> str:
        return f"fas:lock:reclaim:{self.queue_name}"

    async def listen(self) -> AsyncGenerator[AckableMessage, None]:
        await self._ensure_group()
        stop = asyncio.Event()
        tasks = [
            asyncio.create_task(self._read_loop(stop), name="fas-read"),
            asyncio.create_task(self._lease_loop(stop), name="fas-lease"),
            asyncio.create_task(self._reclaim_loop(stop), name="fas-reclaim"),
        ]
        try:
            while True:
                yield await self._inbox.get()
        finally:
            stop.set()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _ensure_group(self) -> None:
        async with Redis(connection_pool=self.connection_pool) as redis:
            try:
                await redis.xgroup_create(
                    self.queue_name,
                    self.consumer_group_name,
                    id=self.consumer_id,
                    mkstream=True,
                )
            except ResponseError as exc:
                if "BUSYGROUP" not in str(exc):
                    raise

    def _ack(self, msg_id: str) -> Callable[[], Awaitable[None]]:
        async def _run() -> None:
            self._owned.discard(msg_id)
            async with Redis(connection_pool=self.connection_pool) as redis:
                await redis.xack(self.queue_name, self.consumer_group_name, msg_id)

        return _run

    def _enqueue(self, msg_id: str, fields: dict) -> None:
        if msg_id in self._owned:
            return
        data = fields.get(b"data", fields.get("data"))
        if data is None:
            return
        if isinstance(data, str):
            data = data.encode()
        self._owned.add(msg_id)
        self._inbox.put_nowait(AckableMessage(data=data, ack=self._ack(msg_id)))

    async def _read_loop(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                async with Redis(connection_pool=self.connection_pool) as redis:
                    while not stop.is_set():
                        fetched = await redis.xreadgroup(
                            self.consumer_group_name,
                            self.consumer_name,
                            {self.queue_name: ">"},
                            block=self.block,
                            count=self.count,
                        )
                        for _stream, messages in fetched or []:
                            for msg_id, fields in messages:
                                self._enqueue(_text(msg_id), fields)
                        self.stream_depth = int(await redis.xlen(self.queue_name))
            except asyncio.CancelledError:
                raise
            except (RedisConnectionError, RedisError, OSError, ResponseError):
                await self._recover()

    async def _recover(self) -> None:
        try:
            await self.connection_pool.disconnect(inuse_connections=True)
            await self._ensure_group()
        except (RedisError, OSError, ResponseError, RuntimeError):
            return
        finally:
            await asyncio.sleep(0.2)

    async def _lease_loop(self, stop: asyncio.Event) -> None:
        interval = self._settings.taskiq_lease_refresh_sec
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
                return
            except TimeoutError:
                pass
            owned = list(self._owned)
            if not owned:
                continue
            try:
                async with Redis(connection_pool=self.connection_pool) as redis:
                    for msg_id in owned:
                        try:
                            await redis.xclaim(
                                self.queue_name,
                                self.consumer_group_name,
                                self.consumer_name,
                                min_idle_time=0,
                                message_ids=[msg_id],
                                justid=True,
                            )
                        except ResponseError:
                            self._owned.discard(msg_id)
            except asyncio.CancelledError:
                raise
            except (RedisConnectionError, RedisError, OSError):
                await asyncio.sleep(0.2)

    async def _reclaim_loop(self, stop: asyncio.Event) -> None:
        interval = self._settings.taskiq_reclaim_interval_sec
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
                return
            except TimeoutError:
                pass
            try:
                await self._reclaim_once()
            except asyncio.CancelledError:
                raise
            except (RedisConnectionError, RedisError, OSError, ResponseError):
                await asyncio.sleep(0.2)

    async def _acquire_reclaim_lock(self, redis) -> str | None:
        token = uuid.uuid4().hex
        ttl_ms = max(int(self._settings.taskiq_reclaim_lock_sec * 1000), 1)
        ok = await redis.set(self.reclaim_lock_key(), token, nx=True, px=ttl_ms)
        if not ok:
            return None
        return token

    async def _release_reclaim_lock(self, redis, token: str) -> None:
        await redis.eval(_RELEASE, 1, self.reclaim_lock_key(), token)

    async def _autoclaim(self, redis) -> None:
        cursor = "0-0"
        while True:
            claimed = await redis.xautoclaim(
                self.queue_name,
                self.consumer_group_name,
                self.consumer_name,
                min_idle_time=self.idle_timeout,
                start_id=cursor,
                count=self.unacknowledged_batch_size,
            )
            rows = _rows(claimed)
            next_id = _text(claimed[0]) if isinstance(claimed, (list, tuple)) and claimed else "0-0"
            for row in rows:
                if not isinstance(row, (list, tuple)) or len(row) < 2:
                    continue
                self._enqueue(_text(row[0]), row[1] or {})
            if not rows or next_id == "0-0":
                return
            cursor = next_id

    async def _reclaim_once(self) -> None:
        async with Redis(connection_pool=self.connection_pool) as redis:
            token = await self._acquire_reclaim_lock(redis)
            if token is None:
                return
            try:
                await self._autoclaim(redis)
                self.stream_depth = int(await redis.xlen(self.queue_name))
            finally:
                await self._release_reclaim_lock(redis, token)
