"""Форма `SummaryDocument` (`summary-2`) для проверки фикстур.

Модель живёт в тестах FAS и не импортирует `finance-context-builder`.
Лишние поля запрещены: так `cell_ids` у подсказки и сырой список членов цикла
не проходят проверку.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IdCount(_Strict):
    count: int
    ids: list[str]


class CycleSummary(_Strict):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    # В JSON поле называется `class`.
    cycle_class: Literal["iterative_ok", "unexpected"] = Field(alias="class")
    members: int


class CircularityHint(_Strict):
    sheet: str
    row: int
    label: str


class SummaryDocument(_Strict):
    schema_version: Literal["summary-2"]
    context_schema_version: str
    graph_schema_version: str
    source_filename: str | None
    content_sha256: str | None
    status: str | None
    stage: str | None
    sheets: list[str]
    formula_count: int
    missing_cached_values: int
    unparsed_formulas: int
    iterate: bool
    defined_name_count: int
    nodes: int
    edges: int
    kinds: dict[str, int]
    unresolved: IdCount
    external: IdCount
    dangling: IdCount
    dynamic: IdCount
    truncated: IdCount
    dangling_classes: dict[str, int]
    cycles: list[CycleSummary]
    circularity_hints: list[CircularityHint]
    warnings: list[str]
