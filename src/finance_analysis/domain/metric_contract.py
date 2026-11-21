"""Реестр реализаций формул. Лестница расчёта его не читает."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


class DuplicateImplementation(ValueError):
    """Повтор ключа (metric_id, formula_id)."""


@dataclass(frozen=True, slots=True)
class Implementation:
    metric_id: str
    formula_id: str
    version: str
    function: Callable[..., object]
    inputs: tuple[str, ...]


REGISTRY: dict[tuple[str, str], Implementation] = {}


def implements(
    metric_id: str,
    formula_id: str,
    *,
    version: str = "",
    inputs: tuple[str, ...] = (),
):
    """Помечает функцию реализации. Повтор того же ключа — ошибка."""

    def decorate(function: Callable[..., object]) -> Callable[..., object]:
        key = (metric_id, formula_id)
        if key in REGISTRY:
            raise DuplicateImplementation(f"реализация уже зарегистрирована: {metric_id} {formula_id}")
        REGISTRY[key] = Implementation(metric_id, formula_id, version, function, tuple(inputs))
        return function

    return decorate
