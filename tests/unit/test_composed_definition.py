"""Составной исполнитель читает стороны определения. Литералы net_debt и ebitda не считаются."""

from datetime import date
from decimal import Decimal

import pytest

from finance_analysis.domain.covenant import composed_ratio, select_ratio
from finance_analysis.domain.execution_contract import (
    CatalogMetricRecord,
    compile_definition,
)
from finance_analysis.domain.metric_contract import REGISTRY, UndeclaredInput
from finance_analysis.domain.model_type import Composed, MetricExpression, Side
from finance_analysis.domain.resolved_plan import ResolvedInput, seal

_EXECUTOR_ID = "composed_ratio"
_EXECUTOR_VERSION = "composed_ratio@1"
_MONEY = frozenset(
    {
        "net_debt",
        "cash",
        "ebitda",
        "ebit",
        "total_debt",
        "off_balance_obligations",
        "escrow_balance",
        "debt_outstanding",
        "cash_taxes",
    }
)

# Каталожная формула и подмена одной стороны. Год схлопывает LTM в один период.
_SPECS = {
    "net_debt_ebitda": {
        "window": "LTM",
        "num": (("net_debt",), ()),
        "den": (("ebitda",), ()),
        "changed_num": (("net_debt",), ("cash",)),
        "changed_den": (("ebitda",), ()),
        "changed_value": Decimal("2.4000000000"),
        "catalog_value": Decimal("3.0000000000"),
    },
    "total_debt_ebitda": {
        "window": "LTM",
        "num": (("total_debt",), ()),
        "den": (("ebitda",), ()),
        "changed_num": (("total_debt",), ()),
        "changed_den": (("ebit",), ()),
        "changed_value": Decimal("6.0000000000"),
        "catalog_value": Decimal("3.0000000000"),
    },
    "debt_off_balance_ebitda": {
        "window": "LTM",
        "num": (("total_debt", "off_balance_obligations"), ()),
        "den": (("ebitda",), ()),
        "changed_num": (("total_debt", "off_balance_obligations"), ()),
        "changed_den": (("ebit",), ()),
        "changed_value": Decimal("6.0000000000"),
        "catalog_value": Decimal("3.0000000000"),
    },
    "escrow_coverage": {
        "window": "period",
        "num": (("escrow_balance",), ()),
        "den": (("debt_outstanding",), ()),
        "changed_num": (("escrow_balance",), ()),
        "changed_den": (("ebitda",), ()),
        "changed_value": Decimal("0.5000000000"),
        "catalog_value": Decimal("0.2500000000"),
    },
}

_VALUES = {
    "net_debt": "300",
    "cash": "60",
    "ebitda": "100",
    "ebit": "50",
    "total_debt": "300",
    "off_balance_obligations": "0",
    "escrow_balance": "50",
    "debt_outstanding": "200",
    "cash_taxes": "7",
}
_AGGREGATIONS = {
    "net_debt": "last",
    "cash": "last",
    "total_debt": "last",
    "off_balance_obligations": "last",
    "escrow_balance": "last",
    "debt_outstanding": "last",
    "ebitda": "sum",
    "ebit": "sum",
    "cash_taxes": "sum",
}


def _expr(num, den) -> MetricExpression:
    return MetricExpression(
        numerator_plus=num[0],
        numerator_minus=num[1],
        denominator_plus=den[0],
        denominator_minus=den[1],
    )


def _formula(num, den, window: str) -> Composed:
    return Composed(Side(num[0], num[1]), Side(den[0], den[1]), window)


def _definition(metric: str, num, den, window: str, **kwargs):
    return compile_definition(
        CatalogMetricRecord(
            metric_id=metric,
            expression=_expr(num, den),
            executor_key="composed",
            executor_id=_EXECUTOR_ID,
            executor_version=_EXECUTOR_VERSION,
            formula_id=metric,
            definition_version=kwargs.pop("definition_version", f"{metric}@2"),
            window=window,
            **kwargs,
        )
    )


def _bind(concept: str) -> dict:
    return {
        "effective_concept": concept,
        "row_key": concept,
        "binding_key": concept,
        "is_primary": True,
        "status": "bound",
        "source": "inferred",
    }


def _fact(
    concept: str,
    value: str,
    period: str = "Y1",
    *,
    cell: str | None = None,
    scale: str | None = None,
) -> dict:
    row = {
        "row_key": concept,
        "axis_id": "a",
        "period_id": period,
        "normalized_value": value,
    }
    if cell is not None:
        row["cell_id"] = cell
    if scale is not None:
        row["value"] = "1"
        row["scale_factor"] = scale
    return row


def _year() -> dict:
    return {
        "axis_id": "a",
        "period_id": "Y1",
        "period_index": 1,
        "grain": "year",
        "timeline_id": "t",
        "period_start": date(2024, 1, 1),
        "period_end": date(2024, 12, 31),
    }


def _bindings():
    return [_bind(name) for name in _VALUES]


def _facts():
    return [_fact(name, value) for name, value in _VALUES.items()]


def _run(metric: str, formula: Composed, definition, **extra) -> dict:
    kwargs = {
        "facts": _facts(),
        "bindings": _bindings(),
        "periods": [_year()],
        "aggregations": _AGGREGATIONS,
    }
    kwargs.update(extra)
    if definition is None:
        return composed_ratio(metric, formula, **kwargs)
    return composed_ratio(metric, formula, definition=definition, **kwargs)


def _value(result: dict) -> Decimal | None:
    rows = [row for row in result["rows"] if row.get("value") is not None]
    if len(rows) != 1:
        return None
    return rows[0]["value"]


@pytest.mark.parametrize("metric", list(_SPECS))
def test_an_in_memory_side_change_changes_the_quotient(metric: str):
    spec = _SPECS[metric]
    catalog = _formula(spec["num"], spec["den"], spec["window"])
    assert _value(_run(metric, catalog, None)) == spec["catalog_value"]
    changed = _definition(metric, spec["changed_num"], spec["changed_den"], spec["window"])
    got = _run(metric, catalog, changed)
    assert got["status"] == "succeeded"
    assert _value(got) == spec["changed_value"]


@pytest.mark.parametrize("metric", list(_SPECS))
def test_an_undeclared_concept_refuses_instead_of_the_old_quotient(metric: str):
    spec = _SPECS[metric]
    definition = _definition(metric, spec["num"], spec["den"], spec["window"])
    names = (*spec["num"][0], *spec["num"][1], *spec["den"][0], *spec["den"][1])
    foreign = "cash_taxes"
    assert foreign not in names
    inputs = tuple(
        ResolvedInput(name, "all_of", "formula", name, name, None, False, True) for name in (*names, foreign)
    )
    plan = seal(
        metric_id=metric,
        variant=None,
        variant_source="formula",
        catalog_version=None,
        semantic_model_version=None,
        build_key=None,
        model_id=None,
        status="resolved",
        inputs=inputs,
        diagnostic=(),
        rejected=(),
        fallbacks=(),
        warnings=(),
        needs_input=(),
        shield=None,
        definition_hash=definition.definition_hash,
    )
    with pytest.raises(UndeclaredInput) as raised:
        _run(metric, _formula(spec["num"], spec["den"], spec["window"]), definition, plan=plan)
    assert raised.value.name == foreign


@pytest.mark.parametrize("metric", list(_SPECS))
def test_an_unexecutable_formula_is_not_computed(metric: str):
    spec = _SPECS[metric]
    expression = MetricExpression(
        numerator_plus=spec["num"][0],
        denominator_plus=spec["den"][0],
        rate="discount_rate",
    )
    definition = compile_definition(
        CatalogMetricRecord(
            metric_id=metric,
            expression=expression,
            executor_key="composed",
            executor_id=_EXECUTOR_ID,
            executor_version=_EXECUTOR_VERSION,
            formula_id=metric,
            window=spec["window"],
        )
    )
    got = _run(metric, _formula(spec["num"], spec["den"], spec["window"]), definition)
    assert got["status"] == "not_computed"
    assert got["reason"] == "unsupported_formula"
    assert _value(got) != spec["catalog_value"]


def test_profile_overlay_changes_the_formula_only_when_compile_receives_it():
    """Профиль ковенанта не подменяет составной коэффициент в ``compute_metrics``.

    ``dscr_definition`` принадлежит DSCR. ``_composed_definitions`` его не читает.
    Подмена ниже — только явный аргумент ``compile_definition``.
    """
    metric = "net_debt_ebitda"
    catalog = _formula((("net_debt",), ()), (("ebitda",), ()), "LTM")
    definition = compile_definition(
        CatalogMetricRecord(
            metric_id=metric,
            expression=_expr((("net_debt",), ()), (("ebitda",), ())),
            executor_key="composed",
            executor_id=_EXECUTOR_ID,
            executor_version=_EXECUTOR_VERSION,
            formula_id=metric,
            definition_version="net_debt_ebitda@2",
            window="LTM",
        ),
        covenant={
            "profile": {
                "dscr_definition": {
                    "numerator": {"plus": ["net_debt"], "minus": ["cash"]},
                    "denominator": {"plus": ["ebitda"]},
                    "window": "LTM",
                }
            },
            "profile_ref": "book@3",
            "default": catalog,
            "concepts": _MONEY,
            "money": _MONEY,
        },
    )
    assert definition.definition_source == "profile"
    assert definition.normalized_expression.numerator_minus == ("cash",)
    got = _run(metric, catalog, definition)
    assert got["status"] == "succeeded"
    assert got["definition_source"] == "profile"
    assert got["definition_ref"]["profile_version"] == "book@3"
    assert _value(got) == Decimal("2.4000000000")


def test_stock_and_flow_follow_aggregations():
    periods = [
        {
            "axis_id": "a",
            "period_id": f"Q{index}",
            "period_index": index,
            "grain": "quarter",
            "timeline_id": "t",
            "period_start": date(2024, (index - 1) * 3 + 1, 1),
            "period_end": date(2024, index * 3, 30 if index < 4 else 31),
        }
        for index in range(1, 5)
    ]
    periods[0]["period_end"] = date(2024, 3, 31)
    periods[1]["period_end"] = date(2024, 6, 30)
    periods[2]["period_end"] = date(2024, 9, 30)
    facts = []
    for index in range(1, 5):
        facts.append(_fact("net_debt", "100", f"Q{index}"))
        facts.append(_fact("ebitda", "10", f"Q{index}"))
        facts.append(_fact("total_debt", "100", f"Q{index}"))
    bindings = [_bind("net_debt"), _bind("ebitda"), _bind("total_debt")]
    formula = _formula((("net_debt",), ()), (("ebitda",), ()), "LTM")
    gross = _formula((("total_debt",), ()), (("ebitda",), ()), "LTM")

    def final(metric, body, aggregations):
        got = composed_ratio(
            metric,
            body,
            facts=facts,
            bindings=bindings,
            periods=periods,
            aggregations=aggregations,
        )
        return next(row["value"] for row in got["rows"] if row["period_id"] == "Q4")

    ending = {"net_debt": "last", "total_debt": "last", "ebitda": "sum"}
    summed = {"net_debt": "sum", "total_debt": "sum", "ebitda": "sum"}
    assert final("net_debt_ebitda", formula, ending) == Decimal("2.5000000000")
    assert final("net_debt_ebitda", formula, summed) == Decimal("10.0000000000")
    assert final("total_debt_ebitda", gross, ending) == Decimal("2.5000000000")
    assert final("total_debt_ebitda", gross, summed) == Decimal("10.0000000000")


def test_executor_versions_land_in_provenance_without_an_invented_implementation():
    metric = "net_debt_ebitda"
    catalog = _formula((("net_debt",), ()), (("ebitda",), ()), "LTM")
    definition = _definition(metric, (("net_debt",), ()), (("ebitda",), ()), "LTM")
    assert REGISTRY[(metric, metric)].implementation_version == ""
    collected: list = []
    got = _run(metric, catalog, definition, collect=collected)
    assert _value(got) == Decimal("3.0000000000")
    assert len(collected) == 1
    evidence = collected[0]
    assert evidence.definition_version == "net_debt_ebitda@2"
    assert evidence.executor_id == _EXECUTOR_ID
    assert evidence.executor_version == _EXECUTOR_VERSION
    assert evidence.implementation == ""
    assert not evidence.implementation.endswith("@1")
    select_collected: list = []
    select_ratio(
        metric,
        None,
        {
            "facts": _facts(),
            "bindings": _bindings(),
            "periods": [_year()],
            "sign_convention": "outflow_negative",
            "marker_class": None,
            "absent": frozenset(),
        },
        profile=None,
        profile_ref=None,
        composed={metric: catalog},
        concepts=_MONEY,
        money=_MONEY,
        aggregations=_AGGREGATIONS,
        definition=definition,
        collect=select_collected,
    )
    assert select_collected[0].executor_version == _EXECUTOR_VERSION
    assert select_collected[0].definition_version == "net_debt_ebitda@2"
    assert select_collected[0].implementation == ""


def test_shipped_composed_definitions_do_not_invent_a_version():
    from finance_analysis.application.analyses import _composed_definitions
    from finance_analysis.application.financial_catalog import load_financial_catalog
    from finance_analysis.application.model_types import load_model_types

    found = _composed_definitions(load_model_types(), load_financial_catalog())
    for metric in _SPECS:
        record = found[metric]
        assert record.definition_version is None
        assert record.executor_id == _EXECUTOR_ID
        assert record.executor_version == _EXECUTOR_VERSION
        assert record.formula_id == metric
        assert "@1" not in record.executor_id
        assert record.definition_source == "catalog"


def test_unknown_aggregation_is_not_computed():
    metric = "net_debt_ebitda"
    catalog = _formula((("net_debt",), ()), (("ebitda",), ()), "LTM")
    definition = _definition(metric, (("net_debt",), ()), (("ebitda",), ()), "LTM")
    got = _run(
        metric,
        catalog,
        definition,
        aggregations={**_AGGREGATIONS, "ebitda": "median"},
    )
    assert got["status"] == "not_computed"
    assert any(row.get("reason") == "aggregation_unknown" for row in got["rows"])
    assert _value(got) != Decimal("3.0000000000")


def test_quarterly_stock_and_flow_follow_the_definition_and_the_plan():
    periods = _quarters()
    facts = []
    for index in range(1, 5):
        facts.append(_fact("net_debt", "100", f"Q{index}", cell=f"N{index}"))
        facts.append(_fact("ebitda", "10", f"Q{index}", cell=f"E{index}"))
    bindings = [_bind("net_debt"), _bind("ebitda")]
    definition = _definition("net_debt_ebitda", (("net_debt",), ()), (("ebitda",), ()), "LTM")
    wrong = _formula((("net_debt",), ()), (("cash",), ()), "LTM")
    plan = _plan(definition, ("net_debt", "ebitda"))
    got = composed_ratio(
        "net_debt_ebitda",
        wrong,
        facts=facts,
        bindings=bindings,
        periods=periods,
        aggregations={"net_debt": "last", "ebitda": "sum"},
        definition=definition,
        plan=plan,
    )
    final = next(row for row in got["rows"] if row["period_id"] == "Q4")
    assert final["status"] == "computed"
    assert final["value"] == Decimal("2.5000000000")


def test_a_computed_trace_records_operands_steps_and_fact_use():
    metric = "net_debt_ebitda"
    definition = _definition(metric, (("net_debt",), ()), (("ebitda",), ()), "LTM")
    collected: list = []
    facts = [
        _fact("net_debt", "300", cell="Debt!N"),
        _fact("ebitda", "100", cell="PL!E"),
    ]
    got = _run(
        metric,
        _formula((("net_debt",), ()), (("ebitda",), ()), "LTM"),
        definition,
        collect=collected,
        facts=facts,
        bindings=[_bind("net_debt"), _bind("ebitda")],
    )
    assert got["status"] == "succeeded"
    assert len(collected) == 1
    evidence = collected[0]
    assert evidence.evidence_status == "evidence_available"
    period = next(item for item in evidence.period_results if item.status == "computed")
    assert period.numerator == Decimal(300)
    assert period.denominator == Decimal(100)
    assert [step.operation for step in period.steps] == [
        "numerator_assembly",
        "denominator_assembly",
        "ratio",
    ]
    uses = {(item.operand, item.cell_id, item.effective_value) for item in evidence.fact_uses}
    assert ("numerator", "Debt!N", Decimal(300)) in uses
    assert ("denominator", "PL!E", Decimal(100)) in uses
    assert evidence.fact_observations


def test_every_exit_publishes_the_definition_and_the_execution_status():
    metric = "net_debt_ebitda"
    definition = _definition(metric, (("net_debt",), ()), (("ebitda",), ()), "LTM")
    catalog = _formula((("net_debt",), ()), (("ebitda",), ()), "LTM")

    def published(**extra):
        collected: list = []
        got = _run(metric, catalog, definition, collect=collected, **extra)
        assert len(collected) == 1
        evidence = collected[0]
        assert evidence.definition_version == f"{metric}@2"
        assert evidence.executor_id == _EXECUTOR_ID
        assert evidence.executor_version == _EXECUTOR_VERSION
        assert evidence.evidence_status != "evidence_available"
        return got, evidence

    blocked, evidence = published(profile={"ebitda_definition": "ras"})
    assert blocked["status"] == "not_computed"
    assert evidence.execution_status == "not_run"

    empty = _plan(definition, (), status="needs_input")
    refused_plan, evidence = published(plan=empty)
    assert refused_plan["status"] == "needs_input"
    assert evidence.execution_status == "not_run"

    partial = _plan(definition, ("net_debt",))
    unplanned, evidence = published(plan=partial)
    assert unplanned["status"] == "missing_input"
    assert evidence.execution_status == "not_run"

    missing, evidence = published(bindings=[_bind("net_debt")])
    assert missing["status"] == "missing_input"
    assert evidence.execution_status == "not_run"

    scaled = [
        _fact("net_debt", "300", cell="Debt!N", scale="1000"),
        _fact("ebitda", "100", cell="PL!E"),
    ]
    scale, evidence = published(
        facts=scaled,
        bindings=[_bind("net_debt"), _bind("ebitda")],
    )
    assert scale["status"] == "scale_unconfirmed"
    assert evidence.execution_status == "refused"

    period_definition = _definition(metric, (("net_debt",), ()), (("ebitda",), ()), "period")
    mismatched = [
        {**_bind("net_debt"), "evidence": {"period_basis": "ytd", "period_basis_source": "label"}},
        _bind("ebitda"),
    ]
    collected: list = []
    basis = composed_ratio(
        metric,
        _formula((("net_debt",), ()), (("ebitda",), ()), "period"),
        facts=[_fact("net_debt", "300"), _fact("ebitda", "100")],
        bindings=mismatched,
        periods=[_year()],
        aggregations=_AGGREGATIONS,
        definition=period_definition,
        collect=collected,
    )
    evidence = collected[0]
    assert basis["status"] == "basis_mismatch"
    assert evidence.execution_status == "refused"
    assert evidence.definition_version == f"{metric}@2"
    assert evidence.evidence_status != "evidence_available"


def test_composed_stamp_changes_when_a_declared_dependency_changes():
    import hashlib
    import inspect

    from finance_analysis.domain.calculation_evidence import (
        composed_calculation_sources,
        composed_calculation_stamp,
        declared_calculation_dependencies,
        declared_composed_dependencies,
    )
    from tests.unit.test_calculation_outcome import EXCLUDED, _project_calls

    declared = {name for name, _obj in declared_composed_dependencies()}
    for required in ("composed_ratio", "_fold_side", "_term_fold", "_stock_choice", "_span", "_part"):
        assert required in declared
    base = composed_calculation_stamp()
    changed = [
        (name, source + "\n" if name == "_fold_side" else source)
        for name, source in composed_calculation_sources()
    ]
    text = "\n".join(f"{name}\n{source}" for name, source in changed)
    assert hashlib.sha256(text.encode("utf-8")).hexdigest()[:16] != base
    covered = declared | {name for name, _obj in declared_calculation_dependencies()}
    calls = set()
    for name, obj in declared_composed_dependencies():
        if inspect.isfunction(obj):
            calls |= _project_calls(obj)
    assert calls - covered - EXCLUDED - _COMPOSED_STAMP_EXCLUDED == set()


async def test_compute_metrics_does_not_treat_an_incomplete_trace_as_support():
    """Отказ без операндов не заменяет ``evidence_not_supported``."""

    got = await _metrics(
        ["net_debt_ebitda"],
        facts=[
            _fact("net_debt", "300", cell="Debt!N", scale="1000"),
            _fact("ebitda", "100", cell="PL!E"),
        ],
        bindings=[_bind("net_debt"), _bind("ebitda")],
        periods=[_year()],
    )
    statuses = {item.evidence_status for item in got["evidences"]}
    assert "evidence_not_supported" in statuses
    assert "evidence_available" not in statuses
    refused = [item for item in got["evidences"] if item.execution_status == "refused"]
    assert refused
    assert refused[0].evidence_status == "evidence_unavailable"


async def test_compute_metrics_keeps_the_catalog_composition_beside_a_dscr_profile():
    """``dscr_definition`` не становится формулой net_debt_ebitda."""

    from finance_analysis.application.analyses import _composed_definitions
    from finance_analysis.application.financial_catalog import load_financial_catalog
    from finance_analysis.application.model_types import load_model_types

    got = await _metrics(
        ["net_debt_ebitda"],
        facts=[_fact("net_debt", "300", cell="Debt!N"), _fact("ebitda", "100", cell="PL!E")],
        bindings=[_bind("net_debt"), _bind("ebitda")],
        periods=[_year()],
        profile={
            "dscr_definition": {
                "numerator": {"plus": ["net_debt"], "minus": ["cash"]},
                "denominator": {"plus": ["ebitda"]},
                "window": "LTM",
            }
        },
    )
    row = next(item for item in got["rows"] if item["metric"] == "net_debt_ebitda")
    assert row["value"] == Decimal("3.0000000000")
    catalog = _composed_definitions(load_model_types(), load_financial_catalog())["net_debt_ebitda"]
    assert got["plans"]["net_debt_ebitda"].definition_hash == catalog.definition_hash
    entry = next(item for item in got["applicability"] if item["metric"] == "net_debt_ebitda")
    assert "definition_source" not in entry
    evidence = next(item for item in got["evidences"] if item.evidence_status == "evidence_available")
    assert evidence.executor_id == _EXECUTOR_ID
    assert {item.cell_id for item in evidence.fact_uses} == {"Debt!N", "PL!E"}


async def _metrics(metrics, *, facts, bindings, periods, profile=None):
    import finance_analysis.application.analyses as analyses_mod
    from finance_analysis.application.analyses import Analyses, Target
    from finance_analysis.application.catalog import load_catalog
    from finance_analysis.application.model_types import load_model_types
    from finance_analysis.domain.book import Head
    from finance_analysis.domain.errors import NotFound
    from finance_analysis.domain.model_type import Effective

    types = load_model_types()
    original = analyses_mod.applicability

    def allow(model_catalog, labels, metric):
        if metric in metrics:
            return "required"
        return original(model_catalog, labels, metric)

    analyses_mod.applicability = allow

    class _Guard:
        async def read_all(self, _job_id):
            return []

    class _Glossary:
        async def profile_body(self, _profile_id):
            return profile or {}

    class _Service:
        async def _dataset_rows(self, _job_id, _head, dataset):
            if dataset == "bindings":
                return bindings
            if dataset == "fact_observation":
                return facts
            if dataset == "dim_period":
                return periods
            if dataset in {"dim_row", "period_semantics", "graph_links"}:
                return []
            raise NotFound(dataset)

        async def resolve_model_type(self, _job_id, _head):
            return Effective(
                ("corporate",),
                "corporate",
                "confirmed",
                None,
                1,
                None,
                1.0,
                {"corporate": 1.0},
                (),
            )

    try:
        head = Head(
            build_key="build",
            state_seq=1,
            derive_key="derive",
            versions={"profile": "book@3"} if profile else {},
        )
        service = _Service()
        service.model_types = types
        service.catalog = load_catalog()
        service.financial_catalog = None
        service.guard = _Guard()
        service.glossary = _Glossary()
        return await Analyses(service).compute_metrics("job", Target(head=head, build="build", manifest={}, fresh=True), metrics)
    finally:
        analyses_mod.applicability = original


_COMPOSED_STAMP_EXCLUDED = frozenset(
    {
        "Composed",
        "Side",
        "UndeclaredInput",
        "_cite",
        "_cite_used",
        "_composed_stop",
        "_escrow_coverage_book",
        "_line",
        "_mark_profile",
        "_missing",
        "_open_trace",
        "_operand_refs",
        "_publish_composed",
        "_record_period",
        "_refused",
        "_remember_composed",
        "_same_end",
        "_stock_message",
        "_trace_ready",
        "_unplanned",
        "bound_rows",
        "composed_calculation_stamp",
    }
)


def _quarters() -> list[dict]:
    periods = []
    for index, end in ((1, date(2024, 3, 31)), (2, date(2024, 6, 30)), (3, date(2024, 9, 30)), (4, date(2024, 12, 31))):
        start_month = (index - 1) * 3 + 1
        periods.append(
            {
                "axis_id": "a",
                "period_id": f"Q{index}",
                "period_index": index,
                "grain": "quarter",
                "timeline_id": "t",
                "period_start": date(2024, start_month, 1),
                "period_end": end,
            }
        )
    return periods


def _plan(definition, names: tuple[str, ...], *, status: str = "resolved"):
    inputs = tuple(
        ResolvedInput(name, "all_of", "formula", name, name, None, False, True) for name in names
    )
    return seal(
        metric_id=definition.metric_id,
        variant=None,
        variant_source="formula",
        catalog_version=None,
        semantic_model_version=None,
        build_key=None,
        model_id=None,
        status=status,
        inputs=inputs,
        diagnostic=(),
        rejected=(),
        fallbacks=(),
        warnings=(),
        needs_input=(),
        shield=None,
        definition_hash=definition.definition_hash,
    )
