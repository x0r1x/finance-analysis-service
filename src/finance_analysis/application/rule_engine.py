"""Реестр правил и прогон аудита (§6.1, §8 Strategy + Registry).

Встроенные правила — `plugins/rules`. Сторонние пакеты добавляют
свои через entry points группы `finance_analysis.rules`: объект — правило
или кортеж правил. Код правила уникален, встроенное правило не заменяется.
"""

from __future__ import annotations

from importlib.metadata import entry_points

from finance_analysis.domain.audit import (
    AuditInput,
    Finding,
    Rule,
    RuleRunResult,
    severity_rank,
)
from finance_analysis.domain.errors import InvalidArgument
from finance_analysis.plugins.rules import RULES

ENTRY_GROUP = "finance_analysis.rules"


def _plugin_rules() -> list[Rule]:
    found: list[Rule] = []
    for point in entry_points(group=ENTRY_GROUP):
        loaded = point.load()
        items = loaded if isinstance(loaded, (tuple, list)) else (loaded,)
        found.extend(item for item in items if isinstance(item, Rule))
    return found


def load_rules() -> dict[str, Rule]:
    registry: dict[str, Rule] = {}
    for rule in (*RULES, *_plugin_rules()):
        registry.setdefault(rule.code, rule)
    return registry


def select_rules(registry: dict[str, Rule], codes: list | None) -> list[Rule]:
    if codes is None:
        return list(registry.values())
    if not isinstance(codes, list) or not all(isinstance(code, str) for code in codes):
        raise InvalidArgument("rules должен быть списком кодов")
    unknown = sorted(set(codes) - set(registry))
    if unknown:
        raise InvalidArgument("неизвестные правила", extra={"rules": unknown, "known": sorted(registry)})
    return [registry[code] for code in dict.fromkeys(codes)]


def requirements(rules: list[Rule]) -> frozenset[str]:
    """Что грузить для прогона: планировщик читает только нужные наборы."""

    needed: set[str] = set()
    for rule in rules:
        needed |= rule.requires
    return frozenset(needed)


def execute_rules(rules: list[Rule], data: AuditInput) -> RuleRunResult:
    """Прогон. Находки читаются из поля, улика — отдельно.

    Источник следа — `rule:<код>`. Правило без расчёта улику не возвращает.
    Несколько доказательств одного правила остаются несколькими следами.
    """

    by_print: dict[str, Finding] = {}
    evidence = []
    sources = []
    for rule in rules:
        outcome = rule.run(data)
        for finding in outcome.findings:
            by_print.setdefault(finding.fingerprint, finding)
        for item in outcome.calculation_evidence:
            evidence.append(item)
            sources.append(f"rule:{rule.code}")
    findings = tuple(
        sorted(by_print.values(), key=lambda item: (-severity_rank(item.severity), item.code, item.fingerprint))
    )
    return RuleRunResult(findings, tuple(evidence), tuple(sources))
