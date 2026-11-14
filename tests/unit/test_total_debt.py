"""Долг: сумма 1410, 1510 и обязательства по аренде на дату."""

from __future__ import annotations

from decimal import Decimal

from finance_analysis.application.catalog import load_catalog
from finance_analysis.application.model_types import load_model_types
from finance_analysis.application.report import render_markdown
from finance_analysis.domain.covenant import select_ratio
from finance_analysis.domain.mapping import assign_rows, marked_line_code

_FORBIDDEN = "Обязательства по финансовой аренде"


def _row(key: str, label: str, **extra) -> dict:
    item = {
        "kind": "fact",
        "binding_key": key,
        "row_key": key,
        "label": label,
        "label_path_text": extra.pop("label_path_text", label),
        "sign": None,
        "unit": "money",
        "sheet": extra.pop("sheet", "Баланс"),
    }
    item.update(extra)
    return item


def _assign(rows: list[dict]) -> dict:
    return assign_rows(rows, [], load_catalog())


def _bind(concept: str, row: str, label: str, **extra) -> dict:
    item = {
        "effective_concept": concept,
        "row_key": row,
        "is_primary": extra.pop("is_primary", True),
        "status": "bound",
        "source": "inferred",
        "label": label,
        "label_path_text": extra.pop("label_path_text", label),
    }
    item.update(extra)
    return item


def _fact(row: str, period: str, value: str, **extra) -> dict:
    item = {
        "row_key": row,
        "axis_id": extra.pop("axis_id", "a"),
        "period_id": period,
        "normalized_value": value,
        "cell_id": extra.pop("cell_id", f"Баланс!{row}"),
    }
    item.update(extra)
    return item


def _period(period: str, *, grain: str = "year", end: str = "2025-12-31", axis: str = "a") -> dict:
    return {
        "axis_id": axis,
        "period_id": period,
        "period_index": 1,
        "grain": grain,
        "timeline_id": "t",
        "period_end": end,
    }


def _common(bindings, facts, periods) -> dict:
    return {
        "facts": facts,
        "bindings": bindings,
        "periods": periods,
        "period_phase": {},
        "explicit_phases": False,
        "sign_convention": "outflow_negative",
        "marker_class": None,
        "absent": frozenset(),
    }


def _debt(bindings, facts, periods, profile=None):
    catalog = load_model_types()
    return select_ratio(
        "total_debt",
        None,
        _common(bindings, facts, periods),
        profile=profile,
        profile_ref=None,
        composed=catalog.composed,
        concepts=catalog.concepts,
        money=frozenset(),
    )


def test_glossary_defines_components_without_the_forbidden_synonym():
    package = load_catalog()
    lease = package.concepts["lease_liability"]
    text = lease.definition["ru"]
    assert _FORBIDDEN not in text
    for phrase in ("приведенн", "НДС", "76.07", "пункт 12", "гипотез"):
        assert phrase.casefold() in text.casefold()
    for concept in ("borrowings_lt", "borrowings_st"):
        body = package.concepts[concept].definition["ru"]
        for phrase in ("процент", "облигац", "вексел", "60", "62", "68"):
            assert phrase in body.casefold(), concept
    assert package.resolve("Обязательства по финансовой аренде") is None
    assert package.resolve("Остаток проектного кредита").concept == "debt_outstanding"
    assert package.resolve("Заемные средства") is None
    assert package.resolve("Займы и кредиты") is None
    assert package.concepts["borrowings_lt"].xref_ifrs
    assert "lease_liability" in package.ids
    assert package.concepts["total_debt"].id == "total_debt"


def test_line_codes_bind_borrowings_and_do_not_bind_lease_from_1520():
    assert marked_line_code("50") is None
    assert marked_line_code("1410") == "1410"
    assert marked_line_code("ф.5 (740)") == "ф.5 (740)"
    glossary_rows = _assign(
        [
            _row("lt", "Заемные средства", line_code="1410"),
            _row("rev", "Выручка"),
            _row("pay", "Кредиторская задолженность", line_code="1520"),
            _row("old", "Займы и кредиты", line_code="610", sheet="Баланс 2010"),
            _row("note", "Амортизация", line_code="ф.5 (740)"),
        ]
    )
    assert glossary_rows["lt"].concept == "borrowings_lt"
    assert glossary_rows["lt"].evidence.get("line_code") == "1410"
    assert glossary_rows["rev"].concept == "revenue"
    assert glossary_rows["pay"].concept == "accounts_payable"
    assert glossary_rows["pay"].concept != "lease_liability"
    assert glossary_rows["old"].concept == "borrowings_st"
    assert glossary_rows["note"].concept == "depreciation_notes"


def test_section_heading_and_model_sheet_split_the_shared_label():
    got = _assign(
        [
            _row(
                "form",
                "Займы и кредиты",
                parent_label="IV. Долгосрочные обязательства",
                label_path_text="IV. Долгосрочные обязательства › Займы и кредиты",
            ),
            _row("model", "Займы и кредиты", sheet="Модель долга"),
            _row("bare", "Заемные средства"),
        ]
    )
    assert got["form"].concept == "borrowings_lt"
    assert got["model"].concept == "debt_outstanding"
    assert got["bare"].concept != "debt_outstanding"
    assert got["bare"].status == "ambiguous"


def test_lease_breakdown_sums_one_level_and_keeps_other_subaccounts():
    got = _assign(
        [
            _row("other", "76.05 Прочие расчёты", label_path_text="76 › 76.05 Прочие расчёты"),
            _row("long", "Долгосрочные", label_path_text="76 › 76.07 Арендные обязательства › Долгосрочные"),
            _row("short", "Краткосрочные", label_path_text="76 › 76.07 Арендные обязательства › Краткосрочные"),
            _row("mixed", "Прочие обязательства", line_code="1450"),
            _row("named", "в том числе обязательства по аренде", line_code="1520"),
        ]
    )
    assert got["other"].concept != "lease_liability"
    assert got["long"].concept == "lease_liability"
    assert got["short"].concept == "lease_liability"
    assert got["long"].is_primary and got["short"].is_primary
    assert got["mixed"].concept != "lease_liability"
    assert got["named"].concept == "lease_liability"


def test_sum_on_one_date_uses_one_lease_level():
    periods = [_period("Y")]
    parts = _debt(
        [
            _bind("borrowings_lt", "lt", "1410", evidence={"line_code": "1410"}),
            _bind("borrowings_st", "st", "1510", evidence={"line_code": "1510"}),
            _bind("lease_liability", "a", "76.07 долгосрочные", label_path_text="76 › 76.07 › долгосрочные"),
            _bind("lease_liability", "b", "76.07 краткосрочные", label_path_text="76 › 76.07 › краткосрочные", is_primary=False),
        ],
        [
            _fact("lt", "Y", "100"),
            _fact("st", "Y", "40"),
            _fact("a", "Y", "7"),
            _fact("b", "Y", "3"),
        ],
        periods,
    )
    assert parts["rows"][0]["value"] == Decimal(150)
    assert parts["rows"][0]["status"] == "computed"
    both = _debt(
        [
            _bind("borrowings_lt", "lt", "1410", evidence={"line_code": "1410"}),
            _bind("borrowings_st", "st", "1510", evidence={"line_code": "1510"}),
            _bind("lease_liability", "total", "76.07 Арендные обязательства", label_path_text="76 › Арендные обязательства"),
            _bind("lease_liability", "a", "долгосрочные", label_path_text="76 › Арендные обязательства › долгосрочные", is_primary=False),
            _bind("lease_liability", "b", "краткосрочные", label_path_text="76 › Арендные обязательства › краткосрочные", is_primary=False),
        ],
        [_fact("lt", "Y", "100"), _fact("st", "Y", "40"), _fact("total", "Y", "10"), _fact("a", "Y", "7"), _fact("b", "Y", "3")],
        periods,
    )
    assert both["rows"][0]["value"] == Decimal(150)


def test_one_c_hypothesis_requires_every_subaccount_and_keeps_an_explicit_zero():
    """Нет субсчёта — нет числа. Ноль и прочерк в существующей ячейке входят в формулу."""

    labels = {
        "1": "76.07.1 Арендные обязательства",
        "2": "76.07.2 Арендные платежи",
        "5": "76.07.5 Проценты по аренде",
        "9": "76.07.9 НДС по аренде",
    }
    numbers = {"1": "1920", "2": "0", "5": "93", "9": "0"}

    def run(include: dict[str, str | None], dashes: frozenset[str] = frozenset()):
        bindings = [
            _bind("borrowings_lt", "lt", "1410", evidence={"line_code": "1410"}),
            _bind("borrowings_st", "st", "1510", evidence={"line_code": "1510"}),
        ]
        facts = [_fact("lt", "Y", "0"), _fact("st", "Y", "0")]
        for key, raw in include.items():
            bindings.append(_bind("lease_liability", key, labels[key], is_primary=key == "1"))
            if key in dashes:
                blank = _fact(key, "Y", "0")
                blank["normalized_value"] = None
                blank["display"] = "—"
                facts.append(blank)
            elif raw is not None:
                facts.append(_fact(key, "Y", raw))
        return _debt(bindings, facts, [_period("Y")])["rows"][0]

    partial = run({"1": "1920", "5": "93"})
    assert partial["value"] is None
    assert partial["status"] == "not_computed"
    assert partial["reason"] == "missing_subaccount"
    assert partial["missing_inputs"] == ["76.07.2", "76.07.9"]
    assert partial["lease_measurement"] == "pv_hypothesis"
    for absent in ("1", "2", "5", "9"):
        got = run({key: numbers[key] for key in numbers if key != absent})
        assert got["value"] is None, absent
        assert got["reason"] == "missing_subaccount", absent
        assert got["missing_inputs"] == [f"76.07.{absent}"], absent
    blank = run({"1": "1920", "2": None, "5": "93", "9": "0"})
    assert blank["value"] is None
    assert blank["missing_inputs"] == ["76.07.2"]
    complete = run(numbers)
    assert complete["value"] == Decimal(1827)
    assert complete["status"] == "computed"
    assert complete["lease_measurement"] == "pv_hypothesis"
    dashed = run(numbers, dashes=frozenset({"9"}))
    assert dashed["value"] == Decimal(1827)
    assert dashed["status"] == "computed"
    zeros = run({"1": "0", "2": "0", "5": "0", "9": "0"})
    assert zeros["value"] == Decimal(0)
    assert zeros["status"] == "computed"


def test_missing_lease_is_not_a_partial_debt_and_confirmed_zero_is():
    missing = _debt(
        [
            _bind("borrowings_lt", "lt", "1410", evidence={"line_code": "1410"}),
            _bind("borrowings_st", "st", "1510", evidence={"line_code": "1510"}),
        ],
        [_fact("lt", "Y", "100"), _fact("st", "Y", "40")],
        [_period("Y")],
    )
    assert missing["status"] == "not_computed"
    assert missing["rows"][0]["value"] is None
    assert "lease_liability" in missing["rows"][0]["missing_inputs"]
    zero = _debt(
        [
            _bind("borrowings_lt", "lt", "1410", evidence={"line_code": "1410"}),
            _bind("borrowings_st", "st", "1510", evidence={"line_code": "1510"}),
            _bind("accounts_payable", "rou", "Пояснение 4.2 права пользования активами отсутствуют", is_primary=False),
            _bind("accounts_payable", "ex", "Применение пункта 11 ФСБУ 25, упрощенный учёт", is_primary=False),
        ],
        [_fact("lt", "Y", "100"), _fact("st", "Y", "40")],
        [_period("Y")],
    )
    assert zero["rows"][0]["value"] == Decimal(140)
    assert zero["rows"][0]["lease_source"] == "confirmed_zero"


def test_section_total_infers_zero_only_when_it_reconciles():
    ok = _debt(
        [
            _bind("section_lt_total", "t", "1400", evidence={"line_code": "1400"}, label_path_text="IV. Долгосрочные обязательства › Итого"),
            _bind("accounts_payable", "o", "Прочие", label_path_text="IV. Долгосрочные обязательства › Прочие"),
            _bind("borrowings_st", "st", "1510", evidence={"line_code": "1510"}),
            _bind("lease_liability", "l", "Обязательства по аренде"),
        ],
        [_fact("t", "Y", "50"), _fact("o", "Y", "50"), _fact("st", "Y", "10"), _fact("l", "Y", "0")],
        [_period("Y")],
    )
    assert ok["rows"][0]["value"] == Decimal(10)
    assert "borrowings_lt" in ok["rows"][0]["inferred_zero"]
    bad = _debt(
        [
            _bind("section_lt_total", "t", "1400", evidence={"line_code": "1400"}, label_path_text="IV. Долгосрочные обязательства › Итого"),
            _bind("accounts_payable", "o", "Прочие", label_path_text="IV. Долгосрочные обязательства › Прочие"),
            _bind("borrowings_st", "st", "1510", evidence={"line_code": "1510"}),
            _bind("lease_liability", "l", "Обязательства по аренде"),
        ],
        [_fact("t", "Y", "80"), _fact("o", "Y", "50"), _fact("st", "Y", "10"), _fact("l", "Y", "0")],
        [_period("Y")],
    )
    assert bad["rows"][0]["value"] is None
    assert "borrowings_lt" in bad["rows"][0]["missing_inputs"]


def test_units_align_and_parentheses_do_not_flip_the_sign():
    aligned = _debt(
        [
            _bind("borrowings_lt", "lt", "1410", unit="тыс. руб.", evidence={"line_code": "1410"}),
            _bind("borrowings_st", "st", "1510", unit="млн руб.", evidence={"line_code": "1510"}),
            _bind("lease_liability", "l", "Обязательства по аренде", unit="тыс. руб."),
        ],
        [_fact("lt", "Y", "100"), _fact("st", "Y", "1"), _fact("l", "Y", "10")],
        [_period("Y")],
    )
    assert aligned["rows"][0]["value"] == Decimal(1110000)
    unknown = _debt(
        [
            _bind("borrowings_lt", "lt", "1410", unit="тыс. руб.", evidence={"line_code": "1410"}),
            _bind("borrowings_st", "st", "1510", evidence={"line_code": "1510"}),
            _bind("lease_liability", "l", "Обязательства по аренде", unit="тыс. руб."),
        ],
        [_fact("lt", "Y", "1"), _fact("st", "Y", "1"), _fact("l", "Y", "1")],
        [_period("Y")],
    )
    assert unknown["rows"][0]["value"] is None
    signed = _debt(
        [
            _bind("borrowings_lt", "lt", "1410", evidence={"line_code": "1410"}),
            _bind("borrowings_st", "st", "1510", evidence={"line_code": "1510"}),
            _bind("lease_liability", "l", "Обязательства по аренде"),
        ],
        [_fact("lt", "Y", "-5", display="(5)"), _fact("st", "Y", "40"), _fact("l", "Y", "10")],
        [_period("Y")],
    )
    assert signed["rows"][0]["value"] == Decimal(45)
    assert signed["rows"][0]["sign_anomaly"] is True


def test_same_date_collapses_equals_and_conflicts_on_difference():
    same = _debt(
        [
            _bind("borrowings_lt", "q", "1410", evidence={"line_code": "1410"}),
            _bind("borrowings_lt", "y", "1410", evidence={"line_code": "1410"}, is_primary=False),
            _bind("borrowings_st", "st", "1510", evidence={"line_code": "1510"}),
            _bind("lease_liability", "l", "Обязательства по аренде"),
        ],
        [
            _fact("q", "Q", "100", axis_id="q"),
            _fact("y", "Y", "100", axis_id="y"),
            _fact("st", "Y", "0", axis_id="y"),
            _fact("l", "Y", "0", axis_id="y"),
        ],
        [_period("Q", grain="quarter", axis="q"), _period("Y", grain="year", axis="y")],
    )
    year = next(row for row in same["rows"] if row["period_id"] == "Y")
    assert year["value"] == Decimal(100)
    clash = _debt(
        [
            _bind("borrowings_lt", "q", "1410", evidence={"line_code": "1410"}),
            _bind("borrowings_lt", "y", "1410", evidence={"line_code": "1410"}, is_primary=False),
            _bind("borrowings_st", "st", "1510", evidence={"line_code": "1510"}),
            _bind("lease_liability", "l", "Обязательства по аренде"),
        ],
        [
            _fact("q", "Q", "100", axis_id="q"),
            _fact("y", "Y", "90", axis_id="y"),
            _fact("st", "Y", "0", axis_id="y"),
            _fact("l", "Y", "0", axis_id="y"),
        ],
        [_period("Q", grain="quarter", axis="q"), _period("Y", grain="year", axis="y")],
    )
    year = next(row for row in clash["rows"] if row["period_id"] == "Y")
    assert year["value"] is None
    assert year["status"] == "not_computed"
    assert year["reason"] == "source_conflict"


def test_quarters_are_not_summed_into_the_year_stock():
    got = _debt(
        [
            _bind("borrowings_lt", "lt", "1410", evidence={"line_code": "1410"}),
            _bind("borrowings_st", "st", "1510", evidence={"line_code": "1510"}),
            _bind("lease_liability", "l", "Обязательства по аренде"),
        ],
        [
            _fact("lt", "Q1", "100"),
            _fact("lt", "Q2", "100"),
            _fact("lt", "Q3", "100"),
            _fact("lt", "Q4", "100"),
            _fact("st", "Q4", "0"),
            _fact("l", "Q4", "0"),
        ],
        [
            _period("Q1", grain="quarter", end="2025-03-31"),
            _period("Q2", grain="quarter", end="2025-06-30"),
            _period("Q3", grain="quarter", end="2025-09-30"),
            _period("Q4", grain="quarter", end="2025-12-31"),
            _period("Y", grain="year", end="2025-12-31"),
        ],
    )
    year = next(row for row in got["rows"] if row["period_id"] == "Y")
    assert year["value"] == Decimal(100)


def test_reclass_between_lines_does_not_change_the_sum():
    def value(lt: str, st: str) -> Decimal:
        got = _debt(
            [
                _bind("borrowings_lt", "lt", "1410", evidence={"line_code": "1410"}),
                _bind("borrowings_st", "st", "1510", evidence={"line_code": "1510"}),
                _bind("lease_liability", "l", "Обязательства по аренде"),
            ],
            [_fact("lt", "Y", lt), _fact("st", "Y", st), _fact("l", "Y", "5")],
            [_period("Y")],
        )
        return got["rows"][0]["value"]

    assert value("80", "20") == value("60", "40") == Decimal(105)


def test_gaap_includes_operating_lease_by_default_and_reports_parts():
    bindings = [
        _bind("borrowings_lt", "lt", "Long-term borrowings"),
        _bind("borrowings_st", "st", "Short-term borrowings"),
        _bind("finance_lease_liability", "f", "Finance lease liability"),
        _bind("operating_lease_liability", "o", "Operating lease liability"),
    ]
    facts = [_fact("lt", "Y", "10"), _fact("st", "Y", "5"), _fact("f", "Y", "7"), _fact("o", "Y", "3")]
    periods = [_period("Y")]
    included = _debt(bindings, facts, periods, {"debt_standard": "gaap"})
    assert included["rows"][0]["value"] == Decimal(25)
    roles = {item["role"]: item["value"] for item in included["rows"][0]["components"]}
    assert roles["finance_lease_liability"] == "7"
    assert roles["operating_lease_liability"] == "3"
    excluded = _debt(bindings, facts, periods, {"debt_standard": "gaap", "include_operating_lease_liability": False})
    assert excluded["rows"][0]["value"] == Decimal(22)
    ras = _debt(
        [
            _bind("borrowings_lt", "lt", "1410", evidence={"line_code": "1410"}),
            _bind("borrowings_st", "st", "1510", evidence={"line_code": "1510"}),
            _bind("lease_liability", "l", "Обязательства по аренде"),
            _bind("operating_lease_liability", "o", "Operating lease liability"),
        ],
        [_fact("lt", "Y", "10"), _fact("st", "Y", "5"), _fact("l", "Y", "7"), _fact("o", "Y", "3")],
        periods,
        {"debt_standard": "ras", "include_operating_lease_liability": False},
    )
    assert ras["rows"][0]["value"] == Decimal(22)
    assert "ФСБУ 4/2023" in ras["rows"][0]["methodology"]


def test_excluded_operating_lease_does_not_change_status_or_sign():
    bindings = [
        _bind("borrowings_lt", "lt", "Long-term borrowings"),
        _bind("borrowings_st", "st", "Short-term borrowings"),
        _bind("finance_lease_liability", "f", "Finance lease liability"),
        _bind("operating_lease_liability", "oq", "Operating lease liability"),
        _bind("operating_lease_liability", "oy", "Operating lease liability", is_primary=False),
    ]
    facts = [
        _fact("lt", "Y", "10"),
        _fact("st", "Y", "5"),
        _fact("f", "Y", "7"),
        _fact("oq", "Y", "-3", display="(3)"),
        _fact("oy", "Y", "9"),
    ]
    periods = [_period("Y")]
    off = _debt(bindings, facts, periods, {"debt_standard": "gaap", "include_operating_lease_liability": False})
    row = off["rows"][0]
    assert row["status"] == "computed"
    assert row["value"] == Decimal(22)
    assert row["sign_anomaly"] is False
    operating = next(item for item in row["components"] if item["role"] == "operating_lease_liability")
    assert operating["included"] is False
    scaled = [
        _bind("borrowings_lt", "lt", "Long-term borrowings"),
        _bind("borrowings_st", "st", "Short-term borrowings"),
        _bind("finance_lease_liability", "f", "Finance lease liability"),
        _bind("operating_lease_liability", "o", "Operating lease liability", unit="тыс. руб."),
    ]
    quiet = _debt(
        scaled,
        [_fact("lt", "Y", "10"), _fact("st", "Y", "5"), _fact("f", "Y", "7"), _fact("o", "Y", "3")],
        periods,
        {"debt_standard": "gaap", "include_operating_lease_liability": False},
    )
    assert quiet["rows"][0]["status"] == "computed"
    assert quiet["rows"][0]["value"] == Decimal(22)
    on = _debt(bindings, facts, periods, {"debt_standard": "gaap", "include_operating_lease_liability": True})
    blocked = on["rows"][0]
    assert blocked["value"] is None
    assert blocked["status"] == "not_computed"
    assert blocked["reason"] == "source_conflict"
    assert blocked["sign_anomaly"] is True


def test_total_borrowings_row_is_used_only_without_the_lines():
    rows = _assign(
        [
            _row("only", "Итого заемные средства"),
        ]
    )
    assert rows["only"].concept == "borrowings_total"
    assert rows["only"].evidence.get("granularity") == "total"
    both = _assign(
        [
            _row("lt", "Заемные средства", line_code="1410"),
            _row("sum", "Итого заемные средства"),
        ]
    )
    assert both["lt"].concept == "borrowings_lt"
    assert both["sum"].is_primary is False
    paren = _assign([_row("row", "Заемные средства (итого)")])
    assert paren["row"].concept == "borrowings_total"
    assert paren["row"].evidence.get("granularity") == "total"
    coded = _assign([_row("row", "Заемные средства (итого)", line_code="1410")])
    assert coded["row"].concept == "borrowings_lt"


def test_ifrs_uses_the_same_three_roles():
    got = _debt(
        [
            _bind("borrowings_lt", "lt", "Long-term borrowings"),
            _bind("borrowings_st", "st", "Short-term borrowings"),
            _bind("lease_liability", "l", "Lease liability"),
        ],
        [_fact("lt", "Y", "10"), _fact("st", "Y", "4"), _fact("l", "Y", "6")],
        [_period("Y")],
        {"debt_standard": "ifrs"},
    )
    assert got["rows"][0]["value"] == Decimal(20)
    assert "IFRS 16" in got["rows"][0]["methodology"]


def test_report_names_the_standard_and_the_lease_source():
    got = _debt(
        [
            _bind("borrowings_lt", "lt", "1410", evidence={"line_code": "1410"}),
            _bind("borrowings_st", "st", "1510", evidence={"line_code": "1510"}),
            _bind("lease_liability", "l", "76.07 Арендные обязательства", label_path_text="76 › Арендные обязательства"),
        ],
        [_fact("lt", "Y", "1"), _fact("st", "Y", "2"), _fact("l", "Y", "3")],
        [_period("Y")],
    )
    text = render_markdown(
        {
            "analysis_id": "a",
            "status": "succeeded",
            "builder_ref": {},
            "versions": {},
            "result_data": {"ratios": [{**got["rows"][0], "metric": "total_debt"}]},
        }
    )
    assert "ФСБУ 4/2023" in text
    assert "76" in text
    assert "total_debt" in text


def test_metric_is_a_sum_in_the_catalog_and_optional_for_corporate():
    catalog = load_model_types()
    formula = catalog.composed["total_debt"]
    assert formula.denominator.plus == () and formula.denominator.minus == ()
    assert catalog.use("corporate", "total_debt") == "optional"
    assert catalog.use("project_finance", "total_debt") == "not_applicable"
    assert "total_debt" in catalog.metric_inputs
