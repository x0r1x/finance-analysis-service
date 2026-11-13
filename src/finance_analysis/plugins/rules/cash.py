"""Сверка остатка денежных средств. Ячейка книги не переписывается."""

from __future__ import annotations

from dataclasses import dataclass

from finance_analysis.domain.audit import ROWS, ROWS_LINKS, AuditInput, Finding, Rule
from finance_analysis.domain.cash_rollforward import CashNote, check_cash, statement_tie


def _notes(rule: Rule, data: AuditInput, notes: list[CashNote]) -> list[Finding]:
    return [
        rule.finding(
            data,
            row_key=note.row_key,
            axis_id=note.axis_id or None,
            period_id=note.period_id or None,
            params=note.params,
        )
        for note in notes
    ]


@dataclass(frozen=True)
class CashRollforwardBreak(Rule):
    def check(self, data: AuditInput) -> list[Finding]:
        return _notes(self, data, [note for note in check_cash(data) if note.tag == "break"])


@dataclass(frozen=True)
class CashStatementTie(Rule):
    def check(self, data: AuditInput) -> list[Finding]:
        return _notes(self, data, statement_tie(data))


CASH_ROLLFORWARD_BREAK = CashRollforwardBreak(
    "cash_rollforward_break",
    "1",
    "quantitative",
    "high",
    ("ПБУ 23/2011 п. 6", "ФНС 31.07.2019 № БА-4-1/15052@"),
    "Остаток денежных средств не сходится с движением",
    ROWS_LINKS,
    2,
    finding_kind="error",
)
CASH_STATEMENT_TIE = CashStatementTie(
    "cash_statement_tie",
    "1",
    "quantitative",
    "medium",
    ("ПБУ 23/2011 п. 22", "IAS 7.45"),
    "Остаток отчёта и строка баланса различаются",
    ROWS,
    2,
    finding_kind="warning",
)
