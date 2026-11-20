"""ГЧП, инвестиционный проект и сверка NPV/IRR со строкой книги (срез 3)."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from finance_analysis.domain.covenant import select_ratio
from finance_analysis.domain.metrics import coverage_ratio, quantize_ratio
from finance_analysis.domain.model_type import applicability, infer
from finance_analysis.domain.returns import fcf_identity, project_return

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "ppp"
_NPV_TOL = Decimal("0.01")
_IRR_TOL = Decimal("1e-9")


def _catalog():
    from finance_analysis.application.model_types import load_model_types

    return load_model_types()


def _load(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def _bind(concept: str) -> dict:
    return {
        "effective_concept": concept,
        "row_key": concept,
        "is_primary": True,
        "status": "bound",
        "source": "inferred",
    }


def _fact(row: str, period: str, value: str, *, axis: str = "a") -> dict:
    return {
        "row_key": row,
        "axis_id": axis,
        "period_id": period,
        "normalized_value": value,
        "cell_id": f"{axis}!{period}",
    }


def _period(period: str, index: int | None, *, axis: str = "a") -> dict:
    item = {"axis_id": axis, "period_id": period, "grain": "year", "timeline_id": "t"}
    if index is not None:
        item["period_index"] = index
    return item


def _flows(years: list[dict], field: str) -> tuple[list[dict], list[dict]]:
    facts, periods = [], []
    for item in years:
        period = f"Y{item['year']}"
        periods.append(_period(period, int(item["year"])))
        facts.append(_fact("project_fcf", period, str(item[field])))
    return facts, periods


def _common(facts, bindings, periods) -> dict:
    return {
        "facts": facts,
        "bindings": bindings,
        "periods": periods,
        "period_phase": {},
        "explicit_phases": False,
        "sign_convention": "outflow_negative",
        "marker_class": None,
        "absent": frozenset(),
    }


def _returns(book: dict, *, field: str, book_npv: str | None, book_irr: str | None):
    catalog = _catalog()
    facts, periods = _flows(book["years"], field)
    bindings = [_bind("project_fcf"), _bind("discount_rate")]
    facts.append(_fact("discount_rate", "rate", book["discount_rate"], axis="p"))
    periods.append(_period("rate", None, axis="p"))
    if book_npv is not None:
        bindings.append(_bind("npv"))
        facts.append(_fact("npv", "npv", book_npv, axis="p"))
        periods.append(_period("npv", None, axis="p"))
    if book_irr is not None:
        bindings.append(_bind("irr"))
        facts.append(_fact("irr", "irr", book_irr, axis="p"))
        periods.append(_period("irr", None, axis="p"))
    common = _common(facts, bindings, periods)
    npv = select_ratio(
        "npv", None, common, profile={}, profile_ref=None, composed=catalog.composed, concepts=catalog.concepts, money=frozenset()
    )
    irr = select_ratio(
        "irr", None, common, profile={}, profile_ref=None, composed=catalog.composed, concepts=catalog.concepts, money=frozenset()
    )
    return npv, irr


def test_grantor_and_debt_service_are_a_ppp_hybrid():
    catalog = _catalog()
    got = infer(
        catalog,
        bound=frozenset({"grantor_payment", "cfads", "debt_service"}),
        sheets=frozenset({"Cash Flow"}),
        accept=0.6,
        gap=0.15,
    )
    assert got.confident is True
    assert got.labels == ("ppp_concession", "project_finance")
    assert got.primary == "ppp_concession"
    assert catalog.types["ppp_concession"].variants["dscr"] == "pf"
    assert applicability(catalog, got.labels, "dscr") == "required"
    assert applicability(catalog, got.labels, "npv") == "optional"


def test_cited_npv_without_debt_service_is_an_investment_project():
    catalog = _catalog()
    got = infer(
        catalog,
        bound=frozenset({"npv", "irr", "discount_rate", "project_fcf"}),
        sheets=frozenset({"Base Model"}),
        accept=0.6,
        gap=0.15,
    )
    assert got.confident is True
    assert got.primary == "investment_project"
    assert got.scores["investment_project"] == 1.0
    assert applicability(catalog, got.labels, "npv") == "required"
    assert applicability(catalog, got.labels, "dscr") == "not_applicable"


def test_project_finance_book_that_also_has_npv_stays_project_finance():
    catalog = _catalog()
    got = infer(
        catalog,
        bound=frozenset({"cfads", "debt_service", "npv", "irr", "discount_rate"}),
        sheets=frozenset({"Debt"}),
        accept=0.6,
        gap=0.15,
    )
    assert got.primary == "project_finance"
    assert got.scores["investment_project"] == 0.0
    assert got.scores["ppp_concession"] == 0.0
    assert applicability(catalog, got.labels, "npv") == "not_applicable"


def test_a_three_statement_book_with_npv_stays_corporate():
    catalog = _catalog()
    got = infer(
        catalog,
        bound=frozenset({"npv", "irr", "discount_rate", "ebitda", "interest"}),
        sheets=frozenset({"Income statement", "Balance sheet", "Cash flow"}),
        accept=0.6,
        gap=0.15,
    )
    assert got.confident is True
    assert got.primary == "corporate"
    assert got.labels == ("corporate",)
    assert applicability(catalog, got.labels, "npv") == "not_applicable"


def test_ppp_and_escrow_keep_their_type_beside_an_investment_score():
    catalog = _catalog()
    ppp = infer(
        catalog,
        bound=frozenset({"grantor_payment", "npv", "irr", "discount_rate"}),
        sheets=frozenset(),
        accept=0.6,
        gap=0.15,
    )
    escrow = infer(
        catalog,
        bound=frozenset({"escrow_balance", "npv", "irr", "discount_rate"}),
        sheets=frozenset(),
        accept=0.6,
        gap=0.15,
    )
    assert ppp.confident is True and ppp.primary == "ppp_concession" and ppp.labels == ("ppp_concession",)
    assert escrow.confident is True and escrow.primary == "development_escrow"


def test_an_empty_book_does_not_score_investment_just_because_debt_is_absent():
    catalog = _catalog()
    got = infer(catalog, bound=frozenset(), sheets=frozenset({"Model"}), accept=0.6, gap=0.15)
    assert got.scores["investment_project"] == 0.0
    assert got.confident is False


def test_toll_road_min_dscr_matches_the_published_minimum():
    book = _load("toll_road.json")
    facts, bindings, periods = [], [], []
    for item in book["years"]:
        period = f"Y{item['year']}"
        periods.append(_period(period, int(item["year"])))
        facts.append(_fact("cfads", period, str(item["cfads"])))
        facts.append(_fact("debt_service", period, str(item["debt_service"])))
    bindings.extend([_bind("cfads"), _bind("debt_service")])
    got = coverage_ratio(
        metric="dscr",
        facts=facts,
        bindings=bindings,
        periods=periods,
        period_phase={},
        explicit_phases=False,
    )
    computed = [row["value"] for row in got["rows"] if row["status"] == "computed"]
    lowest = min(computed)
    assert lowest == quantize_ratio(Decimal(book["min_dscr"]))
    assert round(lowest, 2) == Decimal("0.88")
    assert len(computed) == sum(1 for item in book["years"] if Decimal(item["debt_service"]) != 0)


def test_port_npv_and_irr_match_the_book():
    book = _load("port.json")
    npv, irr = _returns(book, field="project_fcf", book_npv=book["npv"], book_irr=book["project_irr"])
    assert npv["status"] == "succeeded"
    assert irr["status"] == "succeeded"
    assert npv["warnings"] == []
    assert irr["warnings"] == []
    assert abs(npv["rows"][0]["value"] - Decimal(book["npv"])) <= _NPV_TOL
    assert abs(irr["rows"][0]["value"] - Decimal(book["project_irr"])) <= _IRR_TOL


def test_toll_road_npv_and_irr_use_the_year_index():
    book = _load("toll_road.json")
    book = {**book, "discount_rate": book["wacc"]}
    npv, irr = _returns(book, field="fcff", book_npv=book["npv"], book_irr=book["project_irr"])
    assert npv["warnings"] == []
    assert irr["warnings"] == []
    assert abs(npv["rows"][0]["value"] - Decimal(book["npv"])) <= _NPV_TOL
    assert abs(irr["rows"][0]["value"] - Decimal(book["project_irr"])) <= _IRR_TOL


def _quote(flows: list[tuple[int, str | None]], *, rate: str = "0.10", rates: list[str] | None = None, book: list[str] | None = None):
    catalog = _catalog()
    facts, periods = [], []
    bindings = [_bind("project_fcf"), _bind("discount_rate")]
    for index, value in flows:
        period = f"Y{index}"
        periods.append(_period(period, index))
        facts.append(
            {
                "row_key": "project_fcf",
                "axis_id": "a",
                "period_id": period,
                "normalized_value": value,
                "cell_id": f"a!{period}",
            }
        )
    for number, item in enumerate(rates if rates is not None else [rate]):
        period = f"R{number}"
        facts.append(_fact("discount_rate", period, item, axis="p"))
        periods.append(_period(period, None, axis="p"))
    if book is not None:
        bindings.append(_bind("npv"))
        for number, item in enumerate(book):
            period = f"B{number}"
            facts.append(_fact("npv", period, item, axis="p"))
            periods.append(_period(period, None, axis="p"))
    return select_ratio(
        "npv",
        None,
        _common(facts, bindings, periods),
        profile={},
        profile_ref=None,
        composed=catalog.composed,
        concepts=catalog.concepts,
        money=frozenset(),
    )


def test_an_empty_period_outside_the_filled_span_is_ignored():
    plain = _quote([(0, "-100"), (1, "60")])
    edged = _quote([(0, None), (1, "-100"), (2, "60"), (3, None)])
    same_indexes = _quote([(1, "-100"), (2, "60")])
    assert plain["status"] == "succeeded"
    assert plain["rows"][0]["value"] == Decimal("-45.454545")
    assert edged["warnings"] == []
    assert edged["rows"][0]["value"] == same_indexes["rows"][0]["value"]


def test_a_hole_inside_the_span_is_not_computed():
    got = _quote([(0, "-100"), (1, None), (2, "60")])
    assert got["status"] == "not_computed"
    assert got["rows"] == []
    assert got["needs_input"] == []
    assert got["warnings"][0]["code"] == "project_return_incomplete"


def test_two_discount_rates_are_not_computed():
    got = _quote([(0, "-100"), (1, "60")], rates=["0.10", "0.12"])
    assert got["status"] == "not_computed"
    assert got["rows"] == []
    assert got["needs_input"] == []
    assert got["warnings"][0]["code"] == "discount_rate_not_unique"


def test_one_matching_cell_on_the_book_row_does_not_warn():
    got = _quote([(0, "-100"), (1, "60")], book=["10", "-45.454545"])
    assert got["rows"][0]["value"] == Decimal("-45.454545")
    assert got["warnings"] == []


def test_a_book_row_with_no_matching_cell_warns_once():
    got = _quote([(0, "-100"), (1, "60")], book=["10", "11"])
    assert got["rows"][0]["status"] == "computed"
    assert [item["code"] for item in got["warnings"]] == ["npv_book_mismatch"]
    assert got["warnings"][0]["params"]["model"] in {"10", "11"}


def _identity(variant, rows, *, convention="outflow_negative"):
    catalog = _catalog()
    facts, periods, bindings = [], [], []
    concepts = {name for row in rows for name in row}
    for concept in concepts:
        bindings.append(_bind(concept))
    for index, row in enumerate(rows):
        period = f"Y{index}"
        periods.append(_period(period, index))
        for concept, value in row.items():
            facts.append(_fact(concept, period, value))
    return select_ratio(
        "fcf_identity",
        variant,
        _common(facts, bindings, periods) | {"sign_convention": convention},
        profile={},
        profile_ref=None,
        composed=catalog.composed,
        concepts=catalog.concepts,
        money=frozenset(),
    )


def test_vk477_identity_normalizes_a_negative_capex_and_skips_interest():
    got = _identity(
        "vk477",
        [{"operating_cash_flow": "100", "capex": "-30", "project_fcf": "70", "net_interest": "10"}],
    )
    assert got["status"] == "succeeded"
    assert got["warnings"] == []


def test_fcff_identity_matches_interest_after_tax_and_a_shift_warns_without_replacing_npv():
    row = {
        "operating_cash_flow": "100",
        "capex": "30",
        "net_interest": "10",
        "tax_rate": "0.20",
        "project_fcf": "78",
    }
    assert _identity("fcff_after_interest", [row])["warnings"] == []
    shifted = {**row, "net_interest": "11"}
    warned = _identity("fcff_after_interest", [shifted])
    assert warned["warnings"][0]["code"] == "fcf_identity_mismatch"
    assert warned["rows"] == []
    catalog = _catalog()
    facts = [
        _fact("project_fcf", "Y0", "78"),
        _fact("project_fcf", "Y1", "0"),
        _fact("discount_rate", "rate", "0.10", axis="p"),
    ]
    periods = [_period("Y0", 0), _period("Y1", 1), _period("rate", None, axis="p")]
    npv = select_ratio(
        "npv",
        None,
        _common(facts, [_bind("project_fcf"), _bind("discount_rate")], periods),
        profile={},
        profile_ref=None,
        composed=catalog.composed,
        concepts=catalog.concepts,
        money=frozenset(),
    )
    assert npv["rows"][0]["inputs"] == ["project_fcf", "discount_rate"]
    assert "ocf" not in npv["rows"][0]["inputs"]


async def test_optional_identity_without_a_variant_is_not_a_completed_check():
    got = await _ratios(["npv", "irr", "fcf_identity"])
    identity = next(item for item in got["applicability"] if item["metric"] == "fcf_identity")
    assert identity == {"metric": "fcf_identity", "applicability": "optional", "skipped": "variant_absent"}
    assert [item["code"] for item in got["warnings"]] == ["fcf_identity_variant_absent"]
    assert not any(row["metric"] == "fcf_identity" for row in got["rows"])
    recorded = [item for item in got["applicability"] if item["metric"] in {"npv", "irr"}]
    assert recorded == [
        {"metric": "npv", "applicability": "required"},
        {"metric": "irr", "applicability": "required"},
    ]
    assert any(item["subject"] == "project_fcf" for item in got["needs_input"])


async def test_another_not_computed_identity_stays_a_completed_check(monkeypatch):
    from finance_analysis.application import analyses as analyses_mod

    original = analyses_mod.confirmed_variants

    def named(catalog, verdict):
        found = dict(original(catalog, verdict))
        found["fcf_identity"] = "vk477"
        return found

    monkeypatch.setattr(analyses_mod, "confirmed_variants", named)
    got = await _ratios(
        ["fcf_identity"],
        bindings=[
            _bind("project_fcf"),
            _bind("operating_cash_flow"),
            _bind("capex"),
        ],
        facts=[_fact("project_fcf", "Y0", "1"), _fact("project_fcf", "Y2", "1")],
        periods=[_period("Y0", 0), _period("Y1", 1), _period("Y2", 2)],
    )
    assert got["applicability"] == [{"metric": "fcf_identity", "applicability": "optional"}]
    assert [item["code"] for item in got["warnings"]] == ["project_return_incomplete"]
    assert got["rows"] == []


async def _ratios(metrics, *, bindings=None, facts=None, periods=None):
    from finance_analysis.application.analyses import Analyses, Target
    from finance_analysis.application.catalog import load_catalog
    from finance_analysis.application.model_types import load_model_types
    from finance_analysis.domain.book import Head
    from finance_analysis.domain.errors import NotFound
    from finance_analysis.domain.model_type import Effective

    class _Guard:
        async def read_all(self, _job_id):
            return []

    class _Service:
        model_types = load_model_types()
        catalog = load_catalog()
        guard = _Guard()

        async def _dataset_rows(self, _job_id, _head, dataset):
            if dataset == "bindings":
                return bindings or []
            if dataset == "fact_observation":
                return facts or []
            if dataset == "dim_period":
                return periods or []
            if dataset == "dim_row":
                return []
            raise NotFound(dataset)

        async def resolve_model_type(self, _job_id, _head):
            return Effective(
                ("investment_project",),
                "investment_project",
                "confirmed",
                None,
                1,
                None,
                1.0,
                {"investment_project": 1.0},
                (),
            )

    head = Head(build_key="build", state_seq=1, derive_key="derive", versions={})
    target = Target(head=head, build="build", manifest={}, fresh=True)
    return await Analyses(_Service()).compute_metrics("job", target, metrics)


def test_unnamed_identity_variant_does_not_warn():
    row = [{"operating_cash_flow": "100", "capex": "30", "project_fcf": "0"}]
    got = _identity(None, row)
    unknown = _identity("other", row)
    assert got["status"] == "not_computed"
    assert got["rows"] == []
    assert [item["code"] for item in got["warnings"]] == ["fcf_identity_variant_absent"]
    assert unknown["status"] == "not_computed"
    assert unknown["rows"] == []
    assert [item["code"] for item in unknown["warnings"]] == ["fcf_identity_variant_absent"]


def test_full_lease_payment_does_not_match_the_interest_portion():
    built = {
        "operating_cash_flow": "100",
        "capex": "30",
        "net_interest": "40",
        "tax_rate": "0.20",
        "project_fcf": "78",
    }
    got = _identity("fcff_after_interest", [built])
    assert got["warnings"][0]["code"] == "fcf_identity_mismatch"
    assert got["warnings"][0]["params"]["cells"]


def test_book_row_that_disagrees_is_a_warning():
    book = _load("port.json")
    npv, irr = _returns(book, field="project_fcf", book_npv="100", book_irr="0.5")
    assert npv["warnings"][0]["code"] == "npv_book_mismatch"
    assert irr["warnings"][0]["code"] == "irr_book_mismatch"
    assert npv["rows"][0]["status"] == "computed"
    assert irr["rows"][0]["status"] == "computed"


def test_two_axes_of_project_fcf_are_not_added():
    flow = [
        ("base", "Y1", 1, "-100"),
        ("forecast", "Y1", 1, "-120"),
        ("base", "Y2", 2, "60"),
        ("forecast", "Y2", 2, "70"),
    ]
    facts = [
        {
            "row_key": "project_fcf",
            "axis_id": axis,
            "period_id": period,
            "normalized_value": value,
        }
        for axis, period, _index, value in flow
    ]
    facts.append(
        {
            "row_key": "discount_rate",
            "axis_id": "base",
            "period_id": "R",
            "normalized_value": "0.10",
        }
    )
    periods = [
        {"axis_id": axis, "period_id": period, "period_index": index}
        for axis, period, index, _value in flow
    ]
    periods.append({"axis_id": "base", "period_id": "R", "period_index": None})
    bindings = [
        {
            "effective_concept": "project_fcf",
            "row_key": "project_fcf",
            "is_primary": True,
            "status": "bound",
            "source": "inferred",
        },
        {
            "effective_concept": "discount_rate",
            "row_key": "discount_rate",
            "is_primary": True,
            "status": "bound",
            "source": "inferred",
        },
    ]
    for metric in ("npv", "irr"):
        got = project_return(metric, facts=facts, bindings=bindings, periods=periods)
        assert got["status"] == "not_computed"
        assert got["rows"] == []
        assert got["warnings"][0]["code"] == "axis_ambiguous"
    identity_bindings = [
        *bindings,
        {
            "effective_concept": "operating_cash_flow",
            "row_key": "operating_cash_flow",
            "is_primary": True,
            "status": "bound",
            "source": "inferred",
        },
        {
            "effective_concept": "capex",
            "row_key": "capex",
            "is_primary": True,
            "status": "bound",
            "source": "inferred",
        },
    ]
    facts.extend(
        [
            {"row_key": "operating_cash_flow", "axis_id": "base", "period_id": "Y1", "normalized_value": "10"},
            {"row_key": "capex", "axis_id": "base", "period_id": "Y1", "normalized_value": "3"},
        ]
    )
    identity = fcf_identity(
        "vk477",
        facts=facts,
        bindings=identity_bindings,
        periods=periods,
    )
    assert identity["status"] == "not_computed"
    assert identity["rows"] == []
    assert identity["warnings"][0]["code"] == "axis_ambiguous"


def test_two_sign_changes_keep_the_root_and_warn():
    # −100, 230, −132 имеет корни 10% и 20%. Оба внутри (−0.9, 20), поэтому
    # прежняя бисекция видит один знак на концах и корень не возвращает.
    missed = _irr_of(["-100", "230", "-132"])
    assert missed["status"] == "not_computed"
    assert missed["rows"] == []
    assert missed["warnings"] == []
    # −100, 2710, −2860: две перемены, один положительный корень внутри скобки,
    # второй дальше 20. Найденный корень остаётся, какой именно — не закрепляем.
    got = _irr_of(["-100", "2710", "-2860"])
    assert got["status"] == "succeeded"
    assert len(got["rows"]) == 1
    assert got["warnings"] == [
        {"code": "irr_multiple_roots", "params": {"metric": "irr", "sign_changes": 2}}
    ]
    plain = _irr_of(["-100", "60", "70"])
    assert plain["status"] == "succeeded"
    assert plain["warnings"] == []


def _irr_of(values: list[str]) -> dict:
    facts, periods = [], []
    for index, value in enumerate(values):
        period = f"Y{index}"
        facts.append(
            {
                "row_key": "project_fcf",
                "axis_id": "a",
                "period_id": period,
                "normalized_value": value,
            }
        )
        periods.append({"axis_id": "a", "period_id": period, "period_index": index})
    return project_return(
        "irr",
        facts=facts,
        bindings=[
            {
                "effective_concept": "project_fcf",
                "row_key": "project_fcf",
                "is_primary": True,
                "status": "bound",
                "source": "inferred",
            }
        ],
        periods=periods,
    )
