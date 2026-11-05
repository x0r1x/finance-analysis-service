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
        "dscr",
        "moic",
        "exit_enterprise_value",
        "grantor_payment",
        "npv",
        "irr",
        "payback",
    }
)


def _binding(
    concept: str,
    row_key: str,
    *,
    primary: bool = True,
    source: str = "inferred",
    status: str = "bound",
    label: str | None = None,
) -> dict:
    row = {
        "effective_concept": concept,
        "is_primary": primary,
        "status": status,
        "row_key": row_key,
        "source": source,
    }
    if label is not None:
        row["matched_label_id"] = label
    return row


def _fact(
    row_key: str, value, *, scale: int = 1000, status: str = "cached", **fields
) -> dict:
    """Кэш листа в `value_dec`, масштаб — отдельно. Цитата не должна взять масштаб."""

    sheet = None if value is None else Decimal(str(value))
    body = {
        "row_key": row_key,
        "value_dec": None if sheet is None else format(sheet, "f"),
        "normalized_value": None if sheet is None else format(sheet * scale, "f"),
        "scale_factor": scale,
        "value_status": status,
    }
    body.update(fields)
    return body


def _sheet(row: dict) -> list:
    return [item["value"] for item in row["observations"]]


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


def _span(relative: str, sheet: str, ref: str, *, data_only: bool) -> list:
    book = openpyxl.load_workbook(_ROOT / relative, data_only=data_only)
    try:
        block = book[sheet][ref]
        if not isinstance(block, tuple):
            return [block.value]
        return [cell.value for cell in block[0]]
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
    assert [Decimal(_sheet(row)[0]) for row in got] == [
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
    assert _sheet(by_concept["wacc"]) == [format(Decimal(str(wacc)), "f")]
    assert round(Decimal(_sheet(by_concept["wacc"])[0]), 5) == Decimal("0.09614")
    assert [
        round(Decimal(value), 1) for value in _sheet(by_concept["enterprise_value"])
    ] == [
        Decimal("5717.6"),
        Decimal("6192.8"),
    ]
    assert [
        round(Decimal(value), 1) for value in _sheet(by_concept["equity_value"])
    ] == [
        Decimal("5087.6"),
        Decimal("5562.8"),
    ]
    assert len(_sheet(by_concept["terminal_value"])) == 2
    assert len(_sheet(by_concept["enterprise_value"])) == 2
    left = Decimal(_sheet(by_concept["enterprise_value"])[0])
    right = Decimal(_sheet(by_concept["enterprise_value"])[1])
    assert left + right != left


def test_solar_cites_degradation_generation_and_tariff_not_capacity():
    """Деградация Model!D23 равна 0,005. Выработка H58:AK58 — 30 значений, первое около 50 370.

    Тариф H61:AA61 — двадцать раз 72,75. AB61:AK61 — десять нулей кэша формулы IFERROR,
    не пустые ячейки. Цитата отдаёт 30 наблюдений и не включает installed_capacity.
    """

    book = "solar/Solar Financial Model.xlsx"
    package = load_catalog()
    assert package.resolve(_label(book, "Model", "B23")).concept == "degradation"
    assert package.resolve(_label(book, "Model", "B58")).concept == "energy_generation"
    assert package.resolve(_label(book, "Model", "B61")).concept == "energy_tariff"
    assert _span(book, "Model", "D23", data_only=False) == [0.005]
    degradation = _span(book, "Model", "D23", data_only=True)
    generation = _span(book, "Model", "H58:AK58", data_only=True)
    generation_formulas = _span(book, "Model", "H58:AK58", data_only=False)
    ppa = _span(book, "Model", "H61:AA61", data_only=True)
    after = _span(book, "Model", "AB61:AK61", data_only=True)
    after_formulas = _span(book, "Model", "AB61:AK61", data_only=False)
    assert degradation == [0.005]
    assert len(generation) == 30
    assert round(generation[0], 0) == 50370
    assert all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in generation)
    assert all(isinstance(item, str) and item.startswith("=") for item in generation_formulas)
    assert ppa == [72.75] * 20
    assert after == [0] * 10
    assert all(item is not None for item in after)
    assert all(isinstance(item, str) and item.startswith("=IFERROR(") for item in after_formulas)
    tariff = ppa + after
    got = cite_type_book_rows(
        source="inferred",
        primary="renewables_dpm",
        bindings=[
            _binding("degradation", "Model!B23"),
            _binding("energy_generation", "Model!B58"),
            _binding("energy_tariff", "Model!B61"),
            _binding("installed_capacity", "Model!M16"),
            _binding("installed_capacity", "Model!B20"),
            _binding("installed_capacity", "Model!B21"),
        ],
        facts=[
            _fact("Model!B23", degradation[0]),
            *[_fact("Model!B58", value) for value in generation],
            *[_fact("Model!B61", value) for value in tariff],
            _fact("Model!B20", 25),
            _fact("Model!B21", 20),
        ],
    )
    assert CITED_BY_TYPE["renewables_dpm"] == (
        "degradation",
        "energy_generation",
        "energy_tariff",
    )
    assert [row["concept"] for row in got] == list(CITED_BY_TYPE["renewables_dpm"])
    assert len(got[0]["observations"]) == 1
    assert Decimal(_sheet(got[0])[0]) == Decimal("0.005")
    assert len(got[1]["observations"]) == 30
    assert _sheet(got[1]) == [format(Decimal(str(value)), "f") for value in generation]
    assert round(Decimal(_sheet(got[1])[0]), 0) == Decimal(50370)
    assert len(got[2]["observations"]) == 30
    assert [Decimal(value) for value in _sheet(got[2])] == [Decimal("72.75")] * 20 + [
        Decimal(0)
    ] * 10
    assert "installed_capacity" not in {row["concept"] for row in got}


def test_debtlens_cites_cap_rate_and_the_year_one_scalars():
    """Год 1: NOI Summary!D7 и вакансия Assumptions!D13. Ряд прогноза и DSCR не цитируются."""

    book = "debtlens/DebtLens_Underwriting_Model.xlsx"
    package = load_catalog()
    noi_label = _label(book, "Summary", "C7")
    vacancy_label = _label(book, "Assumptions", "C13")
    forecast_noi = _label(book, "Operating Forecast", "C15")
    forecast_vacancy = _label(book, "Operating Forecast", "C9")
    assert package.resolve(noi_label).concept == "noi"
    assert package.resolve(forecast_noi).concept == "noi"
    assert package.resolve(vacancy_label).concept == "vacancy"
    assert package.resolve(forecast_vacancy).concept == "vacancy"
    assert package.resolve(_label(book, "Assumptions", "C20")).concept == "cap_rate"
    assert package.resolve(_label(book, "Summary", "C17")).concept == "dscr"
    assert package.resolve(_label(book, "Summary", "G10")).concept == "dscr"
    rate = _cached(book, "Assumptions", "D20")
    capacity = _cached(book, "Summary", "H10")
    noi_series = _row_numbers(book, "Operating Forecast", 15, 4)
    vacancy_series = _row_numbers(book, "Operating Forecast", 9, 4)
    assert noi_series[0] == 3_288_000 and len(noi_series) > 1
    assert vacancy_series[0] == 0.05 and len(vacancy_series) > 1
    got = cite_type_book_rows(
        source="inferred",
        primary="real_estate_income",
        bindings=[
            _binding(
                "cap_rate",
                "Assumptions!C20",
                label=_label(book, "Assumptions", "C20"),
            ),
            _binding("noi", "Summary!C7", label=noi_label),
            _binding("noi", "Operating Forecast!C15", label=forecast_noi),
            _binding("vacancy", "Assumptions!C13", label=vacancy_label),
            _binding("vacancy", "Operating Forecast!C9", label=forecast_vacancy),
            _binding("dscr", "Summary!C17", label=_label(book, "Summary", "C17")),
            _binding("dscr", "Summary!G10", label=_label(book, "Summary", "G10")),
            _binding("interest", "Debt Schedule!F6"),
            _binding("principal", "Debt Schedule!G6"),
        ],
        facts=[
            _fact("Assumptions!C20", rate),
            _fact("Summary!C7", 3_288_000),
            *[_fact("Operating Forecast!C15", value) for value in noi_series],
            _fact("Assumptions!C13", 0.05),
            *[_fact("Operating Forecast!C9", value) for value in vacancy_series],
            _fact("Summary!C17", _cached(book, "Summary", "D17")),
            _fact("Summary!G10", capacity),
        ],
    )
    assert CITED_BY_TYPE["real_estate_income"] == ("cap_rate", "noi", "vacancy")
    by_concept = {row["concept"]: row for row in got}
    assert list(by_concept) == list(CITED_BY_TYPE["real_estate_income"])
    assert by_concept["cap_rate"]["row_key"] == "Assumptions!C20"
    assert Decimal(_sheet(by_concept["cap_rate"])[0]) * 100 == Decimal("5.75")
    assert by_concept["noi"]["row_key"] == "Summary!C7"
    assert _sheet(by_concept["noi"]) == ["3288000"]
    assert by_concept["vacancy"]["row_key"] == "Assumptions!C13"
    assert _sheet(by_concept["vacancy"]) == ["0.05"]
    assert all(row["status"] == "cited" for row in got)
    quoted = {Decimal(value) for row in got for value in _sheet(row)}
    assert Decimal(str(capacity)) not in quoted
    assert round(capacity / 1_000_000, 1) == 33.5
    assert "dscr" not in by_concept


def test_year_one_label_wins_when_the_forecast_row_is_the_only_primary():
    """Каскад может оставить ряд прогноза единственной основной строкой. Цитата берёт год 1."""

    got = cite_type_book_rows(
        source="inferred",
        primary="real_estate_income",
        bindings=[
            _binding(
                "noi",
                "Summary!C7",
                primary=False,
                status="ambiguous",
                label="Year 1 net operating income",
            ),
            _binding("noi", "Operating Forecast!C15", label="Net operating income"),
            _binding(
                "vacancy",
                "Assumptions!C13",
                primary=False,
                label="Year 1 vacancy",
            ),
            _binding("vacancy", "Operating Forecast!C9", label="Vacancy"),
            _binding("cap_rate", "Assumptions!C20"),
        ],
        facts=[
            _fact("Summary!C7", 3_288_000, scale=1),
            _fact("Operating Forecast!C15", 3_288_000, scale=1),
            _fact("Operating Forecast!C15", 3_400_000, scale=1),
            _fact("Assumptions!C13", 0.05, scale=1),
            _fact("Operating Forecast!C9", 0.05, scale=1),
            _fact("Operating Forecast!C9", 0.07, scale=1),
            _fact("Assumptions!C20", 0.0575, scale=1),
        ],
    )
    by_concept = {row["concept"]: row for row in got}
    assert by_concept["noi"]["status"] == "cited"
    assert by_concept["noi"]["row_key"] == "Summary!C7"
    assert _sheet(by_concept["noi"]) == ["3288000"]
    assert by_concept["vacancy"]["row_key"] == "Assumptions!C13"
    assert _sheet(by_concept["vacancy"]) == ["0.05"]


def test_two_exact_labels_without_the_preferred_phrase_stay_ambiguous():
    """Нет предпочтительной подписи — две основные строки не схлопываются, короткая не побеждает."""

    got = cite_type_book_rows(
        source="inferred",
        primary="real_estate_income",
        bindings=[
            _binding("noi", "Summary!C7", label="Net operating income"),
            _binding("noi", "Operating Forecast!C15", label="Net operating income"),
            _binding(
                "cap_rate",
                "Assumptions!C20",
                label="Underwriting capitalization rate",
            ),
            _binding("dscr", "Summary!C17", label="Debt service coverage ratio"),
            _binding("dscr", "Summary!G10", label="DSCR"),
        ],
        facts=[
            _fact("Summary!C7", 3_288_000, scale=1),
            _fact("Operating Forecast!C15", 33_502_954, scale=1),
            _fact("Assumptions!C20", 0.0575, scale=1),
            _fact("Summary!C17", 1.30, scale=1),
            _fact("Summary!G10", 33_502_954, scale=1),
        ],
    )
    by_concept = {row["concept"]: row for row in got}
    assert by_concept["noi"]["status"] == "ambiguous"
    assert by_concept["noi"]["observations"] == []
    assert "row_key" not in by_concept["noi"]
    assert by_concept["cap_rate"]["status"] == "cited"
    assert "dscr" not in by_concept
    assert all(Decimal(value) < 100 for value in _sheet(by_concept["cap_rate"]))


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
    assert [len(_sheet(row)) for row in got] == [36, 36, 36]
    assert [Decimal(value) for value in _sheet(got[0])[:2]] == [
        Decimal(2000),
        Decimal(2000),
    ]
    assert Decimal(_sheet(got[1])[0]) == Decimal(0)
    assert [Decimal(value) for value in _sheet(got[2])[:2]] == [
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
        assert all(row["status"] == "absent" and _sheet(row) == [] for row in got)


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
    assert cited[0]["status"] == "absent"
    confirmed = cite_type_book_rows(
        source="confirmed",
        primary="real_estate_income",
        bindings=[_binding("cap_rate", "r", source="confirmed")],
        facts=facts,
    )
    assert confirmed[0]["status"] == "cited"
    assert confirmed[0]["observations"][0]["value"] == "0.0575"


def test_cited_number_is_value_dec_not_the_scaled_amount():
    """512,4 на листе не превращается в 512400000."""

    got = cite_type_book_rows(
        source="inferred",
        primary="real_estate_income",
        bindings=[_binding("cap_rate", "Assumptions!C20")],
        facts=[
            {
                "row_key": "Assumptions!C20",
                "value_dec": "512.4",
                "normalized_value": "512400000",
                "scale_factor": 1_000_000,
                "value_status": "cached",
            }
        ],
    )
    assert got[0]["status"] == "cited"
    assert _sheet(got[0]) == ["512.4"]
    assert got[0]["observations"][0]["normalized_value"] == "512400000"
    assert got[0]["observations"][0]["scale_factor"] == 1_000_000


def test_missing_value_dec_is_not_replaced_by_normalized_value():
    got = cite_type_book_rows(
        source="inferred",
        primary="real_estate_income",
        bindings=[_binding("cap_rate", "Assumptions!C20")],
        facts=[
            {
                "row_key": "Assumptions!C20",
                "normalized_value": "0.0575",
                "value_status": "cached",
                "cell_id": "Assumptions!D20",
                "period_id": "uw",
            }
        ],
    )
    observed = got[0]["observations"][0]
    assert got[0]["status"] == "cited"
    assert observed["value"] is None
    assert observed["normalized_value"] == "0.0575"
    assert observed["cell_id"] == "Assumptions!D20"
    assert observed["period_id"] == "uw"


def test_empty_and_error_statuses_are_not_quoted_as_numbers():
    got = cite_type_book_rows(
        source="inferred",
        primary="bank_leasing",
        bindings=[
            _binding("lease_interest_income", "income"),
            _binding("npl_share", "share"),
            _binding("provision_coverage", "cover"),
        ],
        facts=[
            {
                "row_key": "income",
                "value_dec": "260",
                "value_status": "empty",
                "cell_id": "B2",
                "period_id": "t",
            },
            {
                "row_key": "share",
                "value_dec": "0.125",
                "value_status": "error",
                "cell_id": "B5",
                "period_id": "t",
            },
            {
                "row_key": "cover",
                "value_dec": "0.5",
                "value_status": "missing",
                "cell_id": "B8",
                "period_id": "t",
            },
        ],
    )
    assert [_sheet(row) for row in got] == [[None], [None], [None]]
    assert [row["observations"][0]["value_status"] for row in got] == [
        "empty",
        "error",
        "missing",
    ]
    assert [row["observations"][0]["cell_id"] for row in got] == ["B2", "B5", "B8"]


def test_a_gap_keeps_its_slot_and_axes_stay_separate():
    """Пропуск посередине не сдвигает следующий период. Оси не склеиваются."""

    got = cite_type_book_rows(
        source="inferred",
        primary="renewables_dpm",
        bindings=[_binding("energy_generation", "gen")],
        facts=[
            _fact(
                "gen",
                "30",
                cell_id="Model!J58",
                axis_id="north",
                period_id="y2",
                period_index=2,
            ),
            _fact(
                "gen",
                None,
                cell_id="Model!I58",
                axis_id="north",
                period_id="y1",
                period_index=1,
                status="empty",
            ),
            _fact(
                "gen",
                "10",
                cell_id="Model!H58",
                axis_id="south",
                period_id="y0",
                period_index=0,
            ),
            _fact(
                "gen",
                "11",
                cell_id="Model!I58s",
                axis_id="south",
                period_id="y1",
                period_index=1,
            ),
            _fact(
                "gen",
                "10",
                cell_id="Model!H58b",
                axis_id="south",
                period_id="y0",
                period_index=0,
            ),
        ],
    )
    observed = next(
        row["observations"] for row in got if row["concept"] == "energy_generation"
    )
    assert [
        (item["axis_id"], item["period_index"], item["value"]) for item in observed
    ] == [
        ("north", 1, None),
        ("north", 2, "30"),
        ("south", 0, "10"),
        ("south", 0, "10"),
        ("south", 1, "11"),
    ]
    assert [item["cell_id"] for item in observed] == [
        "Model!I58",
        "Model!J58",
        "Model!H58",
        "Model!H58b",
        "Model!I58s",
    ]
    assert [item["period_id"] for item in observed] == ["y1", "y2", "y0", "y0", "y1"]
    assert observed[0]["value_status"] == "empty"
    assert observed[2]["normalized_value"] == "10000"


def test_two_primaries_are_ambiguous_and_human_type_skips_inferred_rows():
    facts = [
        _fact("first", "1", scale=1),
        _fact("second", "2", scale=1),
    ]
    got = cite_type_book_rows(
        source="inferred",
        primary="real_estate_income",
        bindings=[
            _binding("cap_rate", "first"),
            _binding("cap_rate", "second"),
        ],
        facts=facts,
    )
    assert got[0]["status"] == "ambiguous"
    assert got[0]["observations"] == []
    assert "row_key" not in got[0]
    same = cite_type_book_rows(
        source="inferred",
        primary="real_estate_income",
        bindings=[
            _binding("cap_rate", "first"),
            _binding("cap_rate", "first"),
        ],
        facts=facts,
    )
    assert same[0]["status"] == "cited"
    assert same[0]["row_key"] == "first"
    assert _sheet(same[0]) == ["1"]
    skipped = cite_type_book_rows(
        source="profile",
        primary="real_estate_income",
        bindings=[_binding("cap_rate", "first", status="ambiguous")],
        facts=facts,
    )
    assert skipped[0]["status"] == "absent"


def test_book_rows_are_attached_on_ratios_and_full():
    text = Path(_attach_book_rows.__code__.co_filename).read_text(encoding="utf-8")
    assert text.count("_attach_book_rows(envelope, got)") == 2


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
