"""Синтетическая книга: нарастающий ОПиУ, квартальные проценты и ICR.

Числа и подписи выдуманы. Они повторяют раскладку листов, а не частную книгу.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Font

from finance_analysis.domain.cover_metrics import ratio_cells
from finance_analysis.domain.metrics import SCALE_ASSUMED, coverage_ratio
from finance_analysis.domain.period_basis import classify_period_basis
from tests.unit.test_row_selection import _assigned, _row

_TITLE = "ОПиУ (указан накопленным итогом за год)"
_SUBTOTAL = "Прибыль (убыток) от реализации"
_CF_INTEREST = "Проценты к уплате за кв."
_PL_INTEREST = "Проценты к уплате "
_DEBT = "Финансовый долг (все займы, кредиты, остаток долга по финансовому лизингу)"


def _quarter_end(year: int, quarter: int) -> date:
    month = 3 * quarter
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


def _quarter_start(year: int, quarter: int) -> date:
    return date(year, 3 * (quarter - 1) + 1, 1)


def _col(index: int) -> str:
    letters = ""
    number = index
    while number:
        number, rest = divmod(number - 1, 26)
        letters = chr(65 + rest) + letters
    return letters


def _book():
    """Три рабочих листа и баланс. Ось ОПиУ начинается с четвёртого квартала."""

    cf_periods = [(2024, quarter) for quarter in range(1, 5)] + [(2025, quarter) for quarter in range(1, 5)]
    pl_periods = [(2024, 4)] + [(2025, quarter) for quarter in range(1, 5)]
    book = Workbook()
    cf = book.active
    cf.title = "CF"
    pl = book.create_sheet("PL")
    ratios = book.create_sheet("Ratios")
    balance = book.create_sheet("Balance")
    calendar_sheet = book.create_sheet("Calendar")

    for index, (year, quarter) in enumerate(cf_periods, start=4):
        column = _col(index)
        cf[f"{column}4"] = f"{quarter} кв. {year}"
        cf[f"{column}5"] = -10
        cf[f"{column}8"] = 100
    cf["C5"] = _CF_INTEREST
    cf["C8"] = _DEBT

    pl["C10"] = _TITLE
    pl["C11"] = "Выручка"
    pl["C15"] = _SUBTOTAL
    pl["C17"] = "=LEFT('CF'!C5,LEN('CF'!C5)-6)"
    pl["C22"] = "Налог"
    for cell in ("C11", "C15", "C22"):
        pl[cell].font = Font(bold=True)
    for index, (year, quarter) in enumerate(pl_periods, start=4):
        column = _col(index)
        calendar_sheet[f"{column}1"] = f"{quarter} кв. {year}"
        pl[f"{column}10"] = f"=Calendar!{column}1"
        letters = []
        for older in range(quarter):
            older_year = year
            older_quarter = older + 1
            letters.append(_col(4 + cf_periods.index((older_year, older_quarter))))
        added = "+".join(f"'CF'!{letter}5" for letter in reversed(letters))
        current = f"'CF'!{letters[-1]}5"
        pl[f"{column}17"] = (
            f'=IF({current}="","",IF(LEFT({column}$10,1)="1",{current},'
            f'IF(LEFT({column}$10,1)="2",{added if quarter == 2 else current},'
            f'IF(LEFT({column}$10,1)="3",{added if quarter == 3 else current},{added}))))'
        )
        pl[f"{column}12"] = 1
        pl[f"{column}20"] = 1

    ratios["C1"] = "(рассчитаны за 12 месяцев)"
    ratios["C2"] = "тыс."
    ratios["C3"] = "EBITDA"
    ratios["C5"] = "ICR"
    for index, (year, quarter) in enumerate(pl_periods, start=4):
        column = _col(index)
        ratios[f"{column}1"] = f"{quarter} кв. {year}"
        ratios[f"{column}3"] = 40
        ratios[f"{column}5"] = 1

    balance["C4"] = "Займы и кредиты"
    balance["C8"] = "Займы и кредиты"
    balance["D4"] = 5
    balance["D8"] = 5
    return book, cf_periods, pl_periods


def _model():
    book, cf_periods, pl_periods = _book()
    rows = []
    links = []
    facts = []
    calendar = {}
    series: dict[str, dict] = {}

    def add_period(axis: str, year: int, quarter: int, index: int, header: str) -> str:
        period_id = f"{axis}-{year}Q{quarter}"
        calendar[(axis, period_id)] = {
            "grain": "quarter",
            "period_start": _quarter_start(year, quarter),
            "period_end": _quarter_end(year, quarter),
            "period_index": index,
            "calendar_year": year,
            "header_text": header,
        }
        return period_id

    for index, (year, quarter) in enumerate(cf_periods):
        period_id = add_period("cf", year, quarter, index, f"{quarter} кв. {year}")
        column = _col(index + 4)
        for key, row_number, value in (("cf-interest", 5, Decimal(-10)), ("cf-debt", 8, Decimal(100))):
            cell = f"CF!{column}{row_number}"
            facts.append(
                {
                    "row_key": key,
                    "axis_id": "cf",
                    "period_id": period_id,
                    "value_dec": value,
                    "normalized_value": value,
                    "cell_id": cell,
                }
            )
            series.setdefault(key, {})[("cf", period_id)] = value
            links.append(
                {
                    "cell": cell,
                    "row_key": key,
                    "period_id": period_id,
                    "formula": None,
                    "formula_class": None,
                    "ref_cell": None,
                }
            )

    rows.append(_row("cf-interest", _CF_INTEREST, sheet="CF", row_num=5, kind="fact"))
    rows.append(_row("cf-debt", _DEBT, sheet="CF", row_num=8, kind="fact"))

    rows.append(_row("pl-title", _TITLE, sheet="PL", row_num=10, kind="abstract", indent=0))
    for key, number, label in (
        ("pl-revenue-head", 11, "Выручка"),
        ("pl-subtotal", 15, _SUBTOTAL),
        ("pl-tax-head", 22, "Налог"),
    ):
        rows.append(_row(key, label, sheet="PL", row_num=number, kind="abstract", indent=0))
    pl_path = [_TITLE, _SUBTOTAL]
    rows.append(
        _row(
            "pl-revenue",
            "Выручка",
            sheet="PL",
            row_num=12,
            kind="fact",
            indent=0,
            label_path=list(pl_path),
        )
    )
    rows.append(
        _row(
            "pl-interest",
            _PL_INTEREST,
            sheet="PL",
            row_num=17,
            kind="fact",
            indent=1,
            label_path=list(pl_path),
            block_id="pl",
        )
    )
    rows.append(
        _row(
            "pl-tax",
            "Налог",
            sheet="PL",
            row_num=20,
            kind="fact",
            indent=0,
            label_path=list(pl_path),
        )
    )

    for index, (year, quarter) in enumerate(pl_periods):
        period_id = add_period("pl", year, quarter, index, f"{quarter} кв. {year}")
        column = _col(index + 4)
        source_index = cf_periods.index((year, quarter))
        letters = [_col(4 + cf_periods.index((year, older + 1))) for older in range(quarter)]

        def _sum(taken: list[str]) -> str:
            return "+".join(f"'CF'!{letter}5" for letter in reversed(taken))

        one = _sum(letters[-1:])
        two = _sum(letters[-2:]) if len(letters) >= 2 else one
        three = _sum(letters[-3:]) if len(letters) >= 3 else one
        formula = (
            f'=IF({one}="","",IF(LEFT({column}$10,1)="1",{one},'
            f'IF(LEFT({column}$10,1)="2",{two},IF(LEFT({column}$10,1)="3",{three},{_sum(letters)}))))'
        )
        cell = f"PL!{column}17"
        for letter in letters:
            links.append(
                {
                    "cell": cell,
                    "row_key": "pl-interest",
                    "period_id": period_id,
                    "formula": formula,
                    "formula_class": "add",
                    "ref_cell": f"CF!{letter}5",
                }
            )
        links.append(
            {
                "cell": cell,
                "row_key": "pl-interest",
                "period_id": period_id,
                "formula": formula,
                "formula_class": "add",
                "ref_cell": f"PL!{column}10",
            }
        )
        for key, row_number in (("pl-revenue", 12), ("pl-tax", 20)):
            series.setdefault(key, {})[("pl", period_id)] = Decimal(1)
        series.setdefault("pl-interest", {})[("pl", period_id)] = Decimal(-10 * quarter)
        del source_index

    for index, (year, quarter) in enumerate(pl_periods):
        period_id = add_period("ratios", year, quarter, index, f"{quarter} кв. {year}")
        column = _col(index + 4)
        facts.append(
            {
                "row_key": "ratios-ebitda",
                "axis_id": "ratios",
                "period_id": period_id,
                "value_dec": Decimal(40),
                "normalized_value": Decimal(40000),
                "scale_factor": 1000,
                "cell_id": f"Ratios!{column}3",
            }
        )
        series.setdefault("ratios-ebitda", {})[("ratios", period_id)] = Decimal(40000)
        series.setdefault("ratios-icr", {})[("ratios", period_id)] = Decimal(1)

    rows.append(
        _row(
            "ratios-ebitda",
            "EBITDA",
            sheet="Ratios",
            row_num=3,
            kind="fact",
            parent_label="(рассчитаны за 12 месяцев)",
        )
    )
    rows.append(_row("ratios-icr", "ICR", sheet="Ratios", row_num=5, kind="fact"))
    for key, number in (("balance-a", 4), ("balance-b", 8)):
        rows.append(_row(key, "Займы и кредиты", sheet="Balance", row_num=number, kind="fact"))
        period_id = "balance-2025Q4"
        if ("balance", period_id) not in calendar:
            calendar[("balance", period_id)] = {
                "grain": "quarter",
                "period_start": _quarter_start(2025, 4),
                "period_end": _quarter_end(2025, 4),
                "period_index": 0,
                "calendar_year": 2025,
                "header_text": "4 кв. 2025",
            }
        series.setdefault(key, {})[("balance", period_id)] = Decimal(5)

    book.close()
    return {
        "rows": rows,
        "links": links,
        "facts": facts,
        "calendar": calendar,
        "series": series,
        "cf_periods": cf_periods,
        "pl_periods": pl_periods,
    }


def _assigned_book(model: dict):
    return _assigned(
        model["rows"],
        periods=model["series"],
        calendar=model["calendar"],
        links=model["links"],
        facts=model["facts"],
    )


def test_synthetic_book_tags_the_income_statement_as_year_to_date():
    model = _model()
    got = _assigned_book(model)
    for key in ("pl-revenue", "pl-interest", "pl-tax"):
        assert got[key].evidence["period_basis"] == "ytd"
        assert got[key].evidence["period_basis_source"] == "header"
    bare = _row(
        "pl-interest",
        _PL_INTEREST,
        sheet="PL",
        row_num=17,
        label_path=[_TITLE, _SUBTOTAL, _PL_INTEREST.strip()],
    )
    assert classify_period_basis(bare, calendar=None, links=None, series=None) == ("ytd", "header")
    formula_only = _row("pl-interest", _PL_INTEREST.strip(), sheet="PL", row_num=17, label_path=[_SUBTOTAL])
    assert classify_period_basis(
        formula_only,
        calendar=model["calendar"],
        links=model["links"],
        series=model["series"]["pl-interest"],
        facts=model["facts"],
    ) == ("ytd", "formula")
    assert got["cf-interest"].evidence.get("role") != "component"
    assert got["cf-interest"].evidence["period_basis"] == "period"
    assert got["cf-interest"].is_primary
    assert got["pl-interest"].is_primary is False
    assert got["cf-debt"].evidence["match_strength"] == "exact"
    assert got["cf-debt"].is_primary
    assert got["cf-debt"].status == "bound"
    assert got["balance-a"].is_primary is False
    assert got["balance-b"].is_primary is False
    assert got["balance-a"].status != "ambiguous"
    assert got["ratios-ebitda"].evidence["period_basis"] == "ltm"
    periods = [
        {"axis_id": axis, "period_id": period_id, **meta}
        for (axis, period_id), meta in model["calendar"].items()
    ]
    bindings = [
        _ratio_binding("ebitda", "ratios-ebitda", got["ratios-ebitda"]),
        _ratio_binding("interest", "cf-interest", got["cf-interest"]),
    ]
    result = coverage_ratio(
        metric="icr",
        facts=model["facts"],
        bindings=bindings,
        periods=periods,
        period_phase={},
        explicit_phases=False,
    )
    last = next(row for row in result["rows"] if row["period_id"] == "ratios-2025Q4")
    assert last["status"] == "computed"
    assert last["axis_id"] == "ratios"
    assert last["value"] == Decimal("1.0000000000")
    assert len(last["components"]["interest"]) == 4
    assert last["components"]["ebitda"]
    assert last["scale_factor"]["ebitda"] == 1000
    assert last["scale_factor"]["interest"] is None
    assert result["warnings"] == [{"code": "scale_assumed", "params": {"message": SCALE_ASSUMED}}]
    book, _cf_periods, _pl_periods = _book()
    assert book["Ratios"]["C2"].value == "тыс."
    assert all(book["CF"][f"{column}1"].value is None for column in "CDEFGHIJK")
    cited = ratio_cells(last, model["facts"], bindings, periods, frozenset())
    assert {item["cell_id"] for item in cited} == set(last["components"]["interest"]) | set(last["components"]["ebitda"])


def _ratio_binding(concept: str, key: str, item) -> dict:
    return {
        "effective_concept": concept,
        "row_key": key,
        "status": "bound",
        "is_primary": True,
        "evidence_json": json.dumps(
            {
                "period_basis": item.evidence["period_basis"],
                "period_basis_source": item.evidence["period_basis_source"],
            }
        ),
    }
