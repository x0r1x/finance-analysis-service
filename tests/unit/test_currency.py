"""Валюта строки: hints и единственная валюта fact-строк (§5.8)."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from finance_analysis import __version__
from finance_analysis.adapters.builder.acl import parse_context
from finance_analysis.adapters.storage.parquet_io import load_schema
from finance_analysis.application.project import project
from finance_analysis.domain.book import FAS_SCHEMA_VERSION, FAS_VERSION
from finance_analysis.domain.currency import resolve_currencies
from tests.books import BUILDER_ROOT, job_id


def _rows(alias: str) -> list[dict]:
    job = job_id(alias)
    context = json.loads((BUILDER_ROOT / job / "context.json").read_text())
    tables, _warnings = project(parse_context(context), model_id=job, build="0123456789abcdef")
    return tables["dim_row"]


def test_service_version_is_0_23():
    assert FAS_VERSION == "0.23.0"
    assert __version__ == "0.23.0"
    assert FAS_SCHEMA_VERSION == "1.1"


def test_dim_row_schema_has_currency_source():
    doc = load_schema("dim_row")
    names = [column["name"] for column in doc["columns"]]
    assert doc["version"] == "1.0"
    assert names[names.index("currency") + 1] == "currency_source"
    period = json.loads(Path("src/finance_analysis/adapters/storage/schemas/dim_period.json").read_text())
    assert period["version"] == "1.0"


def test_no_named_currency_stays_empty():
    assert resolve_currencies(
        [("fact", None, "money"), ("abstract", None, None), ("fact", "  ", "money")]
    ) == [
        (None, None),
        (None, None),
        (None, None),
    ]


def test_several_fact_currencies_do_not_fill_blanks():
    assert resolve_currencies(
        [
            ("fact", "EUR", "money"),
            ("fact", "USD", "money"),
            ("fact", None, "money"),
            ("abstract", "GBP", "money"),
        ]
    ) == [
        ("EUR", "hints"),
        ("USD", "hints"),
        (None, None),
        ("GBP", "hints"),
    ]


def test_book_currency_skips_flag_rate_and_ratio():
    assert resolve_currencies(
        [
            ("fact", "EUR", "money"),
            ("fact", None, "money"),
            ("fact", None, "price"),
            ("fact", None, "rate"),
            ("fact", None, "%"),
            ("fact", None, "x"),
            ("fact", None, "ratio"),
            ("fact", None, "count"),
            ("fact", None, None),
            ("flag", None, None),
            ("abstract", None, None),
            ("helper", None, "rate"),
            ("abstract", "USD", "money"),
        ]
    ) == [
        ("EUR", "hints"),
        ("EUR", "book_single"),
        ("EUR", "book_single"),
        (None, None),
        (None, None),
        (None, None),
        (None, None),
        (None, None),
        (None, None),
        (None, None),
        (None, None),
        (None, None),
        ("USD", "hints"),
    ]


def test_packt_currency_is_gbp():
    rows = _rows("packt")
    assert len(rows) == 131
    assert Counter((row["currency"], row["currency_source"]) for row in rows) == {
        ("GBP", "hints"): 77,
        (None, None): 54,
    }
    facts = [row for row in rows if row["kind"] == "fact"]
    assert Counter((row["currency"], row["currency_source"], row["unit"]) for row in facts) == {
        ("GBP", "hints", "money"): 77,
        (None, None, "rate"): 12,
        (None, None, "count"): 4,
        (None, None, "years"): 3,
        (None, None, None): 1,
    }


def test_rvi_fact_currency_is_eur_and_reference_list_stays_hints():
    rows = _rows("rvi")
    assert len(rows) == 459
    assert Counter((row["currency"], row["currency_source"]) for row in rows) == {
        ("EUR", "hints"): 230,
        (None, None): 227,
        ("USD", "hints"): 1,
        ("GBP", "hints"): 1,
    }
    facts = [row for row in rows if row["kind"] == "fact"]
    assert {row["currency"] for row in facts if row["currency"] is not None} == {"EUR"}
    assert all(row["currency_source"] != "book_single" for row in rows)
    usd = next(row for row in rows if row["label"] == "US Dollar")
    gbp = next(row for row in rows if row["label"] == "Pound Sterling")
    assert usd["kind"] != "fact"
    assert usd["currency"] == "USD" and usd["currency_source"] == "hints"
    assert gbp["kind"] != "fact"
    assert gbp["currency"] == "GBP" and gbp["currency_source"] == "hints"
