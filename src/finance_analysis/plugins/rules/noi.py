"""Сверка чистого операционного дохода. Ячейка книги не переписывается."""

from __future__ import annotations

from dataclasses import dataclass

from finance_analysis.domain.audit import ROWS_LINKS, AuditInput, Finding, Rule
from finance_analysis.domain.noi_identity import reconcile

_METHOD = frozenset({"double_land", "double_reserve", "forbidden"})


@dataclass(frozen=True)
class NoiMismatch(Rule):
    def check(self, data: AuditInput) -> list[Finding]:
        return [
            self.finding(data, row_key=note.row_key, params=note.params)
            for note in reconcile(data)
            if note.tag == "mismatch"
        ]


@dataclass(frozen=True)
class NoiMethod(Rule):
    def check(self, data: AuditInput) -> list[Finding]:
        return [
            self.finding(data, row_key=note.row_key, params=note.params)
            for note in reconcile(data)
            if note.tag in _METHOD
        ]


NOI_MISMATCH = NoiMismatch(
    "noi_mismatch", "1", "quantitative", "medium", ("Минимущество 568-р IV.5",),
    "Чистый операционный доход не сходится со слагаемыми", ROWS_LINKS,
)
NOI_METHOD = NoiMethod(
    "noi_method", "1", "qualitative", "info", ("Минимущество 568-р IV.5",),
    "Состав чистого операционного дохода расходится с методикой", ROWS_LINKS,
    finding_kind="methodology",
)
