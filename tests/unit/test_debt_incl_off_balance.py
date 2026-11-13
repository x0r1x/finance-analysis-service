"""Долг с учетом забалансовых обязательств: метки слагаемых не занимают остаток долга."""

from __future__ import annotations

from decimal import Decimal

from finance_analysis.application.analyses import RATIO_METRICS
from finance_analysis.application.catalog import load_catalog
from finance_analysis.application.financial_catalog import load_financial_catalog
from finance_analysis.application.model_types import load_model_types
from finance_analysis.domain.covenant import select_ratio
from finance_analysis.domain.debt_incl_off_balance import debt_incl_off_balance
from finance_analysis.domain.model_type import applicability


def test_component_labels_resolve_and_old_debt_labels_stay():
    package = load_catalog()
    assert package.resolve("Строка 1410").concept == "long_term_borrowings"
    assert package.resolve("Строка 1510").concept == "short_term_borrowings"
    assert package.resolve("Прочая финансовая задолженность").concept == "other_financial_debt"
    assert package.resolve("Забалансовые обязательства по обязательствам третьих лиц").concept == "off_balance_third_party"
    assert package.resolve("Забалансовые обязательства по договорам финансового лизинга").concept == "off_balance_lease"
    # «Долгосрочные/Краткосрочные заемные средства» уже у borrowings_lt/st. «Займы и кредиты» эта метрика не забирает.
    assert package.resolve("Долгосрочные заемные средства").concept == "borrowings_lt"
    assert package.resolve("Краткосрочные заемные средства").concept == "borrowings_st"
    assert package.resolve("Займы и кредиты") is None
    assert package.resolve("Заемные средства") is None
    assert package.resolve("Заёмные средства") is None
    assert package.resolve("Остаток долга").concept == "debt_outstanding"
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


_COMPONENTS = (
    "long_term_borrowings",
    "short_term_borrowings",
    "other_financial_debt",
    "off_balance_third_party",
    "off_balance_lease",
)


def _bind(concept: str, row: str, *, primary: bool = True) -> dict:
    return {
        "effective_concept": concept,
        "row_key": row,
        "is_primary": primary,
        "status": "bound",
        "source": "inferred",
    }


def _fact(row: str, period: str, value: str) -> dict:
    return {
        "row_key": row,
        "axis_id": "a",
        "period_id": period,
        "normalized_value": value,
    }


def _year(period: str = "Y1") -> dict:
    return {"axis_id": "a", "period_id": period, "period_index": 1, "grain": "year", "timeline_id": "t"}


def test_sum_adds_bound_rows_and_zeros_a_missing_component():
    got = debt_incl_off_balance(
        components=_COMPONENTS,
        facts=[
            _fact("lt", "Y1", "100"),
            _fact("st", "Y1", "40"),
            _fact("lease_note", "Y1", "10"),
            _fact("derivative", "Y1", "5"),
            _fact("off_lease", "Y1", "7"),
        ],
        bindings=[
            _bind("long_term_borrowings", "lt"),
            _bind("short_term_borrowings", "st"),
            _bind("other_financial_debt", "lease_note"),
            _bind("other_financial_debt", "derivative", primary=False),
            _bind("off_balance_lease", "off_lease"),
        ],
        periods=[_year()],
    )
    assert got["status"] == "succeeded"
    assert got["rows"][0]["value"] == "162"
    assert Decimal(got["rows"][0]["components"]["other_financial_debt"]) == Decimal(15)
    assert got["warnings"] == [
        {"code": "component_absent", "params": {"concepts": ["off_balance_third_party"]}}
    ]


def test_no_bound_component_is_missing_input():
    got = debt_incl_off_balance(
        components=_COMPONENTS,
        facts=[_fact("lt", "Y1", "100")],
        bindings=[],
        periods=[_year()],
    )
    assert got["status"] == "missing_input"
    assert got["rows"] == []
    assert got["needs_input"] == [
        {"kind": "concept", "reason": "concept_unknown", "subject": "debt_incl_off_balance"}
    ]


def test_negative_stock_is_not_flipped():
    got = debt_incl_off_balance(
        components=_COMPONENTS,
        facts=[_fact("lt", "Y1", "-20"), _fact("st", "Y1", "5")],
        bindings=[
            _bind("long_term_borrowings", "lt"),
            _bind("short_term_borrowings", "st"),
        ],
        periods=[_year()],
    )
    assert got["rows"][0]["value"] == "-15"


def test_metric_is_a_money_sum_optional_only_for_corporate():
    catalog = load_model_types()
    financial = load_financial_catalog()
    indicator = financial.get("debt_incl_off_balance")
    assert indicator is not None
    assert indicator.unit == "money"
    assert indicator.formula.numerator.plus == _COMPONENTS
    assert indicator.formula.denominator is None
    assert "debt_incl_off_balance" in RATIO_METRICS
    assert applicability(catalog, ("corporate",), "debt_incl_off_balance") == "optional"
    for type_id in catalog.types:
        if type_id == "corporate":
            continue
        assert applicability(catalog, (type_id,), "debt_incl_off_balance") == "not_applicable"
    got = select_ratio(
        "debt_incl_off_balance",
        None,
        {
            "facts": [_fact("lt", "Y1", "30"), _fact("st", "Y1", "2")],
            "bindings": [
                _bind("long_term_borrowings", "lt"),
                _bind("short_term_borrowings", "st"),
            ],
            "periods": [_year()],
            "absent": frozenset(),
            "sign_convention": "outflow_negative",
            "marker_class": None,
        },
        profile=None,
        profile_ref=None,
        composed=catalog.composed,
        concepts=frozenset(catalog.concepts),
        money=frozenset(),
    )
    assert got["status"] == "succeeded"
    assert got["rows"][0]["value"] == "32"
