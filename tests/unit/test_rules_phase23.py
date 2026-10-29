"""Правила фазы 2 и правила метрик фазы 3 (§6.1) на синтетических входах."""

from __future__ import annotations

from datetime import date

from finance_analysis.domain.audit import AuditInput
from tests.unit.rule_inputs import PERIODS, check, fact, link, row

A = "S|5|S!r2"
B = "S|6|S!r2"
C = "S|7|S!r2"


def _codes(code: str, data: AuditInput) -> list:
    return check(code, data)


def _indexed(periods=PERIODS) -> list[dict]:
    return [{**period, "period_index": index, "timeline_id": period["axis_id"]} for index, period in enumerate(periods)]


def test_daisy_chain_needs_a_reference_to_a_reference():
    data = AuditInput(
        rows=[row(A), row(B)],
        periods=PERIODS,
        links=link("S!C5", "=C6", A, "2024", ("S!C6",)) + link("S!C6", "=C7", B, "2024", ("S!C7",)),
        facts=[fact(A, "S!C5", "2024", "1"), fact(B, "S!C6", "2024", "1")],
    )
    found = _codes("daisy_chain", data)
    assert [item.locations[0].cell_id for item in found] == ["S!C5"]


def test_daisy_chain_reads_r1c1_formulas_of_the_builder():
    data = AuditInput(
        rows=[row(A), row(B)],
        periods=PERIODS,
        links=link("S!C5", "=R[1]C[0]", A, "2024", ("S!C6",)) + link("S!C6", "=R[1]C", B, "2024", ("S!C7",)),
        facts=[fact(A, "S!C5", "2024", "1"), fact(B, "S!C6", "2024", "1")],
    )
    assert [item.locations[0].cell_id for item in _codes("daisy_chain", data)] == ["S!C5"]


def test_r1c1_check_formula_is_not_a_sum():
    rows = [row(A, unit="money", scale_factor=1000), row(B, unit="money", scale_factor=1), row(C, unit="money", scale_factor=1)]
    facts = [fact(A, "S!C5", "2024", "1"), fact(B, "S!C6", "2024", "1"), fact(C, "S!C7", "2024", "1")]
    check_cell = link("S!C5", "=R[-27]C[0]-R[-15]C[0]<0.01", A, "2024", ("S!C6", "S!C7"))
    assert _codes("scale_mismatch", AuditInput(rows=rows, periods=PERIODS, facts=facts, links=check_cell)) == []
    summed = link("S!C5", "=R[1]C[0]+R[2]C[0]", A, "2024", ("S!C6", "S!C7"))
    assert _codes("scale_mismatch", AuditInput(rows=rows, periods=PERIODS, facts=facts, links=summed))


def test_partial_range_reference_sees_the_missing_tail():
    facts = [fact(A, "S!C5", "2024", "1"), fact(A, "S!D5", "2025", "2"), fact(A, "S!E5", "2026@план", "3")]
    partial = AuditInput(
        rows=[row(A)], periods=PERIODS, facts=facts, links=link("S!B5", "=SUM(C5:D5)", A, None, ("S!C5", "S!D5"))
    )
    found = _codes("partial_range_reference", partial)
    assert found and found[0].params["missed"] == ["S!E5"]
    full = AuditInput(
        rows=[row(A)], periods=PERIODS, facts=facts, links=link("S!B5", "=SUM(C5:E5)", A, None, ("S!C5", "S!D5", "S!E5"))
    )
    assert _codes("partial_range_reference", full) == []


def test_row_total_in_logic_flags_a_series_cell_using_the_total_column():
    facts = [fact(A, "S!C5", "2024", "1"), fact(A, "S!D5", "2025", "2"), fact(B, "S!C6", "2024", "3", )]
    data = AuditInput(
        rows=[row(A, kind="fact"), row(B, kind="fact")],
        periods=PERIODS,
        facts=facts,
        links=link("S!B5", "=SUM(C5:D5)", A, None, ("S!C5", "S!D5")) + link("S!C6", "=C5/$B$5", B, "2024", ("S!C5", "S!B5")),
    )
    found = _codes("row_total_in_logic", data)
    assert found and found[0].params["total_cell"] == ["S!B5"]


def test_hidden_used_in_calc_names_the_hidden_row():
    data = AuditInput(
        rows=[row(A), row(B, hidden=True)],
        periods=PERIODS,
        facts=[fact(A, "S!C5", "2024", "1"), fact(B, "S!C6", "2024", "1")],
        links=link("S!C5", "=C6*2", A, "2024", ("S!C6",)),
    )
    found = _codes("hidden_used_in_calc", data)
    assert [item.locations[0].row_key for item in found] == [B]


def test_duplicate_label_and_missing_unit():
    rows = [
        row(A, kind="fact", label="Revenue", label_path_json="[]", unit="money", row_num=5),
        row(B, kind="fact", label="Revenue", label_path_json="[]", unit="money", row_num=6),
        row(C, kind="fact", label="Volume", label_path_json="[]", row_num=7),
    ]
    data = AuditInput(rows=rows, periods=PERIODS, facts=[fact(C, "S!C7", "2024", "5")])
    duplicate = _codes("duplicate_label", data)
    assert [item.locations[0].row_key for item in duplicate] == [B]
    missing = _codes("missing_unit", data)
    assert [item.locations[0].row_key for item in missing] == [C]


def test_hardcoded_value_in_formula_row():
    data = AuditInput(
        rows=[row(A)],
        periods=PERIODS,
        facts=[fact(A, "S!C5", "2024", "1"), fact(A, "S!D5", "2025", "60")],
        links=link("S!C5", "=C4+1", A, "2024", ("S!C4",)) + link("S!D5", "=5*12", A, "2025", ()),
    )
    found = _codes("hardcoded_value_in_formula_row", data)
    assert [item.locations[0].cell_id for item in found] == ["S!D5"]


def test_scale_and_unit_mismatch_need_a_real_sum():
    rows = [
        row(A, unit="money", scale_factor=1000),
        row(B, unit="money", scale_factor=1),
        row(C, unit="rate", scale_factor=None),
    ]
    facts = [fact(A, "S!C5", "2024", "1"), fact(B, "S!C6", "2024", "1"), fact(C, "S!C7", "2024", "0.1")]
    summed = AuditInput(rows=rows, periods=PERIODS, facts=facts, links=link("S!C5", "=C6+C7", A, "2024", ("S!C6", "S!C7")))
    assert _codes("scale_mismatch", summed)
    assert _codes("unit_mismatch", summed)
    copied = AuditInput(rows=rows, periods=PERIODS, facts=facts, links=link("S!C5", "=C6", A, "2024", ("S!C6",)))
    assert _codes("scale_mismatch", copied) == []
    product = AuditInput(rows=rows, periods=PERIODS, facts=facts, links=link("S!C5", "=C6*C7", A, "2024", ("S!C6", "S!C7")))
    assert _codes("unit_mismatch", product) == []


def test_period_gap_between_dated_periods():
    periods = [
        {**PERIODS[0], "period_index": 0, "period_start": date(2024, 1, 1), "period_end": date(2024, 12, 31)},
        {**PERIODS[1], "period_index": 1, "period_start": date(2025, 2, 1), "period_end": date(2025, 12, 31)},
    ]
    found = _codes("period_gap", AuditInput(rows=[], periods=periods))
    assert [(item.params["previous"], item.params["gap_days"]) for item in found] == [("2024", 31)]


def test_rollforward_break_on_hardcoded_opening_and_value_drift():
    periods = _indexed()
    opening, closing = A, B
    facts = [
        fact(opening, "S!C5", "2024", "0"),
        fact(opening, "S!D5", "2025", "10"),
        fact(opening, "S!E5", "2026@план", "99"),
        fact(closing, "S!C6", "2024", "10"),
        fact(closing, "S!D6", "2025", "20"),
        fact(closing, "S!E6", "2026@план", "30"),
    ]
    links = (
        link("S!D5", "=C6", opening, "2025", ("S!C6",))
        + link("S!E5", "=D6", opening, "2026@план", ("S!D6",))
    )
    drift = AuditInput(rows=[row(opening), row(closing)], periods=periods, facts=facts, links=links)
    found = _codes("rollforward_break", drift)
    assert [(item.locations[0].cell_id, item.params["reason"]) for item in found] == [("S!E5", "value_differs")]
    fixed = [dict(item) for item in facts]
    fixed[2] = fact(opening, "S!E5", "2026@план", "20")
    assert _codes("rollforward_break", AuditInput(rows=[row(opening), row(closing)], periods=periods, facts=fixed, links=links)) == []


def test_rollforward_break_reads_r1c1_openings():
    periods = _indexed()
    opening, closing = A, B
    facts = [
        fact(opening, "S!C5", "2024", "0"),
        fact(opening, "S!D5", "2025", "10"),
        fact(opening, "S!E5", "2026@план", "99"),
        fact(closing, "S!C6", "2024", "10"),
        fact(closing, "S!D6", "2025", "20"),
        fact(closing, "S!E6", "2026@план", "30"),
    ]
    links = link("S!D5", "=R[1]C[-1]", opening, "2025", ("S!C6",)) + link("S!E5", "=R[1]C[-1]", opening, "2026@план", ("S!D6",))
    found = _codes("rollforward_break", AuditInput(rows=[row(opening), row(closing)], periods=periods, facts=facts, links=links))
    assert [(item.locations[0].cell_id, item.params["reason"]) for item in found] == [("S!E5", "value_differs")]


def test_sign_anomaly_and_mixed_convention():
    rows = [row(A), row(B), row(C)]
    facts = [
        fact(A, "S!C5", "2024", "-5"),
        fact(A, "S!D5", "2025", "-6"),
        fact(B, "S!C6", "2024", "-7"),
        fact(C, "S!C7", "2024", "8"),
        fact(C, "S!D7", "2025", "-1"),
    ]
    semantics = [
        {"row_key": A, "sign": "outflow"},
        {"row_key": B, "sign": "outflow"},
        {"row_key": C, "sign": "outflow"},
    ]
    data = AuditInput(rows=rows, periods=PERIODS, facts=facts, semantics=semantics)
    assert [item.locations[0].row_key for item in _codes("sign_anomaly", data)] == [C]
    assert _codes("sign_convention_mixed", data) == []
    facts[4] = fact(C, "S!D7", "2025", "2")
    mixed = _codes("sign_convention_mixed", AuditInput(rows=rows, periods=PERIODS, facts=facts, semantics=semantics))
    assert mixed[0].params == {"negative": 2, "positive": 1}
    assert [item.row_key for item in mixed[0].locations] == [C]


def test_cross_sheet_inconsistency_ignores_linked_and_sign_flipped_copies():
    left, right = "S|5|S!r2", "T|5|T!r2"
    periods = _indexed() + [{**period, "axis_id": "T!r2", "timeline_id": "S!r2"} for period in _indexed()]
    rows = [
        row(left, kind="fact", label="Opex", unit="money"),
        row(right, kind="fact", label="Opex", unit="money"),
    ]
    differ = [fact(left, "S!C5", "2024", "10"), fact(right, "T!C5", "2024", "12", axis="T!r2")]
    assert _codes("cross_sheet_inconsistency", AuditInput(rows=rows, periods=periods, facts=differ))
    flipped = [fact(left, "S!C5", "2024", "10"), fact(right, "T!C5", "2024", "-10", axis="T!r2")]
    assert _codes("cross_sheet_inconsistency", AuditInput(rows=rows, periods=periods, facts=flipped)) == []
    linked = AuditInput(rows=rows, periods=periods, facts=differ, links=link("T!C5", "=S!C5*1.2", right, "2024", ("S!C5",)))
    assert _codes("cross_sheet_inconsistency", linked) == []


def test_formula_class_mismatch_skips_the_first_period_and_known_exceptions():
    periods = _indexed(PERIODS + [{"axis_id": "S!r2", "period_id": "2027", "period_key_base": "2027", "period_marker": None}])
    facts = [fact(A, f"S!{col}5", period["period_id"], "1") for col, period in zip("CDEF", periods, strict=True)]
    links = []
    for col, period, kind in zip("CDEF", periods, ("conditional", "same_period", "same_period", "same_period"), strict=True):
        links += [dict(item, formula_class=kind) for item in link(f"S!{col}5", "=X1", A, period["period_id"], ("S!X1",))]
    found = _codes("formula_class_mismatch", AuditInput(rows=[row(A)], periods=periods, facts=facts, links=links))
    assert found == []
    links = [dict(item, formula_class={"S!C5": "same_period", "S!E5": "cross_period"}.get(item["cell"], item["formula_class"])) for item in links]
    found = _codes("formula_class_mismatch", AuditInput(rows=[row(A)], periods=periods, facts=facts, links=links))
    assert [item.locations[0].cell_id for item in found] == ["S!E5"]
    excused = AuditInput(rows=[row(A, formula_exceptions=["S!E5"])], periods=periods, facts=facts, links=links)
    assert _codes("formula_class_mismatch", excused) == []


def _binding(concept: str, row_key: str, **extra) -> dict:
    return {
        "row_key": row_key,
        "binding_key": f"bk-{row_key}",
        "is_primary": True,
        "status": "bound",
        "effective_concept": concept,
        "source": "inferred",
        **extra,
    }


def _coverage_book(dscr: list[str], target: str | None = None, start: date | None = None) -> AuditInput:
    periods = [
        {
            "axis_id": "S!r2",
            "timeline_id": "S!r2",
            "period_id": str(2025 + index),
            "period_key_base": str(2025 + index),
            "period_index": index,
            "grain": "year",
            "period_start": date(2025 + index, 1, 1),
            "period_end": date(2025 + index, 12, 31),
        }
        for index in range(len(dscr))
    ]
    if start is not None:
        periods[0]["period_start"] = start
    facts, bindings = [], [_binding("cfads", A), _binding("debt_service", B)]
    for period, value in zip(periods, dscr, strict=True):
        facts.append(fact(A, f"S!{period['period_id']}A", period["period_id"], value))
        facts.append(fact(B, f"S!{period['period_id']}B", period["period_id"], "-1"))
    rows = [row(A), row(B)]
    if target is not None:
        facts.append(fact(C, "S!T1", "v", target, axis="P!r1"))
        bindings.append(_binding("target_dscr", C))
        rows.append(row(C))
    return AuditInput(rows=rows, periods=periods, facts=facts, bindings=bindings)


def test_sculpting_deviation_against_target_and_median():
    with_target = _coverage_book(["1.30", "1.30", "1.45"], target="1.30")
    found = _codes("sculpting_deviation", with_target)
    assert found[0].params["basis"] == "target_dscr"
    assert [item.period_id for item in found[0].locations] == ["2027"]
    sculpted = _coverage_book(["1.30", "1.30", "1.30", "1.60"])
    assert _codes("sculpting_deviation", sculpted)[0].params["basis"] == "median"
    spread = _coverage_book(["1.10", "1.40", "1.70", "2.00"])
    assert _codes("sculpting_deviation", spread) == []


def test_sculpting_sees_a_target_restored_after_concept_absent():
    book = _coverage_book(["1.30", "1.30", "1.45"], target="1.30")
    restored = [{**item, "source": "confirmed"} if item["effective_concept"] == "target_dscr" else item for item in book.bindings]
    data = AuditInput(rows=book.rows, periods=book.periods, facts=book.facts, bindings=restored, absent=frozenset({"target_dscr"}))
    assert _codes("sculpting_deviation", data)[0].params["basis"] == "target_dscr"
    hidden = AuditInput(rows=book.rows, periods=book.periods, facts=book.facts, bindings=book.bindings, absent=frozenset({"target_dscr"}))
    assert [item.params["basis"] for item in _codes("sculpting_deviation", hidden)] in ([], ["median"])


def test_period_grain_mismatch_on_a_short_first_test_year():
    short = _coverage_book(["1.3", "1.3"], start=date(2025, 7, 1))
    found = _codes("period_grain_mismatch", short)
    assert [(item.locations[0].period_id, item.params["period_days"], item.params["expected_days"]) for item in found] == [
        ("2025", 184, 365)
    ]
    assert _codes("period_grain_mismatch", _coverage_book(["1.3", "1.3"])) == []


def test_missing_total_row_after_concept_absent():
    data = AuditInput(
        rows=[row(A), row(B)],
        periods=PERIODS,
        bindings=[
            {"row_key": None, "effective_concept": "debt_service", "status": "unknown", "source": "confirmed"},
            _binding("interest", A),
            _binding("principal", B),
        ],
        composition={"debt_service": ("interest", "principal")},
    )
    found = _codes("missing_total_row", data)
    assert found[0].params["concept"] == "debt_service"
    assert "llcr" in found[0].params["needed_by"]
    assert sorted(item.row_key for item in found[0].locations) == [A, B]
