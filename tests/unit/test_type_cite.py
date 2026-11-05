"""Цитата строк пяти типов. Формулы нет, вопроса нет, матрица коэффициентов не меняется."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import openpyxl

from finance_analysis.application.analyses import RATIO_METRICS, _attach_book_rows
from finance_analysis.application.catalog import load_catalog
from finance_analysis.application.model_types import load_model_types
from finance_analysis.domain.book import FAS_SCHEMA_VERSION
from finance_analysis.domain.book_cite import CITED_BY_TYPE, cite_type_book_rows
from finance_analysis.domain.model_type import applicability, open_concepts
from finance_analysis.domain.questions import concept_questions

_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "model_books"
_HELD_OUT = frozenset(
    {
        "installed_capacity",
        "noi",
        "vacancy",
        "dscr",
        "moic",
        "exit_enterprise_value",
        "grantor_payment",
        "npv",
        "irr",
        "payback",
    }
)


def _binding(concept: str, row_key: str, *, primary: bool = True) -> dict:
    return {
        "effective_concept": concept,
        "is_primary": primary,
        "status": "bound",
        "row_key": row_key,
        "source": "inferred",
    }


def _fact(row_key: str, value) -> dict:
    return {"row_key": row_key, "normalized_value": value}


def _cached(relative: str, sheet: str, coord: str):
    book = openpyxl.load_workbook(_ROOT / relative, data_only=True)
    try:
        return book[sheet][coord].value
    finally:
        book.close()


def _label(relative: str, sheet: str, coord: str):
    book = openpyxl.load_workbook(_ROOT / relative, data_only=False)
    try:
        return book[sheet][coord].value
    finally:
        book.close()


def _row_numbers(relative: str, sheet: str, row: int, start: int) -> list:
    book = openpyxl.load_workbook(_ROOT / relative, data_only=True)
    try:
        grid = book[sheet]
        found = []
        for column in range(start, grid.max_column + 1):
            value = grid.cell(row, column).value
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            found.append(value)
        return found
    finally:
        book.close()


def _column_numbers(relative: str, sheet: str, column: int, start: int) -> list:
    book = openpyxl.load_workbook(_ROOT / relative, data_only=True)
    try:
        grid = book[sheet]
        found = []
        for row in range(start, grid.max_row + 1):
            value = grid.cell(row, column).value
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            found.append(value)
        return found
    finally:
        book.close()


def test_lease_portfolio_cites_the_three_scalars():
    """Процентный доход 260, доля NPL 0,125, покрытие резервом 0,5."""

    book = "leasing/lease_portfolio.recalc_libreoffice.xlsx"
    package = load_catalog()
    assert (
        package.resolve(_label(book, "Summary", "A2")).concept
        == "lease_interest_income"
    )
    assert package.resolve(_label(book, "Summary", "A5")).concept == "npl_share"
    assert (
        package.resolve(_label(book, "Summary", "A8")).concept == "provision_coverage"
    )
    income, share, cover = (
        _cached(book, "Summary", "B2"),
        _cached(book, "Summary", "B5"),
        _cached(book, "Summary", "B8"),
    )
    got = cite_type_book_rows(
        source="inferred",
        primary="bank_leasing",
        bindings=[
            _binding("lease_interest_income", "Summary!A2"),
            _binding("npl_share", "Summary!A5"),
            _binding("provision_coverage", "Summary!A8"),
        ],
        facts=[
            _fact("Summary!A2", income),
            _fact("Summary!A5", share),
            _fact("Summary!A8", cover),
        ],
    )
    assert [row["concept"] for row in got] == list(CITED_BY_TYPE["bank_leasing"])
    assert [Decimal(row["values"][0]) for row in got] == [
        Decimal(260),
        Decimal("0.125"),
        Decimal("0.5"),
    ]
    assert all(row["status"] == "cited" and "needs_input" not in row for row in got)


def test_meridian_cites_wacc_and_both_bridges_unsummed():
    """WACC!C19 и два столбца EV и капитала. Ссылка на листе DCF второй цитатой не становится."""

    book = "meridian/meridian_dcf.recalc_libreoffice.xlsx"
    package = load_catalog()
    assert package.resolve(_label(book, "WACC", "B19")).concept == "wacc"
    assert package.resolve(_label(book, "DCF", "B32")).concept == "terminal_value"
    assert package.resolve(_label(book, "DCF", "B36")).concept == "enterprise_value"
    assert package.resolve(_label(book, "DCF", "B46")).concept == "equity_value"
    wacc = _cached(book, "WACC", "C19")
    terminal = [_cached(book, "DCF", "C32"), _cached(book, "DCF", "D32")]
    enterprise = [_cached(book, "DCF", "C36"), _cached(book, "DCF", "D36")]
    equity = [_cached(book, "DCF", "C46"), _cached(book, "DCF", "D46")]
    got = cite_type_book_rows(
        source="inferred",
        primary="dcf_valuation",
        bindings=[
            _binding("wacc", "WACC!B19"),
            _binding("wacc", "DCF!B28", primary=False),
            _binding("terminal_value", "Inputs!B14", primary=False),
            _binding("terminal_value", "DCF!B32"),
            _binding("enterprise_value", "DCF!B36"),
            _binding("equity_value", "DCF!B46"),
        ],
        facts=[
            _fact("WACC!B19", wacc),
            _fact("DCF!B28", wacc),
            _fact("DCF!B28", wacc),
            _fact("DCF!B32", terminal[0]),
            _fact("DCF!B32", terminal[1]),
            _fact("DCF!B36", enterprise[0]),
            _fact("DCF!B36", enterprise[1]),
            _fact("DCF!B46", equity[0]),
            _fact("DCF!B46", equity[1]),
        ],
    )
    by_concept = {row["concept"]: row for row in got}
    assert list(by_concept) == list(CITED_BY_TYPE["dcf_valuation"])
    assert by_concept["wacc"]["values"] == [format(Decimal(str(wacc)), "f")]
    assert round(Decimal(by_concept["wacc"]["values"][0]), 5) == Decimal("0.09614")
    assert [
        round(Decimal(value), 1) for value in by_concept["enterprise_value"]["values"]
    ] == [
        Decimal("5717.6"),
        Decimal("6192.8"),
    ]
    assert [
        round(Decimal(value), 1) for value in by_concept["equity_value"]["values"]
    ] == [
        Decimal("5087.6"),
        Decimal("5562.8"),
    ]
    assert len(by_concept["terminal_value"]["values"]) == 2
    assert len(by_concept["enterprise_value"]["values"]) == 2
    left = Decimal(by_concept["enterprise_value"]["values"][0])
    right = Decimal(by_concept["enterprise_value"]["values"][1])
    assert left + right != left


def test_solar_cites_degradation_generation_and_tariff_not_capacity():
    """Деградация 0,5%, первый год выработки 50 370, тариф 72,75. Мощность DC/AC не цитируется."""

    book = "solar/Solar Financial Model.xlsx"
    package = load_catalog()
    assert package.resolve(_label(book, "Model", "B23")).concept == "degradation"
    assert package.resolve(_label(book, "Model", "B58")).concept == "energy_generation"
    assert package.resolve(_label(book, "Model", "B61")).concept == "energy_tariff"
    degradation = _cached(book, "Model", "D23")
    generation = _row_numbers(book, "Model", 58, 8)
    tariff = _row_numbers(book, "Model", 61, 8)
    got = cite_type_book_rows(
        source="confirmed",
        primary="renewables_dpm",
        bindings=[
            _binding("degradation", "Model!B23"),
            _binding("energy_generation", "Model!B58"),
            _binding("energy_tariff", "Model!B61"),
            _binding("installed_capacity", "Model!B20"),
            _binding("installed_capacity", "Model!B21"),
        ],
        facts=[
            _fact("Model!B23", degradation),
            *[_fact("Model!B58", value) for value in generation],
            *[_fact("Model!B61", value) for value in tariff],
            _fact("Model!B20", 25),
            _fact("Model!B21", 20),
        ],
    )
    assert [row["concept"] for row in got] == list(CITED_BY_TYPE["renewables_dpm"])
    assert Decimal(got[0]["values"][0]) == Decimal("0.005")
    assert len(got[1]["values"]) == 30
    assert round(Decimal(got[1]["values"][0]), 0) == Decimal(50370)
    assert len(got[2]["values"]) == 30
    assert Decimal(got[2]["values"][0]) == Decimal("72.75")
    assert "installed_capacity" not in {row["concept"] for row in got}


def test_debtlens_cites_only_the_cap_rate():
    """Assumptions!C20 — подпись ставки 5,75%. NOI, вакансия и DSCR в цитату не входят."""

    book = "debtlens/DebtLens_Underwriting_Model.xlsx"
    package = load_catalog()
    assert package.resolve(_label(book, "Assumptions", "C20")).concept == "cap_rate"
    rate = _cached(book, "Assumptions", "D20")
    got = cite_type_book_rows(
        source="inferred",
        primary="real_estate_income",
        bindings=[
            _binding("cap_rate", "Assumptions!C20"),
            _binding("noi", "Summary!C7"),
            _binding("vacancy", "Assumptions!C13"),
            _binding("dscr", "Summary!C17"),
        ],
        facts=[
            _fact("Assumptions!C20", rate),
            _fact("Summary!C7", 3288000),
            _fact("Assumptions!C13", 0.05),
            _fact("Summary!C17", 1.30),
        ],
    )
    assert [row["concept"] for row in got] == ["cap_rate"]
    assert Decimal(got[0]["values"][0]) * 100 == Decimal("5.75")
    assert got[0]["status"] == "cited"


def test_escrow_cites_inflow_disclosure_and_rate():
    """Поступления, раскрытие и эффективная ставка читаются из столбцов книги и не пересчитываются."""

    book = "escrow/development_escrow_214.recalc_libreoffice.xlsx"
    package = load_catalog()
    headers = {
        "escrow_inflow": 7,
        "escrow_disclosure": 8,
        "effective_rate": 14,
    }
    for concept, column in headers.items():
        letter = openpyxl.utils.get_column_letter(column)
        assert package.resolve(_label(book, "Модель", f"{letter}1")).concept == concept
    series = {
        concept: _column_numbers(book, "Модель", column, 2)
        for concept, column in headers.items()
    }
    got = cite_type_book_rows(
        source="inferred",
        primary="development_escrow",
        bindings=[_binding(concept, f"Модель!{concept}") for concept in headers],
        facts=[
            _fact(f"Модель!{concept}", value)
            for concept, values in series.items()
            for value in values
        ],
    )
    assert [row["concept"] for row in got] == list(CITED_BY_TYPE["development_escrow"])
    assert [len(row["values"]) for row in got] == [36, 36, 36]
    assert [Decimal(value) for value in got[0]["values"][:2]] == [
        Decimal(2000),
        Decimal(2000),
    ]
    assert Decimal(got[1]["values"][0]) == Decimal(0)
    assert [Decimal(value) for value in got[2]["values"][:2]] == [
        Decimal("0.12"),
        Decimal("0.06"),
    ]
    assert "escrow_coverage" not in {row["concept"] for row in got}
    assert all("needs_input" not in row for row in got)


def test_a_missing_row_is_absent_and_not_asked():
    catalog = load_model_types()
    for primary, concepts in CITED_BY_TYPE.items():
        asked = open_concepts(
            catalog, (primary,), bound=frozenset(), absent=frozenset()
        )
        assert set(concepts).isdisjoint(asked), primary
        questions = concept_questions(
            job_id=primary,
            bindings=[],
            rows=[],
            events=[],
            catalog=catalog,
            labels=(primary,),
            concepts=load_catalog().concepts,
            limit=5,
        )
        assert all(item["subject"] not in concepts for item in questions), primary
        got = cite_type_book_rows(
            source="inferred", primary=primary, bindings=[], facts=[]
        )
        assert [row["concept"] for row in got] == list(concepts)
        assert all(row["status"] == "absent" and row["values"] == [] for row in got)


def test_unresolved_and_other_primaries_do_not_cite():
    bindings = [_binding("cap_rate", "r"), _binding("wacc", "w")]
    facts = [_fact("r", "0.0575"), _fact("w", "0.09614")]
    assert (
        cite_type_book_rows(
            source="unresolved", primary="dcf_valuation", bindings=bindings, facts=facts
        )
        == []
    )
    for primary in (
        "lbo_ma",
        "ppp_concession",
        "investment_project",
        "project_finance",
        "corporate",
        "other",
    ):
        assert (
            cite_type_book_rows(
                source="inferred", primary=primary, bindings=bindings, facts=facts
            )
            == []
        ), primary
    cited = cite_type_book_rows(
        source="profile", primary="real_estate_income", bindings=bindings, facts=facts
    )
    assert cited[0]["status"] == "cited"


def test_citation_stays_out_of_the_ratio_matrix_and_an_empty_list_adds_no_key():
    assert FAS_SCHEMA_VERSION == "1.0"
    catalog = load_model_types()
    for concepts in CITED_BY_TYPE.values():
        assert set(concepts).isdisjoint(RATIO_METRICS)
        assert set(concepts).isdisjoint(_HELD_OUT)
    assert applicability(catalog, ("real_estate_income",), "dscr") == "optional"
    assert applicability(catalog, ("renewables_dpm",), "dscr") == "optional"
    assert applicability(catalog, ("bank_leasing",), "dscr") == "not_applicable"
    assert applicability(catalog, ("dcf_valuation",), "npv") == "not_applicable"
    assert (
        applicability(catalog, ("development_escrow",), "escrow_coverage") == "required"
    )
    assert catalog.types["real_estate_income"].variants["dscr"] == "pf"
    assert catalog.types["renewables_dpm"].variants["dscr"] == "pf"
    envelope: dict = {"result_data": {}}
    _attach_book_rows(envelope, {"book_rows": []})
    assert "book_rows" not in envelope["result_data"]
    _attach_book_rows(
        envelope,
        {
            "book_rows": [
                {"concept": "cap_rate", "status": "cited", "values": ["0.0575"]}
            ]
        },
    )
    assert envelope["result_data"]["book_rows"][0]["concept"] == "cap_rate"
