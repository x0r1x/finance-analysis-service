"""Цитата строк пяти типов. Формулы нет, вопроса нет, матрица коэффициентов не меняется."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import openpyxl

from finance_analysis.application.analyses import RATIO_METRICS, _attach_book_rows
from finance_analysis.application.catalog import load_catalog
from finance_analysis.application.model_types import load_model_types
from finance_analysis.domain.book import FAS_SCHEMA_VERSION
from finance_analysis.domain.book_cite import (
    CITED_BY_TYPE,
    PREFERRED_LABEL,
    cite_type_book_rows,
)
from finance_analysis.domain.glossary import normalize_label
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


def _band(grid, row: int, start: int, end: int) -> list[tuple[str, object]]:
    """Ячейки строки слева направо: `Model!H58` и значение."""

    return [
        (f"Model!{grid.cell(row, column).coordinate}", grid.cell(row, column).value)
        for column in range(start, end + 1)
    ]


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
    """Процентный доход Summary!B2 — кэш 260 формулы SUM(Schedule!F2:F7).

    Доля NPL Summary!B5 равна 0,125, покрытие Summary!B8 равно 0,5. У каждого
    понятия одно наблюдение со статусом cached, row_key остаётся подписью столбца A.
    Ряд Schedule!F2:F7 сидит на interest и в наблюдения процентного дохода не входит.
    Summary!B6 тоже 0,5: это ставка резерва, не покрытие. Предпочтительной подписи нет.
    """

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
    assert package.resolve(_label(book, "Schedule", "F1")).concept == "interest"
    assert _label(book, "Summary", "B2") == "=SUM(Schedule!F2:F7)"
    assert _label(book, "Summary", "A6") == "Provision rate"
    income, share, cover = (
        _cached(book, "Summary", "B2"),
        _cached(book, "Summary", "B5"),
        _cached(book, "Summary", "B8"),
    )
    provision_rate = _cached(book, "Summary", "B6")
    assert income == 260 and share == 0.125 and cover == 0.5 and provision_rate == 0.5
    schedule_interest = [
        (f"Schedule!F{row}", _cached(book, "Schedule", f"F{row}")) for row in range(2, 8)
    ]
    assert [cell_id for cell_id, _value in schedule_interest] == [
        "Schedule!F2",
        "Schedule!F3",
        "Schedule!F4",
        "Schedule!F5",
        "Schedule!F6",
        "Schedule!F7",
    ]
    assert "bank_leasing" not in PREFERRED_LABEL
    got = cite_type_book_rows(
        source="inferred",
        primary="bank_leasing",
        bindings=[
            _binding("lease_interest_income", "Summary!A2"),
            _binding("npl_share", "Summary!A5"),
            _binding("provision_coverage", "Summary!A8"),
            _binding("interest", "Schedule!F1"),
            _binding("principal", "Schedule!G1"),
        ],
        facts=[
            _fact("Summary!A2", income, cell_id="Summary!B2"),
            _fact("Summary!A5", share, cell_id="Summary!B5"),
            _fact("Summary!A8", cover, cell_id="Summary!B8"),
            _fact("Summary!A6", provision_rate, cell_id="Summary!B6"),
            *[
                _fact("Schedule!F1", value, cell_id=cell_id)
                for cell_id, value in schedule_interest
            ],
        ],
    )
    assert [row["concept"] for row in got] == list(CITED_BY_TYPE["bank_leasing"])
    assert CITED_BY_TYPE["bank_leasing"] == (
        "lease_interest_income",
        "npl_share",
        "provision_coverage",
    )
    assert [row["row_key"] for row in got] == ["Summary!A2", "Summary!A5", "Summary!A8"]
    assert [len(row["observations"]) for row in got] == [1, 1, 1]
    observed = [row["observations"][0] for row in got]
    assert [item["cell_id"] for item in observed] == [
        "Summary!B2",
        "Summary!B5",
        "Summary!B8",
    ]
    assert [item["value_status"] for item in observed] == ["cached", "cached", "cached"]
    assert [Decimal(item["value"]) for item in observed] == [
        Decimal(str(income)),
        Decimal(str(share)),
        Decimal(str(cover)),
    ]
    assert [Decimal(_sheet(row)[0]) for row in got] == [
        Decimal(260),
        Decimal("0.125"),
        Decimal("0.5"),
    ]
    quoted = {item["cell_id"] for row in got for item in row["observations"]}
    assert quoted.isdisjoint(cell_id for cell_id, _value in schedule_interest)
    assert "Summary!B6" not in quoted
    assert {row["concept"] for row in got}.isdisjoint({"interest", "principal"})
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


def _solar_series(row_key: str, cells, years, periods) -> list[dict]:
    """Факты строки в обратном порядке. Период берётся из книги, не из порядка вставки."""

    facts = []
    for (cell_id, value), (_, year), (_, index) in reversed(
        list(zip(cells, years, periods, strict=True))
    ):
        facts.append(
            _fact(
                row_key,
                value,
                cell_id=cell_id,
                axis_id="Model",
                period_id=str(year),
                period_index=index,
            )
        )
    return facts


def test_solar_cites_degradation_generation_and_tariff_not_capacity():
    """Деградация Model!D23 равна 0,005. Выработка H58:AK58 и тариф H61:AK61 — по 30 ячеек.

    Год и номер периода читаются из строки книги. Наблюдения идут по period_index,
    а не по порядку фактов. Хвост AB61:AK61 — нули кэша IFERROR, не пустые слоты.
    Весь ряд H61:AK61 — формула IFERROR. installed_capacity в цитату типа не входит.
    """

    book = "solar/Solar Financial Model.xlsx"
    package = load_catalog()
    assert package.resolve(_label(book, "Model", "B23")).concept == "degradation"
    assert package.resolve(_label(book, "Model", "B58")).concept == "energy_generation"
    assert package.resolve(_label(book, "Model", "B61")).concept == "energy_tariff"
    cached = openpyxl.load_workbook(_ROOT / book, data_only=True)
    formulas = openpyxl.load_workbook(_ROOT / book, data_only=False)
    try:
        start, end = 8, 37  # H:AK
        generation = _band(cached["Model"], 58, start, end)
        tariff = _band(cached["Model"], 61, start, end)
        years = _band(cached["Model"], 53, start, end)
        periods = _band(cached["Model"], 54, start, end)
        generation_formulas = _band(formulas["Model"], 58, start, end)
        tariff_formulas = _band(formulas["Model"], 61, start, end)
        assert formulas["Model"]["D23"].value == 0.005
        assert cached["Model"]["D23"].value == 0.005
    finally:
        cached.close()
        formulas.close()
    generation_ids = [cell_id for cell_id, _ in generation]
    tariff_ids = [cell_id for cell_id, _ in tariff]
    assert [year for _, year in years] == list(range(2020, 2050))
    assert [index for _, index in periods] == list(range(1, 31))
    assert generation_ids[0] == "Model!H58" and generation_ids[-1] == "Model!AK58"
    assert tariff_ids[0] == "Model!H61" and tariff_ids[19] == "Model!AA61"
    assert tariff_ids[20] == "Model!AB61" and tariff_ids[-1] == "Model!AK61"
    assert round(generation[0][1], 0) == 50370
    assert [value for _, value in tariff[:20]] == [72.75] * 20
    assert [value for _, value in tariff[20:]] == [0] * 10
    assert all(value is not None for _, value in tariff)
    assert all(
        isinstance(formula, str) and formula.startswith("=")
        for _, formula in generation_formulas
    )
    assert all(
        isinstance(formula, str) and formula.startswith("=IFERROR(")
        for _, formula in tariff_formulas
    )
    generation_facts = _solar_series("Model!B58", generation, years, periods)
    tariff_facts = _solar_series("Model!B61", tariff, years, periods)
    assert generation_facts[0]["cell_id"] == "Model!AK58"
    assert tariff_facts[0]["cell_id"] == "Model!AK61"
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
            _fact("Model!B23", 0.005, cell_id="Model!D23"),
            *generation_facts,
            *tariff_facts,
            _fact("Model!B20", 25, cell_id="Model!D20"),
            _fact("Model!B21", 20, cell_id="Model!D21"),
        ],
    )
    assert CITED_BY_TYPE["renewables_dpm"] == (
        "degradation",
        "energy_generation",
        "energy_tariff",
    )
    assert [row["concept"] for row in got] == list(CITED_BY_TYPE["renewables_dpm"])
    assert "installed_capacity" not in {row["concept"] for row in got}
    degradation = got[0]["observations"]
    assert len(degradation) == 1
    assert degradation[0]["cell_id"] == "Model!D23"
    assert degradation[0]["value_status"] == "cached"
    assert Decimal(degradation[0]["value"]) == Decimal("0.005")
    for row, cells in ((got[1], generation), (got[2], tariff)):
        observed = row["observations"]
        assert len(observed) == 30
        assert [item["cell_id"] for item in observed] == [cell_id for cell_id, _ in cells]
        assert [item["period_index"] for item in observed] == list(range(1, 31))
        assert [item["period_id"] for item in observed] == [str(year) for year in range(2020, 2050)]
        assert [item["axis_id"] for item in observed] == ["Model"] * 30
        assert [item["value_status"] for item in observed] == ["cached"] * 30
        assert [item["value"] for item in observed] == [
            format(Decimal(str(value)), "f") for _, value in cells
        ]
    assert round(Decimal(got[1]["observations"][0]["value"]), 0) == Decimal(50370)
    tail = got[2]["observations"][20:]
    assert [item["cell_id"] for item in tail] == [cell_id for cell_id, _ in tariff[20:]]
    assert [item["value"] for item in tail] == ["0"] * 10
    assert [item["value_status"] for item in tail] == ["cached"] * 10
    blank = cite_type_book_rows(
        source="inferred",
        primary="renewables_dpm",
        bindings=[_binding("energy_tariff", "Model!B61")],
        facts=[
            _fact(
                "Model!B61",
                0,
                status="empty",
                cell_id="Model!AB61",
                axis_id="Model",
                period_id="2040",
                period_index=21,
            )
        ],
    )
    assert blank[2]["observations"][0]["value"] is None
    assert blank[2]["observations"][0]["value_status"] == "empty"
    assert blank[2]["observations"][0]["cell_id"] == "Model!AB61"


def test_solar_capacity_primaries_stay_ambiguous_if_cited(monkeypatch):
    """Тела Project Size (DC) и (AC) совпадают. Две и три основные строки не схлопываются.

    Пока понятие не в CITED_BY_TYPE, тип его не отдаёт. Если бы отдавал, выбор строки
    был бы ambiguous и наблюдения пустые: последняя из B20, B21 и M16 не побеждает.
    """

    book = "solar/Solar Financial Model.xlsx"
    package = load_catalog()
    dc = _label(book, "Model", "B20")
    ac = _label(book, "Model", "B21")
    per_w = _label(book, "Model", "M16")
    assert dc == "Project Size (DC)" and ac == "Project Size (AC)"
    assert per_w == "€/W (DC)"
    assert normalize_label(dc) == normalize_label(ac) == "project size"
    assert normalize_label(per_w) != "project size"
    assert package.resolve(dc).concept == "installed_capacity"
    assert package.resolve(ac).concept == "installed_capacity"
    assert package.resolve_match(per_w)[1] == "abbrev"
    original = CITED_BY_TYPE["renewables_dpm"]
    assert original == ("degradation", "energy_generation", "energy_tariff")
    assert "installed_capacity" not in original
    monkeypatch.setitem(CITED_BY_TYPE, "renewables_dpm", (*original, "installed_capacity"))
    pair = [
        _binding("installed_capacity", "Model!B20", label=dc),
        _binding("installed_capacity", "Model!B21", label=ac),
    ]
    triple = [*pair, _binding("installed_capacity", "Model!M16", label=per_w)]
    facts = [
        _fact("Model!B20", 25, scale=1, cell_id="Model!D20"),
        _fact("Model!B21", 20, scale=1, cell_id="Model!D21"),
        _fact("Model!M16", 1, scale=1, cell_id="Model!M16"),
    ]
    for bindings in (pair, triple):
        got = cite_type_book_rows(
            source="inferred",
            primary="renewables_dpm",
            bindings=bindings,
            facts=facts,
        )
        capacity = got[-1]
        assert capacity["concept"] == "installed_capacity"
        assert capacity["status"] == "ambiguous"
        assert capacity["observations"] == []
        assert "row_key" not in capacity
    alone = cite_type_book_rows(
        source="inferred",
        primary="renewables_dpm",
        bindings=[_binding("installed_capacity", "Model!B20", label=dc)],
        facts=facts,
    )
    assert alone[-1]["status"] == "cited"
    assert alone[-1]["row_key"] == "Model!B20"
    assert alone[-1]["observations"][0]["cell_id"] == "Model!D20"
    assert alone[-1]["observations"][0]["value"] == "25"


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


def _escrow_column(grid, column: int, row_key: str) -> list[dict]:
    """Факты столбца с конца листа. Порядок наблюдений задаёт period_index, не вставка."""

    facts = []
    for row in range(grid.max_row, 1, -1):
        cell = grid.cell(row, column)
        facts.append(
            _fact(
                row_key,
                cell.value,
                cell_id=f"Модель!{cell.coordinate}",
                axis_id="Модель",
                period_id=str(grid.cell(row, 1).value),
                period_index=int(grid.cell(row, 1).value),
            )
        )
    return facts


def test_escrow_cites_inflow_disclosure_and_rate():
    """Поступления G2:G37, раскрытие H2:H37 и ставка N2:N37 цитируются по ячейке.

    H25 равно 48000, N26 равно 0,12. Первые два поступления — 2000 и 2000,
    поступление месяца 25 (G26) — 0. У понятия одна основная строка. Капитальные
    затраты, проценты, покрытие, остаток эскроу и остаток долга не цитируются.
    M25:M37 пустые: это месяцы с нулевым знаменателем, не нули покрытия.
    """

    book = "escrow/development_escrow_214.recalc_libreoffice.xlsx"
    package = load_catalog()
    headers = {
        "escrow_inflow": (7, "Модель!G1"),
        "escrow_disclosure": (8, "Модель!H1"),
        "effective_rate": (14, "Модель!N1"),
    }
    uncited = {
        "escrow_balance": (9, "Модель!I1"),
        "capex": (10, "Модель!J1"),
        "escrow_coverage": (13, "Модель!M1"),
        "interest": (15, "Модель!O1"),
        "debt_outstanding": (17, "Модель!Q1"),
    }
    for concept, (column, _row_key) in {**headers, **uncited}.items():
        letter = openpyxl.utils.get_column_letter(column)
        assert package.resolve(_label(book, "Модель", f"{letter}1")).concept == concept
    cached = openpyxl.load_workbook(_ROOT / book, data_only=True)
    formulas = openpyxl.load_workbook(_ROOT / book, data_only=False)
    try:
        grid = cached["Модель"]
        assert grid["H25"].value == 48000
        assert grid["N26"].value == 0.12
        assert grid["G2"].value == 2000 and grid["G3"].value == 2000
        assert grid["G26"].value == 0
        for row in range(25, 38):
            assert grid.cell(row, 13).value is None, row
            assert formulas["Модель"].cell(row, 13).value == f'=IF(Q{row}<=0,"",I{row}/Q{row})'
        series = {
            concept: _escrow_column(grid, column, row_key)
            for concept, (column, row_key) in headers.items()
        }
    finally:
        cached.close()
        formulas.close()
    got = cite_type_book_rows(
        source="inferred",
        primary="development_escrow",
        bindings=[
            *[_binding(concept, row_key) for concept, (_column, row_key) in headers.items()],
            _binding("escrow_inflow", "Модель!G99", primary=False),
            *[_binding(concept, row_key) for concept, (_column, row_key) in uncited.items()],
        ],
        facts=[fact for values in series.values() for fact in values],
    )
    assert [row["concept"] for row in got] == list(CITED_BY_TYPE["development_escrow"])
    assert "escrow_coverage" not in CITED_BY_TYPE["development_escrow"]
    assert {
        "capex",
        "interest",
        "escrow_coverage",
        "escrow_balance",
        "debt_outstanding",
    }.isdisjoint(row["concept"] for row in got)
    assert [row["status"] for row in got] == ["cited", "cited", "cited"]
    assert [row["row_key"] for row in got] == ["Модель!G1", "Модель!H1", "Модель!N1"]
    expected_ids = {
        "escrow_inflow": [f"Модель!G{row}" for row in range(2, 38)],
        "escrow_disclosure": [f"Модель!H{row}" for row in range(2, 38)],
        "effective_rate": [f"Модель!N{row}" for row in range(2, 38)],
    }
    for row in got:
        observed = row["observations"]
        assert [item["cell_id"] for item in observed] == expected_ids[row["concept"]]
        assert [item["period_index"] for item in observed] == list(range(1, 37))
        assert [item["period_id"] for item in observed] == [str(month) for month in range(1, 37)]
        assert [item["axis_id"] for item in observed] == ["Модель"] * 36
        assert [item["value_status"] for item in observed] == ["cached"] * 36
    by_cell = {
        item["cell_id"]: item["value"] for row in got for item in row["observations"]
    }
    assert [Decimal(by_cell["Модель!G2"]), Decimal(by_cell["Модель!G3"])] == [
        Decimal(2000),
        Decimal(2000),
    ]
    assert Decimal(by_cell["Модель!G26"]) == Decimal(0)
    assert Decimal(by_cell["Модель!H25"]) == Decimal(48000)
    assert Decimal(by_cell["Модель!N26"]) == Decimal("0.12")
    assert Decimal(_sheet(got[1])[0]) == Decimal(0)
    assert [Decimal(value) for value in _sheet(got[2])[:2]] == [
        Decimal("0.12"),
        Decimal("0.06"),
    ]
    quoted = {item["cell_id"] for row in got for item in row["observations"]}
    assert quoted.isdisjoint(f"Модель!M{row}" for row in range(2, 38))
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
    assert FAS_SCHEMA_VERSION == "1.1"
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
