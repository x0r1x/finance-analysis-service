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


DSCR_COVENANT_DEFINITION = (
    "Ковенантный DSCR по умолчанию, не текст договора: "
    "(EBITDA - денежные налоги - capex) / (проценты + основной долг), окно LTM. "
    "На годовой зернистости окно совпадает с одним периодом. "
    "Профиль может подменить состав."
)


def test_dscr_corporate_covenant_catalog_matches_python_and_golden():
    variant = load_financial_catalog().indicators["dscr"].variants["corporate_covenant"]
    terms = {
        "ebitda": "money",
        "cash_taxes": "money",
        "capex": "money",
        "interest": "money",
        "principal": "money",
    }
    assert_slice(
        variant,
        definition=DSCR_COVENANT_DEFINITION,
        all_of=frozenset(terms),
        one_of=frozenset(),
        formula={
            "numerator": {"plus": ["ebitda"], "minus": ["cash_taxes", "capex"]},
            "denominator": {"plus": ["interest", "principal"], "minus": []},
        },
        unit="ratio",
        window="LTM",
        dimensions=terms,
    )
    values = {
        "ebitda": "100",
        "cash_taxes": "10",
        "capex": "20",
        "interest": "15",
        "principal": "5",
    }
    assert set(values) == variant.inputs.concepts
    got = _run("dscr", "corporate_covenant", values)
    assert got["status"] == "succeeded"
    assert got["definition_source"] == "default"
    # (100 - 10 - 20) / (15 + 5) = 3.5 на годе: LTM схлопывается в один период.
    assert got["rows"][0]["value"] == Decimal("3.5000000000")
    assert got["rows"][0]["window"] == ["Y1"]
    assert set(got["rows"][0]["inputs"]) == variant.inputs.concepts


ICR_DEFINITION = (
    "ICR: EBITDA или EBIT, делённые на проценты. "
    "Если в книге один числитель, частное считается по нему. "
    "Если оба, Python берёт EBITDA и ставит предупреждение icr_numerator."
)

ICR_USE = {
    "bank_leasing": ("not_applicable", None),
    "corporate": ("required", None),
    "dcf_valuation": ("not_applicable", None),
    "development_escrow": ("not_applicable", None),
    "investment_project": ("not_applicable", None),
    "lbo_ma": ("not_applicable", None),
    "other": ("optional", None),
    "ppp_concession": ("optional", None),
    "project_finance": ("optional", None),
    "real_estate_income": ("not_applicable", None),
    "renewables_dpm": ("not_applicable", None),
}

ICR_FORMULA = {
    "denominator": {"plus": ["interest"], "minus": []},
    "one_of": ["ebit", "ebitda"],
}


def assert_book(record, values: dict[str, str], components: dict) -> None:
    """all_of входят все. Из one_of в книге ровно то, что оказалось в components.

    Оба члена one_of в книге сюда не подходят: лишний числитель не входит в components.
    """

    present = set(values)
    used_one = set(components) & record.inputs.one_of
    assert record.inputs.all_of <= present
    assert present & record.inputs.one_of == used_one
    assert set(components) == record.inputs.all_of | used_one


def test_icr_catalog_matches_python_and_golden():
    icr = load_financial_catalog().indicators["icr"]
    assert icr.base is None
    assert icr.status == "active"
    assert icr.variants == {}
    terms = {"ebitda": "money", "ebit": "money", "interest": "money"}
    assert_slice(
        icr,
        definition=ICR_DEFINITION,
        all_of=frozenset({"interest"}),
        one_of=frozenset({"ebitda", "ebit"}),
        formula=ICR_FORMULA,
        unit="ratio",
        window=None,
        dimensions=terms,
    )
    assert set(icr.model_types) == set(ICR_USE)
    for type_id, (use, variant) in ICR_USE.items():
        got = icr.model_types[type_id]
        assert (got.use, got.variant) == (use, variant)

    ebitda_only = {"ebitda": "80", "interest": "20"}
    # one_of не требует обоих числителей: set(values) == inputs.concepts здесь ложно.
    assert set(ebitda_only) != icr.inputs.concepts
    got = _run("icr", None, ebitda_only)
    assert got["status"] == "succeeded"
    assert got["warnings"] == []
    # 80 / 20. В components есть ebitda и interest, ebit нет.
    assert got["rows"][0]["value"] == Decimal("4.0000000000")
    assert_book(icr, ebitda_only, got["rows"][0]["components"])
    assert "ebit" not in got["rows"][0]["components"]

    ebit_only = {"ebit": "30", "interest": "10"}
    got = _run("icr", None, ebit_only)
    assert got["status"] == "succeeded"
    assert got["warnings"] == []
    # 30 / 10, числитель — ebit.
    assert got["rows"][0]["value"] == Decimal("3.0000000000")
    assert_book(icr, ebit_only, got["rows"][0]["components"])
    assert set(got["rows"][0]["components"]) == {"ebit", "interest"}

    both = {"ebitda": "80", "ebit": "10", "interest": "20"}
    assert set(both) == icr.inputs.concepts
    got = _run("icr", None, both)
    assert got["status"] == "succeeded"
    # Оба числителя: код берёт ebitda (80/20), не ebit (10/20).
    assert got["rows"][0]["value"] == Decimal("4.0000000000")
    assert set(got["rows"][0]["components"]) == {"ebitda", "interest"}
    assert got["warnings"] == [{"code": "icr_numerator", "params": {"concept": "ebitda"}}]
