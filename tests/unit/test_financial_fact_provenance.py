"""Golden-контракт FinancialFactProvenance (фаза 1 метаслоя)."""

from __future__ import annotations

import pytest

from finance_analysis.domain.provenance import (
    ProvenanceJoinError,
    assemble_financial_fact_provenance,
)

# Минимальная golden-книга: одна ячейка ebitda за 2024Y на листе P&L.
_MODEL = "job_golden_book"
_BUILD = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
_DERIVE = "abcdefabcdefabcd"
_ROW = "P&L|12|blk1"
_BIND = "bk_ebitda_primary"
_AXIS = "axis_time_1"
_PERIOD = "2024Y"


def _golden_book() -> dict:
    return {
        "fact_observation": [
            {
                "model_id": _MODEL,
                "build_key": _BUILD,
                "row_key": _ROW,
                "axis_id": _AXIS,
                "axis_kind": "time",
                "period_id": _PERIOD,
                "cell_id": "P&L!D12",
                "value_raw": "1500000",
                "value": 1_500_000.0,
                "value_dec": "1500000.0000000000",
                "normalized_value": "1500000.000000",
                "value_status": "ok",
            }
        ],
        "dim_row": [
            {
                "model_id": _MODEL,
                "build_key": _BUILD,
                "row_key": _ROW,
                "binding_key": _BIND,
                "sheet": "P&L",
                "row_num": 12,
                "label": "EBITDA",
                "kind": "line",
                "indent": 0,
                "hidden": False,
                "check_row": False,
                "unit": "RUB",
                "currency": "RUB",
                "scale": "units",
                "has_formula": False,
            }
        ],
        "dim_period": [
            {
                "model_id": _MODEL,
                "build_key": _BUILD,
                "axis_id": _AXIS,
                "timeline_id": _AXIS,
                "axis_kind": "time",
                "period_id": _PERIOD,
                "period_index": 3,
                "col": 4,
                "header_text": "2024",
                "grain": "Y",
                "period_key_base": "2024",
                "calendar_year": 2024,
                "hidden": False,
                "date_source": "header",
            }
        ],
        "bindings": [
            {
                "model_id": _MODEL,
                "build_key": _BUILD,
                "state_seq": 7,
                "derive_key": _DERIVE,
                "concept": "ebitda",
                "effective_concept": "ebitda",
                "is_primary": True,
                "matched_label_id": "lbl_ebitda_ru",
                "status": "bound",
                "binding_key": _BIND,
                "row_key": _ROW,
                "label_path_text": "EBITDA",
                "source": "glossary",
                "confidence": 0.97,
                "glossary_version": "g-2026.11.01",
                "taxonomy_version": "tax-1.4",
                "decided_by": "infer",
                "stale": False,
            }
        ],
        "row_semantics": [
            {
                "model_id": _MODEL,
                "build_key": _BUILD,
                "state_seq": 7,
                "derive_key": _DERIVE,
                "binding_key": _BIND,
                "row_key": _ROW,
                "sign": "positive",
                "nature": "flow",
                "aggregation": "sum",
                "excluded": False,
                "is_check": False,
                "source": "default",
                "stale": False,
            }
        ],
    }


def test_golden_row_assembles_full_provenance():
    book = _golden_book()
    fact = book["fact_observation"][0]
    record = assemble_financial_fact_provenance(
        fact,
        rows=book["dim_row"],
        periods=book["dim_period"],
        bindings=book["bindings"],
        row_semantics=book["row_semantics"],
        semantic_model_version=None,
    )
    payload = record.to_dict()

    assert payload["concept"] == "ebitda"
    assert payload["effective_concept"] == "ebitda"
    assert payload["period_id"] == _PERIOD
    assert payload["axis_id"] == _AXIS
    assert payload["period_index"] == 3
    assert payload["calendar_year"] == 2024
    assert payload["grain"] == "Y"
    assert payload["cell_id"] == "P&L!D12"
    assert payload["value"] == 1_500_000.0
    assert payload["value_status"] == "ok"
    assert payload["binding_source"] == "glossary"
    assert payload["glossary_version"] == "g-2026.11.01"
    assert payload["taxonomy_version"] == "tax-1.4"
    assert payload["matched_label_id"] == "lbl_ebitda_ru"
    assert payload["build_key"] == _BUILD
    assert payload["derive_key"] == _DERIVE
    assert payload["semantic_model_version"] is None
    assert payload["sign"] == "positive"
    assert payload["nature"] == "flow"
    assert payload["sheet"] == "P&L"
    assert payload["binding_key"] == _BIND
    assert payload["state_seq"] == 7
    assert payload["is_primary"] is True


def test_smv_stub_passed_through_without_replacing_derive_key():
    book = _golden_book()
    record = assemble_financial_fact_provenance(
        book["fact_observation"][0],
        rows=book["dim_row"],
        periods=book["dim_period"],
        bindings=book["bindings"],
        semantic_model_version="smv-stub-phase2",
    )
    assert record.semantic_model_version == "smv-stub-phase2"
    assert record.derive_key == _DERIVE


def test_optional_row_semantics_may_be_absent():
    book = _golden_book()
    record = assemble_financial_fact_provenance(
        book["fact_observation"][0],
        rows=book["dim_row"],
        periods=book["dim_period"],
        bindings=book["bindings"],
        row_semantics=None,
    )
    assert record.sign is None
    assert record.excluded is None
    assert record.concept == "ebitda"


def test_missing_dim_row_raises():
    book = _golden_book()
    with pytest.raises(ProvenanceJoinError, match="dim_row"):
        assemble_financial_fact_provenance(
            book["fact_observation"][0],
            rows=[],
            periods=book["dim_period"],
            bindings=book["bindings"],
        )


def test_field_sources_match_contract_mapping():
    """Явная проверка field→dataset: значения не выдуманы сборкой."""

    book = _golden_book()
    fact = book["fact_observation"][0]
    row = book["dim_row"][0]
    period = book["dim_period"][0]
    binding = book["bindings"][0]
    record = assemble_financial_fact_provenance(
        fact,
        rows=book["dim_row"],
        periods=book["dim_period"],
        bindings=book["bindings"],
        row_semantics=book["row_semantics"],
    )

    # fact_observation
    assert record.cell_id == fact["cell_id"]
    assert record.value == fact["value"]
    assert record.value_status == fact["value_status"]
    # dim_row
    assert record.binding_key == row["binding_key"]
    assert record.sheet == row["sheet"]
    assert record.unit == row["unit"]
    # bindings
    assert record.concept == binding["concept"]
    assert record.binding_source == binding["source"]
    assert record.glossary_version == binding["glossary_version"]
    assert record.derive_key == binding["derive_key"]
    assert record.build_key == fact["build_key"]
    # dim_period
    assert record.period_index == period["period_index"]
    assert record.header_text == period["header_text"]
    # row_semantics
    assert record.aggregation == book["row_semantics"][0]["aggregation"]
