"""Даты, @marker и ACL builder."""

from __future__ import annotations

import json
from datetime import date

import pytest

from finance_analysis.adapters.builder.acl import parse_context, parse_summary
from finance_analysis.application.project import project
from finance_analysis.domain.errors import UnsupportedBuilderShape
from finance_analysis.domain.periods import marker_class, resolve_period_dates, split_period_key
from tests.conftest import GOLDEN, JOB


def test_marker_does_not_move_dates():
    base, marker = split_period_key("2025@факт")
    assert base == "2025"
    assert marker == "факт"
    assert marker_class(marker) == "actual"
    start, end, source = resolve_period_dates(base, calendar_year=2025, start_date=None, end_date=None, previous_end=None)
    assert (start, end, source) == (date(2025, 1, 1), date(2025, 12, 31), "key")
    anchor_start, anchor_end, anchor_source = resolve_period_dates(
        "Y1", calendar_year=2030, start_date=None, end_date=None, previous_end=None
    )
    assert anchor_source == "anchor"
    assert anchor_start == date(2030, 1, 1)
    assert anchor_end == date(2030, 12, 31)
    assert marker_class("план") == "plan"
    assert marker_class("прогноз") == "estimate"
    assert marker_class("custom") == "other"


def test_acl_golden_and_missing_field():
    folder = GOLDEN / JOB
    summary = json.loads((folder / "summary.json").read_text())
    parsed = parse_summary(summary, etag=summary["etag"], job_id=JOB)
    assert parsed.content_sha256.startswith("b")
    context = json.loads((folder / "context.json").read_text())
    snapshot = parse_context(context)
    tables = project(snapshot, model_id=JOB, build="0123456789abcdef")
    periods = {row["period_id"]: row for row in tables["dim_period"]}
    assert periods["2024"]["date_source"] == "key"
    assert periods["2024"]["period_start"] == date(2024, 1, 1)
    assert periods["2025@факт"]["period_marker"] == "факт"
    assert periods["2025@факт"]["marker_class"] == "actual"
    assert periods["2025@факт"]["period_start"] == date(2025, 1, 1)
    facts = {(row["row_key"], row["period_id"]): row for row in tables["fact_observation"]}
    assert facts[("rev", "2024")]["cell_id"] == "Model!H10"
    assert str(facts[("rev", "2024")]["value_raw"]) == "100.5"
    broken = json.loads((folder / "context.json").read_text())
    del broken["axes"]["years"]["periods"][0]["period_key"]
    with pytest.raises(UnsupportedBuilderShape):
        parse_context(broken)


def test_builder_dates_win():
    start, end, source = resolve_period_dates(
        "2024",
        calendar_year=2024,
        start_date=date(2024, 2, 1),
        end_date=date(2024, 2, 28),
        previous_end=None,
    )
    assert source == "builder"
    assert start == date(2024, 2, 1)
    assert end == date(2024, 2, 28)
