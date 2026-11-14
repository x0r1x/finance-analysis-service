"""Новые метки не привязывают строки Packt и RVI. Halyard отдаёт только точные совпадения."""

from __future__ import annotations

import json
from pathlib import Path

from finance_analysis.application.catalog import load_catalog
from tests.workbook_labels import resolved_workbook

_NEW = frozenset(
    {
        "sources_and_uses",
        "exit_enterprise_value",
        "moic",
        "lbo_leverage",
        "wacc",
        "terminal_value",
        "enterprise_value",
        "equity_value",
        "noi",
        "cap_rate",
        "vacancy",
        "installed_capacity",
        "energy_generation",
        "capacity_factor",
        "degradation",
        "energy_tariff",
        "purchase_price_allocation",
        "lease_interest_income",
        "npl_share",
        "provision_coverage",
    }
)
_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "builder"


def test_packt_and_rvi_labels_do_not_resolve_to_new_concepts():
    package = load_catalog()
    hits: list[tuple[str, str]] = []
    for path in _ROOT.glob("*/context.json"):

        def walk(node):
            if isinstance(node, dict):
                label = node.get("label")
                if isinstance(label, str):
                    found = package.resolve(label)
                    if found is not None and found.concept in _NEW:
                        hits.append((label, found.concept))
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(json.loads(path.read_text(encoding="utf-8")))
    assert hits == []


# Подписи Halyard, которые остаются свободными: словаря синонимов для них нет.
_HALYARD_FREE = (
    "IRR",
    "Net debt / EBITDA",
    "Total sources",
    "Total uses",
    "Revenue",
    "Net income",
    "Purchase enterprise value",
    "Sponsor equity at exit",
    "Cash interest",
    "Goodwill",
)


def test_halyard_resolves_only_its_exact_labels():
    """Книга отдаёт девять понятий. Соседние подписи LBO, включая IRR, не привязываются."""

    bound, _sheets = resolved_workbook(
        "halyard/project_halyard.recalc_libreoffice.xlsx"
    )
    assert bound == frozenset(
        {
            "sources_and_uses",
            "exit_enterprise_value",
            "moic",
            "ebitda",
            "ebit",
            "capex",
            "net_debt",
            "tax_rate",
            "total_debt",
        }
    )
    package = load_catalog()
    for label in _HALYARD_FREE:
        assert package.resolve(label) is None, label
    # Предпочтительная метка входного плеча в книге не встречается и ряд чистого долга её не занимает.
    assert package.resolve("Entry debt to EBITDA multiple").concept == "lbo_leverage"
    assert "lbo_leverage" not in bound
    assert package.resolve("Net debt / EBITDA") is None
