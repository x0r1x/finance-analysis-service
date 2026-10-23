"""Полный jitter повтора задачи (§4.13.5)."""

from __future__ import annotations

import random

from taskiq.middlewares import SmartRetryMiddleware


def full_jitter(base: float, max_delay: float, attempt: int) -> float:
    power = max(attempt - 1, 0)
    cap = min(max_delay, base * (2**power))
    if cap <= 0:
        return 0.0
    return random.random() * cap


class FasRetryMiddleware(SmartRetryMiddleware):
    """Повтор через RedisScheduleSource. Потолок запусков — TASK_RETRY_MAX + 1.

    В taskiq 0.13 счётчик в on_error начинается с 1 и сравнивается через `< max`.
    Чтобы начальный запуск и TASK_RETRY_MAX повторов дали три выполнения при
    TASK_RETRY_MAX = 2, в библиотеку передаётся `default_retry_count = TASK_RETRY_MAX + 1`.
    Исчерпание закрывает операцию и пишет `fas:dlq` (вызывающий задаёт `on_exhausted`).
    """

    def __init__(self, *, settings, schedule_source, on_exhausted=None) -> None:
        super().__init__(
            default_retry_count=settings.task_retry_max + 1,
            default_retry_label=True,
            schedule_source=schedule_source,
            use_delay_exponent=False,
            use_jitter=False,
        )
        self._settings = settings
        self._on_exhausted = on_exhausted

    def make_delay(self, message, retries: int) -> float:
        return full_jitter(
            self._settings.task_retry_base_sec,
            self._settings.task_retry_max_delay_sec,
            retries,
        )

    async def on_error(self, message, result, exception) -> None:
        await super().on_error(message, result, exception)
        retries = int(message.labels.get("_retries", 0)) + 1
        limit = int(message.labels.get("max_retries", self.default_retry_count))
        if retries >= limit and self._on_exhausted is not None:
            await self._on_exhausted(message, exception)
