"""Счётчики, которые увеличивает сценарий, а не HTTP-адаптер."""

from prometheus_client import Counter

BUILDER_INCONSISTENT = Counter(
    "fas_builder_inconsistent_total",
    "Публикации builder, не прошедшие проверку согласованности",
)
