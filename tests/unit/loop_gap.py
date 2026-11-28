"""Зазор между пробуждениями цикла.

Медленный callback asyncio пишет в логгер `asyncio`, а не в exception handler.
"""

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

TICK = 0.02
LIMIT = 0.1


@asynccontextmanager
async def loop_gaps() -> AsyncIterator[list[float]]:
    gaps: list[float] = []
    stop = asyncio.Event()

    async def pulse() -> None:
        last = time.monotonic()
        while not stop.is_set():
            await asyncio.sleep(TICK)
            now = time.monotonic()
            gaps.append(now - last)
            last = now

    beat = asyncio.create_task(pulse())
    await asyncio.sleep(0)
    try:
        yield gaps
    finally:
        stop.set()
        await beat
