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
from finance_analysis.domain.metrics import _primaries
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


def _fact(row_key: str, value_dec, normalized_value, scale_factor=1, **extra) -> dict:
    """Поля `fact_observation`: ячейка, базовые единицы и масштаб по отдельности."""

    fact = {
        "row_key": row_key,
        "value_dec": value_dec,
        "normalized_value": normalized_value,
        "scale_factor": scale_factor,
        "value_status": extra.pop("value_status", "cached"),
    }
    fact.update(extra)
    return fact


def _cached(sheet: str, coord: str):
    book = openpyxl.load_workbook(_BOOK, data_only=True)
    try:
        return book[sheet][coord].value
    finally:
        book.close()


def test_confident_halyard_cites_moic_and_exit_enterprise_value():
    """Кэш Returns цитируется как есть: MOIC 2.13x и стоимость предприятия на выходе.

    У exit EV масштаб `$mm`: в ячейке 1417.151736, в базовых единицах 1417151736.
    Цитата берёт ячейку. MOIC безмасштабен, поэтому оба поля совпадают.
    """

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
        facts=[
            _fact("Returns!B9", moic, moic, 1, cell_id="Returns!C9"),
            _fact(
                "Returns!B4",
                exit_value,
                Decimal(str(exit_value)) * Decimal(1_000_000),
                1_000_000,
                cell_id="Returns!C4",
            ),
        ],
    )
    assert [row["concept"] for row in got] == ["moic", "exit_enterprise_value"]
    moic_row, exit_row = got
    assert moic_row["status"] == "cited" and exit_row["status"] == "cited"
    assert "values" not in moic_row and "needs_input" not in moic_row
    moic_obs = moic_row["observations"][0]
    assert moic_obs["cell_id"] == "Returns!C9"
    assert moic_obs["value"] == "2.13091813829771"
    assert moic_obs["normalized_value"] == moic_obs["value"]
    assert moic_obs["scale_factor"] == "1"
    assert round(Decimal(moic_obs["value"]), 2) == Decimal("2.13")
    exit_obs = exit_row["observations"][0]
    assert exit_obs == {
        "cell_id": "Returns!C4",
        "value": "1417.151736",
        "normalized_value": "1417151736",
        "scale_factor": "1000000",
        "value_status": "cached",
    }


def test_value_dec_is_not_replaced_by_normalized_value():
    """Нет `value_dec` — базовые единицы не становятся числом ячейки."""

    got = cite_lbo_book_rows(
        source="inferred",
        primary="lbo_ma",
        bindings=[_binding("exit_enterprise_value", "Returns!B4")],
        facts=[
            _fact(
                "Returns!B4",
                None,
                "1417151736",
                1_000_000,
                cell_id="Returns!C4",
            )
        ],
    )
    assert got[1]["status"] == "absent"
    assert got[1]["observations"] == []
    assert got[1]["row_key"] == "Returns!B4"


def test_several_cells_of_one_row_stay_unsummed():
    got = cite_lbo_book_rows(
        source="confirmed",
        primary="lbo_ma",
        bindings=[_binding("moic", "r")],
        facts=[
            _fact("r", "1.5", "1.5", cell_id="Returns!C9", period_index=1),
            _fact("r", "2.5", "2.5", cell_id="Returns!D9", period_index=2),
        ],
    )
    assert [item["value"] for item in got[0]["observations"]] == ["1.5", "2.5"]
    assert [item["cell_id"] for item in got[0]["observations"]] == [
        "Returns!C9",
        "Returns!D9",
    ]
    assert got[1]["status"] == "absent" and got[1]["observations"] == []


def test_empty_and_invalid_values_are_not_citations():
    """Пустой статус и неразборное число не становятся цитатой, даже если база есть."""

    got = cite_lbo_book_rows(
        source="inferred",
        primary="lbo_ma",
        bindings=[_binding("moic", "r"), _binding("exit_enterprise_value", "e")],
        facts=[
            _fact("r", "2.13", "2.13", value_status="empty", cell_id="Returns!C9"),
            _fact("r", "нет", "2.13", cell_id="Returns!D9"),
            _fact("e", "1", "1", value_status="not_applicable", cell_id="Returns!C4"),
            _fact("e", True, "1", cell_id="Returns!D4"),
        ],
    )
    assert got[0]["status"] == "absent" and got[0]["observations"] == []
    assert got[1]["status"] == "absent" and got[1]["observations"] == []


def test_non_finite_decimals_are_not_citations():
    """NaN и бесконечность не становятся значением цитаты."""

    got = cite_lbo_book_rows(
        source="inferred",
        primary="lbo_ma",
        bindings=[_binding("moic", "r"), _binding("exit_enterprise_value", "e")],
        facts=[
            _fact("r", Decimal("NaN"), "2.13", cell_id="Returns!C9"),
            _fact("r", Decimal("Infinity"), "2.13", cell_id="Returns!D9"),
            _fact("e", Decimal("-Infinity"), "1417.151736", cell_id="Returns!C4"),
        ],
    )
    assert got[0]["status"] == "absent" and got[0]["observations"] == []
    assert got[1]["status"] == "absent" and got[1]["observations"] == []
    rendered = str(got)
    assert "NaN" not in rendered
    assert "Infinity" not in rendered


def test_observation_keeps_cell_provenance():
    got = cite_lbo_book_rows(
        source="inferred",
        primary="lbo_ma",
        bindings=[_binding("moic", "Returns!B9")],
        facts=[
            _fact(
                "Returns!B9",
                "2.13",
                "2.13",
                1,
                cell_id="Returns!C9",
                axis_id="Returns!axis",
                period_id="exit",
                period_index=5,
            )
        ],
    )
    assert got[0]["observations"] == [
        {
            "cell_id": "Returns!C9",
            "value": "2.13",
            "normalized_value": "2.13",
            "scale_factor": "1",
            "axis_id": "Returns!axis",
            "period_id": "exit",
            "value_status": "cached",
            "period_index": 5,
        }
    ]


def test_several_primaries_are_not_the_last_row():
    """`_primaries` оставляет последнюю привязку. Цитата в этом случае неоднозначна."""

    first = _binding("moic", "Returns!B9")
    last = _binding("moic", "Returns!B10")
    assert _primaries([first, last])["moic"]["row_key"] == "Returns!B10"
    got = cite_lbo_book_rows(
        source="inferred",
        primary="lbo_ma",
        bindings=[first, last],
        facts=[
            _fact("Returns!B9", "2.13", "2.13", cell_id="Returns!C9"),
            _fact("Returns!B10", "9.99", "9.99", cell_id="Returns!C10"),
        ],
    )
    assert got[0]["status"] == "ambiguous"
    assert got[0]["observations"] == []
    assert "row_key" not in got[0]


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
        {"concept": "moic", "status": "absent", "observations": []},
        {"concept": "exit_enterprise_value", "status": "absent", "observations": []},
    ]


def test_unresolved_type_and_other_primaries_do_not_cite():
    bindings = [_binding("moic", "r"), _binding("exit_enterprise_value", "e")]
    facts = [_fact("r", "2.13", "2.13"), _fact("e", "100", "100")]
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
    """Цитата не входит в матрицу коэффициентов. Второй сигнал типа — только moic. Схема 1.0."""

    assert FAS_SCHEMA_VERSION == "1.1"
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
        ("moic",),
    ]
