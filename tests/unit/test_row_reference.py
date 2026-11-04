"""Роль reference и запрет нулевой строки в выборе основной."""

from __future__ import annotations

from decimal import Decimal

from finance_analysis.application.catalog import load_catalog
from finance_analysis.application.sheet_roles import load_sheet_roles
from finance_analysis.domain.mapping import assign_rows
from finance_analysis.domain.references import formula_reference, values_match
from tests.unit.test_row_selection import _row

_ROLES = load_sheet_roles()


def _assigned(rows, **extra):
    return assign_rows(rows, [], load_catalog(), roles=_ROLES, **extra)


def test_single_cell_formula_is_a_reference():
    rows = [
        _row("src", "Interest", sheet="Model", row_num=10),
        _row("echo", "Interest", sheet="Model", row_num=20, formula="=C10"),
    ]
    got = _assigned(rows)
    assert got["src"].is_primary and got["src"].evidence["selection"] == "reference"
    assert got["echo"].is_primary is False
    assert got["echo"].evidence["role"] == "reference"
    assert got["echo"].evidence["reference_of"] == "src"
    assert got["echo"].status == "bound"


def test_scale_factor_keeps_the_reference():
    divided = formula_reference("=C10/1000", default_sheet="Model")
    multiplied = formula_reference("=C10*1000", default_sheet="Model")
    assert divided == ("Model", 10)
    assert multiplied == ("Model", 10)
    rows = [
        _row("src", "Interest", sheet="Model", row_num=10),
        _row("echo", "Interest", sheet="Notes", row_num=4, formula="=Model!C10/1000"),
    ]
    got = _assigned(rows)
    assert got["echo"].evidence["reference_of"] == "src"
    assert got["src"].is_primary
    assert formula_reference("=C10/2", default_sheet="Model") is None
    assert formula_reference("=C10+C11", default_sheet="Model") is None


def test_scale_other_than_one_or_a_unit_is_not_a_reference():
    assert formula_reference("=C10*1", default_sheet="Model") == ("Model", 10)
    assert formula_reference("=C10*1000", default_sheet="Model") == ("Model", 10)
    assert formula_reference("=C10/1000000", default_sheet="Model") == ("Model", 10)
    assert formula_reference("=C10*1.1", default_sheet="Model") is None
    assert formula_reference("=Other!C10*1.1", default_sheet="Model") is None
    assert formula_reference("=C10*10", default_sheet="Model") is None
    assert not values_match({"a": Decimal(10)}, {"a": Decimal("1.1")})
    assert not values_match({"a": Decimal(10)}, {"a": Decimal(1)})
    assert values_match({"a": Decimal(1_000_000)}, {"a": Decimal(1)})
    rows = [
        _row("src", "Interest", sheet="Model", row_num=10),
        _row("uplift", "Interest", sheet="Notes", row_num=4, formula="=Model!C10*1.1"),
    ]
    got = _assigned(rows)
    assert "role" not in got["uplift"].evidence


def test_cross_sheet_link_and_r1c1_point_at_the_source_row():
    parsed = formula_reference("='Денежные потоки'!C38", default_sheet="Outputs")
    assert parsed == ("Денежные потоки", 38)
    relative = formula_reference("=R[-10]C[0]", default_sheet="Model", origin_row=20)
    assert relative == ("Model", 10)
    rows = [
        _row("src", "Interest", sheet="Денежные потоки", row_num=38),
        _row("echo", "Interest", sheet="Outputs", row_num=56, has_formula=True),
    ]
    links = [
        {
            "row_key": "echo",
            "cell": "Outputs!C56",
            "formula": "='Денежные потоки'!C38",
            "refs": ["Денежные потоки!C38"],
        }
    ]
    got = _assigned(rows, links=links)
    assert got["echo"].evidence["role"] == "reference"
    assert got["echo"].evidence["reference_of"] == "src"
    assert got["src"].is_primary


def test_lagged_column_on_the_same_row_is_not_a_reference():
    rows = [
        _row("close", "Interest", sheet="Debt", row_num=11),
        _row("open", "Interest", sheet="Debt", row_num=8, has_formula=True),
    ]
    links = [
        {"row_key": "open", "cell": "Debt!B8", "formula": "=A11", "refs": ["Debt!A11"]},
        {"row_key": "open", "cell": "Debt!C8", "formula": "=B11", "refs": ["Debt!B11"]},
        {"row_key": "open", "cell": "Debt!D8", "formula": "=C11", "refs": ["Debt!C11"]},
    ]
    periods = {
        "close": {("ax", "1"): Decimal(100), ("ax", "2"): Decimal(80), ("ax", "3"): Decimal(60)},
        "open": {("ax", "1"): Decimal(0), ("ax", "2"): Decimal(100), ("ax", "3"): Decimal(80)},
    }
    got = _assigned(rows, links=links, periods=periods)
    assert "role" not in got["open"].evidence
    assert "role" not in got["close"].evidence
    same = [
        _row("src", "Interest", sheet="Debt", row_num=14),
        _row("echo", "Interest", sheet="P&L", row_num=19, has_formula=True),
    ]
    same_links = [
        {"row_key": "echo", "cell": "P&L!AA19", "formula": "=Debt!AA14", "refs": ["Debt!AA14"]},
    ]
    copied = _assigned(same, links=same_links)
    assert copied["echo"].evidence["role"] == "reference"
    assert copied["echo"].evidence["reference_of"] == "src"
    assert formula_reference("=R[3]C[-1]", default_sheet="Debt", origin_row=8) is None
    assert formula_reference("=R[-5]C[0]", default_sheet="Debt", origin_row=16) == ("Debt", 11)


def test_pasted_copy_matches_within_tolerance_and_scale():
    assert values_match({"a": Decimal(1000)}, {"a": Decimal("1000.05")})
    assert values_match({"a": Decimal(1000), "b": Decimal(0)}, {"a": Decimal(1), "b": Decimal(0)})
    assert not values_match({"a": Decimal(1000)}, {"a": Decimal(1010)})
    periods = {
        "src": {("ax", "1"): Decimal(10), ("ax", "2"): Decimal(20), ("ax", "3"): Decimal(30)},
        "copy": {("ax", "1"): Decimal(10), ("ax", "2"): Decimal(20)},
        "other": {("ax", "1"): Decimal(7)},
    }
    rows = [
        _row("src", "Interest", sheet="Model"),
        _row("copy", "Interest", sheet="Notes"),
        _row("other", "Interest", sheet="Debt"),
    ]
    got = _assigned(rows, periods=periods)
    assert got["copy"].evidence["role"] == "reference"
    assert got["copy"].evidence["reference_of"] == "src"
    assert got["copy"].is_primary is False
    assert got["src"].is_primary
    assert "role" not in got["other"].evidence


def test_shorter_statement_is_not_hidden_by_a_longer_paste():
    periods = {
        "pnl": {("ax", "1"): Decimal(10), ("ax", "2"): Decimal(20)},
        "model": {
            ("ax", "1"): Decimal(10),
            ("ax", "2"): Decimal(20),
            ("ax", "3"): Decimal(30),
            ("ax", "4"): Decimal(40),
        },
    }
    rows = [
        _row("pnl", "Interest", sheet="P&L"),
        _row("model", "Interest", sheet="Model"),
    ]
    got = _assigned(rows, periods=periods)
    assert "role" not in got["pnl"].evidence
    assert got["pnl"].is_primary
    assert got["model"].is_primary is False
    different = {
        "pnl": {("ax", "1"): Decimal(10), ("ax", "2"): Decimal(20)},
        "model": {("ax", "1"): Decimal(10), ("ax", "2"): Decimal(99)},
    }
    kept = _assigned(rows, periods=different)
    assert kept["pnl"].is_primary and kept["pnl"].evidence["selection"] == "formula"
    equal = {
        "pnl": {("ax", "1"): Decimal(10), ("ax", "2"): Decimal(20)},
        "debt": {("ax", "1"): Decimal(10), ("ax", "2"): Decimal(20)},
    }
    formula_rows = [
        _row("pnl", "Interest", sheet="P&L"),
        _row("debt", "Interest", sheet="Debt", has_formula=True, formula="=B8*C5"),
    ]
    stated = _assigned(formula_rows, periods=equal)
    assert "role" not in stated["pnl"].evidence
    assert stated["pnl"].is_primary
    assert stated["debt"].is_primary is False


def test_small_numbers_keep_the_relative_tolerance():
    assert not values_match({"a": Decimal("0.05")}, {"a": Decimal("0.05009")})
    assert not values_match(
        {"a": Decimal(100), "b": Decimal(0)},
        {"a": Decimal(100), "b": Decimal("0.00009")},
    )
    assert values_match({"a": Decimal(1000)}, {"a": Decimal("1000.05")})
    periods = {
        "pnl": {("ax", "1"): Decimal(100), ("ax", "2"): Decimal(0)},
        "model": {("ax", "1"): Decimal(100), ("ax", "2"): Decimal("0.00009"), ("ax", "3"): Decimal(50)},
    }
    rows = [
        _row("pnl", "Interest", sheet="P&L"),
        _row("model", "Interest", sheet="Model"),
    ]
    got = _assigned(rows, periods=periods)
    assert "role" not in got["pnl"].evidence
    assert got["pnl"].is_primary


def test_overlap_marks_only_the_shorter_row_and_rejects_an_empty_overlap():
    history = {("ax", "2023"): Decimal(10), ("ax", "2024"): Decimal(12)}
    forecast = {
        ("ax", "2023"): Decimal(10),
        ("ax", "2024"): Decimal(12),
        ("ax", "2025"): Decimal(14),
        ("ax", "2026"): Decimal(16),
    }
    assert values_match(forecast, history)
    assert not values_match(history, forecast)
    assert not values_match({("ax", "2021"): Decimal(10)}, {("ax", "2025"): Decimal(10)})
    assert not values_match({}, {})
    periods = {"history": history, "forecast": forecast, "other": {("ax", "2020"): Decimal(10)}}
    rows = [
        _row("history", "Interest", sheet="Model"),
        _row("forecast", "Interest", sheet="Notes"),
        _row("other", "Interest", sheet="Debt"),
    ]
    got = _assigned(rows, periods=periods)
    assert got["history"].evidence["role"] == "reference"
    assert got["history"].evidence["reference_of"] == "forecast"
    assert got["history"].is_primary is False
    assert got["forecast"].is_primary
    assert "role" not in got["forecast"].evidence
    assert "role" not in got["other"].evidence


def test_equal_rows_without_a_stronger_source_stay_a_tie():
    periods = {
        "left": {("ax", "1"): Decimal(5), ("ax", "2"): Decimal(6)},
        "right": {("ax", "1"): Decimal(5), ("ax", "2"): Decimal(6)},
    }
    rows = [
        _row("left", "Interest", sheet="Model"),
        _row("right", "Interest", sheet="Notes"),
    ]
    got = _assigned(rows, periods=periods)
    assert got["left"].status == "ambiguous" and got["right"].status == "ambiguous"
    assert "role" not in got["left"].evidence


def test_only_reference_stays_primary():
    rows = [
        _row("src", "Revenue", sheet="Model", row_num=10),
        _row("echo", "Interest", sheet="Notes", row_num=20, formula="=Model!C10"),
    ]
    got = _assigned(rows)
    assert got["echo"].is_primary
    assert got["echo"].evidence["role"] == "reference"
    assert got["echo"].evidence["reference_of"] == "src"


def test_zero_and_empty_rows_lose_to_a_nonzero_candidate():
    periods = {
        "live": {("ax", "1"): Decimal(5)},
        "zeros": {("ax", "1"): Decimal(0), ("ax", "2"): Decimal(0)},
    }
    rows = [
        _row("live", "Interest", sheet="Model"),
        _row("zeros", "Interest", sheet="Notes"),
        _row("empty", "Interest", sheet="Debt"),
    ]
    got = _assigned(rows, periods=periods)
    assert got["live"].is_primary and got["live"].evidence["selection"] == "zero"
    assert got["zeros"].is_primary is False and got["zeros"].status == "bound"
    assert got["empty"].is_primary is False
    both = [
        _row("a", "Interest", sheet="Model"),
        _row("b", "Interest", sheet="Notes"),
    ]
    tied = _assigned(both, periods={"a": {("ax", "1"): 0}, "b": {("ax", "1"): 0}})
    assert tied["a"].status == "ambiguous" and tied["b"].status == "ambiguous"


def test_confirmed_row_keeps_primary():
    catalog = load_catalog()
    rows = [
        _row("src", "Interest", sheet="Model", row_num=10),
        _row("echo", "Interest", sheet="Notes", row_num=20, formula="=Model!C10"),
        _row("other", "Interest", sheet="Debt"),
    ]
    events = [
        {"seq": 1, "type": "concept.set", "target": "echo", "binding_key": "echo", "value": "interest"},
        {"seq": 2, "type": "concept.set", "target": "other", "binding_key": "other", "value": "interest"},
    ]
    got = assign_rows(rows, events, catalog, roles=_ROLES)
    assert got["echo"].source == "confirmed" and got["echo"].is_primary
    assert got["echo"].evidence["role"] == "reference"
    assert got["other"].source == "confirmed" and got["other"].is_primary
    single_rows = [
        _row("plain", "Interest", sheet="Model", row_num=10),
        _row("echo", "Interest", sheet="Notes", row_num=20, formula="=Model!C10"),
    ]
    single = assign_rows(
        single_rows,
        [{"seq": 1, "type": "concept.set", "target": "echo", "binding_key": "echo", "value": "interest"}],
        catalog,
        roles=_ROLES,
    )
    assert single["echo"].source == "confirmed" and single["echo"].is_primary
    assert single["plain"].is_primary is False


def test_sole_zero_total_stays_primary():
    alone = _assigned(
        [_row("interest", "Interest", sheet="Model")],
        periods={"interest": {("ax", "1"): Decimal(0), ("ax", "2"): Decimal(0)}},
    )
    assert alone["interest"].is_primary
    assert alone["interest"].status == "bound"
    rows = [
        _row("src", "Revenue", sheet="Revenue", row_num=4),
        _row("total", "Interest", sheet="Model"),
        _row("echo", "Interest", sheet="Notes", row_num=20, formula="=Revenue!C4"),
    ]
    periods = {
        "total": {("ax", "1"): Decimal(0)},
        "echo": {("ax", "1"): Decimal(4)},
    }
    got = _assigned(rows, periods=periods)
    assert got["total"].is_primary
    assert got["echo"].is_primary is False
    assert got["echo"].evidence["role"] == "reference"


def test_nonzero_reference_beats_an_all_zero_row():
    rows = [
        _row("echo", "Interest", sheet="Notes", row_num=20, formula="=Model!C10"),
        _row("src", "Interest", sheet="Model", row_num=10),
        _row("zeros", "Interest", sheet="Debt"),
    ]
    periods = {
        "echo": {("ax", "1"): Decimal(4)},
        "src": {("ax", "1"): Decimal(8)},
        "zeros": {("ax", "1"): Decimal(0)},
    }
    got = _assigned(rows, periods=periods)
    assert got["zeros"].is_primary is False
    assert got["echo"].is_primary is False
    assert got["src"].is_primary
