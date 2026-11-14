"""Сверка чистого операционного дохода. Ячейка книги не переписывается."""

from __future__ import annotations

from dataclasses import dataclass

from finance_analysis.domain.audit import ROWS_LINKS, AuditInput, Finding, Rule
from finance_analysis.domain.noi_identity import reconcile

_METHOD = frozenset({"double_land", "double_reserve", "forbidden"})
_COVERAGE = frozenset({"period_unchecked", "optional_omitted"})


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


@dataclass(frozen=True)
class NoiCoverage(Rule):
    def check(self, data: AuditInput) -> list[Finding]:
        return [
            self.finding(data, row_key=note.row_key, params=note.params)
            for note in reconcile(data)
            if note.tag in _COVERAGE
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
NOI_COVERAGE = NoiCoverage(
    "noi_coverage",
    "1",
    "omission",
    "info",
    ("Минимущество 568-р IV.5",),
    "Сверка чистого операционного дохода покрыла не все периоды",
    ROWS_LINKS,
    finding_kind="insufficient_data",
)
