"""Публичный JSON Schema book_rows@1.0: массив result_data.book_rows."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from finance_analysis.domain.book_cite import cite_type_book_rows
from finance_analysis.domain.lbo_cite import cite_lbo_book_rows

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "finance_analysis"
    / "adapters"
    / "storage"
    / "schemas"
    / "book_rows.json"
)


@pytest.fixture(scope="module")
def validator() -> Draft202012Validator:
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _binding(concept: str, row_key: str, *, primary: bool = True) -> dict:
    return {
        "effective_concept": concept,
        "is_primary": primary,
        "status": "bound",
        "row_key": row_key,
        "source": "inferred",
    }


def _fact(row_key: str, value, **fields) -> dict:
    sheet = None if value is None else Decimal(str(value))
    body = {
        "row_key": row_key,
        "value_dec": None if sheet is None else format(sheet, "f"),
        "normalized_value": None if sheet is None else format(sheet * 1000, "f"),
        "scale_factor": 1000,
        "value_status": fields.pop("value_status", "cached"),
    }
    body.update(fields)
    return body


def test_schema_accepts_cited_absent_ambiguous_list(validator):
    """Валидирует голый список, как result_data.book_rows после _attach_book_rows."""

    rows = cite_type_book_rows(
        source="inferred",
        primary="real_estate_income",
        bindings=[
            _binding("cap_rate", "Assumptions!C20"),
            _binding("noi", "Summary!C7"),
            _binding("vacancy", "A!1"),
            _binding("vacancy", "A!2"),
        ],
        facts=[
            _fact(
                "Assumptions!C20",
                "0.0575",
                cell_id="Assumptions!D20",
                axis_id="a",
                period_id="y1",
                period_index=0,
            ),
            _fact(
                "Summary!C7",
                None,
                value_status="empty",
                cell_id="Summary!D7",
                axis_id="a",
                period_id="y1",
                period_index=0,
            ),
        ],
    )
    by_concept = {row["concept"]: row for row in rows}
    assert by_concept["cap_rate"]["status"] == "cited"
    assert by_concept["noi"]["status"] == "cited"
    assert by_concept["vacancy"]["status"] == "ambiguous"
    assert by_concept["vacancy"]["observations"] == []
    assert list(validator.iter_errors(rows)) == []


def test_schema_accepts_lbo_rows_list(validator):
    rows = cite_lbo_book_rows(
        source="inferred",
        primary="lbo_ma",
        bindings=[
            _binding("moic", "Returns!B9"),
            _binding("exit_enterprise_value", "Returns!B4"),
        ],
        facts=[
            {
                "row_key": "Returns!B9",
                "value_dec": "2.13",
                "normalized_value": "2.13",
                "scale_factor": 1,
                "value_status": "cached",
                "cell_id": "Returns!C9",
            }
        ],
        absent=frozenset({"exit_enterprise_value"}),
    )
    assert rows[0]["status"] == "cited"
    assert rows[1]["status"] == "absent"
    assert list(validator.iter_errors(rows)) == []


def test_schema_rejects_bad_status_and_extra_fields(validator):
    assert list(
        validator.iter_errors(
            [{"concept": "cap_rate", "status": "bound", "observations": []}]
        )
    )
    assert list(
        validator.iter_errors(
            [
                {
                    "concept": "cap_rate",
                    "status": "cited",
                    "row_key": "r",
                    "observations": [{"value": "1"}],
                    "needs_input": True,
                }
            ]
        )
    )
    assert list(
        validator.iter_errors(
            [
                {
                    "concept": "cap_rate",
                    "status": "absent",
                    "observations": [{"value": "1"}],
                }
            ]
        )
    )
    # Wrapper object is not the API shape.
    assert list(
        validator.iter_errors(
            {
                "version": "1.0",
                "book_rows": [
                    {
                        "concept": "cap_rate",
                        "status": "cited",
                        "row_key": "r",
                        "observations": [{"value": "1"}],
                    }
                ],
            }
        )
    )


@pytest.mark.parametrize(
    "bad",
    ["NaN", "Infinity", "-Infinity", "not-a-number", "1e3", "01", "+1", ".5", "1."],
)
def test_schema_rejects_non_plain_decimal_text(validator, bad):
    payload = [
        {
            "concept": "cap_rate",
            "status": "cited",
            "row_key": "r",
            "observations": [{"value": bad}],
        }
    ]
    assert list(validator.iter_errors(payload))
    payload[0]["observations"] = [{"value": "1", "normalized_value": bad}]
    assert list(validator.iter_errors(payload))


@pytest.mark.parametrize("ok", ["0", "1", "-2", "0.0575", "512.4", "1417.151736", None])
def test_schema_accepts_plain_decimal_text(validator, ok):
    payload = [
        {
            "concept": "cap_rate",
            "status": "cited",
            "row_key": "r",
            "observations": [{"value": ok}],
        }
    ]
    assert list(validator.iter_errors(payload)) == []


def test_book_rows_schema_is_not_a_parquet_dataset():
    from finance_analysis.domain.published_parquet import schema_file_names

    assert "book_rows" not in schema_file_names()
    doc = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert doc["$schema"].endswith("2020-12/schema")
    assert "dataset" not in doc
    assert doc["type"] == "array"
    assert "book_rows@1.0" in doc["$comment"]
