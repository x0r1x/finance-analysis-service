"""Ашан: три потока есть, общего интервала нет. Цитата NCF не вход."""

from __future__ import annotations

import os
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from finance_analysis.application.catalog import load_catalog
from finance_analysis.application.sheet_roles import load_sheet_roles
from finance_analysis.domain.covenant import select_ratio
from finance_analysis.domain.mapping import assign_rows, marked_line_code

_BOOK = Path(
    os.environ.get(
        "FAS_AUCHAN_BOOK",
        "/Users/alekseykashin/projects/finance-context-builder/resources/corpus/АШАН_модель_CF.xlsx",
    )
)
_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_RID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
_WATCH = frozenset(
    {
        "operating_cash_flow",
        "investing_cash_flow",
        "financing_cash_flow",
        "capex",
        "debt_service",
        "interest",
        "cash",
        "cash_balance",
    }
)
_QUARTER = re.compile(r"(?i)\d\s*кв")
_YEAR = re.compile(r"^(?:19|20)\d{2}$")
_NUMBER = re.compile(r"^-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$")
_INTEREST = "Проценты к уплате"
_CAPEX = "Капитальные затраты без учета приобретений с учетом НДС за кв."
_QUOTE = (
    "Денежный поток от операционной деятельности на i-ом интервале планирования (CFO)"
    " + Денежный поток от инвестиционной деятельности на i-ом интервале планирования (CFI)"
    " + Денежный поток от финансовой деятельности на i-ом интервале планирования (CFF)"
)
# sheet, row, label, concept, primary, status. Кода строки нет ни у одной.
_BOUND = (
    ("Фин отчетность РСБУ", 33, "- Проценты к уплате", "interest", False, "bound"),
    ("Фин отчетность РСБУ", 76, "Денежные средства", "cash", False, "bound"),
    ("Фин отчетность РСБУ", 136, _INTEREST, "interest", False, "bound"),
    # «Финансовые расходы (процентные расходы)» резолвится в finance_costs, не в interest.
    ("Фин отчетность МСФО", 20, "Interest expense", "interest", False, "bound"),
    ("Фин отчетность МСФО", 42, "Cash and cash equivalents", "cash", False, "bound"),
    ("Фин отчетность МСФО", 73, "Interest expense", "interest", False, "bound"),
    *[
        ("Предпосылки", row, _INTEREST, "interest", False, "bound")
        for row in (431, 438, 445, 452, 458, 464, 470, 476, 495)
    ],
    ("Предпосылки", 566, "Денежные средства", "cash", False, "bound"),
    ("ОПиУ", 17, _INTEREST, "interest", False, "ambiguous"),
    ("Баланс", 23, "Денежные средства", "cash", True, "bound"),
    (
        "Денежные потоки",
        9,
        (
            "Укажите значение, на которое необходимо корректировать чистый денежный поток"
            " и остаток денежных средств на конец периода"
        ),
        None,
        False,
        "unknown",
    ),
    ("Денежные потоки", 38, "Проценты к уплате за кв.", "interest", False, "ambiguous"),
    (
        "Денежные потоки",
        46,
        "ИТОГО - Операционный денежный поток",
        "operating_cash_flow",
        True,
        "bound",
    ),
    ("Денежные потоки", 48, _CAPEX, "capex", True, "bound"),
    (
        "Денежные потоки",
        52,
        "ИТОГО - Инвестиционный денежный поток",
        None,
        False,
        "unknown",
    ),
    (
        "Денежные потоки",
        68,
        "ИТОГО - Финансовый денежный поток",
        None,
        False,
        "unknown",
    ),
    ("Денежные потоки", 112, "ИТОГО - Чистый денежный поток", None, False, "unknown"),
    (
        "Денежные потоки",
        113,
        "Остаток денежных средств на конец периода",
        "cash_balance",
        False,
        "ambiguous",
    ),
    (
        "Денежные потоки",
        123,
        (
            'В графе "Минимальный остаток денежных средств" выше, укажите значение,'
            " на котрое необходимо корректировать чистый денежный поток"
            " и остаток денежных средств на конец периода"
        ),
        None,
        False,
        "unknown",
    ),
    (
        "Денежные потоки",
        128,
        "ИТОГО - Чистый денежный поток за кв.",
        None,
        False,
        "unknown",
    ),
    (
        "Денежные потоки",
        130,
        "Остаток денежных средств на конец периода",
        "cash_balance",
        False,
        "ambiguous",
    ),
    (
        "Outputs",
        10,
        "Остаток денежных средств на конец периода",
        "cash_balance",
        False,
        "bound",
    ),
    (
        "Outputs",
        11,
        "Денежный поток от операционной деятельности (CFO)",
        "operating_cash_flow",
        False,
        "bound",
    ),
    (
        "Outputs",
        12,
        "Денежный поток от инвестиционной деятельности (CFI)",
        "investing_cash_flow",
        True,
        "bound",
    ),
    (
        "Outputs",
        13,
        "Денежный поток от финансовой деятельности (CFF)",
        "financing_cash_flow",
        True,
        "bound",
    ),
    ("Outputs", 22, "Обслуживание долга (Debt Service)", "debt_service", True, "bound"),
    ("Outputs", 24, _INTEREST, "interest", False, "bound"),
    ("Outputs", 35, "Чистый денежный поток за период (NCF)", "ncf", False, "ambiguous"),
    (
        "Outputs",
        36,
        "Остаток денежных средств на конец периода",
        "cash_balance",
        False,
        "bound",
    ),
    (
        "Outputs",
        46,
        "Остаток денежных средств на конец периода",
        "cash_balance",
        False,
        "bound",
    ),
    ("Outputs", 49, "Чистый денежный поток (NCF)", "ncf", False, "ambiguous"),
    (
        "Outputs",
        50,
        "Чистый денежный поток накопительным итогом (NCCF)",
        None,
        False,
        "unknown",
    ),
    ("Outputs", 56, _INTEREST, "interest", False, "bound"),
    ("Формулы", 58, "Чистый денежный поток за период (NCF)", "ncf", False, "bound"),
    (
        "Формулы",
        61,
        "Остаток денежных средств на конец периода",
        "cash_balance",
        False,
        "bound",
    ),
    ("Формулы", 81, _QUOTE, None, False, "unknown"),
    (
        "Формулы",
        82,
        "Чистый денежный поток на i-ом интервале планирования (NCF)",
        None,
        False,
        "unknown",
    ),
    (
        "Формулы",
        85,
        "Чистый денежный поток накопительным итогом (NCCF)",
        None,
        False,
        "unknown",
    ),
    *[
        item
        for row in (64, 76, 88, 100)
        for item in (
            ("Для Стратегии 2017", row, "CFO", "operating_cash_flow", False, "bound"),
            ("Для Стратегии 2017", row + 1, "CAPEX", "capex", False, "bound"),
        )
    ],
)


def test_auchan_workbook_ncf_has_no_shared_interval():
    if not _BOOK.is_file():
        pytest.skip(f"нет книги {_BOOK}")
    roles = load_sheet_roles()
    sheets = frozenset(roles.statement)
    assert "Денежные потоки" in sheets
    rows, facts, periods = _read(_BOOK)
    assigned = assign_rows(rows, [], load_catalog(), roles=roles)
    found = tuple(_seen(row, assigned[row["binding_key"]]) for row in rows)
    assert found == _BOUND
    for row in rows:
        assert "line_code" not in assigned[row["binding_key"]].evidence
    assert not any(row["label"] == "Денежные средства и их эквиваленты" for row in rows)
    bindings = [_binding(row, assigned[row["binding_key"]]) for row in rows]
    got = select_ratio(
        "ncf",
        None,
        {
            "facts": facts,
            "bindings": bindings,
            "periods": periods,
            "absent": frozenset(),
        },
        profile=None,
        profile_ref=None,
        composed={},
        concepts=frozenset(),
        money=frozenset(),
        statement_sheets=sheets,
    )
    assert got["status"] == "not_computed"
    assert got["needs_input"] == []
    assert got["warnings"] == []
    assert len(got["rows"]) == 90
    assert sum(row["axis_id"] == "Денежные потоки" for row in got["rows"]) == 84
    assert sum(row["axis_id"] == "Outputs" for row in got["rows"]) == 6
    for row in got["rows"]:
        assert row["value"] is None
        assert row["status"] == "not_computed"
        assert row["reason"] == "missing_input"
    quarter = next(row for row in got["rows"] if row["period_id"] == "4 кв. 2015")
    year = next(
        row
        for row in got["rows"]
        if row["axis_id"] == "Outputs" and row["period_id"] == "2015"
    )
    assert quarter["axis_id"] == "Денежные потоки"
    assert year["value"] is None
    assert any(
        fact["cell_id"] == "Денежные потоки!E46" and fact["normalized_value"] == "11260814.5"
        for fact in facts
    )
    assert any(
        fact["cell_id"] == "Outputs!U12" and fact["normalized_value"] == "-8953834"
        for fact in facts
    )
    assert any(
        fact["cell_id"] == "Outputs!U13" and fact["normalized_value"] == "7375427"
        for fact in facts
    )


def _seen(row: dict, item) -> tuple:
    return (
        row["sheet"],
        row["row_num"],
        row["label"],
        item.concept,
        item.is_primary,
        item.status,
    )


def _binding(row: dict, item) -> dict:
    return {
        "effective_concept": item.concept,
        "is_primary": item.is_primary,
        "status": item.status,
        "source": item.source,
        "binding_key": row["binding_key"],
        "row_key": row["row_key"],
        "sheet": row["sheet"],
        "evidence": dict(item.evidence),
    }


def _read(path: Path) -> tuple[list[dict], list[dict], list[dict]]:
    rows: list[dict] = []
    facts: list[dict] = []
    order: dict[str, list[str]] = {}
    glossary = load_catalog()
    for name, by_row in _sheets(path):
        headers = {
            number: {
                col: text.strip()
                for col, text in cells.items()
                if _period(text)
            }
            for number, cells in by_row.items()
            if sum(_period(text) for text in cells.values()) >= 3
        }
        header_rows = sorted(headers)
        for number, cells in sorted(by_row.items()):
            # Заголовок кварталов сам подписан «Операционный денежный поток». Это не факт.
            amounts = [
                text
                for text in cells.values()
                if _number(text) and not _YEAR.fullmatch(text.strip())
            ]
            if sum(_period(text) for text in cells.values()) >= 3 and not amounts:
                continue
            above = [item for item in header_rows if item < number]
            header = headers[above[-1]] if above else {}
            for col, text in sorted(cells.items()):
                if col > 8:
                    continue
                label = " ".join(text.replace("\n", " ").split())
                if not label or _number(label) or _period(label):
                    continue
                if not _wanted(glossary, label):
                    continue
                key = f"{name}|{number}|{col}"
                right = cells.get(col + 1)
                code = marked_line_code(right.strip()) if isinstance(right, str) else None
                item = {
                    "kind": "fact",
                    "binding_key": key,
                    "row_key": key,
                    "label": label,
                    "sheet": name,
                    "row_num": number,
                    "sign": None,
                    "unit": "money",
                }
                if code:
                    item["line_code"] = code
                rows.append(item)
                seen: set[tuple[str, str]] = set()
                for value_col, raw in cells.items():
                    if value_col <= col or value_col not in header or not _number(raw):
                        continue
                    if _YEAR.fullmatch(raw.strip()):
                        continue
                    period = header[value_col].strip()
                    if (name, period) in seen:
                        period = f"{period}|{_column(value_col)}"
                    seen.add((name, period))
                    facts.append(
                        {
                            "row_key": key,
                            "axis_id": name,
                            "period_id": period,
                            "normalized_value": raw.strip(),
                            "cell_id": f"{name}!{_column(value_col)}{number}",
                        }
                    )
                    bucket = order.setdefault(name, [])
                    if period not in bucket:
                        bucket.append(period)
    periods = [
        {
            "axis_id": axis,
            "period_id": period,
            "period_index": index,
            "timeline_id": axis,
            "grain": "quarter" if "кв" in period.casefold() else "year",
        }
        for axis, periods_of in order.items()
        for index, period in enumerate(periods_of, start=1)
    ]
    return rows, facts, periods


def _wanted(glossary, label: str) -> bool:
    found = glossary.resolve(label)
    concept = None if found is None else found.concept
    folded = label.casefold()
    if concept in _WATCH:
        return True
    if "чистый денеж" in folded:
        return True
    return folded.startswith("итого") and "денеж" in folded


def _sheets(path: Path) -> list[tuple[str, dict[int, dict[int, str]]]]:
    with zipfile.ZipFile(path) as book:
        strings = [
            "".join(node.text or "" for node in item.iter(_MAIN + "t"))
            for item in ET.fromstring(book.read("xl/sharedStrings.xml")).findall("m:si", _NS)
        ]
        workbook = ET.fromstring(book.read("xl/workbook.xml"))
        rels = ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))
        targets = {}
        for rel in rels:
            target = rel.attrib.get("Target") or ""
            if not target.startswith("xl/"):
                target = "xl/" + target.lstrip("/")
            targets[rel.attrib.get("Id")] = target
        found = []
        for sheet in workbook.findall("m:sheets/m:sheet", _NS):
            root = ET.fromstring(book.read(targets[sheet.attrib[_RID]]))
            by_row: dict[int, dict[int, str]] = {}
            for sheet_row in root.findall("m:sheetData/m:row", _NS):
                number = int(sheet_row.attrib.get("r") or 0)
                cells: dict[int, str] = {}
                for cell in sheet_row.findall("m:c", _NS):
                    value = cell.find("m:v", _NS)
                    if value is None or not value.text:
                        continue
                    text = (
                        strings[int(value.text)]
                        if cell.attrib.get("t") == "s"
                        else value.text
                    )
                    cells[_column_of(cell.attrib.get("r") or "")] = text
                if cells:
                    by_row[number] = cells
            found.append((sheet.attrib["name"], by_row))
    return found


def _column_of(ref: str) -> int:
    match = re.match(r"([A-Z]+)", ref)
    if match is None:
        return 0
    number = 0
    for char in match.group(1):
        number = number * 26 + ord(char) - 64
    return number


def _column(number: int) -> str:
    letters = ""
    while number:
        number, rem = divmod(number - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _number(text: str) -> bool:
    return bool(_NUMBER.fullmatch((text or "").strip()))


def _period(text: str) -> bool:
    raw = (text or "").strip()
    return bool(_YEAR.fullmatch(raw) or _QUARTER.search(raw))
