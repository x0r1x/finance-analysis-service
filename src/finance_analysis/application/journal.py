"""Журнал с номерами: put_if_absent, без пропусков (§4.5)."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from finance_analysis.application.keys import log_key
from finance_analysis.domain.book import Actor
from finance_analysis.domain.errors import AlreadyExists, BindingConflict, NotFound
from finance_analysis.domain.state import fold


class Journal:
    def __init__(self, store) -> None:
        self.store = store
        self._locks: dict[str, asyncio.Lock] = {}
        self._last: dict[str, int] = {}
        self._keys: dict[str, dict[str, int]] = {}
        self._seen: dict[str, bool] = {}

    def _lock(self, job_id: str) -> asyncio.Lock:
        lock = self._locks.get(job_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[job_id] = lock
        return lock

    async def last_seq(self, job_id: str) -> int:
        if not await self.store.stat(log_key(job_id, 1)):
            return 0
        low, high = 1, 1
        while await self.store.stat(log_key(job_id, high)):
            low = high
            high *= 2
            if high > 1_000_000:
                break
        found = low
        left, right = low, high
        while left <= right:
            mid = (left + right) // 2
            if await self.store.stat(log_key(job_id, mid)):
                found = mid
                left = mid + 1
            else:
                right = mid - 1
        return found

    async def _sync(self, job_id: str) -> None:
        last = await self.last_seq(job_id)
        start = 1 if not self._seen.get(job_id) else self._last.get(job_id, 0) + 1
        self._seen[job_id] = True
        bucket = self._keys.setdefault(job_id, {})
        for seq in range(start, last + 1):
            try:
                raw = await self.store.get(log_key(job_id, seq))
            except NotFound:
                continue
            event = json.loads(raw)
            target = event.get("target") or event.get("binding_key")
            if target:
                bucket[str(target)] = int(event["seq"])
        self._last[job_id] = last

    async def read_all(self, job_id: str) -> list[dict]:
        last = await self.last_seq(job_id)
        events = []
        for seq in range(1, last + 1):
            events.append(json.loads(await self.store.get(log_key(job_id, seq))))
        return events

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
    ) -> dict:
        async with self._lock(job_id):
            while True:
                await self._sync(job_id)
                actual = self._keys.get(job_id, {}).get(target)
                if actual != expected_seq:
                    current = None
                    if actual:
                        current = json.loads(await self.store.get(log_key(job_id, actual)))
                    raise BindingConflict(
                        "номер expected_seq устарел",
                        extra={"target": target, "actual_seq": actual, "current": current},
                    )
                seq = self._last.get(job_id, 0) + 1
                event = {
                    "seq": seq,
                    "type": event_type,
                    "target": target,
                    "binding_key": target,
                    "value": value,
                    "actor": {"user_id": actor.user_id, "client_id": actor.client_id},
                    "expected_seq": expected_seq,
                    "request_id": request_id,
                    "at_utc": (at_utc or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
                try:
                    await self.store.put_if_absent(
                        log_key(job_id, seq),
                        json.dumps(event, ensure_ascii=False).encode(),
                    )
                except AlreadyExists:
                    self._last[job_id] = 0
                    self._seen[job_id] = False
                    continue
                self._last[job_id] = seq
                self._keys.setdefault(job_id, {})[target] = seq
                return event

    async def folded(self, job_id: str) -> dict[str, dict]:
        return fold(await self.read_all(job_id))
