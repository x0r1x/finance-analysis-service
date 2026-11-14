"""Тождество остатка денежных средств: строка книги не подменяется."""

from __future__ import annotations

from decimal import Decimal

import pytest

from finance_analysis.application.catalog import load_catalog, load_identities
from finance_analysis.application.financial_catalog import load_financial_catalog
from finance_analysis.application.rule_engine import load_rules, select_rules
from finance_analysis.domain.audit import AuditInput
from finance_analysis.domain.cash_rollforward import check_cash
from finance_analysis.domain.derive_fingerprint import configs_root
from finance_analysis.domain.semantic_model import (
    live_components,
    semantic_model_version_for,
    stamp_path,
    validate_manifest,
)
from tests.unit.rule_inputs import check, fact, link, row

_ROWS = {
    "cash_opening": ("S|1|S!r2", 1),
    "cash_inflow": ("S|2|S!r2", 2),
    "cash_outflow": ("S|3|S!r2", 3),
    "cash_net": ("S|4|S!r2", 4),
    "fx_on_cash": ("S|5|S!r2", 5),
    "cash_balance": ("S|6|S!r2", 6),
    "cash": ("B|1|B!r3", 1),
}
_COLUMNS = {"2024": "C", "2025": "D"}


def test_labels_bind_and_the_sum_identity_stays_a_sum():
    package = load_catalog()
    assert package.resolve("Остаток денежных средств на начало периода").concept == "cash_opening"
    assert package.resolve("Cash at beginning").concept == "cash_opening"
    assert package.resolve("Приток денежных средств за период").concept == "cash_inflow"
    assert package.resolve("Отток денежных средств за период").concept == "cash_outflow"
    assert package.resolve("Change in cash").concept == "cash_net"
    assert package.resolve("Сальдо денежных потоков за отчетный период").concept == "cash_net"
    assert package.resolve("Величина влияния изменения курса иностранной валюты по отношению к рублю").concept == "fx_on_cash"
    assert package.resolve("Остаток денежных средств на конец периода").concept == "cash_balance"
    assert load_identities() == {
        "debt_service": ["interest", "principal"],
        "lease_payments": ["lease_principal", "lease_interest"],
    }
    assert "dscr" in load_financial_catalog().indicators
    assert "cash_balance" not in load_financial_catalog().indicators


def test_two_row_balance_is_silent_and_keeps_the_cell():
    data = _book(
        {
            "cash_opening": {"2024": "100"},
            "cash_inflow": {"2024": "40"},
            "cash_outflow": {"2024": "25"},
            "cash_balance": {"2024": "115"},
        }
    )
    sheet = _cell(data, "cash_balance", "2024")
    assert check_cash(data) == []
    assert check("cash_rollforward_break", data) == []
    assert sheet["value_dec"] == Decimal(115)


def test_unit_gap_is_a_break_and_keeps_the_book_value():
    data = _book(
        {
            "cash_opening": {"2024": "100"},
            "cash_inflow": {"2024": "40"},
            "cash_outflow": {"2024": "25"},
            "cash_balance": {"2024": "116"},
        }
    )
    found = check("cash_rollforward_break", data)
    assert len(found) == 1
    assert found[0].finding_kind == "error"
    assert found[0].params["periods"] == ["2024"]
    assert found[0].params["reason"] == "residual"
    assert found[0].params["fx"] is False
    assert _cell(data, "cash_balance", "2024")["value_dec"] == Decimal(116)


def test_single_row_uses_the_prior_close():
    balanced = _book(
        {
            "cash_inflow": {"2025": "40"},
            "cash_outflow": {"2025": "25"},
            "cash_balance": {"2024": "100", "2025": "115"},
        }
    )
    assert check("cash_rollforward_break", balanced) == []
    gap = _book(
        {
            "cash_inflow": {"2025": "40"},
            "cash_outflow": {"2025": "25"},
            "cash_balance": {"2024": "100", "2025": "116"},
        }
    )
    found = check("cash_rollforward_break", gap)
    assert found[0].params["periods"] == ["2025"]
    assert found[0].params["basis"] == "gross"


def test_two_row_opening_must_equal_the_prior_close():
    held = _movement("100", "115")
    assert check("cash_rollforward_break", held) == []
    shifted = _movement("90", "105")
    found = check("cash_rollforward_break", shifted)
    assert [item.params["reason"] for item in found] == ["continuity"]
    assert found[0].params["periods"] == ["2025"]


def test_negative_outflow_is_not_subtracted_twice():
    data = _book(
        {
            "cash_opening": {"2024": "100"},
            "cash_inflow": {"2024": "40"},
            "cash_outflow": {"2024": "-25"},
            "cash_balance": {"2024": "115"},
        }
    )
    assert check("cash_rollforward_break", data) == []


def test_bound_fx_enters_the_equation():
    held = _book(
        {
            "cash_opening": {"2024": "100"},
            "cash_inflow": {"2024": "40"},
            "cash_outflow": {"2024": "25"},
            "fx_on_cash": {"2024": "-3"},
            "cash_balance": {"2024": "112"},
        }
    )
    assert check("cash_rollforward_break", held) == []
    gap = _book(
        {
            "cash_opening": {"2024": "100"},
            "cash_inflow": {"2024": "40"},
            "cash_outflow": {"2024": "25"},
            "fx_on_cash": {"2024": "-3"},
            "cash_balance": {"2024": "115"},
        }
    )
    found = check("cash_rollforward_break", gap)
    assert found[0].params["fx"] is True
    assert found[0].params["reason"] == "residual"


def test_missing_fx_row_is_a_break_and_not_called_fx():
    data = _book(
        {
            "cash_opening": {"2024": "100"},
            "cash_inflow": {"2024": "40"},
            "cash_outflow": {"2024": "25"},
            "cash_balance": {"2024": "112"},
        }
    )
    found = check("cash_rollforward_break", data)
    assert found[0].params["fx"] is False
    assert found[0].params["reason"] == "residual"
    assert "курс" not in str(found[0].params)


def test_gross_and_net_are_not_added():
    held = _book(
        {
            "cash_opening": {"2024": "100"},
            "cash_inflow": {"2024": "40"},
            "cash_outflow": {"2024": "25"},
            "cash_net": {"2024": "15"},
            "cash_balance": {"2024": "115"},
        }
    )
    assert check("cash_rollforward_break", held) == []
    summed = _book(
        {
            "cash_opening": {"2024": "100"},
            "cash_inflow": {"2024": "40"},
            "cash_outflow": {"2024": "25"},
            "cash_net": {"2024": "15"},
            "cash_balance": {"2024": "130"},
        }
    )
    assert check("cash_rollforward_break", summed)[0].params["basis"] == "gross"


def test_formula_that_names_only_the_net_line_does_not_use_gross():
    """Прецеденты закрытия — только сальдо. Валовые строки рядом в сумму не входят."""

    data = _book(
        {
            "cash_opening": {"2025": "100"},
            "cash_inflow": {"2025": "40"},
            "cash_outflow": {"2025": "25"},
            "cash_net": {"2025": "10"},
            "cash_balance": {"2025": "110"},
        },
        links=link("S!D6", "=D4", "S|6|S!r2", "2025", ("S!D4",)),
    )
    assert check_cash(data) == []
    assert check("cash_rollforward_break", data) == []


def test_indirect_net_line_is_checked_without_gross_lines():
    held = _book(
        {
            "cash_opening": {"2024": "100"},
            "cash_net": {"2024": "15"},
            "cash_balance": {"2024": "115"},
        }
    )
    assert check("cash_rollforward_break", held) == []
    gap = _book(
        {
            "cash_opening": {"2024": "100"},
            "cash_net": {"2024": "15"},
            "cash_balance": {"2024": "116"},
        }
    )
    assert check("cash_rollforward_break", gap)[0].params["basis"] == "net"


def test_close_only_is_insufficient_and_not_a_break():
    data = _book({"cash_balance": {"2024": "100"}})
    assert [note.tag for note in check_cash(data)] == ["insufficient_data"]
    assert check("cash_rollforward_break", data) == []


def test_no_close_declares_nothing():
    data = _book({"cash_inflow": {"2024": "40"}, "cash_outflow": {"2024": "25"}})
    assert check_cash(data) == []
    assert check("cash_rollforward_break", data) == []


def test_tolerance_passes_a_rounding_tail_and_catches_a_unit():
    tail = _amounts("115.004")
    edge = _amounts("115.005")
    unit = _amounts("116")
    assert check("cash_rollforward_break", tail) == []
    assert check("cash_rollforward_break", edge) == []
    assert check("cash_rollforward_break", unit)[0].params["reason"] == "residual"


def test_statement_tie_reports_the_difference_without_a_standard_verdict():
    same = _book({"cash_balance": {"2025": "100"}, "cash": {"2025": "100"}})
    assert check("cash_statement_tie", same) == []
    assert check("cash_statement_tie", _book({"cash_balance": {"2025": "100"}})) == []
    gap = _book({"cash_balance": {"2025": "100"}, "cash": {"2025": "90"}})
    found = check("cash_statement_tie", gap)
    assert len(found) == 1
    assert found[0].finding_kind == "warning"
    assert found[0].params["periods"] == ["2025"]
    rule = select_rules(load_rules(), ["cash_statement_tie"])[0]
    title = rule.title.casefold()
    assert "различ" in title
    assert "мсфо" not in title and "рсбу" not in title
    assert "допустим" not in str(found[0].params)


def test_live_manifest_stamps_the_corkscrew_and_an_old_manifest_still_validates():
    components = live_components(
        "none",
        model_types_version="mt",
        metrics_version="catalog1",
        rules_versions={"missing_total_row": "1"},
    )
    stamp = stamp_path(configs_root(), "configs/identities/cash_corkscrew.yaml")[:16]
    assert components["cash_corkscrew"] == stamp
    fresh = {
        "version": semantic_model_version_for(components),
        "components": components,
        "fas_version": "0.23.0",
        "created_at_utc": "2026-11-13T00:00:00Z",
    }
    assert validate_manifest(fresh)["components"]["cash_corkscrew"] == stamp
    legacy_components = {key: value for key, value in components.items() if key != "cash_corkscrew"}
    legacy = {
        "version": semantic_model_version_for(legacy_components),
        "components": legacy_components,
        "fas_version": "0.23.0",
        "created_at_utc": "2026-11-06T00:00:00Z",
    }
    assert validate_manifest(legacy)["version"] == legacy["version"]
    empty = dict(components)
    empty["cash_corkscrew"] = ""
    with pytest.raises(ValueError, match="cash_corkscrew"):
        validate_manifest({**fresh, "version": semantic_model_version_for(empty), "components": empty})


def _movement(opening_2025: str, close_2025: str) -> AuditInput:
    """2024 сходится. В 2025 остаток собран из своего открытия; связка с 2024 — отдельно."""

    return _book(
        {
            "cash_opening": {"2024": "80", "2025": opening_2025},
            "cash_inflow": {"2024": "30", "2025": "40"},
            "cash_outflow": {"2024": "10", "2025": "25"},
            "cash_balance": {"2024": "100", "2025": close_2025},
        }
    )


def _amounts(close: str) -> AuditInput:
    return _book(
        {
            "cash_opening": {"2024": "100"},
            "cash_inflow": {"2024": "40"},
            "cash_outflow": {"2024": "25"},
            "cash_balance": {"2024": close},
        }
    )


def _book(lines: dict[str, dict[str, str]], *, links: list[dict] | None = None) -> AuditInput:
    rows = []
    facts = []
    bindings = []
    for concept, values in lines.items():
        row_key, number = _ROWS[concept]
        rows.append(row(row_key))
        bindings.append(
            {"effective_concept": concept, "row_key": row_key, "status": "bound", "is_primary": True}
        )
        sheet = "B" if concept == "cash" else "S"
        axis = "B!r3" if concept == "cash" else "S!r2"
        for period, value in values.items():
            cell = f"{sheet}!{_COLUMNS[period]}{number}"
            facts.append(fact(row_key, cell, period, value, axis=axis))
    periods = [
        {"axis_id": "S!r2", "period_id": "2024", "period_index": 0, "period_key_base": "2024"},
        {"axis_id": "S!r2", "period_id": "2025", "period_index": 1, "period_key_base": "2025"},
        {"axis_id": "B!r3", "period_id": "2024", "period_index": 0, "period_key_base": "2024"},
        {"axis_id": "B!r3", "period_id": "2025", "period_index": 1, "period_key_base": "2025"},
    ]
    return AuditInput(rows=rows, periods=periods, facts=facts, links=links or [], bindings=bindings)


def _cell(data: AuditInput, concept: str, period: str) -> dict:
    row_key = _ROWS[concept][0]
    return next(item for item in data.facts if item["row_key"] == row_key and item["period_id"] == period)
