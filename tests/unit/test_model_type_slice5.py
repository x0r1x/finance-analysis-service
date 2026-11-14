"""Срез 5: новые типы не срабатывают от одной соседней метки."""

from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

import openpyxl
import yaml

from finance_analysis.application.analyses import RATIO_METRICS
from finance_analysis.application.catalog import load_catalog
from finance_analysis.domain.book_cite import CITED_BY_TYPE
from finance_analysis.domain.model_type import applicability, infer, open_concepts
from finance_analysis.domain.model_type_eval import Expectation, build_report
from tests.workbook_labels import resolved_workbook

_BOOKS = Path(__file__).resolve().parents[1] / "fixtures" / "model_books"
# Точные подписи DebtLens. G10 — вторая подпись DSCR в шапке ёмкости, не коэффициент 1,30x.
_DEBTLENS_HITS = (
    ("Summary", "C7", "Year 1 net operating income", "noi"),
    ("Summary", "G10", "DSCR", "dscr"),
    ("Summary", "C17", "Debt service coverage ratio", "dscr"),
    ("Assumptions", "C13", "Year 1 vacancy", "vacancy"),
    ("Assumptions", "C20", "Underwriting capitalization rate", "cap_rate"),
    ("Operating Forecast", "C9", "Vacancy", "vacancy"),
    ("Operating Forecast", "C12", "Effective gross income", "effective_gross_income"),
    ("Operating Forecast", "C13", "Operating expense ($/sf)", "operating_expenses"),
    ("Operating Forecast", "C14", "Operating expenses", "operating_expenses"),
    ("Operating Forecast", "C15", "Net operating income", "noi"),
    ("Debt Schedule", "F6", "Interest", "interest"),
    ("Debt Schedule", "G6", "Principal", "principal"),
)
_DEBTLENS_FREE = (
    ("Assumptions", "C21", "Exit capitalization rate"),
    ("Operating Forecast", "C11", "Vacancy loss"),
    ("Assumptions", "C27", "Minimum DSCR"),
    ("Summary", "C13", "DSCR capacity"),
    ("Sensitivity", "C16", "Value adj. / Cap rate"),
)
# Шестнадцать подписей solar_dogu. Project Size (AC) и €/W (DC) — известные принятые
# привязки installed_capacity: тело AC совпадает после снятия скобки, €/W (DC) приходит
# через аббревиатуру dc. Глоссарий и сопоставитель пока не чиним.
_SOLAR_HITS = (
    ("Model", "J14", "Capex", "capex"),
    ("Model", "M16", "€/W (DC)", "installed_capacity"),
    ("Model", "B20", "Project Size (DC)", "installed_capacity"),
    ("Model", "B21", "Project Size (AC)", "installed_capacity"),
    ("Model", "B23", "Degredation ", "degradation"),
    ("Model", "B58", "Annual Energy per year", "energy_generation"),
    ("Model", "B61", "PPA Power Price", "energy_tariff"),
    ("Model", "B123", "Depreciation", "depreciation"),
    ("Model", "B128", "Depreciation", "depreciation"),
    ("Model", "B133", "Depreciation", "depreciation"),
    ("Model", "B138", "Depreciation", "depreciation"),
    ("Model", "B143", "Depreciation", "depreciation"),
    ("Model", "B164", "EBITDA", "ebitda"),
    ("Model", "C168", "Interest", "interest"),
    ("Model", "C169", "Principal", "principal"),
    ("Model", "B220", "EBITDA", "ebitda"),
)
_SOLAR_FREE = (
    ("Model", "B62", "Post PPA Power Price"),
    ("Model", "H15", "P50"),
    ("Model", "F18", "P50"),
    ("Model", "F20", "P90"),
    ("Model", "F21", "P99"),
    ("Model", "G86", "P99"),
    ("Model", "N16", "€/W (AC)"),
    ("Model", "G17", "Production"),
    ("Model", "I37", "DSCR P50 minimum"),
    ("Model", "I38", "DSCR P99 minimum"),
    ("Model", "B57", "Revenue"),
    ("Model", "B218", "Revenue"),
    ("Model", "B55", "Degredation Year/Inflation year"),
    ("Model", "B59", "% of original output"),
    ("Model", "B54", "Production Year"),
    ("Model", "B63", "Total Revenue"),
    ("Model", "B78", "EBITDA, used for financing"),
    ("Model", "B148", "EBITDA for year"),
    ("Model", "B91", "Less: Interest"),
    ("Model", "B105", "Less: Principal"),
    ("Model", "P16", "Post PPA Term"),
    ("Model", "G206", "Post PPA Rate"),
)
# Пять подписей lease_portfolio. Interest — точный pref, четыре остальные — точный alt.
# Слова портфеля, ставки резерва и шапки графика остаются свободными.
_LEASE_HITS = (
    ("Schedule", "F1", "Interest", "interest", "pref"),
    ("Schedule", "G1", "Principal", "principal", "alt"),
    ("Summary", "A2", "Interest income", "lease_interest_income", "alt"),
    ("Summary", "A5", "NPL share", "npl_share", "alt"),
    ("Summary", "A8", "Provision coverage", "provision_coverage", "alt"),
)
_LEASE_FREE = (
    ("Schedule", "A1", "Contract"),
    ("Schedule", "B1", "Year"),
    ("Schedule", "C1", "Opening"),
    ("Schedule", "D1", "Rate"),
    ("Schedule", "E1", "DPD"),
    ("Schedule", "H1", "Payment"),
    ("Schedule", "I1", "Closing"),
    ("Schedule", "J1", "NPL"),
    ("Schedule", "A2", "A"),
    ("Schedule", "A3", "A"),
    ("Schedule", "A4", "B"),
    ("Schedule", "A5", "B"),
    ("Schedule", "A6", "C"),
    ("Schedule", "A7", "C"),
    ("Summary", "A1", "Lessor portfolio"),
    ("Summary", "A3", "Gross portfolio"),
    ("Summary", "A4", "NPL balance"),
    ("Summary", "A6", "Provision rate"),
    ("Summary", "A7", "Provisions"),
)
_LEASE_CONCEPTS = ("lease_interest_income", "npl_share", "provision_coverage")
_LEASE_SHEETS = frozenset({"Schedule", "Summary"})
_LEASE_BOOK = "leasing/lease_portfolio.recalc_libreoffice.xlsx"


def _catalog():
    from finance_analysis.application.model_types import load_model_types

    return load_model_types()


def _infer(**kwargs):
    return infer(_catalog(), accept=0.6, gap=0.15, **kwargs)


def test_lbo_needs_sources_exit_and_a_return():
    full = _infer(
        bound=frozenset({"sources_and_uses", "exit_enterprise_value", "moic"}),
        sheets=frozenset(),
    )
    sources = _infer(bound=frozenset({"sources_and_uses", "moic"}), sheets=frozenset())
    assert full.confident is True and full.primary == "lbo_ma" and full.labels == ("lbo_ma",)
    assert sources.confident is False and sources.reason == "unknown"
    assert sources.scores["lbo_ma"] == 0.5


def test_sources_exit_and_catalog_irr_without_moic_are_not_a_confident_lbo():
    """Связка sources_and_uses, exit_enterprise_value и каталожного irr без moic не даёт уверенный lbo_ma.

    Срабатывает только первый сигнал. Score равен 0.5 и остаётся ниже порога принятия 0.6.
    """
    got = _infer(
        bound=frozenset({"sources_and_uses", "exit_enterprise_value", "irr"}),
        sheets=frozenset(),
    )
    assert got.scores["lbo_ma"] == 0.5
    assert got.confident is False
    assert got.reason == "unknown"
    assert got.labels == ()


def test_halyard_stays_confident_lbo_ma_at_full_score():
    """Книга Halyard остаётся уверенным lbo_ma со score 1.0, потому что привязан moic."""
    bound, sheets = resolved_workbook("halyard/project_halyard.recalc_libreoffice.xlsx")
    got = _infer(bound=bound, sheets=sheets)
    assert got.confident is True
    assert got.primary == "lbo_ma"
    assert got.labels == ("lbo_ma",)
    assert got.scores["lbo_ma"] == 1.0


def test_meridian_stays_confident_dcf_valuation_at_full_score():
    """Книга Meridian остаётся уверенным dcf_valuation со score 1.0, потому что привязаны все четыре понятия сигнала."""
    bound, sheets = resolved_workbook("meridian/meridian_dcf.recalc_libreoffice.xlsx")
    got = _infer(bound=bound, sheets=sheets)
    assert got.confident is True
    assert got.primary == "dcf_valuation"
    assert got.labels == ("dcf_valuation",)
    assert got.scores["dcf_valuation"] == 1.0


def test_ppa_allocation_is_not_renewables_but_capacity_or_tariff_is():
    allocation = _infer(bound=frozenset({"purchase_price_allocation"}), sheets=frozenset())
    capacity = _infer(bound=frozenset({"installed_capacity"}), sheets=frozenset())
    tariff = _infer(bound=frozenset({"energy_tariff"}), sheets=frozenset())
    assert allocation.confident is False
    assert allocation.scores["renewables_dpm"] == 0.0
    assert capacity.primary == "renewables_dpm" and capacity.confident is True
    assert tariff.primary == "renewables_dpm" and tariff.labels == ("renewables_dpm",)


def test_solar_sources_without_exit_stay_renewables():
    got = _infer(
        bound=frozenset(
            {"installed_capacity", "energy_generation", "degradation", "energy_tariff", "sources_and_uses", "moic"}
        ),
        sheets=frozenset(),
    )
    assert got.confident is True
    assert got.primary == "renewables_dpm"
    assert got.labels == ("renewables_dpm",)
    assert got.scores["lbo_ma"] == 0.5


def test_dcf_real_estate_and_leasing_need_their_full_set():
    dcf = _infer(
        bound=frozenset({"wacc", "terminal_value", "enterprise_value", "equity_value"}),
        sheets=frozenset(),
    )
    wacc = _infer(bound=frozenset({"wacc"}), sheets=frozenset())
    estate = _infer(bound=frozenset({"noi", "cap_rate", "vacancy"}), sheets=frozenset())
    noi = _infer(bound=frozenset({"noi", "cap_rate"}), sheets=frozenset())
    lease = _infer(
        bound=frozenset({"lease_interest_income", "npl_share", "provision_coverage"}),
        sheets=frozenset(),
    )
    assert dcf.primary == "dcf_valuation" and dcf.confident is True
    assert wacc.confident is False and wacc.scores["dcf_valuation"] == 0.0
    assert estate.primary == "real_estate_income"
    assert noi.confident is False
    assert lease.primary == "bank_leasing" and lease.labels == ("bank_leasing",)


def test_wacc_and_terminal_value_without_enterprise_and_equity_are_not_confident_dcf():
    """Связка wacc и terminal_value без enterprise_value и equity_value не даёт уверенный dcf_valuation.

    Сигнал один и имеет вид concepts_bound_all по всем четырём понятиям, поэтому score равен 0.0.
    """
    got = _infer(bound=frozenset({"wacc", "terminal_value"}), sheets=frozenset())
    assert got.scores["dcf_valuation"] == 0.0
    assert got.confident is False
    assert got.reason == "unknown"
    assert got.labels == ()


def test_enterprise_and_equity_without_wacc_are_not_confident_dcf():
    """Связка enterprise_value и equity_value без wacc и без terminal_value не даёт уверенный dcf_valuation.

    Сигнал один и имеет вид concepts_bound_all по всем четырём понятиям, поэтому score равен 0.0.
    """
    got = _infer(bound=frozenset({"enterprise_value", "equity_value"}), sheets=frozenset())
    assert got.scores["dcf_valuation"] == 0.0
    assert got.confident is False
    assert got.reason == "unknown"
    assert got.labels == ()


def test_debtlens_stays_confident_real_estate_income_at_full_score():
    """Книга связывает восемь понятий и остаётся уверенным real_estate_income со score 1.0.

    Близкие подписи не привязываются. Цитата типа — cap_rate, noi и vacancy.
    """

    book = "debtlens/DebtLens_Underwriting_Model.xlsx"
    package = load_catalog()
    grid = openpyxl.load_workbook(_BOOKS / book, data_only=False)
    hits: list[tuple[str, str, str, str]] = []
    try:
        for sheet, coord, text, concept in _DEBTLENS_HITS:
            assert grid[sheet][coord].value == text
            assert package.resolve(text).concept == concept
        for sheet, coord, text in _DEBTLENS_FREE:
            assert grid[sheet][coord].value == text
            assert package.resolve(text) is None, text
        assert package.resolve("Cap rate") is None
        for sheet in grid.worksheets:
            for row in sheet.iter_rows():
                for cell in row:
                    label = cell.value
                    if (
                        not isinstance(label, str)
                        or not label.strip()
                        or label.startswith("=")
                    ):
                        continue
                    found = package.resolve(label)
                    if found is not None:
                        hits.append(
                            (sheet.title, cell.coordinate, label, found.concept)
                        )
    finally:
        grid.close()
    assert hits == list(_DEBTLENS_HITS)
    bound, sheets = resolved_workbook(book)
    assert bound == frozenset(
        {
            "cap_rate",
            "dscr",
            "effective_gross_income",
            "interest",
            "noi",
            "operating_expenses",
            "principal",
            "vacancy",
        }
    )
    got = infer(_catalog(), bound=bound, sheets=sheets, accept=0.6, gap=0.15)
    assert got.confident is True
    assert got.primary == "real_estate_income"
    assert got.labels == ("real_estate_income",)
    assert got.scores["real_estate_income"] == 1.0
    assert CITED_BY_TYPE["real_estate_income"] == ("cap_rate", "noi", "vacancy")


def test_solar_dogu_stays_confident_renewables_dpm_at_full_score():
    """Книга solar_dogu связывает девять понятий и остаётся уверенным renewables_dpm со score 1.0.

    Близкие подписи не привязываются. Сигнал остаётся concepts_bound_any и держит
    installed_capacity. Цитата типа — degradation, energy_generation и energy_tariff.
    """

    book = "solar/Solar Financial Model.xlsx"
    package = load_catalog()
    grid = openpyxl.load_workbook(_BOOKS / book, data_only=False)
    hits: list[tuple[str, str, str, str]] = []
    try:
        for sheet, coord, text, concept in _SOLAR_HITS:
            assert grid[sheet][coord].value == text
            assert package.resolve(text).concept == concept
        # Известные принятые привязки. (AC) — точное тело, €/W (DC) — аббревиатура dc.
        ac = package.resolve_match("Project Size (AC)")
        per_dc = package.resolve_match("€/W (DC)")
        assert ac is not None and ac[0].concept == "installed_capacity" and ac[1] == "exact"
        assert (
            per_dc is not None
            and per_dc[0].concept == "installed_capacity"
            and per_dc[1] == "abbrev"
        )
        for sheet, coord, text in _SOLAR_FREE:
            assert grid[sheet][coord].value == text
            assert package.resolve(text) is None, text
        for sheet in grid.worksheets:
            for row in sheet.iter_rows():
                for cell in row:
                    label = cell.value
                    if (
                        not isinstance(label, str)
                        or not label.strip()
                        or label.startswith("=")
                    ):
                        continue
                    found = package.resolve(label)
                    if found is not None:
                        hits.append((sheet.title, cell.coordinate, label, found.concept))
    finally:
        grid.close()
    assert hits == list(_SOLAR_HITS)
    bound, sheets = resolved_workbook(book)
    assert sheets == frozenset({"Model"})
    assert bound == frozenset(
        {
            "capex",
            "degradation",
            "depreciation",
            "ebitda",
            "energy_generation",
            "energy_tariff",
            "installed_capacity",
            "interest",
            "principal",
        }
    )
    catalog = _catalog()
    signal = catalog.types["renewables_dpm"].signals
    assert tuple(item.kind for item in signal) == ("concepts_bound_any",)
    assert "installed_capacity" in signal[0].concepts
    got = infer(catalog, bound=bound, sheets=sheets, accept=0.6, gap=0.15)
    assert got.confident is True
    assert got.primary == "renewables_dpm"
    assert got.labels == ("renewables_dpm",)
    assert got.scores["renewables_dpm"] == 1.0
    others = {name: score for name, score in got.scores.items() if name != "renewables_dpm"}
    assert others and set(others.values()) == {0.0}
    assert CITED_BY_TYPE["renewables_dpm"] == (
        "degradation",
        "energy_generation",
        "energy_tariff",
    )
    assert "installed_capacity" not in CITED_BY_TYPE["renewables_dpm"]


def test_lease_portfolio_stays_confident_bank_leasing_at_full_score():
    """Книга lease_portfolio связывает пять понятий и остаётся уверенным bank_leasing со score 1.0.

    Близкие подписи не привязываются. Сигнал остаётся concepts_bound_all веса 1 по
    трём понятиям лизинга. Цитата типа — lease_interest_income, npl_share и
    provision_coverage. Interest и principal в неё не входят.
    """

    package = load_catalog()
    grid = openpyxl.load_workbook(_BOOKS / _LEASE_BOOK, data_only=False)
    hits: list[tuple[str, str, str, str]] = []
    try:
        for sheet, coord, text, concept, kind in _LEASE_HITS:
            assert grid[sheet][coord].value == text
            found = package.resolve_match(text)
            assert found is not None, text
            hit, strength = found
            assert hit.concept == concept and hit.kind == kind and strength == "exact"
        for sheet, coord, text in _LEASE_FREE:
            assert grid[sheet][coord].value == text
            assert package.resolve(text) is None, text
        for sheet in grid.worksheets:
            for row in sheet.iter_rows():
                for cell in row:
                    label = cell.value
                    if (
                        not isinstance(label, str)
                        or not label.strip()
                        or label.startswith("=")
                    ):
                        continue
                    found = package.resolve(label)
                    if found is not None:
                        hits.append((sheet.title, cell.coordinate, label, found.concept))
    finally:
        grid.close()
    assert hits == [
        (sheet, coord, text, concept) for sheet, coord, text, concept, _kind in _LEASE_HITS
    ]
    bound, sheets = resolved_workbook(_LEASE_BOOK)
    assert sheets == _LEASE_SHEETS
    assert bound == frozenset({"interest", "principal", *_LEASE_CONCEPTS})
    catalog = _catalog()
    signal = catalog.types["bank_leasing"].signals
    assert tuple(item.kind for item in signal) == ("concepts_bound_all",)
    assert signal[0].weight == 1.0
    assert signal[0].concepts == _LEASE_CONCEPTS
    got = infer(catalog, bound=bound, sheets=sheets, accept=0.6, gap=0.15)
    assert got.confident is True
    assert got.primary == "bank_leasing"
    assert got.labels == ("bank_leasing",)
    assert got.scores["bank_leasing"] == 1.0
    others = {name: score for name, score in got.scores.items() if name != "bank_leasing"}
    assert others and set(others.values()) == {0.0}
    assert CITED_BY_TYPE["bank_leasing"] == _LEASE_CONCEPTS


def test_lease_portfolio_and_signal_scores_only_the_full_set():
    """Один concepts_bound_all веса 1. Собственное подмножество трёх понятий даёт 0.0.

    Причина unknown, метки пустые. Проценты с основным долгом сами тип не дают.
    Пять понятий держат score 1.0 только у bank_leasing. Вариантов нет.
    Семнадцать метрик каталога: ncf необязателен, остальные неприменимы. Открытых вопросов нет.
    При нулевом score лидер остаётся bank_leasing: равенство режется по id.
    """

    catalog = _catalog()
    signal = catalog.types["bank_leasing"].signals
    assert len(signal) == 1
    item = signal[0]
    assert item.kind == "concepts_bound_all"
    assert item.weight == 1.0
    assert item.concepts == _LEASE_CONCEPTS
    assert item.absent == ()
    assert item.groups == ()
    assert catalog.types["bank_leasing"].variants == {}
    metrics = catalog.types["bank_leasing"].metrics
    assert len(RATIO_METRICS) == 17
    assert set(metrics) == set(RATIO_METRICS)
    assert metrics["ncf"] == "optional"
    assert {use for name, use in metrics.items() if name != "ncf"} == {"not_applicable"}
    for metric in RATIO_METRICS:
        expected = "optional" if metric == "ncf" else "not_applicable"
        assert applicability(catalog, ("bank_leasing",), metric) == expected, metric
    bound, _sheets = resolved_workbook(_LEASE_BOOK)
    assert open_concepts(catalog, ("bank_leasing",), bound=bound, absent=frozenset()) == ()
    assert open_concepts(
        catalog, ("bank_leasing",), bound=frozenset(), absent=frozenset()
    ) == ()
    for size in range(len(_LEASE_CONCEPTS)):
        for subset in combinations(_LEASE_CONCEPTS, size):
            got = _infer(bound=frozenset(subset), sheets=_LEASE_SHEETS)
            assert got.scores["bank_leasing"] == 0.0, subset
            assert set(got.scores.values()) == {0.0}, subset
            assert got.confident is False and got.reason == "unknown" and got.labels == ()
            assert got.primary == "bank_leasing"
    debt = _infer(bound=frozenset({"interest", "principal"}), sheets=_LEASE_SHEETS)
    assert debt.scores["bank_leasing"] == 0.0
    assert set(debt.scores.values()) == {0.0}
    assert debt.confident is False and debt.reason == "unknown" and debt.labels == ()
    assert debt.primary == "bank_leasing"
    five = _infer(
        bound=frozenset({"interest", "principal", *_LEASE_CONCEPTS}),
        sheets=_LEASE_SHEETS,
    )
    assert five.confident is True
    assert five.primary == "bank_leasing"
    assert five.labels == ("bank_leasing",)
    assert five.scores["bank_leasing"] == 1.0
    others = {name: score for name, score in five.scores.items() if name != "bank_leasing"}
    assert others and set(others.values()) == {0.0}


def test_lease_portfolio_eval_row_still_matches_the_snapshot():
    """Строка снимка lease_portfolio не переписывается: bank_leasing 1, corporate 0, разрыв 1."""

    root = Path(__file__).resolve().parents[2]
    snapshot = json.loads((root / "eval" / "model_type" / "report.json").read_text(encoding="utf-8"))
    assert (snapshot["accept"], snapshot["gap"]) == (0.6, 0.15)
    stored = next(row for row in snapshot["cases"] if row["id"] == "lease_portfolio")
    spec = yaml.safe_load(
        (root / "tests" / "fixtures" / "model_type_eval" / "cases.yaml").read_text(encoding="utf-8")
    )
    case = next(item for item in spec["cases"] if item["id"] == "lease_portfolio")
    assert case["source"] == "workbook"
    assert case["book"] == _LEASE_BOOK
    expect = case["expect"]
    assert expect == {"kind": "type", "primary": "bank_leasing", "labels": ["bank_leasing"]}
    bound, sheets = resolved_workbook(case["book"])
    catalog = _catalog()
    got = infer(catalog, bound=bound, sheets=sheets, accept=0.6, gap=0.15)
    report = build_report(
        [
            (
                "lease_portfolio",
                Expectation("type", expect["primary"], tuple(expect["labels"])),
                got,
            )
        ],
        accept=0.6,
        gap=0.15,
        type_ids=tuple(sorted(catalog.ids)),
    )
    assert stored["primary"] == "bank_leasing"
    assert stored["scores"]["bank_leasing"] == 1.0
    assert stored["top2"] == "corporate"
    assert stored["top2_score"] == 0.0
    assert stored["gap"] == 1.0
    assert stored["false_positives"] == []
    assert report["cases"][0] == stored


def test_fixture_workbooks_classify_from_their_own_labels():
    """Тип берётся из подписей книги, а не из вручную перечисленных id."""
    package = load_catalog()
    assert package.resolve("IRR") is None
    expect = {
        "halyard/project_halyard.recalc_libreoffice.xlsx": "lbo_ma",
        "meridian/meridian_dcf.recalc_libreoffice.xlsx": "dcf_valuation",
        "debtlens/DebtLens_Underwriting_Model.xlsx": "real_estate_income",
        "solar/Solar Financial Model.xlsx": "renewables_dpm",
        "leasing/lease_portfolio.recalc_libreoffice.xlsx": "bank_leasing",
    }
    catalog = _catalog()
    for book, primary in expect.items():
        bound, sheets = resolved_workbook(book)
        got = infer(catalog, bound=bound, sheets=sheets, accept=0.6, gap=0.15)
        assert got.confident is True and got.primary == primary and got.labels == (primary,), book


def test_project_finance_book_does_not_become_a_new_type():
    got = _infer(bound=frozenset({"cfads", "debt_service"}), sheets=frozenset({"Debt", "CFS"}))
    assert got.confident is True
    assert got.primary == "project_finance"
    assert got.labels == ("project_finance",)
    assert got.scores["lbo_ma"] == 0.0
    assert got.scores["renewables_dpm"] == 0.0
