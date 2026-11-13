"""Срез C1: пометка профиля и отказ публиковать сырую сумму РСБУ или МСФО."""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from finance_analysis.application.catalog import load_catalog
from finance_analysis.application.model_types import load_model_types
from finance_analysis.domain.covenant import select_ratio
from finance_analysis.domain.mapping import assign_rows
from finance_analysis.domain.metrics import (
    coverage_ratio,
    ebitda_definition,
    ebitda_definition_error,
    recipe_block,
)

_RAS_SKIP = (
    "Коэффициент не посчитан: выбрана EBITDA (РСБУ), а она ещё не собрана. "
    "Нужны прибыль от продаж и амортизация за тот же период. "
    "Прочие доходы и расходы входят только после удаления курсовых разниц, резервов, "
    "продажи и переоценки имущества, штрафов и других статей не обычной работы. "
    "Строка EBITDA из модели сюда не подставляется."
)
_IFRS_SKIP = (
    "Коэффициент не посчитан: выбрана EBITDA (МСФО), а она ещё не собрана. "
    "Нужны операционная прибыль и амортизация за тот же период. "
    "Продажу активов, переоценку, курсовые разницы и участие в других организациях убирают "
    "только если они внутри этой операционной прибыли и человек их отметил. "
    "Строка EBITDA из модели сюда не подставляется."
)
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


def _bind(concept: str, row: str, label: str | None = None, line_code: str | None = None) -> dict:
    item = {
        "effective_concept": concept,
        "row_key": row,
        "is_primary": True,
        "status": "bound",
        "source": "inferred",
    }
    if label:
        item["label"] = label
        item["label_path_text"] = label
    if line_code:
        item["evidence_json"] = '{"line_code": "' + line_code + '"}'
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
    assert glossary.resolve("EBITDA (РСБУ)").concept == "ebitda_ras"
    assert glossary.resolve("EBITDA (МСФО)").concept == "ebitda_ifrs"
    assert glossary.display_label("ebitda_ras", "ru") == "EBITDA (РСБУ)"
    assert glossary.display_label("ebitda_ifrs", "ru") == "EBITDA (МСФО)"
    assert "не EBITDA (РСБУ)" in glossary.concepts["ebitda"].definition["ru"]
    assert "ещё не собрана" not in glossary.concepts["ebitda"].definition["ru"]
    assert "Пока показатель не считается" in glossary.concepts["ebitda_ras"].definition["ru"]
    assert "Пока показатель не считается" in glossary.concepts["ebitda_ifrs"].definition["ru"]
    assert "finance-lease" in glossary.concepts["ebitda_ras"].definition["en"]
    assert "does not define EBITDA" in glossary.concepts["ebitda_ifrs"].definition["en"]
    notes = _assign(glossary, "Амортизация на конец года (заполняется только 4 кв.)")
    assert notes.status == "bound" and notes.concept == "depreciation_notes"
    bare = _row("bare", "Амортизация на конец года (заполняется только 4 кв.)")
    bare["line_code"] = "ф.5 (740)"
    coded = assign_rows([bare], [], glossary)["bare"]
    assert coded.concept == "depreciation_notes"
    assert coded.evidence.get("line_code") == "ф.5 (740)"
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
            _bind("profit_from_sales", "sales", "Прибыль (убыток) от реализации", "50"),
            _bind("other_income", "income", "Прочие доходы", "90"),
            _bind("other_expense", "expense", "Прочие расходы", "100"),
            _bind("depreciation_notes", "dep", "Амортизация на конец года (заполняется только 4 кв.)", "ф.5 (740)"),
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
            folded = _blob(got)
            assert "20385911" not in folded
            expected = _RAS_SKIP if kind == "ras" else _IFRS_SKIP
            assert text == expected
            assert expected in [item.get("params", {}).get("message") for item in got["warnings"]]


def test_project_finance_dscr_still_uses_cfads_when_the_recipe_is_requested():
    common = _common(
        [_fact("c", "Y1", "10"), _fact("d", "Y1", "5"), _fact("e", "Y1", "20385911")],
        [_bind("cfads", "c"), _bind("debt_service", "d"), _bind("ebitda", "e")],
    )
    got = _select("dscr", "pf", common, {"ebitda_definition": "ras"})
    assert got["rows"][0]["value"] == Decimal("2.0000000000")


@pytest.mark.parametrize("value", [{"recipe": "ras"}, ["ras"], 1, True])
def test_ebitda_definition_rejects_a_non_string(value):
    assert ebitda_definition_error(value) == "ebitda_definition: book, ras или ifrs"
    profile = {"ebitda_definition": value}
    assert ebitda_definition(profile) == "invalid"
    blocked = recipe_block(profile, [], metric="icr")
    assert blocked["status"] == "not_computed"


def test_stored_profile_reads_a_non_string_ebitda_definition_as_invalid(tmp_path):
    import json

    from finance_analysis.adapters.storage.store import LocalStore
    from finance_analysis.application.glossary_store import GlossaryStore
    from finance_analysis.domain.errors import InvalidArgument

    async def run():
        store = LocalStore(tmp_path)
        gloss = GlossaryStore(store)
        for value in ({"recipe": "ras"}, ["ras"], 1, True):
            with pytest.raises(InvalidArgument):
                await gloss.put_profile(
                    "bank",
                    {"sign_convention": "outflow_negative", "ebitda_definition": value},
                    if_match=None,
                    if_none_match="*",
                )
            saved = {
                "id": "bank",
                "seq": 1,
                "etag": "p-1",
                "body": {
                    "sign_convention": "outflow_negative",
                    "marker_class": None,
                    "ebitda_definition": value,
                },
            }
            await store.put("profiles/bank/_head.json", json.dumps(saved).encode())
            loaded = await gloss.profile_body("bank")
            assert ebitda_definition(loaded) == "invalid"

    asyncio.run(run())


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


def test_code_column_beside_the_label_reaches_the_binding():
    """Явная форма «Ф. 5 (740)» в соседней ячейке — код. Голое 50 с ролью value — нет.

    Билдер помечает числовую ячейку ролью value. Роли code у него нет.
    """

    from finance_analysis.adapters.builder.acl import parse_context
    from finance_analysis.application.project import derive_rows, project
    from finance_analysis.domain.book import WorkbookSnapshot

    snapshot = parse_context(
        {
            "axes": [
                {
                    "id": "ax",
                    "sheet": "Фин отчетность РСБУ",
                    "kind": "time",
                    "periods": [{"col": 6, "period_key": "Y1", "index": 1, "text": "2024"}],
                }
            ],
            "blocks": [
                {
                    "block_id": "Фин отчетность РСБУ!r1",
                    "sheet": "Фин отчетность РСБУ",
                    "kind": "timeline",
                    "label_col": 3,
                    "rows": [
                        _sheet_row(30, "Прибыль (убыток) от реализации", 50),
                        _sheet_row(43, "Амортизация на конец года (заполняется только 4 кв.)", "Ф. 5 (740)"),
                    ],
                }
            ],
        }
    )
    assert isinstance(snapshot, WorkbookSnapshot)
    projected, _warnings = project(snapshot, model_id="m", build="b")
    by_num = {row["row_num"]: row for row in projected["dim_row"]}
    assert by_num[30]["line_code"] is None
    assert by_num[43]["line_code"] == "ф.5 (740)"
    assert "50" not in by_num[30]["label"]
    assert "ф.5" not in by_num[43]["label_path_text"]
    derived = derive_rows(projected, state_seq=1, derive="d", versions={"glossary": "g"}, glossary=load_catalog())
    rows = {row["row_key"]: row for row in derived["bindings"]}
    sales = rows["Фин отчетность РСБУ|30|Фин отчетность РСБУ!r1"]
    notes = rows["Фин отчетность РСБУ|43|Фин отчетность РСБУ!r1"]
    assert sales["concept"] == "profit_from_sales"
    assert notes["concept"] == "depreciation_notes"
    assert "line_code" not in sales["evidence_json"]
    assert "ф.5 (740)" in notes["evidence_json"]
    assert "ф.5" not in notes["label_path_text"]


@pytest.mark.parametrize("value", [50, 90, 100])
def test_numeric_neighbour_does_not_bind_profit_from_sales(value: int):
    """Неизвестная подпись и соседнее число с ролью value не становятся кодом строки."""

    from finance_analysis.adapters.builder.acl import parse_context
    from finance_analysis.application.project import derive_rows, project

    snapshot = parse_context(
        {
            "axes": [
                {
                    "id": "ax",
                    "sheet": "Фин отчетность РСБУ",
                    "kind": "time",
                    "periods": [{"col": 6, "period_key": "Y1", "index": 1, "text": "2024"}],
                }
            ],
            "blocks": [
                {
                    "block_id": "Фин отчетность РСБУ!r1",
                    "sheet": "Фин отчетность РСБУ",
                    "kind": "timeline",
                    "label_col": 3,
                    "rows": [_sheet_row(12, "Прочая строка без кода", value)],
                }
            ],
        }
    )
    projected, _warnings = project(snapshot, model_id="m", build="b")
    assert projected["dim_row"][0]["line_code"] is None
    derived = derive_rows(projected, state_seq=1, derive="d", versions={"glossary": "g"}, glossary=load_catalog())
    binding = derived["bindings"][0]
    assert binding["concept"] != "profit_from_sales"
    assert binding["status"] == "unknown"
    assert binding["concept"] is None


@pytest.mark.parametrize("code", ["50", "90", "100"])
def test_bare_line_code_is_not_a_semantic_match(code: str):
    """Даже если код уже лежит на строке, голое число понятие не выбирает."""

    row = _row("row", "Прочая строка без кода")
    row["line_code"] = code
    item = assign_rows([row], [], load_catalog())["row"]
    assert item.concept != "profit_from_sales"
    assert item.status == "unknown"
    assert item.concept is None
    assert "line_code" not in item.evidence


def _sheet_row(number: int, label: str, code: object) -> dict:
    return {
        "row_key": f"Фин отчетность РСБУ|{number}|Фин отчетность РСБУ!r1",
        "sheet": "Фин отчетность РСБУ",
        "row": number,
        "label": label,
        "kind": "fact",
        "unit": "money",
        "cells": [{"col": 4, "cached_value": code, "role": "value"}],
    }
