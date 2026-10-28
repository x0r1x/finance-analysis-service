"""Дедлайн запроса и таймаут стадии (§4.13.4). Без ввода-вывода."""

from __future__ import annotations

import time
from contextvars import ContextVar
from dataclasses import dataclass, field

RESERVE_SEC = 0.05


@dataclass(frozen=True)
class Deadline:
    at: float = field(default_factory=lambda: time.monotonic() + 3600)

    @classmethod
    def after_ms(cls, ms: float | None) -> Deadline:
        if ms is None or ms <= 0:
            return cls()
        return cls(time.monotonic() + ms / 1000)

    def remaining(self) -> float:
        return max(self.at - time.monotonic(), 0.0)

    def budget(self, stage_timeout: float) -> float | None:
        """min(таймаут стадии, остаток − резерв). None — остатка не хватает, стадию пропускаем."""

        left = self.remaining() - RESERVE_SEC
        if left <= 0:
            return None
        return min(stage_timeout, left)


_REQUEST: ContextVar[Deadline | None] = ContextVar("fas_request_deadline", default=None)


def bind_request_deadline(deadline: Deadline | None):
    return _REQUEST.set(deadline)


def reset_request_deadline(token) -> None:
    _REQUEST.reset(token)


def effective(default_ms: float) -> Deadline:
    """Дедлайн стадии: остаток дедлайна запроса (X-FAS-Deadline-Ms), но не дольше default_ms."""

    own = Deadline.after_ms(default_ms)
    request = _REQUEST.get()
    if request is None or request.at >= own.at:
        return own
    return request
