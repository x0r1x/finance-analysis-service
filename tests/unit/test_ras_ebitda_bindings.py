"""Срез 1: узнать строки РСБУ. Ничего не складывать и не подменять EBITDA."""

from finance_analysis.application.catalog import load_catalog
from finance_analysis.application.financial_catalog import load_financial_catalog
from finance_analysis.domain.mapping import assign_rows
from tests.unit.test_mapping_ml import _row

_BOUND = {
    "Прибыль (убыток) от продаж": "operating_profit",
    "Прибыль (убыток) от продаж (2200)": "operating_profit",
    "Прибыль от продаж (2200)": "operating_profit",
    "Операционная прибыль": "operating_profit",
    "Амортизация (5640)": "production_cost_depreciation",
    "Прочие доходы": "other_income",
    "Прочие доходы (2340)": "other_income",
    "Прочие расходы": "other_expenses",
    "Прочие расходы (2350)": "other_expenses",
    "Расходы по финансовому лизингу в себестоимости": "finance_lease_in_cost",
}

_UNKNOWN = (
    "Амортизация",
    "Накопленная амортизация",
    "Курсовые разницы",
    "Резерв по сомнительным долгам",
    "Субсидия на уплату процентов",
    "Штрафы",
    "Прибыль от продажи основных средств",
    "Переоценка",
    "Прибыль от участия в других организациях",
    "Лизинг",
    "Финансовый лизинг",
)

_FRESH = frozenset(
    {"production_cost_depreciation", "other_income", "other_expenses", "finance_lease_in_cost"}
)


def _assign(glossary, label: str):
    return assign_rows([_row("row", label, unit="money")], [], glossary)["row"]


def test_ras_lines_bind_and_exclusions_stay_unknown():
    glossary = load_catalog()
    for label, concept in _BOUND.items():
        item = _assign(glossary, label)
        assert item.status == "bound", label
        assert item.concept == concept, label
    for label in _UNKNOWN:
        item = _assign(glossary, label)
        assert item.status == "unknown", label
        assert item.concept is None, label
    assert glossary.resolve("EBITDA").concept == "ebitda"
    assert glossary.resolve("Процентный доход лизингодателя").concept == "lease_interest_income"


def test_new_lines_do_not_enter_ratio_inputs():
    catalog = load_financial_catalog()
    for metric in ("icr", "dscr", "net_debt_ebitda"):
        indicator = catalog.indicators[metric]
        names = set(indicator.inputs.concepts)
        for variant in indicator.variants.values():
            names |= set(variant.inputs.concepts)
        assert names.isdisjoint(_FRESH), metric
        assert "ebitda" in names or metric == "dscr"
    dscr = catalog.indicators["dscr"]
    assert "ebitda" in dscr.variants["corporate_covenant"].inputs.concepts
    assert "ebitda" not in dscr.inputs.concepts
