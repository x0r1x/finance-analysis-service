"""Способ показа периода: заголовок, формула, каскад и покрытие (§5.5.2)."""

from __future__ import annotations

import inspect
import json
from datetime import date, timedelta
from decimal import Decimal

from finance_analysis.application.project import attach_graph_links
from finance_analysis.application.service import FasService
from finance_analysis.domain.cover_metrics import adscr, dscr_reductions
from finance_analysis.domain.mapping import _by_basis
from finance_analysis.domain.metrics import coverage_ratio
from finance_analysis.domain.period_basis import classify_period_basis, restate_series
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
    quarters = ["2024Q1", "2024Q2", "2024Q3", "2024Q4"]
    calendar = _quarter_calendar(quarters)
    calendar[("ax", "2024")] = {
        "grain": "year",
        "period_start": date(2024, 1, 1),
        "period_end": date(2024, 12, 31),
        "period_index": 4,
        "calendar_year": 2024,
    }
    links = []
    for index, period in enumerate(quarters):
        links.append(_formula_link(f"S!C{index}", "src", period, None, None))
    for index, period in enumerate(quarters):
        links.append(_formula_link("S!Y1", "flow", "2024", "=SUM(C1:C4)", f"S!C{index}"))
    series = {("ax", period): 10 * (index + 1) for index, period in enumerate(quarters)}
    series[("ax", "2024")] = 100
    assert classify_period_basis(_row("flow", "CFADS"), calendar=calendar, links=links, series=series) == ("period", "default")
    each = []
    for index, period in enumerate(quarters):
        each.append(_formula_link(f"S!L{index}", "ltm", period, "=SUM(C1:C4)", f"S!C{index}"))
        # Каждая колонка квартала ссылается на четыре квартала источника.
        for source in range(4):
            each.append(_formula_link(f"S!L{index}", "ltm", period, "=SUM(C1:C4)", f"S!C{source}"))
    assert classify_period_basis(
        _row("ltm", "EBITDA"), calendar=calendar, links=links + each, series={("ax", period): 40 for period in quarters}
    ) == ("period", "default")


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
    series = {("ax", period): 1 for period in periods}
    links = _running_links(reset=True)
    assert classify_period_basis(_row("r", "Выручка"), calendar=calendar, links=links, series=series) == ("ytd", "formula")
    continuous = _running_links(reset=False)
    assert classify_period_basis(_row("r", "Выручка"), calendar=calendar, links=continuous, series=series) == ("period", "default")


def test_one_formula_cell_does_not_retag_the_row_and_a_balance_stays_period():
    periods = ["2024Q1", "2024Q2", "2024Q3", "2024Q4"]
    calendar = _quarter_calendar(periods)
    series = {("ax", period): value for period, value in zip(periods, (10, 20, 30, 40), strict=True)}
    links = [
        _formula_link("S!A1", "r", "2024Q1", "=B1", "S!B1"),
        _formula_link("S!A2", "r", "2024Q2", "=B2", "S!B2"),
        _formula_link("S!A3", "r", "2024Q3", "=B3", "S!B3"),
        _formula_link("S!A4", "r", "2024Q4", "=A3+B4", "S!A3"),
        _formula_link("S!A4", "r", "2024Q4", "=A3+B4", "S!B4"),
    ]
    assert classify_period_basis(_row("r", "Interest"), calendar=calendar, links=links, series=series) == ("period", "default")
    copied = []
    for index, period in enumerate(periods):
        if index == 0:
            copied.append(_formula_link(f"S!C{index}", "bal", period, "=Open", "S!Open"))
            continue
        copied.append(_formula_link(f"S!C{index}", "bal", period, f"=C{index - 1}", f"S!C{index - 1}"))
    balance = {("ax", period): value for period, value in zip(periods, (100, 100, 110, 110), strict=True)}
    assert classify_period_basis(_row("bal", "Debt"), calendar=calendar, links=copied, series=balance) == ("period", "default")
    headed = classify_period_basis(
        _row("bal", "Debt", parent_label="нарастающим итогом"), calendar=calendar, links=copied, series=balance
    )
    assert headed == ("ytd", "header")


def test_a_typed_opening_cell_is_visible_to_the_running_total():
    periods = ["2024H1", "2024H2", "2025H1", "2025H2"]
    calendar = {}
    for index, period in enumerate(periods):
        year = 2024 + index // 2
        start = date(year, 1, 1) if index % 2 == 0 else date(year, 7, 1)
        end = date(year, 6, 30) if index % 2 == 0 else date(year, 12, 31)
        calendar[("ax", period)] = {
            "grain": "half",
            "period_start": start,
            "period_end": end,
            "period_index": index,
            "calendar_year": year,
        }
    series = {("ax", period): 1 for period in periods}
    links = [
        _formula_link("S!C1", "r", "2024H2", "=B1+5", "S!B1"),
        _formula_link("S!E1", "r", "2025H2", "=D1+5", "S!D1"),
    ]
    facts = [
        {"cell_id": "S!B1", "row_key": "r", "period_id": "2024H1"},
        {"cell_id": "S!D1", "row_key": "r", "period_id": "2025H1"},
    ]
    assert classify_period_basis(_row("r", "Выручка"), calendar=calendar, links=links, series=series) == ("period", "default")
    assert classify_period_basis(_row("r", "Выручка"), calendar=calendar, links=links, series=series, facts=facts) == (
        "ytd",
        "formula",
    )


def test_a_later_derive_keeps_formula_links_on_the_projection():
    periods = ["2024Q1", "2024Q2", "2024Q3", "2024Q4"]
    calendar = _quarter_calendar(periods)
    series = {("ax", period): 1 for period in periods}
    links = _running_links(reset=True)
    bare = {"dim_period": []}
    assert "graph_links" not in bare
    projected = attach_graph_links(bare, links)
    assert projected["graph_links"] == links
    assert classify_period_basis(_row("r", "Выручка"), calendar=calendar, links=projected["graph_links"], series=series) == (
        "ytd",
        "formula",
    )
    assert classify_period_basis(_row("r", "Выручка"), calendar=calendar, links=bare.get("graph_links"), series=series) == (
        "period",
        "default",
    )
    assert "attach_graph_links" in inspect.getsource(FasService.derive_for_build)
    assert "attach_graph_links" in inspect.getsource(FasService._fold_derived)


def test_ltm_formula_slides_across_years_and_a_reset_or_cross_row_does_not():
    periods = [f"{year}Q{quarter}" for year in (2024, 2025) for quarter in range(1, 5)]
    calendar = _quarter_calendar(periods)
    cells = {period: f"S!C{index}" for index, period in enumerate(periods)}
    source = [_formula_link(cells[period], "src", period, None, None) for period in periods]
    sliding = []
    shown = periods[3:]
    for index, period in enumerate(periods):
        if index < 3:
            continue
        for offset in range(index - 3, index + 1):
            sliding.append(_formula_link(f"S!L{index}", "ltm", period, "=SUM(window)", cells[periods[offset]]))
    series = {("ax", period): 40 for period in shown}
    assert classify_period_basis(_row("ltm", "EBITDA"), calendar=calendar, links=source + sliding, series=series) == (
        "ltm",
        "formula",
    )
    reset = []
    for year in (2024, 2025):
        for quarter in range(1, 5):
            reset.append(
                _formula_link(f"S!Y{year}", "flow", f"{year}Q4", "=SUM(year)", cells[f"{year}Q{quarter}"])
            )
    assert classify_period_basis(
        _row("flow", "Проценты"),
        calendar=calendar,
        links=source + reset,
        series={("ax", "2024Q4"): 100, ("ax", "2025Q4"): 80},
    ) == ("ytd", "formula")
    same_period = [
        _formula_link("S!E1", "ebitda", "2024Q1", "=OP+DA", "S!O1"),
        _formula_link("S!E1", "ebitda", "2024Q1", "=OP+DA", "S!D1"),
        _formula_link("S!E2", "ebitda", "2024Q2", "=OP+DA", "S!O2"),
        _formula_link("S!E2", "ebitda", "2024Q2", "=OP+DA", "S!D2"),
    ]
    located = [
        _formula_link("S!O1", "op", "2024Q1", None, None),
        _formula_link("S!D1", "da", "2024Q1", None, None),
        _formula_link("S!O2", "op", "2024Q2", None, None),
        _formula_link("S!D2", "da", "2024Q2", None, None),
    ]
    quarterly = {("ax", "2024Q1"): 10, ("ax", "2024Q2"): 12}
    assert classify_period_basis(
        _row("ebitda", "EBITDA"), calendar=calendar, links=same_period + located, series=quarterly
    ) == ("period", "default")
    tailed = [
        _formula_link(link["cell"].replace("S!L", "S!T"), "tail", link["period_id"], link["formula"], link["ref_cell"])
        for link in sliding
    ]
    assert classify_period_basis(
        _row("tail", "Расчет EBITDA за квартал"), calendar=calendar, links=source + tailed, series=series
    ) == ("period", "default")


def test_a_monthly_formula_is_ltm_only_as_a_sliding_twelve_month_window():
    periods = []
    calendar = {}
    for index in range(14):
        year = 2024 + index // 12
        month = index % 12 + 1
        period = f"{year}-{month:02d}"
        periods.append(period)
        start = date(year, month, 1)
        end = date(year, 12, 31) if month == 12 else date(year, month + 1, 1) - timedelta(days=1)
        calendar[("ax", period)] = {
            "grain": "month",
            "period_start": start,
            "period_end": end,
            "period_index": index,
            "calendar_year": year,
        }
    cells = {period: f"S!M{index}" for index, period in enumerate(periods)}
    source = [_formula_link(cells[period], "src", period, None, None) for period in periods]
    links = []
    for index, period in enumerate(periods):
        if index < 11:
            continue
        for offset in range(index - 11, index + 1):
            links.append(_formula_link(f"S!L{index}", "ltm", period, "=SUM(window)", cells[periods[offset]]))
    series = {("ax", period): 1 for period in periods[11:]}
    assert classify_period_basis(_row("ltm", "EBITDA"), calendar=calendar, links=source + links, series=series) == (
        "ltm",
        "formula",
    )


def test_a_ytd_header_wins_over_a_formula_that_looks_like_four_quarters():
    periods = ["2024Q4", "2025Q4"]
    calendar = _quarter_calendar(["2024Q1", "2024Q2", "2024Q3", "2024Q4", "2025Q1", "2025Q2", "2025Q3", "2025Q4"])
    links = []
    for year in (2024, 2025):
        for quarter in range(1, 5):
            links.append(_formula_link(f"S!S{year}{quarter}", "src", f"{year}Q{quarter}", None, None))
        for quarter in range(1, 5):
            links.append(
                _formula_link(f"S!Y{year}", "flow", f"{year}Q4", "=SUM(S1:S4)", f"S!S{year}{quarter}")
            )
    series = {("ax", period): 100 for period in periods}
    row = _row("flow", "Проценты", parent_label="накопленным итогом за год")
    assert classify_period_basis(row, calendar=calendar, links=links, series=series) == ("ytd", "header")
    for period in periods:
        calendar[("ax", period)] = {**calendar[("ax", period)], "header_text": "накопленным итогом за год"}
    agreed = _row("flow", "Проценты")
    assert classify_period_basis(agreed, calendar=calendar, links=links, series=series) == ("ytd", "header")


def test_a_column_header_applies_only_when_every_numeric_column_agrees():
    periods = ["2024Q1", "2024Q2", "2024Q3", "2024Q4"]
    series = {("ax", period): 10 * (index + 1) for index, period in enumerate(periods)}
    calendar = _quarter_calendar(periods)
    calendar[("ax", "2024Q4")] = {**calendar[("ax", "2024Q4")], "header_text": "Итого с начала года проекта"}
    assert classify_period_basis(_row("a", "Interest"), calendar=calendar, links=None, series=series) == ("period", "default")
    calendar[("ax", "2024Q4")] = {**calendar[("ax", "2024Q4")], "header_text": "LTM"}
    assert classify_period_basis(_row("a", "Interest"), calendar=calendar, links=None, series=series) == ("period", "default")
    for period in periods:
        calendar[("ax", period)] = {**calendar[("ax", period)], "header_text": "LTM"}
    assert classify_period_basis(_row("a", "Interest"), calendar=calendar, links=None, series=series) == ("ltm", "header")
    assert classify_period_basis(_row("a", "Interest", sheet="нарастающим итогом"), calendar=None, links=None, series=None) == (
        "ytd",
        "header",
    )


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


def test_a_missing_quarter_is_not_subtracted_into_the_next_one():
    periods = _quarters(2025, 4)
    for period in periods:
        period["calendar_year"] = period["period_start"].year
    kept = [periods[0], periods[2], periods[3]]
    facts = _series("c", kept, ["10", "60", "100"]) + _series("d", periods, ["-10", "-10", "-10", "-10"])
    binding = {"evidence": {"period_basis": "ytd", "period_basis_source": "header"}}
    totals = {
        (periods[0]["axis_id"], periods[0]["period_id"]): Decimal(10),
        (periods[2]["axis_id"], periods[2]["period_id"]): Decimal(60),
        (periods[3]["axis_id"], periods[3]["period_id"]): Decimal(100),
    }
    restated = restate_series(totals, binding, periods, {})
    assert (periods[2]["axis_id"], periods[2]["period_id"]) not in restated
    assert restated[(periods[0]["axis_id"], periods[0]["period_id"])] == Decimal(10)
    assert restated[(periods[3]["axis_id"], periods[3]["period_id"])] == Decimal(40)
    bindings = [
        _binding("cfads", "c", evidence_json=json.dumps({"period_basis": "ytd", "period_basis_source": "header"})),
        _binding("debt_service", "d"),
    ]
    result = coverage_ratio(metric="dscr", **_common(periods, facts, bindings))
    by_period = {row["period_id"]: row for row in result["rows"]}
    assert periods[2]["period_id"] not in by_period
    assert by_period[periods[3]["period_id"]]["value"] == Decimal("4.0000000000")


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


def test_dscr_avg_ratio_of_sums_does_not_add_an_ltm_row():
    periods = _quarters(2025, 4)
    facts = _series("c", periods, ["40", "40", "40", "40"]) + _series("d", periods, ["-10", "-10", "-10", "-10"])
    bindings = [
        _binding("cfads", "c", evidence_json=json.dumps({"period_basis": "ltm", "period_basis_source": "label"})),
        _binding("debt_service", "d"),
    ]
    result = dscr_reductions("dscr_avg", **_common(periods, facts, bindings))
    ratio = next(row for row in result["rows"] if row.get("variant") == "ratio_of_sums")
    assert ratio["value"] == Decimal("1.0000000000")


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
