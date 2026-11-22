"""R1C1 одного прохода и отрезки ряда."""

from finance_analysis.domain.formula_shape import _REF, normalize, series_kind


def test_year_inside_a_name_is_not_a_cell():
    # Имя целиком. Кусок e2025 внутри Revenue2025 — не адрес.
    for name in ("Revenue2025", "Budget2025", "Выручка2025"):
        assert _REF.search(name) is None
        assert _REF.search(f"={name}+1") is None
    assert _REF.fullmatch("A1").group("col") == "A"
    assert _REF.fullmatch("$A$1").group("abscol") == "$"
    assert _REF.fullmatch("Sheet1!A1").group("sheet") == "Sheet1"
    assert _REF.fullmatch("'Лист'!A1").group("sheet") == "'Лист'"
    kept = normalize(
        "=Revenue2025+A1",
        host_sheet="S",
        host_col=2,
        host_row=1,
        year_at=lambda *_: None,
        host_year=None,
    )
    assert kept.startswith("Revenue2025+")
    assert "R2025" not in kept


def test_copied_formula_is_one_pattern():
    left = normalize("=C10+1", host_sheet="S", host_col=4, host_row=10, year_at=lambda *_: None, host_year=None)
    right = normalize("=D10+1", host_sheet="S", host_col=5, host_row=10, year_at=lambda *_: None, host_year=None)
    assert left == right == "RC[-1]+1"


def test_absolute_range_does_not_drift_across_columns():
    formula = "=LOOKUP(YEAR(M7),$M$185:$AY$185,$M$189:$AY$189)"
    left = normalize(formula, host_sheet="PF Model", host_col=13, host_row=356, year_at=lambda *_: None, host_year=None)
    shifted = formula.replace("M7", "N7")
    right = normalize(shifted, host_sheet="PF Model", host_col=14, host_row=356, year_at=lambda *_: None, host_year=None)
    assert left == right
    assert "$" not in left


def test_quarter_block_of_this_year_is_one_token():
    def year_at(sheet: str, col: int) -> int | None:
        if sheet != "Денежные потоки":
            return None
        return 2016 if 6 <= col <= 9 else 2017 if 10 <= col <= 13 else None

    first = normalize(
        "=SUM('Денежные потоки'!F38:I38)",
        host_sheet="Outputs",
        host_col=22,
        host_row=34,
        year_at=year_at,
        host_year=2016,
    )
    second = normalize(
        "=SUM('Денежные потоки'!J38:M38)",
        host_sheet="Outputs",
        host_col=23,
        host_row=34,
        year_at=year_at,
        host_year=2017,
    )
    assert first == second == "SUM(«год»)"


def test_dscr_keeps_four_patterns_after_year_collapse():
    def year_at(sheet: str, col: int) -> int | None:
        if sheet != "Денежные потоки":
            return None
        if col < 6:
            return None
        return 2016 + (col - 6) // 4

    formulas = {
        21: "(U11+'Фин отчетность РСБУ'!K33-Outputs!U15)/('Фин отчетность РСБУ'!K33+'Фин отчетность РСБУ'!O97)",
        22: "(V11+SUM('Денежные потоки'!F38:I38)-V15)/(SUM('Денежные потоки'!F38:I38)+SUM('Денежные потоки'!F54:I54)+SUM('Денежные потоки'!F58:I58))",
        23: "(W11+SUM('Денежные потоки'!J38:M38)-W15+2000000)/(SUM('Денежные потоки'!J38:M38)++SUM('Денежные потоки'!J54:M54)+SUM('Денежные потоки'!J58:M58))",
        24: "(X11+SUM('Денежные потоки'!N38:Q38)-X15+2000000)/(SUM('Денежные потоки'!N38:Q38)+SUM('Денежные потоки'!N54:Q54)+SUM('Денежные потоки'!N58:Q58))",
        25: "(Y11+SUM('Денежные потоки'!R38:U38)-Y15+2000000)/(SUM('Денежные потоки'!R38:U38)+SUM('Денежные потоки'!R54:U54)+SUM('Денежные потоки'!R58:U58))",
        26: "(Z11+SUM('Денежные потоки'!V38:Y38)-Z15+2000000)/(SUM('Денежные потоки'!V38:Y38)+SUM('Денежные потоки'!V54:Y54)+SUM('Денежные потоки'!V58:Y58))",
    }
    patterns = [
        normalize(formula, host_sheet="Outputs", host_col=col, host_row=34, year_at=year_at, host_year=2015 + (col - 21))
        for col, formula in formulas.items()
    ]
    assert len(set(patterns)) == 4
    assert patterns[3] == patterns[4] == patterns[5]
    assert series_kind([(col, pattern) for col, pattern in zip(formulas, patterns, strict=True)]) == "break"


def test_opening_cell_and_two_segments():
    assert series_kind([(1, "a"), (2, "b"), (3, "b")]) == "opening"
    assert series_kind([(1, "a"), (2, "a"), (3, "b"), (4, "b")]) == "segment"
    assert series_kind([(1, "a"), (2, "b"), (3, "a")]) == "break"
