"""Redis: блокировки, кэш, GCRA, идемпотентность. Только redis.asyncio."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as redis_async

from finance_analysis.application.ports import Fence
from finance_analysis.domain.book import Actor
from finance_analysis.domain.errors import (
    DependencyUnavailable,
    IdempotencyReused,
    RateLimited,
    RequestInProgress,
    TooManyInflight,
)
from finance_analysis.settings import Settings

_RELEASE = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
else
  return 0
end
"""

_RENEW = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('pexpire', KEYS[1], ARGV[2])
else
  return 0
end
"""

_ABORT_PENDING = """
local raw = redis.call('GET', KEYS[1])
if not raw then
  return 0
end
if string.find(raw, '"status": "pending"', 1, true) then
  return redis.call('DEL', KEYS[1])
end
return 0
"""

_GCRA = """
local now = tonumber(ARGV[1])
local interval = tonumber(ARGV[2])
local burst = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])
local tat = redis.call('GET', KEYS[1])
if not tat then
  tat = now
else
  tat = tonumber(tat)
end
local new_tat = math.max(now, tat) + (interval * cost)
local allow_at = new_tat - (burst * interval)
if allow_at > now then
  return {0, math.ceil((allow_at - now) / 1000)}
end
local ttl = math.ceil(burst * interval + interval)
redis.call('SET', KEYS[1], tostring(new_tat), 'PX', ttl)
return {1, 0}
"""


def version_at_least(version: str | None, minimum: tuple[int, int, int] = (8, 6, 5)) -> bool:
    if not version:
        return False
    parts: list[int] = []
    for piece in version.split("."):
        digits = ""
        for char in piece:
            if char.isdigit():
                digits += char
            else:
                break
        if not digits:
            break
        parts.append(int(digits))
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3]) >= minimum


def _flight_dump(value) -> str | None:
    if isinstance(value, dict):
        return json.dumps({"kind": "dict", "body": value})
    operation = getattr(value, "operation", None)
    if type(value).__name__ == "Accepted" and isinstance(operation, dict):
        retry = getattr(value, "retry_after", 1)
        return json.dumps(
            {"kind": "accepted", "operation": operation, "retry_after": int(retry or 1)}
        )
    return None


def _flight_value(raw: bytes | str):
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    kind = parsed.get("kind")
    if kind == "dict" and isinstance(parsed.get("body"), dict):
        return parsed["body"]
    if kind == "accepted" and isinstance(parsed.get("operation"), dict):
        from finance_analysis.application.service import Accepted

        return Accepted(parsed["operation"], retry_after=int(parsed.get("retry_after") or 1))
    if kind is None:
        return parsed
    return None


class RedisRuntime:
    def __init__(self, client: redis_async.Redis, settings: Settings) -> None:
        self.redis = client
        self.settings = settings

    @classmethod
    def connect(cls, settings: Settings) -> RedisRuntime:
        if not settings.fas_redis_url:
            raise DependencyUnavailable("FAS_REDIS_URL не задан")
        pool = redis_async.ConnectionPool.from_url(
            settings.fas_redis_url,
            max_connections=settings.redis_max_connections,
            socket_timeout=1,
            socket_connect_timeout=1,
        )
        return cls(redis_async.Redis(connection_pool=pool), settings)

    async def server_version(self) -> str | None:
        try:
            info = await self.redis.info("server")
        except redis_async.RedisError:
            return None
        version = info.get("redis_version") or info.get(b"redis_version")
        if isinstance(version, bytes):
            return version.decode()
        return str(version) if version else None

    async def ping(self) -> bool:
        try:
            return bool(await self.redis.ping())
        except redis_async.RedisError:
            return False

    async def close(self) -> None:
        await self.redis.aclose()

    def lock(self, name: str, ttl_ms: int):
        runtime = self

        @asynccontextmanager
        async def _ctx():
            key = f"fas:lock:{name}"
            fence_key = f"fas:fence:{name}"
            token = uuid.uuid4().hex
            timeout = ttl_ms / 1000
            deadline = time.monotonic() + timeout
            acquired = False
            while time.monotonic() < deadline:
                try:
                    ok = await runtime.redis.set(key, token, nx=True, px=ttl_ms)
                except redis_async.RedisError as exc:
                    raise DependencyUnavailable("Redis недоступен") from exc
                if ok:
                    acquired = True
                    break
                await asyncio.sleep(0.05)
            if not acquired:
                raise TimeoutError(name)
            try:
                fence = int(await runtime.redis.incr(fence_key))
            except redis_async.RedisError as exc:
                await runtime.redis.eval(_RELEASE, 1, key, token)
                raise DependencyUnavailable("Redis недоступен") from exc
            stop = asyncio.Event()

            async def _renew() -> None:
                interval = max(ttl_ms / 3000, 0.2)
                while not stop.is_set():
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=interval)
                        return
                    except TimeoutError:
                        pass
                    try:
                        await runtime.redis.eval(_RENEW, 1, key, token, str(ttl_ms))
                    except redis_async.RedisError:
                        return

            task = asyncio.create_task(_renew())
            try:
                yield Fence(token=token, fence=fence)
            finally:
                stop.set()
                task.cancel()
                try:
                    await runtime.redis.eval(_RELEASE, 1, key, token)
                except redis_async.RedisError:
                    pass

        return _ctx()

    def try_lock(self, name: str, ttl_ms: int):
        """Одна попытка захвата. None — блокировка занята, задача переставляется (§4.13.5)."""
        runtime = self

        @asynccontextmanager
        async def _ctx():
            key = f"fas:lock:{name}"
            fence_key = f"fas:fence:{name}"
            token = uuid.uuid4().hex
            try:
                ok = await runtime.redis.set(key, token, nx=True, px=ttl_ms)
            except redis_async.RedisError as exc:
                raise DependencyUnavailable("Redis недоступен") from exc
            if not ok:
                yield None
                return
            try:
                fence = int(await runtime.redis.incr(fence_key))
            except redis_async.RedisError as exc:
                await runtime.redis.eval(_RELEASE, 1, key, token)
                raise DependencyUnavailable("Redis недоступен") from exc
            stop = asyncio.Event()

            async def _renew() -> None:
                interval = max(ttl_ms / 3000, 0.2)
                while not stop.is_set():
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=interval)
                        return
                    except TimeoutError:
                        pass
                    try:
                        await runtime.redis.eval(_RENEW, 1, key, token, str(ttl_ms))
                    except redis_async.RedisError:
                        return

            task = asyncio.create_task(_renew())
            try:
                yield Fence(token=token, fence=fence)
            finally:
                stop.set()
                task.cancel()
                try:
                    await runtime.redis.eval(_RELEASE, 1, key, token)
                except redis_async.RedisError:
                    pass

        return _ctx()

    async def held(self, name: str) -> bool:
        try:
            return bool(await self.redis.exists(f"fas:lock:{name}"))
        except redis_async.RedisError:
            return False

    async def cache_get(self, key: str) -> bytes | None:
        try:
            value = await self.redis.get(key)
        except redis_async.RedisError:
            return None
        return value

    async def cache_set(self, key: str, value: bytes, ttl: int) -> None:
        try:
            await self.redis.set(key, value, ex=ttl)
        except redis_async.RedisError as exc:
            raise DependencyUnavailable("Redis недоступен") from exc

    async def cache_delete(self, key: str) -> None:
        try:
            await self.redis.delete(key)
        except redis_async.RedisError:
            return

    async def publish(self, channel: str, message: str) -> None:
        try:
            await self.redis.publish(channel, message)
        except redis_async.RedisError:
            return

    async def messages(self, channel: str):
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(channel)
        try:
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if not message or message.get("type") != "message":
                    await asyncio.sleep(0.2)
                    continue
                data = message.get("data")
                if isinstance(data, bytes):
                    data = data.decode()
                if isinstance(data, str):
                    yield data
        finally:
            await pubsub.aclose()

    async def rate_limit(self, actor: Actor) -> None:
        now_ms = int(time.time() * 1000)
        checks: list[tuple[str, float, int]] = []
        if actor.user_id != "anonymous":
            checks.append((f"fas:rl:user:{actor.user_id}", self.settings.rate_user_rps, self.settings.rate_user_burst))
        if actor.client_id != "anonymous":
            checks.append(
                (f"fas:rl:client:{actor.client_id}", self.settings.rate_client_rps, self.settings.rate_client_burst)
            )
        if actor.user_id == "anonymous" and actor.client_id == "anonymous":
            checks.append(("fas:rl:anon", self.settings.rate_anon_rps, 20))
        for key, rps, burst in checks:
            interval = max(int(1000 / rps), 1)
            try:
                allowed, retry = await self.redis.eval(_GCRA, 1, key, str(now_ms), str(interval), str(burst), "1")
            except redis_async.RedisError:
                return
            if int(allowed) == 0:
                raise RateLimited("превышена квота", extra={"retry_after": max(int(retry), 1)})

    @asynccontextmanager
    async def user_inflight(self, actor: Actor) -> AsyncIterator[None]:
        key = f"fas:conc:user:{actor.user_id}"
        member = uuid.uuid4().hex
        now = time.time()
        limit = self.settings.user_max_inflight
        try:
            pipe = self.redis.pipeline()
            pipe.zremrangebyscore(key, 0, now - 120)
            pipe.zcard(key)
            _, count = await pipe.execute()
            if int(count) >= limit:
                raise TooManyInflight("слишком много запросов пользователя", extra={"retry_after": 1, "limit": limit})
            await self.redis.zadd(key, {member: now})
            await self.redis.expire(key, 180)
        except redis_async.RedisError as exc:
            raise DependencyUnavailable("Redis недоступен") from exc
        try:
            yield
        finally:
            try:
                await self.redis.zrem(key, member)
            except redis_async.RedisError:
                pass

    async def idem_begin(self, actor: Actor, method: str, route: str, key: str, body: bytes) -> dict | None:
        digest = hashlib.sha256(body).hexdigest()
        redis_key = f"fas:idem:{actor.user_id}:{actor.client_id}:{method}:{route}:{key}"
        try:
            existing = await self.redis.get(redis_key)
        except redis_async.RedisError as exc:
            raise DependencyUnavailable("Redis недоступен") from exc
        if existing:
            stored = json.loads(existing)
            if stored["hash"] != digest:
                raise IdempotencyReused("ключ идемпотентности использован с другим телом")
            if stored["status"] == "pending":
                raise RequestInProgress("запрос с этим ключом ещё выполняется", extra={"retry_after": 1})
            return stored
        payload = json.dumps({"hash": digest, "status": "pending"})
        pending_ttl = max(
            int(self.settings.lock_ttl_ms / 1000),
            int(self.settings.load_sync_sec) + 30,
            30,
        )
        try:
            ok = await self.redis.set(redis_key, payload, nx=True, ex=pending_ttl)
        except redis_async.RedisError as exc:
            raise DependencyUnavailable("Redis недоступен") from exc
        if not ok:
            return await self.idem_begin(actor, method, route, key, body)
        return None

    async def idem_abort(self, actor: Actor, method: str, route: str, key: str, body: bytes) -> None:
        del body
        redis_key = f"fas:idem:{actor.user_id}:{actor.client_id}:{method}:{route}:{key}"
        try:
            await self.redis.eval(_ABORT_PENDING, 1, redis_key)
        except redis_async.RedisError:
            return

    async def take(self, key: str, limit: int, ttl: int) -> bool:
        """Атомарный счётчик бюджета (CLM на книгу, §4.13.4): INCR + TTL при первом взятии."""

        try:
            async with self.redis.pipeline(transaction=True) as pipe:
                pipe.incr(key)
                pipe.expire(key, ttl, nx=True)
                used, _expire = await pipe.execute()
        except redis_async.RedisError:
            # Без Redis бюджет не проверить: CLM не вызываем, строка остаётся ambiguous.
            return False
        return int(used) <= limit

    async def singleflight(self, key: str, factory):
        """Один расчёт на ключ. При отказе Redis вызывающий считает сам."""

        lock = f"fas:sf:{key}"
        result_key = f"fas:sf:res:{key}"
        token = uuid.uuid4().hex
        try:
            owned = await self.redis.set(lock, token, nx=True, px=30_000)
        except redis_async.RedisError:
            return await factory()
        if not owned:
            for _ in range(200):
                cached = await self.cache_get(result_key)
                if cached:
                    loaded = _flight_value(cached)
                    if loaded is not None:
                        return loaded
                await asyncio.sleep(0.05)
            return await factory()
        try:
            value = await factory()
            encoded = _flight_dump(value)
            if encoded is not None:
                try:
                    await self.redis.set(result_key, encoded, px=30_000)
                except redis_async.RedisError:
                    pass
            return value
        finally:
            try:
                await self.redis.eval(_RELEASE, 1, lock, token)
            except redis_async.RedisError:
                pass

    async def idem_finish(self, actor: Actor, method: str, route: str, key: str, body: bytes, response: dict, status: int) -> None:
        digest = hashlib.sha256(body).hexdigest()
        redis_key = f"fas:idem:{actor.user_id}:{actor.client_id}:{method}:{route}:{key}"
        payload = json.dumps({"hash": digest, "status": "done", "response": response, "http_status": status})
        try:
            await self.redis.set(redis_key, payload, ex=self.settings.idempotency_ttl)
        except redis_async.RedisError:
            return
