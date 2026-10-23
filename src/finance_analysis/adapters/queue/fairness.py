"""Справедливость очереди interactive: одна задача пользователя в stream (§4.13.5)."""

from __future__ import annotations

import json

import redis.asyncio as redis_async

from finance_analysis.domain.errors import RateLimited

_ADMIT = """
local n = redis.call('INCR', KEYS[1])
if n > tonumber(ARGV[1]) then
  redis.call('DECR', KEYS[1])
  return -1
end
return n
"""

_COMPLETE = """
local nxt = redis.call('LPOP', KEYS[2])
if nxt then
  return nxt
end
local n = redis.call('DECR', KEYS[1])
if n < 0 then
  redis.call('SET', KEYS[1], '0')
end
return false
"""


def fair_keys(queue: str, user_id: str) -> tuple[str, str]:
    return f"fas:fair:n:{queue}:{user_id}", f"fas:fair:wait:{queue}:{user_id}"


async def admit(redis, queue: str, user_id: str, limit: int) -> int:
    count_key, _wait = fair_keys(queue, user_id)
    try:
        admitted = await redis.eval(_ADMIT, 1, count_key, str(limit))
    except redis_async.RedisError as exc:
        from finance_analysis.domain.errors import DependencyUnavailable

        raise DependencyUnavailable("Redis недоступен") from exc
    number = int(admitted)
    if number < 0:
        raise RateLimited(
            f"в очереди {queue} у пользователя уже {limit} задач",
            extra={"limit": limit},
        )
    return number


async def push_waiting(redis, queue: str, user_id: str, payload: dict) -> None:
    _count, wait_key = fair_keys(queue, user_id)
    await redis.rpush(wait_key, json.dumps(payload, ensure_ascii=False))


async def rollback(redis, queue: str, user_id: str) -> None:
    count_key, _wait = fair_keys(queue, user_id)
    remaining = int(await redis.decr(count_key))
    if remaining < 0:
        await redis.set(count_key, 0)


async def complete(redis, queue: str, user_id: str) -> dict | None:
    count_key, wait_key = fair_keys(queue, user_id)
    nxt = await redis.eval(_COMPLETE, 2, count_key, wait_key)
    if not nxt:
        return None
    if isinstance(nxt, bytes):
        nxt = nxt.decode()
    return json.loads(nxt)
