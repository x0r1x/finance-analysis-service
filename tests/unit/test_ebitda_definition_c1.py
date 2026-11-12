"""Срез C1: пометка профиля и отказ публиковать сырую сумму РСБУ или МСФО."""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from finance_analysis.application.catalog import load_catalog
from finance_analysis.application.model_types import load_model_types
from finance_analysis.domain.covenant import select_ratio
from finance_analysis.domain.mapping import assign_rows
from finance_analysis.domain.metrics import coverage_ratio

_FRESH = frozenset(
    {
        "profit_from_sales",
        "ifrs_operating_profit",
        "other_income",
        "other_expense",
        "depreciation_notes",
        "ebitda_ras",
        "ebitda_ifrs",
    }
)
_BOUND = {
    "Прибыль (убыток) от реализации": "profit_from_sales",
    "Прибыль (убыток) от продаж": "profit_from_sales",
    "Прибыль (убыток) от продаж (2200)": "profit_from_sales",
    "50": "profit_from_sales",
    "2200": "profit_from_sales",
    "Операционная прибыль": "ifrs_operating_profit",
    "Операционная прибыль (убыток)": "ifrs_operating_profit",
    "Прочие доходы": "other_income",
    "Прочие доходы (2340)": "other_income",
    "Прочие доходы (90)": "other_income",
    "90": "other_income",
    "2340": "other_income",
    "Прочие расходы": "other_expense",
    "Прочие расходы (2350)": "other_expense",
    "Прочие расходы (100)": "other_expense",
    "100": "other_expense",
    "2350": "other_expense",
    "ф.5 (740)": "depreciation_notes",
    "5640": "depreciation_notes",
    "740": "depreciation_notes",
    "Амортизация (5640)": "depreciation_notes",
}
_UNKNOWN = (
    "Амортизация",
    "Курсовые разницы",
    "Резерв по сомнительным долгам",
    "Переоценка",
    "Штрафы",
    "Бонусы",
    "Лизинг",
)


def _row(key: str, label: str) -> dict:
    return {
        "kind": "fact",
        "binding_key": key,
        "row_key": key,
        "label": label,
        "label_path_text": label,
        "sign": None,
        "unit": "money",
    }


def _assign(glossary, label: str):
    return assign_rows([_row("row", label)], [], glossary)["row"]


def _bind(concept: str, row: str, label: str | None = None) -> dict:
    item = {
        "effective_concept": concept,
        "row_key": row,
        "is_primary": True,
        "status": "bound",
        "source": "inferred",
    }
    if label:
        item["label_path_text"] = label
    return item


def _fact(row: str, period: str, value: str) -> dict:
    return {"row_key": row, "axis_id": "a", "period_id": period, "normalized_value": value}


def _year() -> dict:
    return {"axis_id": "a", "period_id": "Y1", "period_index": 1, "grain": "year", "timeline_id": "t"}


def _catalog():
    return load_model_types()


def _common(facts, bindings) -> dict:
    return {
        "facts": facts,
        "bindings": bindings,
        "periods": [_year()],
        "period_phase": {},
        "explicit_phases": False,
        "sign_convention": "outflow_negative",
        "marker_class": None,
        "absent": frozenset(),
    }


def _select(metric: str, variant: str | None, common: dict, profile: dict | None) -> dict:
    catalog = _catalog()
    return select_ratio(
        metric,
        variant,
        common,
        profile=profile,
        profile_ref=None,
        composed=catalog.composed,
        concepts=catalog.concepts,
        money=frozenset(name for name in catalog.concepts),
        interest_order=catalog.interest_order,
        row_fallbacks=catalog.row_fallbacks,
    )


def _blob(result: dict) -> str:
    return str(result)


def test_ras_lines_bind_and_operating_profit_stays_apart():
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
    assert glossary.resolve("Операционная прибыль").concept != "profit_from_sales"
    assert "ebitda_ras" in glossary.ids and "ebitda_ifrs" in glossary.ids
    catalog = _catalog()
    for formula in catalog.composed.values():
        names = {
            *formula.numerator.plus,
            *formula.numerator.minus,
            *formula.denominator.plus,
            *formula.denominator.minus,
        }
        assert names.isdisjoint(_FRESH)


def test_book_icr_keeps_the_ebitda_line_and_ebit_fallback():
    line = _common(
        [_fact("e", "Y1", "20385911"), _fact("i", "Y1", "1")],
        [_bind("ebitda", "e"), _bind("interest", "i")],
    )
    got = _select("icr", None, line, None)
    assert got["rows"][0]["value"] == Decimal("20385911.0000000000")
    ebit = _common(
        [_fact("b", "Y1", "8"), _fact("i", "Y1", "2")],
        [_bind("ebit", "b"), _bind("interest", "i")],
    )
    fallback = coverage_ratio(metric="icr", **ebit)
    assert fallback["rows"][0]["value"] == Decimal("4.0000000000")


def test_ras_and_ifrs_skip_the_three_ratios_without_the_dirty_sum():
    auchan = _common(
        [
            _fact("e", "Y1", "20385911"),
            _fact("b", "Y1", "1"),
            _fact("sales", "Y1", "16985459"),
            _fact("income", "Y1", "9946869"),
            _fact("expense", "Y1", "10041949"),
            _fact("dep", "Y1", "3495532"),
            _fact("i", "Y1", "1"),
            _fact("debt", "Y1", "100"),
            _fact("tax", "Y1", "0"),
            _fact("capex", "Y1", "0"),
            _fact("principal", "Y1", "1"),
        ],
        [
            _bind("ebitda", "e", "EBITDA"),
            _bind("ebit", "b", "EBIT"),
            _bind("profit_from_sales", "sales", "Прибыль (убыток) от реализации (50)"),
            _bind("other_income", "income", "Прочие доходы (90)"),
            _bind("other_expense", "expense", "Прочие расходы (100)"),
            _bind("depreciation_notes", "dep", "ф.5 (740)"),
            _bind("interest", "i"),
            _bind("net_debt", "debt"),
            _bind("cash_taxes", "tax"),
            _bind("capex", "capex"),
            _bind("principal", "principal"),
        ],
    )
    for kind in ("ras", "ifrs"):
        profile = {"ebitda_definition": kind}
        for metric, variant in (("icr", None), ("net_debt_ebitda", None), ("dscr", "corporate_covenant")):
            got = _select(metric, variant, auchan, profile)
            assert got["status"] == "not_computed", (kind, metric)
            assert got["rows"] == [], (kind, metric)
            text = got["message"]
            assert "20385911" not in text
            assert "ebitda" not in text.casefold()
            assert "ebit" not in text.casefold()
            folded = _blob(got)
            assert "20385911" not in folded
            if kind == "ras":
                assert "Прибыль от продаж найдена" in text
                assert "50" in text and "90" in text and "100" in text and "ф.5 (740)" in text
                assert "расшифровки исключений нет" in text
                assert "год, а не период прибыли" in text
            else:
                assert "операционной прибыли" in text
                assert "того же периода" in text


def test_project_finance_dscr_still_uses_cfads_when_the_recipe_is_requested():
    common = _common(
        [_fact("c", "Y1", "10"), _fact("d", "Y1", "5"), _fact("e", "Y1", "20385911")],
        [_bind("cfads", "c"), _bind("debt_service", "d"), _bind("ebitda", "e")],
    )
    got = _select("dscr", "pf", common, {"ebitda_definition": "ras"})
    assert got["rows"][0]["value"] == Decimal("2.0000000000")


def test_profile_stores_only_book_ras_or_ifrs(tmp_path):
    from finance_analysis.adapters.storage.store import LocalStore
    from finance_analysis.application.glossary_store import GlossaryStore
    from finance_analysis.domain.errors import InvalidArgument

    async def run():
        gloss = GlossaryStore(LocalStore(tmp_path))
        saved = await gloss.put_profile(
            "bank",
            {"sign_convention": "outflow_negative", "ebitda_definition": "ras"},
            if_match=None,
            if_none_match="*",
        )
        assert saved["body"]["ebitda_definition"] == "ras"
        cleared = await gloss.put_profile(
            "bank",
            {"ebitda_definition": None},
            if_match=saved["etag"],
            if_none_match=None,
        )
        assert "ebitda_definition" not in cleared["body"]
        with pytest.raises(InvalidArgument):
            await gloss.put_profile(
                "bank",
                {"ebitda_definition": "2200+5640"},
                if_match=cleared["etag"],
                if_none_match=None,
            )

    asyncio.run(run())
