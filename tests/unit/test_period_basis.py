"""Способ показа периода: заголовок, формула, каскад и покрытие (§5.5.2)."""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal

from finance_analysis.domain.cover_metrics import adscr
from finance_analysis.domain.mapping import _by_basis
from finance_analysis.domain.metrics import coverage_ratio
from finance_analysis.domain.period_basis import classify_period_basis
from tests.unit.test_cover_metrics import _binding, _common, _quarters, _series
from tests.unit.test_row_selection import _assigned, _calendar, _row


def test_fact_row_without_ytd_or_ltm_is_period_including_period_tails():
    assert classify_period_basis(_row("a", "Выручка за год"), calendar=None, links=None, series=None) == ("period", "default")
    assert classify_period_basis(_row("a", "Выручка за кв."), calendar=None, links=None, series=None) == ("period", "default")
    assert classify_period_basis(_row("a", "Выручка за квартал"), calendar=None, links=None, series=None) == ("period", "default")
    assert classify_period_basis(_row("a", "Выручка за период"), calendar=None, links=None, series=None) == ("period", "default")


def test_ltm_comes_from_the_label_a_header_or_a_four_quarter_sum():
    assert classify_period_basis(_row("a", "EBITDA, LTM"), calendar=None, links=None, series=None)[0] == "ltm"
    assert classify_period_basis(_row("a", "EBITDA last 12 months"), calendar=None, links=None, series=None)[0] == "ltm"
    assert classify_period_basis(_row("a", "EBITDA за 12 месяцев"), calendar=None, links=None, series=None) == ("ltm", "label")
    headed = _row("a", "EBITDA", parent_label="за 12 месяцев")
    assert classify_period_basis(headed, calendar=None, links=None, series=None) == ("ltm", "header")
    label_wins = _row("a", "EBITDA, LTM", parent_label="нарастающим итогом")
    assert classify_period_basis(label_wins, calendar=None, links=None, series=None) == ("ltm", "label")
    periods = ["2024Q1", "2024Q2", "2024Q3", "2024Q4"]
    calendar = _quarter_calendar(periods)
    links = []
    for index, period in enumerate(periods):
        links.append(_formula_link(f"S!C{index}", "src", period, None, None))
        links.append(_formula_link("S!D4", "ltm", "2024Q4", "=SUM(C1:C4)", f"S!C{index}"))
    got = classify_period_basis(_row("ltm", "EBITDA"), calendar=calendar, links=links, series=None)
    assert got == ("ltm", "formula")


def test_ytd_comes_only_from_a_header_or_a_formula_that_resets_each_year():
    headed = _row("a", "Выручка", sheet="ОПиУ нарастающим итогом")
    assert classify_period_basis(headed, calendar=None, links=None, series=None) == ("ytd", "header")
    section = _row("a", "Выручка", label_path=["накопленным итогом"])
    assert classify_period_basis(section, calendar=None, links=None, series=None) == ("ytd", "header")
    series = {("ax", "1"): 10}
    calendar = {("ax", "1"): {"header_text": "с начала года", "grain": "quarter"}}
    assert classify_period_basis(_row("a", "Выручка"), calendar=calendar, links=None, series=series) == ("ytd", "header")
    periods = ["2024Q1", "2024Q2", "2024Q3", "2024Q4", "2025Q1", "2025Q2"]
    calendar = _quarter_calendar(periods)
    links = _running_links(reset=True)
    assert classify_period_basis(_row("r", "Выручка"), calendar=calendar, links=links, series=None) == ("ytd", "formula")
    continuous = _running_links(reset=False)
    assert classify_period_basis(_row("r", "Выручка"), calendar=calendar, links=continuous, series=None) == ("period", "default")


def test_a_series_that_only_grows_stays_period():
    growing = {("ax", str(index)): index + 1 for index in range(4)}
    assert classify_period_basis(_row("a", "Выручка"), calendar=_calendar({"a": growing}), links=None, series=growing) == (
        "period",
        "default",
    )


def test_period_and_unknown_beat_ytd_and_ltm_is_kept():
    rows = [
        _row("flow", "Interest"),
        _row("cum", "Interest", parent_label="нарастающим итогом"),
    ]
    got = _assigned(rows)
    assert got["flow"].is_primary and got["flow"].evidence["selection"] == "period_basis"
    assert got["flow"].evidence["period_basis"] == "period"
    assert got["cum"].evidence["period_basis"] == "ytd" and got["cum"].evidence["period_basis_source"] == "header"
    assert got["cum"].is_primary is False
    kept, ran = _by_basis([{"period_basis": "ltm"}, {"period_basis": "ytd"}])
    assert ran is False and len(kept) == 2
    kept, ran = _by_basis([{"period_basis": "unknown"}, {"period_basis": "ytd"}, {"period_basis": "ltm"}])
    assert ran is True and [row["period_basis"] for row in kept] == ["unknown", "ltm"]


def test_coverage_is_silent_when_the_month_gap_is_shorter_than_one_period():
    rows = [
        _row("full", "Interest"),
        _row("short", "Interest"),
    ]
    periods = {
        "full": {("ax", f"f{i}"): 1 for i in range(4)},
        "short": {("ax", f"s{i}"): 1 for i in range(4)},
    }
    calendar = _calendar(periods)
    start = calendar[("ax", "s3")]["period_start"]
    calendar[("ax", "s3")] = {**calendar[("ax", "s3")], "period_end": start + timedelta(days=27)}
    got = _assigned(rows, periods=periods, calendar=calendar)
    assert got["full"].status == "ambiguous" and got["short"].status == "ambiguous"


def test_ytd_is_decumulated_for_the_metric_and_not_dropped():
    periods = _quarters(2025, 4)
    for period in periods:
        period["calendar_year"] = period["period_start"].year
    facts = _series("c", periods, ["10", "30", "60", "100"]) + _series("d", periods, ["-10", "-10", "-10", "-10"])
    bindings = [
        _binding("cfads", "c", evidence_json=json.dumps({"period_basis": "ytd", "period_basis_source": "header"})),
        _binding("debt_service", "d"),
    ]
    result = coverage_ratio(metric="dscr", **_common(periods, facts, bindings))
    assert result["status"] == "succeeded"
    by_period = {row["period_id"]: row["value"] for row in result["rows"]}
    assert by_period[periods[1]["period_id"]] == Decimal("2.0000000000")
    untouched = [
        _binding("cfads", "c", evidence_json=json.dumps({"period_basis": "ytd", "period_basis_source": "shape"})),
        _binding("debt_service", "d"),
    ]
    raw = coverage_ratio(metric="dscr", **_common(periods, facts, untouched))
    raw_by = {row["period_id"]: row["value"] for row in raw["rows"]}
    assert raw_by[periods[1]["period_id"]] == Decimal("3.0000000000")


def test_ltm_row_is_taken_as_is_and_not_summed_over_four_quarters():
    periods = _quarters(2025, 4)
    for period in periods:
        period["calendar_year"] = period["period_start"].year
    facts = _series("c", periods, ["40", "40", "40", "40"]) + _series("d", periods, ["-10", "-10", "-10", "-10"])
    bindings = [
        _binding("cfads", "c", evidence_json=json.dumps({"period_basis": "ltm", "period_basis_source": "label"})),
        _binding("debt_service", "d"),
    ]
    result = adscr(**_common(periods, facts, bindings))
    computed = [row for row in result["rows"] if row["status"] == "computed"]
    assert computed
    assert computed[-1]["value"] == Decimal("1.0000000000")


def _quarter_calendar(periods: list[str]) -> dict:
    found = {}
    for index, period in enumerate(periods):
        year = int(period[:4])
        quarter = int(period[-1])
        start = date(year, 3 * (quarter - 1) + 1, 1)
        end_month = 3 * quarter
        if end_month == 12:
            end = date(year, 12, 31)
        else:
            end = date(year, end_month + 1, 1) - timedelta(days=1)
        found[("ax", period)] = {
            "grain": "quarter",
            "period_start": start,
            "period_end": end,
            "period_index": index,
            "calendar_year": year,
        }
    return found


def _formula_link(cell: str, row_key: str, period: str, formula: str | None, ref: str | None) -> dict:
    return {
        "cell": cell,
        "row_key": row_key,
        "period_id": period,
        "formula": formula,
        "formula_class": "sum" if formula and "SUM" in formula.upper() else "add",
        "ref_cell": ref,
    }


def _running_links(*, reset: bool) -> list[dict]:
    periods = ["2024Q1", "2024Q2", "2024Q3", "2024Q4", "2025Q1", "2025Q2"]
    cells = [f"S!A{index}" for index in range(1, 7)]
    links = [_formula_link(cells[0], "r", periods[0], "=B1", "S!B1")]
    for index in range(1, 6):
        if index == 4 and reset:
            links.append(_formula_link(cells[index], "r", periods[index], "=B5", "S!B5"))
            continue
        prior = cells[index - 1]
        links.append(_formula_link(cells[index], "r", periods[index], f"={prior}+B{index}", prior))
        links.append(_formula_link(cells[index], "r", periods[index], f"={prior}+B{index}", f"S!B{index}"))
    return links
