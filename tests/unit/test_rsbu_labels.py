"""Официальные строки форм Минфина режутся той же нормализацией, что и остальные метки.

Короткие английские имена вроде Revenue и Cash на книгах Packt и RVI не заняты:
иначе счётчики привязок сдвинутся.
"""

from __future__ import annotations

import json
from pathlib import Path

from finance_analysis.application.catalog import load_catalog

_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "builder"

_HITS = {
    "Выручка": "revenue",
    "Выручка (нетто) от реализации товаров, продукции, работ, услуг (без НДС)": "revenue",
    "Себестоимость продаж": "cogs",
    "Себестоимость реализации товаров, продукции, работ, услуг": "cogs",
    "Валовая прибыль": "gross_profit",
    "Валовая прибыль (убыток)": "gross_profit",
    "Коммерческие расходы": "selling_expenses",
    "Прибыль (убыток) от реализации": "operating_profit",
    "Прибыль (убыток) от продаж": "operating_profit",
    "Операционная прибыль": "operating_profit",
    "Операционная прибыль (убыток)": "operating_profit",
    "Прибыль (убыток) до налогообложения": "ebt",
    "Налог на прибыль": "income_tax",
    "Чистая прибыль (убыток)": "net_income",
    "Чистая прибыль (убыток) отчетного года": "net_income",
    "Основные средства": "fixed_assets",
    "Нематериальные активы": "intangibles",
    "Запасы": "inventory",
    "Дебиторская задолженность": "receivables",
    "Денежные средства": "cash",
    "Денежные средства и денежные эквиваленты": "cash",
    "Остаток денежных средств на начало периода": "cash_opening",
    "Остаток денежных средств и денежных эквивалентов на начало отчетного периода": "cash_opening",
    "Сальдо денежных потоков за отчетный период": "cash_net",
    "Величина влияния изменения курса иностранной валюты по отношению к рублю": "fx_on_cash",
    "Величина влияния изменений курса иностранной валюты по отношению к рублю": "fx_on_cash",
    "Остаток денежных средств на конец периода": "cash_balance",
    "Остаток денежных средств и денежных эквивалентов на конец отчетного периода": "cash_balance",
    "Займы и кредиты": "debt_outstanding",
    "Заемные средства": "debt_outstanding",
    "Заёмные средства": "debt_outstanding",
    "Уставный капитал": "share_capital",
    "Уставный капитал (складочный капитал, уставный фонд, вклады товарищей)": "share_capital",
    "Нераспределенная прибыль (непокрытый убыток)": "retained_earnings",
    "ИТОГО АКТИВЫ": "total_assets",
    "Баланс": "total_assets",
    "БАЛАНС": "total_assets",
    "Отложенные налоговые активы": "deferred_tax_asset",
    "Отложенные налоговые обязательства": "deferred_tax_liability",
    "Проценты к уплате": "interest",
}

# Эти подписи уже есть в Packt или RVI. Новые метки их не забирают.
_UNTOUCHED = (
    "Revenues",
    "Revenue",
    "Net income",
    "Retained earnings",
    "Retained Earnings",
    "Cash",
    "Total Assets",
    "Share capital",
    "Income Tax",
    "EBIT",
    "Interest",
)


def test_official_form_lines_resolve_by_the_same_label_keys():
    package = load_catalog()
    for text, concept in _HITS.items():
        found = package.resolve(text)
        assert found is not None and found.concept == concept, text
    for text in _UNTOUCHED:
        found = package.resolve(text)
        assert found is None or found.concept in {"ebit", "interest"}, text


def test_packt_and_rvi_rows_do_not_pick_up_the_form_lines():
    package = load_catalog()
    fresh = {
        "revenue",
        "cogs",
        "gross_profit",
        "selling_expenses",
        "operating_profit",
        "ebt",
        "income_tax",
        "net_income",
        "fixed_assets",
        "intangibles",
        "inventory",
        "receivables",
        "cash",
        "cash_balance",
        "share_capital",
        "retained_earnings",
        "total_assets",
        "deferred_tax_asset",
        "deferred_tax_liability",
    }
    hits: list[tuple[str, str]] = []
    for path in _ROOT.glob("*/context.json"):

        def walk(node):
            if isinstance(node, dict):
                label = node.get("label")
                if isinstance(label, str):
                    found = package.resolve(label)
                    if found is not None and found.concept in fresh:
                        hits.append((label, found.concept))
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(json.loads(path.read_text(encoding="utf-8")))
    assert hits == []
