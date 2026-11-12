"""Контракт каталога и золотой результат Python.

Каталог не исполняется. Число считает select_ratio.
"""

from decimal import Decimal

from finance_analysis.application.catalog import load_catalog
from finance_analysis.application.financial_catalog import load_financial_catalog
from finance_analysis.application.model_types import load_model_types
from finance_analysis.domain.covenant import select_ratio

AXIS = "Sheet!r1"

DSCR_BASE_DEFINITION = (
    "CFADS / обслуживание долга. "
    "Вариант pf считает это за период. "
    "Вариант corporate_covenant считает другой состав и окно LTM."
)
DSCR_PF_DEFINITION = (
    "Проектное финансирование: CFADS / обслуживание долга за один период. "
    "Знак оттока и неполное окно считает Python. "
    "Уплаченные проценты вместо debt_service — запасной путь кода, не вход этой формулы."
)

DSCR_USE = {
    "bank_leasing": ("not_applicable", None),
    "corporate": ("optional", "corporate_covenant"),
    "dcf_valuation": ("not_applicable", None),
    "development_escrow": ("optional", "pf"),
    "investment_project": ("not_applicable", None),
    "lbo_ma": ("not_applicable", None),
    "other": ("optional", None),
    "ppp_concession": ("required", "pf"),
    "project_finance": ("required", "pf"),
    "real_estate_income": ("optional", "pf"),
    "renewables_dpm": ("optional", "pf"),
}

PF_FORMULA = {
    "numerator": {"plus": ["cfads"], "minus": []},
    "denominator": {"plus": ["debt_service"], "minus": []},
}


def _bind(concept: str) -> dict:
    return {
        "effective_concept": concept,
        "row_key": concept,
        "is_primary": True,
        "status": "bound",
        "source": "inferred",
    }


def _fact(concept: str, value: str) -> dict:
    return {
        "row_key": concept,
        "axis_id": AXIS,
        "period_id": "Y1",
        "normalized_value": value,
    }


def _period() -> dict:
    return {
        "axis_id": AXIS,
        "period_id": "Y1",
        "period_index": 1,
        "period_key_base": "Y1",
        "grain": "year",
        "timeline_id": "t",
    }


def _money(package) -> frozenset[str]:
    return frozenset(name for name, item in package.concepts.items() if item.unit == "money")


def assert_slice(
    record,
    *,
    definition: str,
    all_of: frozenset[str],
    one_of: frozenset[str],
    formula: dict,
    unit: str,
    window: str | None,
    dimensions: dict[str, str],
) -> None:
    assert record.definition == definition
    assert record.inputs.all_of == all_of
    assert record.inputs.one_of == one_of
    assert record.inputs.concepts == all_of | one_of
    assert record.formula.as_dict() == formula
    assert record.unit == unit
    assert record.window == window
    package = load_catalog()
    for name, dimension in dimensions.items():
        assert package.concepts[name].dimension == dimension


def _run(metric: str, variant: str | None, values: dict[str, str]) -> dict:
    package = load_catalog()
    types = load_model_types()
    common = {
        "facts": [_fact(name, value) for name, value in values.items()],
        "bindings": [_bind(name) for name in values],
        "periods": [_period()],
        "period_phase": {},
        "explicit_phases": False,
        "sign_convention": "outflow_negative",
        "marker_class": None,
        "absent": frozenset(),
    }
    return select_ratio(
        metric,
        variant,
        common,
        profile=None,
        profile_ref=None,
        composed=types.composed,
        concepts=package.ids,
        money=_money(package),
        interest_order=types.interest_order,
        row_fallbacks=types.row_fallbacks,
    )


def test_dscr_pf_catalog_matches_python_and_golden():
    catalog = load_financial_catalog()
    dscr = catalog.indicators["dscr"]
    pf = dscr.variants["pf"]
    assert dscr.base is None
    assert dscr.status == "active"
    money = {"cfads": "money", "debt_service": "money"}
    assert_slice(
        dscr,
        definition=DSCR_BASE_DEFINITION,
        all_of=frozenset({"cfads", "debt_service"}),
        one_of=frozenset(),
        formula=PF_FORMULA,
        unit="ratio",
        window=None,
        dimensions=money,
    )
    assert_slice(
        pf,
        definition=DSCR_PF_DEFINITION,
        all_of=frozenset({"cfads", "debt_service"}),
        one_of=frozenset(),
        formula=PF_FORMULA,
        unit="ratio",
        window="period",
        dimensions=money,
    )
    assert set(dscr.model_types) == set(DSCR_USE)
    for type_id, (use, variant) in DSCR_USE.items():
        got = dscr.model_types[type_id]
        assert (got.use, got.variant) == (use, variant)
    values = {"cfads": "100", "debt_service": "40"}
    assert set(values) == pf.inputs.concepts
    got = _run("dscr", "pf", values)
    assert got["status"] == "succeeded"
    # 100 / 40, quantize_ratio до 1e-10. Знак плюса не переворачивается.
    assert got["rows"][0]["value"] == Decimal("2.5000000000")
    assert set(got["rows"][0]["components"]) == pf.inputs.concepts
