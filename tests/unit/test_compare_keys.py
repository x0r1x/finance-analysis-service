"""Ключи периодов `…:compare`: строки метрик стыкуются по шкале, а не по номеру оси на листе."""

from decimal import Decimal

from finance_analysis.application.compare import Comparisons


def _period(axis: str, timeline: str, period_id: str, index: int) -> dict:
    return {"axis_id": axis, "timeline_id": timeline, "period_id": period_id, "period_index": index}


def _dscr(axis: str, period_id: str, value: str) -> dict:
    return {"metric": "dscr", "axis_id": axis, "period_id": period_id, "value": Decimal(value), "status": "computed"}


def test_new_axis_on_the_same_sheet_keeps_metric_rows_matched():
    old = [_period("Debt!r10", "T-debt", year, index) for index, year in enumerate(("2025", "2026"))]
    added = [_period("Debt!r4", "T-ops", year, index) for index, year in enumerate(("2025", "2026"))]
    base = {"periods": old, "rows": [_dscr("Debt!r10", "2025", "1.3"), _dscr("Debt!r10", "2026", "1.4")]}
    other = {"periods": added + old, "rows": [_dscr("Debt!r10", "2025", "1.3"), _dscr("Debt!r10", "2026", "1.5")]}
    deltas = Comparisons._metric_deltas(base, other)
    assert [(item["period_id"], item["base"], item["other"]) for item in deltas] == [("2025", "1.3", "1.3"), ("2026", "1.4", "1.5")]
