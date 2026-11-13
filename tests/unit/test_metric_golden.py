"""Контракт каталога и золотой результат Python.

Каталог не исполняется. Число считает тот же Python, что и расчёт коэффициентов.
"""

from datetime import date, timedelta
from decimal import Decimal

from finance_analysis.application.catalog import load_catalog
from finance_analysis.application.financial_catalog import load_financial_catalog
from finance_analysis.application.model_types import load_model_types
from finance_analysis.domain.covenant import select_ratio
from finance_analysis.domain.cover_metrics import (
    LOAN_LIFE,
    REDUCED,
    add_months,
    adscr,
    dscr_reductions,
    loan_life_ratio,
)
from tests.unit.test_cover_metrics import LLCR_2025, PLCR_2025

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
    "development_escrow": ("required", "housing"),
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


def _fact(concept: str, value: str, *, period_id: str = "Y1", axis: str = AXIS) -> dict:
    return {
        "row_key": concept,
        "axis_id": axis,
        "period_id": period_id,
        "normalized_value": value,
    }


def _period(
    *,
    period_id: str = "Y1",
    index: int = 1,
    grain: str = "year",
    start: date | None = None,
    end: date | None = None,
    axis: str = AXIS,
) -> dict:
    item = {
        "axis_id": axis,
        "period_id": period_id,
        "period_index": index,
        "period_key_base": period_id,
        "grain": grain,
        "timeline_id": "t",
    }
    if start is not None:
        item["period_start"] = start
        item["period_end"] = end
    return item


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


def _run(
    metric: str,
    variant: str | None,
    values: dict[str, str],
    *,
    periods: list[dict] | None = None,
    series: dict[str, list[str]] | None = None,
) -> dict:
    package = load_catalog()
    types = load_model_types()
    period_rows = periods if periods is not None else [_period()]
    if series is None:
        facts = [_fact(name, value) for name, value in values.items()]
        bound = list(values)
    else:
        facts = []
        for name, column in series.items():
            if len(column) != len(period_rows):
                raise AssertionError(name)
            for period, value in zip(period_rows, column, strict=True):
                facts.append(_fact(name, value, period_id=period["period_id"], axis=period["axis_id"]))
        bound = list(series)
    common = {
        "facts": facts,
        "bindings": [_bind(name) for name in bound],
        "periods": period_rows,
        "period_phase": {},
        "explicit_phases": False,
        "sign_convention": "outflow_negative",
        "marker_class": None,
        "absent": frozenset(),
    }
    if metric in LOAN_LIFE:
        return loan_life_ratio(metric, basis="period_end", **common)
    if metric in REDUCED:
        return dscr_reductions(metric, **common)
    if metric == "adscr":
        return adscr(direction="lookback", **common)
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
    assert set(icr.variants) == {"bank"}
    bank = icr.variants["bank"]
    assert bank.window == "LTM"
    assert bank.formula.as_dict()["numerator"]["plus"] == ["ebitda"]
    assert bank.formula.as_dict()["denominator"]["plus"] == ["interest"]
    assert "ebit" not in bank.inputs.concepts
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


NET_DEBT_EBITDA_DEFINITION = (
    "Чистый долг на конец периода / EBITDA как поток, окно LTM. "
    "На годовой зернистости окно совпадает с одним периодом."
)


def test_net_debt_ebitda_catalog_matches_python_and_golden():
    record = load_financial_catalog().indicators["net_debt_ebitda"]
    assert record.base is None
    assert record.status == "active"
    assert record.variants == {}
    terms = {"net_debt": "money", "ebitda": "money"}
    assert_slice(
        record,
        definition=NET_DEBT_EBITDA_DEFINITION,
        all_of=frozenset(terms),
        one_of=frozenset(),
        formula={
            "numerator": {"plus": ["net_debt"], "minus": []},
            "denominator": {"plus": ["ebitda"], "minus": []},
        },
        unit="ratio",
        window="LTM",
        dimensions=terms,
    )
    assert record.model_types["corporate"].use == "optional"
    assert record.model_types["corporate"].variant is None
    values = {"net_debt": "300", "ebitda": "100"}
    assert set(values) == record.inputs.concepts
    got = _run("net_debt_ebitda", None, values)
    assert got["status"] == "succeeded"
    # 300 / 100 на годе: LTM схлопывается в один период.
    assert got["rows"][0]["value"] == Decimal("3.0000000000")
    assert got["rows"][0]["window"] == ["Y1"]
    assert set(got["rows"][0]["inputs"]) == record.inputs.concepts


ESCROW_COVERAGE_DEFINITION = (
    "Покрытие счетов эскроу: остаток эскроу / остаток долга за период. Это покрытие, не ставка."
)


def test_escrow_coverage_catalog_matches_python_and_golden():
    record = load_financial_catalog().indicators["escrow_coverage"]
    assert record.base is None
    assert record.status == "active"
    terms = {"escrow_balance": "money", "debt_outstanding": "money"}
    assert_slice(
        record,
        definition=ESCROW_COVERAGE_DEFINITION,
        all_of=frozenset(terms),
        one_of=frozenset(),
        formula={
            "numerator": {"plus": ["escrow_balance"], "minus": []},
            "denominator": {"plus": ["debt_outstanding"], "minus": []},
        },
        unit="ratio",
        window="period",
        dimensions=terms,
    )
    assert record.model_types["development_escrow"].use == "required"
    assert record.model_types["development_escrow"].variant is None
    values = {"escrow_balance": "50", "debt_outstanding": "200"}
    # Строка книги escrow_coverage в золото не входит: иначе предупреждение стало бы контрактом.
    assert "escrow_coverage" not in values
    assert set(values) == record.inputs.concepts
    got = _run("escrow_coverage", None, values)
    assert got["status"] == "succeeded"
    assert got["warnings"] == []
    # 50 / 200.
    assert got["rows"][0]["value"] == Decimal("0.2500000000")
    assert set(got["rows"][0]["inputs"]) == record.inputs.concepts


ADSCR_DEFINITION = (
    "ADSCR наследует входы DSCR, CFADS и обслуживание долга, "
    "и считает сумму CFADS к сумме обслуживания долга за 12 месяцев lookback. "
    "На годе код отвечает adscr_not_applicable. "
    "Неполное окно FAS не досчитывает доли периода."
)


def test_adscr_catalog_matches_python_and_golden():
    record = load_financial_catalog().indicators["adscr"]
    assert record.base == "dscr"
    assert record.status == "active"
    money = {"cfads": "money", "debt_service": "money"}
    assert_slice(
        record,
        definition=ADSCR_DEFINITION,
        all_of=frozenset(money),
        one_of=frozenset(),
        formula={"base": "dscr"},
        unit="ratio",
        window=None,
        dimensions=money,
    )
    year = _run("adscr", None, {"cfads": "100", "debt_service": "40"})
    assert year["rows"] == []
    assert any(item["code"] == "adscr_not_applicable" for item in year["warnings"])
    periods = []
    for index in range(4):
        start = add_months(date(2025, 1, 1), 3 * index)
        end = add_months(start, 3) - timedelta(days=1)
        quarter = (start.month - 1) // 3 + 1
        periods.append(
            _period(
                period_id=f"{start.year}Q{quarter}",
                index=index,
                grain="quarter",
                start=start,
                end=end,
            )
        )
    series = {"cfads": ["25", "25", "25", "25"], "debt_service": ["20", "20", "20", "20"]}
    assert set(series) == record.inputs.concepts
    got = _run("adscr", None, {}, periods=periods, series=series)
    by_period = {row["period_id"]: row for row in got["rows"]}
    assert by_period["2025Q1"]["status"] == "not_computed"
    assert by_period["2025Q1"]["reason"] == "partial_window"
    # 100 / 80 за четыре квартала.
    assert by_period["2025Q4"]["value"] == Decimal("1.2500000000")
    assert by_period["2025Q4"]["window"] == ["2025Q1", "2025Q2", "2025Q3", "2025Q4"]


DSCR_MIN_DEFINITION = "Минимум посчитанных DSCR. Входы те же, что у базового DSCR."
DSCR_AVG_DEFINITION = (
    "Среднее DSCR двумя методиками, mean_of_ratios и ratio_of_sums. "
    "Код отдаёт обе, а не выбирает одну молча."
)


def _two_dscr_years() -> tuple[list[dict], dict[str, list[str]]]:
    periods = [_period(period_id="Y1", index=1), _period(period_id="Y2", index=2)]
    return periods, {"cfads": ["100", "100"], "debt_service": ["50", "25"]}


def test_dscr_min_catalog_matches_python_and_golden():
    record = load_financial_catalog().indicators["dscr_min"]
    assert record.base == "dscr"
    money = {"cfads": "money", "debt_service": "money"}
    assert_slice(
        record,
        definition=DSCR_MIN_DEFINITION,
        all_of=frozenset(money),
        one_of=frozenset(),
        formula={"base": "dscr"},
        unit="ratio",
        window=None,
        dimensions=money,
    )
    periods, series = _two_dscr_years()
    assert set(series) == record.inputs.concepts
    got = _run("dscr_min", None, {}, periods=periods, series=series)
    assert got["status"] == "succeeded"
    # Отношения 2 и 4, минимум 2.
    assert got["rows"][0]["value"] == Decimal("2.0000000000")
    assert got["rows"][0]["period_id"] == "Y1"
    assert set(got["rows"][0]["components"]) == record.inputs.concepts


def test_dscr_avg_catalog_matches_python_and_golden():
    record = load_financial_catalog().indicators["dscr_avg"]
    assert record.base == "dscr"
    money = {"cfads": "money", "debt_service": "money"}
    assert_slice(
        record,
        definition=DSCR_AVG_DEFINITION,
        all_of=frozenset(money),
        one_of=frozenset(),
        formula={"base": "dscr"},
        unit="ratio",
        window=None,
        dimensions=money,
    )
    periods, series = _two_dscr_years()
    got = _run("dscr_avg", None, {}, periods=periods, series=series)
    assert got["status"] == "succeeded"
    # Среднее отношений 3, отношение сумм 200/75.
    assert {row["variant"]: row["value"] for row in got["rows"]} == {
        "mean_of_ratios": Decimal("3.0000000000"),
        "ratio_of_sums": Decimal("2.6666666667"),
    }


LLCR_DEFINITION = (
    "LLCR: дисконт CFADS по дням/365, делённый на остаток долга. "
    "DSRA в числитель не входит. "
    "basis period_end берёт поток со следующего периода. "
    "period_start читает остаток как открывающий."
)
PLCR_DEFINITION = (
    "PLCR: дисконт CFADS по дням/365 до конца шкалы, делённый на остаток долга. "
    "basis period_end считает по умолчанию. "
    "period_start сдвигает окно на текущий период."
)


def _loan_life_book() -> tuple[list[dict], dict[str, list[str]]]:
    periods = [
        _period(
            period_id=str(year),
            index=index,
            grain="year",
            start=date(year, 1, 1),
            end=date(year, 12, 31),
        )
        for index, year in enumerate((2025, 2026, 2027, 2028))
    ]
    series = {
        "cfads": ["100", "100", "100", "100"],
        "debt_service": ["-50", "-50", "-50", "0"],
        "debt_outstanding": ["140", "95", "0", "0"],
        "discount_rate": ["0.10", "0.10", "0.10", "0.10"],
    }
    return periods, series


def _cover_life(metric: str):
    record = load_financial_catalog().indicators[metric]
    assert record.base is None
    terms = {"cfads": "money", "debt_outstanding": "money", "discount_rate": "ratio"}
    assert_slice(
        record,
        definition=LLCR_DEFINITION if metric == "llcr" else PLCR_DEFINITION,
        all_of=frozenset(terms),
        one_of=frozenset(),
        formula={
            "numerator": {"plus": ["cfads"], "minus": []},
            "denominator": {"plus": ["debt_outstanding"], "minus": []},
            "rate": "discount_rate",
        },
        unit="ratio",
        window=None,
        dimensions=terms,
    )
    # Срок долга режет Python по debt_service. В каталоге этого входа нет.
    assert "debt_service" not in record.inputs.concepts
    periods, series = _loan_life_book()
    return record, _run(metric, None, {}, periods=periods, series=series)


def test_llcr_catalog_matches_python_and_golden():
    _record, got = _cover_life("llcr")
    row = next(item for item in got["rows"] if item["period_id"] == "2025")
    assert row["value"] == LLCR_2025
    assert row["basis"] == "period_end"
    assert any(
        item["code"] == "dsra_not_included" and item["params"]["period_id"] == "2025" for item in got["warnings"]
    )


def test_plcr_catalog_matches_python_and_golden():
    _record, got = _cover_life("plcr")
    row = next(item for item in got["rows"] if item["period_id"] == "2025")
    assert row["value"] == PLCR_2025
    assert row["basis"] == "period_end"
    assert not any(item["code"] == "dsra_not_included" for item in got["warnings"])


NPV_DEFINITION = (
    "NPV дисконтирует project_fcf степенью period_index и квантует деньги. Это не дисконт LLCR по дням/365."
)
IRR_DEFINITION = (
    "IRR: ставка, обнуляющая NPV потока project_fcf. Степень дисконта - period_index, результат - отношение."
)


def test_npv_catalog_matches_python_and_golden():
    record = load_financial_catalog().indicators["npv"]
    assert record.base is None
    assert record.unit == "money"
    terms = {"project_fcf": "money", "discount_rate": "ratio"}
    assert_slice(
        record,
        definition=NPV_DEFINITION,
        all_of=frozenset(terms),
        one_of=frozenset(),
        formula={
            "numerator": {"plus": ["project_fcf"], "minus": []},
            "rate": "discount_rate",
        },
        unit="money",
        window=None,
        dimensions=terms,
    )
    assert record.model_types["investment_project"].use == "required"
    assert record.model_types["investment_project"].variant is None
    periods = [_period(period_id="Y0", index=0), _period(period_id="Y1", index=1)]
    series = {"project_fcf": ["100", "100"], "discount_rate": ["0.10", "0.10"]}
    assert set(series) == record.inputs.concepts
    got = _run("npv", None, {}, periods=periods, series=series)
    assert got["status"] == "succeeded"
    # 100 + 100/1.1, квант MONEY, не quantize_ratio.
    assert got["rows"][0]["value"] == Decimal("190.909091")
    assert set(got["rows"][0]["inputs"]) == record.inputs.concepts


def test_irr_catalog_matches_python_and_golden():
    record = load_financial_catalog().indicators["irr"]
    assert record.base is None
    assert_slice(
        record,
        definition=IRR_DEFINITION,
        all_of=frozenset({"project_fcf"}),
        one_of=frozenset(),
        formula={"numerator": {"plus": ["project_fcf"], "minus": []}},
        unit="ratio",
        window=None,
        dimensions={"project_fcf": "money"},
    )
    assert record.model_types["investment_project"].use == "required"
    periods = [_period(period_id="Y0", index=0), _period(period_id="Y1", index=1)]
    series = {"project_fcf": ["-100", "110"]}
    assert set(series) == record.inputs.concepts
    got = _run("irr", None, {}, periods=periods, series=series)
    assert got["status"] == "succeeded"
    # Минус 100, плюс 110 через один шаг: 0.10 после quantize_ratio.
    assert got["rows"][0]["value"] == Decimal("0.1000000000")
    assert got["rows"][0]["inputs"] == ["project_fcf"]


def test_dscr_pf_interest_fallback_matches_python_and_golden():
    pf = load_financial_catalog().indicators["dscr"].variants["pf"]
    assert_slice(
        pf,
        definition=DSCR_PF_DEFINITION,
        all_of=frozenset({"cfads", "debt_service"}),
        one_of=frozenset(),
        formula=PF_FORMULA,
        unit="ratio",
        window="period",
        dimensions={"cfads": "money", "debt_service": "money"},
    )
    values = {"cfads": "100", "interest_paid": "20", "principal": "30"}
    assert "interest_paid" not in pf.inputs.concepts
    assert "debt_service" not in values
    got = _run("dscr", "pf", values)
    assert got["status"] == "succeeded"
    # 100 / (20 + 30). Каталог по-прежнему говорит debt_service.
    assert got["rows"][0]["value"] == Decimal("2.0000000000")
    assert any(item["code"] == "interest_basis_fallback" for item in got["warnings"])
    assert set(got["rows"][0]["components"]) == {"cfads", "interest_paid", "principal"}
