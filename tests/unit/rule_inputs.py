"""Входы правил для unit-тестов: строки, факты, связи, периоды и golden-книги."""

from __future__ import annotations

import json
from decimal import Decimal
from functools import lru_cache

from finance_analysis.adapters.builder.acl import (
    parse_context,
    parse_links,
    parse_summary,
)
from finance_analysis.application.project import project
from finance_analysis.application.rule_engine import load_rules, run_rules, select_rules
from finance_analysis.domain.audit import AuditInput, Finding
from finance_analysis.domain.book import with_links
from tests.books import BUILDER_ROOT, job_id

PERIODS = [
    {"axis_id": "S!r2", "period_id": "2024", "period_key_base": "2024", "period_marker": None},
    {"axis_id": "S!r2", "period_id": "2025", "period_key_base": "2025", "period_marker": None},
    {"axis_id": "S!r2", "period_id": "2026@план", "period_key_base": "2026", "period_marker": "план"},
]


def row(row_key: str, **extra) -> dict:
    sheet, row_num, _block = row_key.split("|")
    return {
        "row_key": row_key,
        "binding_key": f"bk-{sheet}-{row_num}",
        "sheet": sheet,
        "label": extra.pop("label", f"row {row_num}"),
        "has_formula": extra.pop("has_formula", True),
        "formula": extra.pop("formula", "=R[0]C[-1]+1"),
        "check_row": extra.pop("check_row", False),
        "formula_exceptions": extra.pop("formula_exceptions", []),
        **extra,
    }


def fact(row_key: str, cell: str, period: str, value: str | None, status: str = "cached", axis: str = "S!r2") -> dict:
    return {
        "row_key": row_key,
        "cell_id": cell,
        "axis_id": axis,
        "period_id": period,
        "value_raw": value,
        "value_dec": None if value is None else Decimal(value),
        "normalized_value": None if value is None else Decimal(value),
        "value_status": status,
    }


def link(cell: str, formula: str, row_key: str | None, period: str | None, refs: tuple[str, ...] = ("S!A1",)) -> list[dict]:
    return [
        {"cell": cell, "formula": formula, "formula_class": "same_period", "ref_cell": ref, "row_key": row_key, "period_id": period}
        for ref in refs
    ] or [{"cell": cell, "formula": formula, "formula_class": None, "ref_cell": None, "row_key": row_key, "period_id": period}]


def check(code: str, data: AuditInput) -> list[Finding]:
    return select_rules(load_rules(), [code])[0].check(data)


@lru_cache(maxsize=2)
def golden(alias: str) -> AuditInput:
    """Golden-книга builder → проекция и счётчики R1, как их видит аудит."""

    job = job_id(alias)
    folder = BUILDER_ROOT / job
    snapshot = with_links(
        parse_context(json.loads((folder / "context.json").read_text())),
        parse_links(json.loads((folder / "graph.json").read_text())),
    )
    summary = parse_summary(json.loads((folder / "summary.json").read_text()), etag='"summary-2:x"')
    tables, _warnings = project(snapshot, model_id=job, build="0123456789abcdef")
    rows = [dict(item, formula_exceptions=json.loads(item["formula_exceptions_json"])) for item in tables["dim_row"]]
    return AuditInput(
        rows=rows,
        periods=tables["dim_period"],
        facts=tables["fact_observation"],
        links=tables["graph_links"],
        counters=summary.counters,
    )


def golden_count(alias: str, code: str) -> int:
    return len(run_rules(select_rules(load_rules(), [code]), golden(alias)))
