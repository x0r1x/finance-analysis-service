"""Локальные ожидания чужой модели со счетами эскроу. Файлов в репозитории нет.

Схема escrow: primary — development_escrow, либо этот тип лидирует и не ниже порога.
Схема ddy — вопрос unknown. Это не эскроу: тот же тип был бы ложным, гибрид
тоже требует метку development_escrow. Листы модели не три формы отчётности.
"""

from __future__ import annotations

from finance_analysis.domain.model_type import decision_ranking


def assert_variant(got, spec: dict, *, accept: float) -> None:
    scheme = spec.get("scheme")
    expect = spec.get("expect") if isinstance(spec.get("expect"), dict) else {}
    kind = expect.get("kind")
    if scheme == "escrow":
        _escrow(got, expect, kind, accept=accept)
        return
    if scheme == "ddy":
        _ddy(got, expect, kind, accept=accept)
        return
    raise AssertionError("scheme в .local.yaml: escrow или ddy")


def _escrow(got, expect: dict, kind, *, accept: float) -> None:
    ranked = decision_ranking(got, accept=accept)
    leader = ranked[0] if ranked else None
    if kind == "type":
        assert expect.get("primary") == "development_escrow"
        assert got.confident is True and got.primary == "development_escrow"
        assert got.scores["development_escrow"] >= accept
        return
    if kind == "candidate":
        assert leader is not None and leader.type_id == "development_escrow" and leader.score >= accept
        return
    raise AssertionError("escrow: в .local.yaml ожидается kind type или candidate")


def _ddy(got, expect: dict, kind, *, accept: float) -> None:
    assert kind == "question" and expect.get("reason") == "unknown", "ddy остаётся вопросом, не типом и не гибридом"
    assert got.confident is False and got.reason == "unknown"
    assert got.scores["development_escrow"] < accept
    assert "development_escrow" not in got.labels
