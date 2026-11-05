"""Цитирование MOIC и exit EV. Формулы нет, вопроса нет, матрица коэффициентов не меняется."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import openpyxl

from finance_analysis.application.analyses import RATIO_METRICS
from finance_analysis.application.catalog import load_catalog
from finance_analysis.application.model_types import load_model_types
from finance_analysis.domain.book import FAS_SCHEMA_VERSION
from finance_analysis.domain.lbo_cite import cite_lbo_book_rows
from finance_analysis.domain.model_type import applicability, open_concepts
from finance_analysis.domain.questions import concept_questions

_BOOK = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "model_books"
    / "halyard"
    / "project_halyard.recalc_libreoffice.xlsx"
)


def _binding(concept: str, row_key: str) -> dict:
    return {
        "effective_concept": concept,
        "is_primary": True,
        "status": "bound",
        "row_key": row_key,
        "source": "inferred",
    }


def _fact(row_key: str, value) -> dict:
    return {"row_key": row_key, "normalized_value": value}


def _cached(sheet: str, coord: str):
    book = openpyxl.load_workbook(_BOOK, data_only=True)
    try:
        return book[sheet][coord].value
    finally:
        book.close()


def test_confident_halyard_cites_moic_and_exit_enterprise_value():
    """Кэш Returns цитируется как есть: MOIC 2.13x и стоимость предприятия на выходе."""

    moic = _cached("Returns", "C9")
    exit_value = _cached("Returns", "C4")
    package = load_catalog()
    book = openpyxl.load_workbook(_BOOK, data_only=False)
    try:
        assert package.resolve(book["Returns"]["B9"].value).concept == "moic"
        assert (
            package.resolve(book["Returns"]["B4"].value).concept
            == "exit_enterprise_value"
        )
    finally:
        book.close()
    got = cite_lbo_book_rows(
        source="inferred",
        primary="lbo_ma",
        bindings=[
            _binding("moic", "Returns!B9"),
            _binding("exit_enterprise_value", "Returns!B4"),
        ],
        facts=[_fact("Returns!B9", moic), _fact("Returns!B4", exit_value)],
    )
    assert [row["concept"] for row in got] == ["moic", "exit_enterprise_value"]
    assert got[0]["status"] == "cited" and got[1]["status"] == "cited"
    assert round(Decimal(got[0]["values"][0]), 2) == Decimal("2.13")
    assert Decimal(got[0]["values"][0]) == Decimal(str(moic))
    assert Decimal(got[1]["values"][0]) == Decimal(str(exit_value))
    assert "needs_input" not in got[0]


def test_several_cells_of_one_row_stay_unsummed():
    got = cite_lbo_book_rows(
        source="confirmed",
        primary="lbo_ma",
        bindings=[_binding("moic", "r")],
        facts=[_fact("r", "1.5"), _fact("r", "2.5")],
    )
    assert got[0]["values"] == ["1.5", "2.5"]
    assert got[1]["status"] == "absent" and got[1]["values"] == []


def test_a_book_without_the_rows_is_not_asked():
    """Нет строк — статус absent. Вопрос по этим понятиям не ставится."""

    catalog = load_model_types()
    asked = open_concepts(catalog, ("lbo_ma",), bound=frozenset(), absent=frozenset())
    assert "moic" not in asked
    assert "exit_enterprise_value" not in asked
    questions = concept_questions(
        job_id="halyard",
        bindings=[],
        rows=[],
        events=[],
        catalog=catalog,
        labels=("lbo_ma",),
        concepts=load_catalog().concepts,
        limit=5,
    )
    assert all(
        item["subject"] not in {"moic", "exit_enterprise_value", "irr"}
        for item in questions
    )
    got = cite_lbo_book_rows(source="inferred", primary="lbo_ma", bindings=[], facts=[])
    assert got == [
        {"concept": "moic", "status": "absent", "values": []},
        {"concept": "exit_enterprise_value", "status": "absent", "values": []},
    ]


def test_unresolved_type_and_other_primaries_do_not_cite():
    bindings = [_binding("moic", "r"), _binding("exit_enterprise_value", "e")]
    facts = [_fact("r", "2.13"), _fact("e", "100")]
    assert (
        cite_lbo_book_rows(
            source="unresolved", primary="lbo_ma", bindings=bindings, facts=facts
        )
        == []
    )
    assert (
        cite_lbo_book_rows(
            source="inferred", primary="project_finance", bindings=bindings, facts=facts
        )
        == []
    )
    assert (
        cite_lbo_book_rows(
            source="profile", primary="lbo_ma", bindings=bindings, facts=facts
        )[0]["status"]
        == "cited"
    )


def test_citation_stays_out_of_the_ratio_matrix():
    """Сигналы, схема и применимость покрытия не меняются."""

    assert FAS_SCHEMA_VERSION == "1.0"
    assert "moic" not in RATIO_METRICS
    assert "exit_enterprise_value" not in RATIO_METRICS
    catalog = load_model_types()
    assert applicability(catalog, ("lbo_ma",), "irr") == "not_applicable"
    assert applicability(catalog, ("lbo_ma",), "net_debt_ebitda") == "not_applicable"
    assert applicability(catalog, ("lbo_ma",), "dscr") == "not_applicable"
    assert applicability(catalog, ("lbo_ma",), "icr") == "not_applicable"
    spec = catalog.types["lbo_ma"]
    assert spec.required_concepts == frozenset(
        {"sources_and_uses", "exit_enterprise_value", "moic"}
    )
    assert [signal.concepts for signal in spec.signals] == [
        ("sources_and_uses", "exit_enterprise_value"),
        ("moic", "irr"),
    ]
