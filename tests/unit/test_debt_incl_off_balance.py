"""Долг с учетом забалансовых обязательств: метки слагаемых не занимают остаток долга."""

from __future__ import annotations

from finance_analysis.application.catalog import load_catalog


def test_component_labels_resolve_and_old_debt_labels_stay():
    package = load_catalog()
    assert package.resolve("Долгосрочные заемные средства").concept == "long_term_borrowings"
    assert package.resolve("Строка 1410").concept == "long_term_borrowings"
    assert package.resolve("Краткосрочные заемные средства").concept == "short_term_borrowings"
    assert package.resolve("Строка 1510").concept == "short_term_borrowings"
    assert package.resolve("Прочая финансовая задолженность").concept == "other_financial_debt"
    assert package.resolve("Забалансовые обязательства по обязательствам третьих лиц").concept == "off_balance_third_party"
    assert package.resolve("Забалансовые обязательства по договорам финансового лизинга").concept == "off_balance_lease"
    assert package.resolve("Займы и кредиты").concept == "debt_outstanding"
    assert package.resolve("Заемные средства").concept == "debt_outstanding"
    assert package.resolve("Заёмные средства").concept == "debt_outstanding"
    for concept_id in (
        "long_term_borrowings",
        "short_term_borrowings",
        "other_financial_debt",
        "off_balance_third_party",
        "off_balance_lease",
    ):
        concept = package.concepts[concept_id]
        assert concept.semantic_role == "measure"
        assert concept.dimension == "money"
        assert concept.temporal_nature == "stock"
