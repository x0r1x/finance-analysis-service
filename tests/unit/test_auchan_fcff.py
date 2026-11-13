"""Ашан: кандидат из предшественников, щит выключен, Outputs!18 не вход."""

from __future__ import annotations

import inspect
import zipfile
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from finance_analysis.application.analyses import Analyses
from finance_analysis.application.catalog import load_catalog
from finance_analysis.application.sheet_roles import load_sheet_roles
from finance_analysis.domain.audit import AuditInput
from finance_analysis.domain.covenant import select_ratio
from finance_analysis.domain.mapping import assign_rows
from finance_analysis.domain.metrics import confirm_paid_interest
from tests.unit.rule_inputs import check, fact, link, row

_MONEY = Decimal("0.000001")
_BOOK = Path(
    "/Users/alekseykashin/projects/finance-context-builder/resources/corpus/АШАН_модель_CF.xlsx"
)
_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_HISTORICAL = "12780359.5"
_OUTPUTS_CELL = "Outputs!U18"
_U18 = "=U11+(1-0.2)*('Фин отчетность РСБУ'!K33)-Outputs!U15"


def test_compute_metrics_passes_graph_links():
    source = inspect.getsource(Analyses.compute_metrics)
    assert '"graph_links"' in source


def test_bare_70_is_not_paid_interest():
    primaries: dict = {}
    injected = confirm_paid_interest(
        primaries,
        [
            {
                "effective_concept": "interest",
                "status": "bound",
                "source": "inferred",
                "row_key": "r38",
                "is_primary": False,
                "line_code": "70",
            }
        ],
    )
    assert injected is None
    assert "interest_paid" not in primaries


def test_row_46_is_operating_cash_flow_and_outputs_18_is_not_project_fcf():
    roles = load_sheet_roles()
    rows = [
        _label("ocf", "ИТОГО - Операционный денежный поток", "Денежные потоки", 46),
        _label("cfo", "Денежный поток от операционной деятельности (CFO)", "Outputs", 11),
        _label("fcf", "Свободный денежный поток (FCF)", "Outputs", 18),
        _label("paid", "Проценты к уплате за кв.", "Денежные потоки", 38, line_code="70"),
    ]
    got = assign_rows(rows, [], load_catalog(), roles=roles)
    assert got["ocf"].concept == "operating_cash_flow"
    assert got["ocf"].is_primary
    assert got["ocf"].evidence.get("line_code") != "стр. 4100"
    assert got["cfo"].concept == "operating_cash_flow"
    assert not got["cfo"].is_primary
    assert got["fcf"].concept != "project_fcf"
    assert got["paid"].concept == "interest"
    assert got["paid"].evidence.get("line_code") != "стр. 4123"


def test_auchan_candidate_does_not_apply_the_shield_or_read_outputs_18():
    periods = [_quarter(index) for index in range(1, 5)]
    bindings = [
        _bind("operating_cash_flow", "ocf", formula="=E43+E44+E45"),
        _bind("capex", "capex"),
        _bind("net_income", "ni"),
        _bind("interest", "accrued"),
        _bind("interest", "r38", primary=False, code="70"),
        _bind("income_tax_rate", "rate"),
    ]
    facts = [_fact("outputs18", "2015Q1", _HISTORICAL, _OUTPUTS_CELL)]
    links = []
    for index, col in enumerate("EFGH", start=1):
        pid = f"2015Q{index}"
        facts.extend(
            [
                _fact("ocf", pid, "100", f"Денежные потоки!{col}46"),
                _fact("capex", pid, "-30", f"Денежные потоки!{col}48"),
                _fact("accrued", pid, "-10", f"ОПиУ!{col}33"),
                _fact("r38", pid, "-10", f"Денежные потоки!{col}38"),
                _fact("rate", pid, "0.2", f"Предпосылки!{col}5"),
                _fact("ni", pid, "40", f"Денежные потоки!{col}43"),
            ]
        )
        links.extend(
            [
                _edge("ocf", f"Денежные потоки!{col}46", f"Денежные потоки!{col}43", pid),
                _edge("ocf", f"Денежные потоки!{col}46", f"Денежные потоки!{col}44", pid),
                _edge("ocf", f"Денежные потоки!{col}46", f"Денежные потоки!{col}45", pid),
                _edge("ni", f"Денежные потоки!{col}43", f"Денежные потоки!{col}41", pid, "E41-E42"),
                _edge("nwc", f"Денежные потоки!{col}45", None, pid, "Предпосылки!G51"),
            ]
        )
    book = [{"cell_id": _OUTPUTS_CELL, "value": _HISTORICAL, "calendar_year": 2015}]
    got = _run(bindings, facts, periods, links, book)
    assert got["status"] == "not_computed"
    assert [row["period_id"] for row in got["rows"]] == [item["period_id"] for item in periods]
    for item in got["rows"]:
        assert item["value"] is None
        assert item["reason"] == "interest_paid_unconfirmed"
        assert "interest_paid" not in item
        assert _OUTPUTS_CELL not in str(item)
        assert _HISTORICAL not in str(item)
    [note] = [item for item in got["warnings"] if item["code"] == "fcff_book_mismatch"]
    assert note["params"]["cell"] == _OUTPUTS_CELL
    assert note["params"]["book"] == Decimal(_HISTORICAL)
    assert note["params"]["fas"] is None
    assert note["params"]["calendar_year"] == 2015
    assert "не посчитан" in note["params"]["message"]


def test_cell_ref_text_without_a_bound_precedent_stays_unknown():
    got = _run(
        [_bind("operating_cash_flow", "ocf", formula="=E43+E44+E45"), _bind("capex", "capex")],
        [_fact("ocf", "2015Q1", "100", "Денежные потоки!E46"), _fact("capex", "2015Q1", "-30", "Денежные потоки!E48")],
        [_quarter(1)],
        [_edge("ocf", "Денежные потоки!E46", "Денежные потоки!E45", "2015Q1")],
    )
    assert got["rows"][0]["reason"] == "ocf_basis_unknown"
    assert got["rows"][0]["value"] is None


def test_precedent_concepts_override_a_named_formula():
    got = _run(
        [
            _bind("operating_cash_flow", "ocf", formula="net_income+depreciation"),
            _bind("capex", "capex"),
            _bind("net_income", "ni"),
            _bind("interest", "r38", code="70"),
            _bind("income_tax_rate", "rate"),
        ],
        [
            _fact("ocf", "2015Q1", "100", "Денежные потоки!E46"),
            _fact("capex", "2015Q1", "-30", "Денежные потоки!E48"),
            _fact("ni", "2015Q1", "40", "Денежные потоки!E43"),
            _fact("r38", "2015Q1", "-10", "Денежные потоки!E38"),
            _fact("rate", "2015Q1", "0.2", "Предпосылки!E5"),
        ],
        [_quarter(1)],
        [
            _edge("ocf", "Денежные потоки!E46", "Денежные потоки!E43", "2015Q1", "net_income+depreciation"),
            _edge("ocf", "Денежные потоки!E46", "Денежные потоки!E38", "2015Q1", "net_income+depreciation"),
            _edge("ni", "Денежные потоки!E43", "Денежные потоки!E41", "2015Q1", "E41-E42"),
            _edge("r38", "Денежные потоки!E38", None, "2015Q1", "РСБУ!K33"),
        ],
    )
    assert got["rows"][0]["reason"] == "ocf_basis_unknown"
    assert got["rows"][0]["value"] is None


def test_interest_precedent_is_not_a_candidate():
    got = _run(
        [
            _bind("operating_cash_flow", "ocf", formula="=E43+E38"),
            _bind("capex", "capex"),
            _bind("net_income", "ni"),
            _bind("interest", "r38", code="70"),
            _bind("income_tax_rate", "rate"),
        ],
        [
            _fact("ocf", "2015Q1", "100", "Денежные потоки!E46"),
            _fact("capex", "2015Q1", "-30", "Денежные потоки!E48"),
            _fact("ni", "2015Q1", "40", "Денежные потоки!E43"),
            _fact("r38", "2015Q1", "-10", "Денежные потоки!E38"),
            _fact("rate", "2015Q1", "0.2", "Предпосылки!E5"),
        ],
        [_quarter(1)],
        [
            _edge("ocf", "Денежные потоки!E46", "Денежные потоки!E43", "2015Q1"),
            _edge("ocf", "Денежные потоки!E46", "Денежные потоки!E38", "2015Q1", "E43+E38"),
            _edge("ni", "Денежные потоки!E43", "Денежные потоки!E41", "2015Q1", "E41-E42"),
            _edge("r38", "Денежные потоки!E38", None, "2015Q1", "РСБУ!K33"),
        ],
    )
    assert got["rows"][0]["reason"] == "ocf_basis_unknown"
    assert got["rows"][0]["value"] is None


def test_annual_book_check_sums_quarters_and_does_not_read_the_book_cell():
    periods = [_quarter(index, year=2016) for index in range(1, 5)]
    bindings, facts, _links = _included(periods)
    facts.append(_fact("outputs18", "2016Q1", _HISTORICAL, "Outputs!V18"))
    differed = _run(
        bindings,
        facts,
        periods,
        book=[{"cell_id": "Outputs!V18", "value": "1000", "calendar_year": 2016}],
    )
    assert [row["value"] for row in differed["rows"]] == [Decimal(78).quantize(_MONEY)] * 4
    assert [row["period_id"] for row in differed["rows"]] == [item["period_id"] for item in periods]
    for item in differed["rows"]:
        assert "Outputs!V18" not in str(item.get("components"))
        assert _HISTORICAL not in str(item["value"])
    [note] = [item for item in differed["warnings"] if item["code"] == "fcff_book_mismatch"]
    assert note["params"]["fas"] == Decimal(312).quantize(_MONEY)
    assert note["params"]["book"] == Decimal(1000)
    assert note["params"]["cell"] == "Outputs!V18"

    matched = _run(
        bindings,
        facts,
        periods,
        book=[{"cell_id": "Outputs!V18", "value": "312", "calendar_year": 2016}],
    )
    assert not any(item["code"] == "fcff_book_mismatch" for item in matched["warnings"])

    # Одинаковая ставка 0.2 на три квартала раскрывается на весь год. Дыра — капекс.
    partial_facts = [
        item
        for item in facts
        if not (item["row_key"] == "capex" and item["period_id"] == "2016Q4")
    ]
    partial = _run(
        bindings,
        partial_facts,
        periods,
        book=[{"cell_id": "Outputs!V18", "value": "234", "calendar_year": 2016}],
    )
    assert [row["value"] for row in partial["rows"]] == [Decimal(78).quantize(_MONEY)] * 3 + [None]
    [gap] = [item for item in partial["warnings"] if item["code"] == "fcff_book_mismatch"]
    assert gap["params"]["fas"] is None
    assert gap["params"]["book"] == Decimal(234)
    assert "не посчитан" in gap["params"]["message"]

    absent_ocf = [
        item
        for item in facts
        if not (item["row_key"] == "ocf" and item["period_id"] == "2016Q4")
    ]
    dropped = _run(
        bindings,
        absent_ocf,
        periods,
        book=[{"cell_id": "Outputs!V18", "value": "234", "calendar_year": 2016}],
    )
    [hole] = [item for item in dropped["warnings"] if item["code"] == "fcff_book_mismatch"]
    assert hole["params"]["fas"] is None


def test_outputs_row_18_literal_is_point_two():
    key = "Outputs|18|Outputs!r1"
    data = AuditInput(
        rows=[row(key, label="Свободный денежный поток (FCF)", sheet="Outputs")],
        periods=[{"axis_id": "Outputs!r1", "period_id": "2015", "period_key_base": "2015"}],
        facts=[fact(key, _OUTPUTS_CELL, "2015", _HISTORICAL, axis="Outputs!r1")],
        links=link(_OUTPUTS_CELL, _U18, key, "2015", refs=("Outputs!U11",)),
    )
    [found] = check("literal_in_formula", data)
    assert found.params["literals"] == ["0.2"]
    assert found.binding_key == "bk-Outputs-18"
    assert found.locations[0].cell_id == _OUTPUTS_CELL


def test_auchan_workbook_formulas_and_literal():
    if not _BOOK.is_file():
        pytest.skip(f"нет книги {_BOOK}")
    outputs = _sheet_cells(_BOOK, "xl/worksheets/sheet13.xml", {15, 18})
    cash = _sheet_cells(_BOOK, "xl/worksheets/sheet9.xml", {38, 46})
    ras = _sheet_cells(_BOOK, "xl/worksheets/sheet2.xml", {33, 136})
    formulas = [(ref, formula) for ref, formula, _value in outputs[18] if formula]
    assert ("U18", _U18) in [(ref, "=" + formula) for ref, formula in formulas]
    assert all("0.2" in formula for _ref, formula in formulas)
    # В xlsx литерал стоит в U18:Z18, по одному разу. В постановке сказано «десять раз».
    assert len(formulas) == 6
    cached = {ref: value for ref, _formula, value in outputs[18]}
    assert cached["U18"] == _HISTORICAL
    by_ref = {ref: formula for ref, formula, _value in outputs[15]}
    assert "U15/4*3" in by_ref["V15"]
    assert "/4" not in by_ref["W15"]
    assert "V15" in {ref: formula for ref, formula, _value in outputs[18]}["V18"]
    assert "E43+E44+E45" in {ref: formula for ref, formula, _value in cash[46]}["E46"]
    assert "4123" not in {ref: value or formula or "" for ref, formula, value in cash[38]}["D38"]
    assert {ref: value for ref, _formula, value in ras[33]}["D33"] == "70"
    assert {ref: value for ref, _formula, value in ras[136]}["D136"] == "70"
    key = "Outputs|18|Outputs!r1"
    data = AuditInput(
        rows=[row(key, label="Свободный денежный поток (FCF)", sheet="Outputs")],
        periods=[{"axis_id": "Outputs!r1", "period_id": "2015", "period_key_base": "2015"}],
        facts=[fact(key, ref if "!" in ref else f"Outputs!{ref}", "2015", "1", axis="Outputs!r1") for ref, _formula in formulas],
        links=[
            item
            for ref, formula in formulas
            for item in link(f"Outputs!{ref}", "=" + formula, key, "2015", refs=("Outputs!U11",))
        ],
    )
    [found] = check("literal_in_formula", data)
    assert found.params["literals"] == ["0.2"]
    assert found.params["cells"] == len(formulas)


def _run(bindings, facts, periods, links=(), book=()):
    return select_ratio(
        "fcff",
        None,
        {
            "facts": facts,
            "bindings": bindings,
            "periods": periods,
            "sign_convention": "outflow_negative",
            "absent": frozenset(),
            "graph_links": list(links),
            "book_fcff": list(book),
        },
        profile=None,
        profile_ref=None,
        composed={},
        concepts=frozenset(),
        money=frozenset(),
    )


def _included(periods):
    bindings = [
        _bind("operating_cash_flow", "ocf", code="стр. 4100"),
        _bind("capex", "capex"),
        _bind("interest", "paid", code="стр. 4123"),
        _bind("income_tax_rate", "rate"),
    ]
    facts = []
    for index, period in enumerate(periods, start=1):
        pid = period["period_id"]
        facts.extend(
            [
                _fact("ocf", pid, "100", f"S!A{index}"),
                _fact("capex", pid, "-30", f"S!B{index}"),
                _fact("paid", pid, "-10", f"S!C{index}"),
                _fact("rate", pid, "0.2", f"S!D{index}"),
            ]
        )
    return bindings, facts, []


def _label(key: str, label: str, sheet: str, number: int, **extra) -> dict:
    return {
        "kind": "fact",
        "binding_key": key,
        "row_key": key,
        "label": label,
        "sheet": sheet,
        "row_num": number,
        "sign": None,
        "unit": "money",
        **extra,
    }


def _bind(concept, row_key, *, primary=True, code=None, formula=None):
    item = {
        "effective_concept": concept,
        "row_key": row_key,
        "binding_key": row_key,
        "is_primary": primary,
        "status": "bound",
        "source": "inferred",
    }
    if code:
        item["line_code"] = code
    if formula:
        item["formula"] = formula
    return item


def _fact(row_key, period, value, cell):
    return {
        "row_key": row_key,
        "axis_id": "a",
        "period_id": period,
        "normalized_value": value,
        "cell_id": cell,
    }


def _edge(row_key, cell, ref, period, formula="E43+E44+E45"):
    return {
        "model_id": "m",
        "build_key": "b",
        "cell": cell,
        "formula": formula,
        "formula_class": "same_period",
        "ref_cell": ref,
        "row_key": row_key,
        "period_id": period,
        "truncated": False,
    }


def _quarter(index: int, *, year: int = 2015) -> dict:
    return {
        "axis_id": "a",
        "period_id": f"{year}Q{index}",
        "period_index": index,
        "timeline_id": "t",
        "grain": "quarter",
        "calendar_year": year,
    }


def _sheet_cells(path: Path, sheet: str, wanted: set[int]) -> dict[int, list[tuple[str, str | None, str | None]]]:
    with zipfile.ZipFile(path) as book:
        strings = [
            "".join(node.text or "" for node in item.iter(_MAIN + "t"))
            for item in ET.fromstring(book.read("xl/sharedStrings.xml")).findall("m:si", _NS)
        ]
        root = ET.fromstring(book.read(sheet))
    found = {number: [] for number in wanted}
    for sheet_row in root.findall("m:sheetData/m:row", _NS):
        number = int(sheet_row.attrib.get("r") or 0)
        if number not in wanted:
            continue
        for cell in sheet_row.findall("m:c", _NS):
            ref = cell.attrib.get("r") or ""
            formula = cell.find("m:f", _NS)
            value = cell.find("m:v", _NS)
            text = None
            if value is not None and value.text:
                text = strings[int(value.text)] if cell.attrib.get("t") == "s" else value.text
            found[number].append((ref, None if formula is None else formula.text, text))
    return found
