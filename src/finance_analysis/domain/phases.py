"""Словарь фаз периода (§5.4, §5.12).

Имена флагов таймлайна сюда не входят и не толкуются.
"""

from __future__ import annotations

from finance_analysis.domain.validation.semantics import Verdict

# Порядок словаря: строительство, затем эксплуатация.
PHASES = ("construction", "operation")


def phase_target(axis_id: str, period_key_base: str) -> str:
    return f"{axis_id}+{period_key_base}"


def split_phase_target(target: str) -> tuple[str, str] | None:
    axis_id, sep, base = target.partition("+")
    if not sep or not axis_id or not base:
        return None
    return axis_id, base


def check_phase_value(value) -> Verdict:
    if not isinstance(value, str) or value not in PHASES:
        return Verdict(False, "schema_invalid", "фаза вне словаря")
    return Verdict(True)


def check_phase_order(assignments: list[tuple[int, str]]) -> Verdict:
    """По index фаза оси не возвращается назад: construction → operation."""

    rank = {name: index for index, name in enumerate(PHASES)}
    last = -1
    for _index, phase in sorted(assignments, key=lambda item: item[0]):
        if phase not in rank:
            return Verdict(False, "schema_invalid", "фаза вне словаря")
        current = rank[phase]
        if current < last:
            return Verdict(False, "schema_invalid", "порядок фаз оси нарушен")
        last = current
    return Verdict(True)
