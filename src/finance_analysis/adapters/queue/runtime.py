"""Состояние процесса worker-а. Задаёт worker перед listen."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WorkerRuntime:
    settings: object
    redis: object
    store: object
    schedule: object
    broker: object
    locks: object


RUNTIME: WorkerRuntime | None = None
