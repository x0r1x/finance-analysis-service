"""Журнал с номерами: put_if_absent, без пропусков (§4.5)."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from finance_analysis.application.keys import log_key
from finance_analysis.domain.book import Actor
from finance_analysis.domain.errors import AlreadyExists, BindingConflict, NotFound
from finance_analysis.domain.mapping import operating_profit_stamp
from finance_analysis.domain.state import fold


def _slot(event_type: str, target: str) -> str:
    return f"{event_type}\x1f{target}"


def _same_meaning(found: dict, meaning: str | None) -> bool:
    if meaning is None:
        return True
    return found.get("meaning") == meaning


class Journal:
    def __init__(self, store) -> None:
        self.store = store
        self._locks: dict[str, asyncio.Lock] = {}
        self._last: dict[str, int] = {}
        self._keys: dict[str, dict[str, int]] = {}
        self._seen: dict[str, bool] = {}
        self._values: dict[str, dict[tuple[str, str, str], dict]] = {}
        self._requests: dict[str, dict[str, dict]] = {}

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
                bucket[_slot(event.get("type") or "", str(target))] = int(event["seq"])
            self._remember(job_id, event)
        self._last[job_id] = last

    def _remember(self, job_id: str, event: dict) -> None:
        target = event.get("target") or event.get("binding_key")
        event_type = event.get("type")
        if target and event_type:
            canon = json.dumps(event.get("value"), ensure_ascii=False, sort_keys=True, default=str)
            self._values.setdefault(job_id, {})[(str(target), str(event_type), canon)] = event
        request_id = event.get("request_id")
        if request_id:
            self._requests.setdefault(job_id, {})[str(request_id)] = event

    def _duplicate_locked(
        self,
        job_id: str,
        *,
        target: str,
        event_type: str,
        value,
        request_id: str,
        meaning: str | None = None,
    ) -> dict | None:
        if request_id and request_id in self._requests.get(job_id, {}):
            found = self._requests[job_id][request_id]
            if _same_meaning(found, meaning):
                return found
        canon = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        found = self._values.get(job_id, {}).get((target, event_type, canon))
        if found is None:
            return None
        if self._keys.get(job_id, {}).get(_slot(event_type, target)) != found.get("seq"):
            return None
        if not _same_meaning(found, meaning):
            return None
        return found

    async def matching(
        self,
        job_id: str,
        *,
        target: str,
        event_type: str,
        value,
        request_id: str,
    ) -> dict | None:
        async with self._lock(job_id):
            await self._sync(job_id)
            return self._duplicate_locked(
                job_id,
                target=target,
                event_type=event_type,
                value=value,
                request_id=request_id,
                meaning=operating_profit_stamp(event_type, value),
            )

    async def read_all(self, job_id: str) -> list[dict]:
        last = await self.last_seq(job_id)
        events = []
        for seq in range(1, last + 1):
            events.append(json.loads(await self.store.get(log_key(job_id, seq))))
        return events

    async def commit(
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
        binding_key: str | None = None,
        supersedes: dict | None = None,
        question_id: str | None = None,
    ) -> tuple[dict, bool]:
        """Проверка дубля и запись под одним замком. Второй элемент — duplicate."""

        async with self._lock(job_id):
            while True:
                await self._sync(job_id)
                meaning = operating_profit_stamp(event_type, value)
                existing = self._duplicate_locked(
                    job_id,
                    target=target,
                    event_type=event_type,
                    value=value,
                    request_id=request_id,
                    meaning=meaning,
                )
                if existing is not None:
                    return existing, True
                try:
                    event = await self._write_locked(
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
                        meaning=meaning,
                    )
                except AlreadyExists:
                    self._last[job_id] = 0
                    self._seen[job_id] = False
                    continue
                return event, False

    async def _write_locked(
        self,
        job_id: str,
        *,
        target: str,
        event_type: str,
        value,
        actor: Actor,
        expected_seq: int | None,
        request_id: str,
        at_utc: datetime | None,
        binding_key: str | None = None,
        supersedes: dict | None = None,
        question_id: str | None = None,
        meaning: str | None = None,
    ) -> dict:
        actual = self._keys.get(job_id, {}).get(_slot(event_type, target))
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
            "binding_key": binding_key or target,
            "value": value,
            "actor": {"user_id": actor.user_id, "client_id": actor.client_id},
            "expected_seq": expected_seq,
            "request_id": request_id,
            "at_utc": (at_utc or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        if supersedes is not None:
            event["supersedes"] = supersedes
        if question_id:
            event["question_id"] = question_id
        if meaning:
            event["meaning"] = meaning
        await self.store.put_if_absent(
            log_key(job_id, seq),
            json.dumps(event, ensure_ascii=False).encode(),
        )
        self._last[job_id] = seq
        self._keys.setdefault(job_id, {})[_slot(event_type, target)] = seq
        self._remember(job_id, event)
        return event

    async def folded(self, job_id: str) -> dict[str, dict]:
        return fold(await self.read_all(job_id))
