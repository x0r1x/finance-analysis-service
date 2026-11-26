"""Адреса фактов: вертикальные годы цитируют ячейку значения, горизонтальные — как раньше."""

from __future__ import annotations

from decimal import Decimal

from finance_analysis.adapters.builder.acl import parse_context
from finance_analysis.application.project import project

BUILD = "build"
MODEL = "model"


def _period(col: int, key: str, index: int, row: int | None = None) -> dict:
    item = {"col": col, "period_key": key, "text": key, "index": index}
    if row is not None:
        item["row"] = row
    return item


def _axis(axis_id: str, periods: list[dict], *, transposed: bool = False) -> dict:
    axis = {
        "id": axis_id,
        "sheet": "Model",
        "grain": "year",
        "timeline_id": axis_id,
        "periods": periods,
    }
    if transposed:
        axis["transposed"] = True
    return axis


def _row(
    row_key: str,
    row: int,
    label: str,
    axis_id: str,
    values: list[str],
    *,
    value_col: int | None = None,
) -> dict:
    item = {
        "row_key": row_key,
        "sheet": "Model",
        "row": row,
        "kind": "fact",
        "label": label,
        "series": [{"axis_id": axis_id, "values": values, "value_statuses": ["cached"] * len(values)}],
    }
    if value_col is not None:
        item["value_col"] = value_col
    return item


def _block(block_id: str, row: dict) -> dict:
    return {
        "block_id": block_id,
        "sheet": "Model",
        "kind": "timeline",
        "rows": [row],
    }


def _project(payload: dict) -> dict[str, list[dict]]:
    tables, _warnings = project(parse_context(payload), model_id=MODEL, build=BUILD)
    return tables


def test_transposed_year_columns_cite_the_value_cell():
    """Шапка годов в колонке, значения вниз по соседней: как Model!Q22:Q24 и Model!S22:S23.

    Сейчас проекция берёт period.col и row.row, поэтому оба ряда схлопываются в
    ячейки шапки Model!P21 и Model!R21.
    """

    generation = "Model!c16r22"
    tariff = "Model!c18r22"
    payload = {
        "axes": [
            _axis(
                generation,
                [
                    _period(16, "2024", 0, 22),
                    _period(16, "2025", 1, 23),
                    _period(16, "2026", 2, 24),
                ],
                transposed=True,
            ),
            _axis(
                tariff,
                [
                    _period(18, "2025", 0, 22),
                    _period(18, "2026", 1, 23),
                ],
                transposed=True,
            ),
        ],
        "blocks": [
            _block(
                generation,
                _row(
                    "Model|21|c17|Model!c16r22",
                    21,
                    "Generation",
                    generation,
                    ["10", "11", "12"],
                    value_col=17,
                ),
            ),
            _block(
                tariff,
                _row(
                    "Model|21|c19|Model!c18r22",
                    21,
                    "Tariff",
                    tariff,
                    ["1.5", "2"],
                    value_col=19,
                ),
            ),
        ],
    }
    tables = _project(payload)
    facts = tables["fact_observation"]
    by_row = {}
    for fact in facts:
        by_row.setdefault(fact["row_key"], []).append(
            (fact["cell_id"], fact["period_id"], fact["value_dec"])
        )
    assert by_row["Model|21|c17|Model!c16r22"] == [
        ("Model!Q22", "2024", Decimal(10)),
        ("Model!Q23", "2025", Decimal(11)),
        ("Model!Q24", "2026", Decimal(12)),
    ]
    assert by_row["Model|21|c19|Model!c18r22"] == [
        ("Model!S22", "2025", Decimal("1.5")),
        ("Model!S23", "2026", Decimal(2)),
    ]
    assert {fact["cell_id"] for fact in facts}.isdisjoint({"Model!P21", "Model!R21"})
    year_cols = [
        (period["axis_id"], period["col"], period["period_id"])
        for period in tables["dim_period"]
    ]
    assert year_cols == [
        (generation, 16, "2024"),
        (generation, 16, "2025"),
        (generation, 16, "2026"),
        (tariff, 18, "2025"),
        (tariff, 18, "2026"),
    ]
    assert [row["row_num"] for row in tables["dim_row"]] == [21, 21]


def test_horizontal_axis_keeps_period_column_and_series_row():
    axis_id = "Model!r4"
    payload = {
        "axes": [
            _axis(
                axis_id,
                [
                    _period(2, "2024", 0),
                    _period(3, "2025", 1),
                ],
            )
        ],
        "blocks": [
            _block(
                axis_id,
                _row("Model|5|Model!r4", 5, "Revenue", axis_id, ["5", "6"]),
            )
        ],
    }
    tables = _project(payload)
    assert [
        (fact["cell_id"], fact["period_id"], fact["value_dec"])
        for fact in tables["fact_observation"]
    ] == [
        ("Model!B5", "2024", Decimal(5)),
        ("Model!C5", "2025", Decimal(6)),
    ]
