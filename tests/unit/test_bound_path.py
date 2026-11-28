"""Characterization связанного пути. Продакшен не меняется.

Слоты и план синтетические. Книги Packt и RVI сюда не входят.
Связанный путь использует план: https://www.w3.org/TR/prov-dm/#term-Usage
"""

from decimal import Decimal

from finance_analysis.domain.calculation_evidence import CalculationOutcome
from finance_analysis.domain.execution_contract import (
    CatalogMetricRecord,
    ExecutionContractError,
    MetricExecutionContext,
    compile_definition,
    execute_bound,
)
from finance_analysis.domain.metric_dispatch import CalculationRequest, run_calculation
from finance_analysis.domain.model_type import MetricExpression
from finance_analysis.domain.resolved_plan import ResolvedInput, seal

_EIGHT = Decimal("8.0000000000")
_TWO = Decimal("2.0000000000")
_BOUND_REASONS = frozenset(
    {
        "metric_mismatch",
        "variant_mismatch",
        "definition_mismatch",
        "semantic_mismatch",
        "plan_not_resolved",
        "undeclared_input",
    }
)


def _expr(**kwargs) -> MetricExpression:
    return MetricExpression(**kwargs)


def _definition(metric: str, expression: MetricExpression, *, executor_key: str, **kwargs):
    semantic_model_version = kwargs.pop("semantic_model_version", None)
    return compile_definition(
        CatalogMetricRecord(
            metric_id=metric,
            expression=expression,
            executor_key=executor_key,
            executor_id=kwargs.pop("executor_id", executor_key),
            executor_version=kwargs.pop("executor_version", f"{executor_key}@1"),
            **kwargs,
        ),
        semantic_model_version=semantic_model_version,
    )


def _coverage(metric: str, expression: MetricExpression, **kwargs):
    return _definition(
        metric,
        expression,
        executor_key="coverage",
        executor_id="calculate_coverage",
        executor_version="calculate_coverage@1",
        **kwargs,
    )


def _bind(concept: str, row: str) -> dict:
    return {
        "effective_concept": concept,
        "row_key": row,
        "binding_key": row,
        "is_primary": True,
        "status": "bound",
        "source": "inferred",
    }


def _fact(row: str, value: str, period: str = "Y1") -> dict:
    return {"row_key": row, "axis_id": "a", "period_id": period, "normalized_value": value}


def _periods(*indexes: int) -> list[dict]:
    return [
        {
            "axis_id": "a",
            "period_id": f"Y{index}",
            "period_index": index,
            "grain": "year",
            "timeline_id": "t",
        }
        for index in indexes
    ]


def _request(metric: str, facts, bindings, **kwargs) -> CalculationRequest:
    concepts = frozenset({"cfads", "ebitda", "ebit", "debt_service", "interest", "principal"})
    return CalculationRequest(
        metric=metric,
        common={
            "facts": facts,
            "bindings": bindings,
            "periods": kwargs.pop("periods", _periods(1)),
            "period_phase": {},
            "explicit_phases": False,
            "sign_convention": "outflow_negative",
            "marker_class": None,
            "absent": frozenset(),
        },
        composed={},
        concepts=concepts,
        money=concepts,
        **kwargs,
    )


def _context(definition=None, plan=None) -> MetricExecutionContext:
    return MetricExecutionContext(definition=definition, plan=plan)


def _plan(definition, concepts: tuple[str, ...], **kwargs):
    from finance_analysis.domain.semantic_input import resolve_metric_plan

    if kwargs.get("inputs") is None and kwargs.get("status", "resolved") == "resolved" and not kwargs.get("manual"):
        bindings = [_bind(name, name) for name in concepts]
        return resolve_metric_plan(
            definition.metric_id,
            bindings,
            None,
            variant=definition.variant,
            definition=definition,
            semantic_model_version=kwargs.get("semantic_model_version"),
        )
    return seal(
        metric_id=kwargs.get("metric_id", definition.metric_id),
        variant=definition.variant,
        variant_source=definition.variant_source,
        catalog_version=None,
        semantic_model_version=kwargs.get("semantic_model_version"),
        build_key=None,
        model_id=None,
        status=kwargs.get("status", "resolved"),
        inputs=kwargs.get(
            "inputs",
            tuple(ResolvedInput(name, "all_of", "formula", name, name) for name in concepts),
        ),
        diagnostic=(),
        rejected=(),
        fallbacks=(),
        warnings=(),
        needs_input=(),
        shield=None,
        definition_hash=definition.definition_hash,
    )


def test_bound_dscr_uses_plan_slots(monkeypatch):
    """DSCR читает слот плана. Вторая строка CFADS с меньшим ключом частное не сдвигает.

    https://www.w3.org/TR/prov-dm/#term-Plan
    """

    from finance_analysis.domain.semantic_input import resolve_metric_plan

    def boom(*_args, **_kwargs):
        raise AssertionError("_plan_rows")

    monkeypatch.setattr("finance_analysis.domain.metrics._plan_rows", boom)
    definition = _coverage("dscr", _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)))
    confirmed = _bind("cfads", "z-confirmed")
    decoy = _bind("cfads", "a-decoy")
    debt = _bind("debt_service", "debt")
    plan = resolve_metric_plan("dscr", [confirmed, debt], None, definition=definition)
    facts = [_fact("z-confirmed", "80"), _fact("a-decoy", "8"), _fact("debt", "-10")]
    outcome = run_calculation(
        "select_ratio",
        _request("dscr", facts, [decoy, confirmed, debt]),
        _context(definition, plan),
    )
    assert plan.status == "resolved"
    assert outcome.result["rows"][0]["value"] == _EIGHT
    assert outcome.result["rows"][0]["value"] != Decimal("0.8000000000")


def test_bound_icr_keeps_selected_one_of(monkeypatch):
    """Выбран EBIT, хотя EBITDA есть и choose_one_of взял бы её. Один DSCR этого не показывает.

    https://www.w3.org/TR/prov-dm/#term-Plan
    """

    def boom(*_args, **_kwargs):
        raise AssertionError("choose_one_of")

    monkeypatch.setattr("finance_analysis.domain.metrics.choose_one_of", boom)
    definition = _coverage(
        "icr",
        _expr(
            one_of=frozenset({"ebitda", "ebit"}),
            one_of_order=("ebitda", "ebit"),
            denominator_plus=("interest",),
        ),
    )
    plan = _plan(
        definition,
        (),
        manual=True,
        inputs=(
            ResolvedInput("ebit", "one_of", "formula", "ebit", "ebit"),
            ResolvedInput("interest", "all_of", "formula", "interest", "interest"),
        ),
    )
    facts = [_fact("ebitda", "80"), _fact("ebit", "20"), _fact("interest", "-10")]
    bindings = [_bind("ebitda", "ebitda"), _bind("ebit", "ebit"), _bind("interest", "interest")]
    outcome = run_calculation(
        "select_ratio",
        _request("icr", facts, bindings),
        _context(definition, plan),
    )
    assert outcome.result["rows"][0]["value"] == _TWO
    assert outcome.result["rows"][0]["value"] != _EIGHT


def test_bound_calculation_does_not_promote_missing_to_zero():
    """Период без числителя пропускается. Пропуск не становится нулём и не даёт частное 0."""

    from finance_analysis.domain.semantic_input import resolve_metric_plan

    definition = _coverage("dscr", _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)))
    bindings = [_bind("cfads", "cfads"), _bind("debt_service", "debt")]
    plan = resolve_metric_plan("dscr", bindings, None, definition=definition)
    facts = [
        _fact("cfads", "80", "Y1"),
        _fact("debt", "-10", "Y1"),
        _fact("debt", "-10", "Y2"),
    ]
    periods = _periods(1, 2)
    outcome = run_calculation(
        "select_ratio",
        _request("dscr", facts, bindings, periods=periods),
        _context(definition, plan),
    )
    rows = outcome.result["rows"]
    assert [row["period_id"] for row in rows] == ["Y1"]
    assert rows[0]["value"] == _EIGHT
    assert all(row["value"] != 0 and row["value"] != Decimal(0) for row in rows)
    assert "Y2" not in {row["period_id"] for row in rows}


def test_bound_calculation_rejects_foreign_semantic_version():
    """Чужая SMV — semantic_mismatch до исполнителя. Тот же хеш формулы отказом не является.

    https://www.w3.org/TR/skos-reference/#concepts
    """

    definition = _coverage(
        "dscr",
        _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)),
        semantic_model_version="smv-current",
    )
    same = _plan(definition, ("cfads", "debt_service"), manual=True, semantic_model_version="smv-current")
    foreign = _plan(definition, ("cfads", "debt_service"), manual=True, semantic_model_version="smv-foreign")
    assert definition.definition_hash == same.definition_hash
    assert foreign.definition_hash == definition.definition_hash

    class _Idle:
        def execute(self, _context):
            raise AssertionError("executor")

    try:
        execute_bound(_Idle(), definition, foreign)
    except ExecutionContractError as exc:
        assert exc.reason == "semantic_mismatch"
    else:
        raise AssertionError("foreign semantic version must be refused")

    class _Ran:
        def __init__(self) -> None:
            self.called = False

        def execute(self, _context) -> CalculationOutcome:
            self.called = True
            return CalculationOutcome(result={"metric": "dscr", "rows": []}, evidence=None)

    ran = _Ran()
    assert execute_bound(ran, definition, same).result["rows"] == []
    assert ran.called
    outcome = run_calculation(
        "select_ratio",
        _request("dscr", [], []),
        _context(definition, foreign),
    )
    assert outcome.result["status"] == "not_computed"
    assert outcome.result["reason"] == "semantic_mismatch"
    assert outcome.result["rows"] == []
    assert outcome.evidence is None


def test_unbound_legacy_path_is_explicit(monkeypatch):
    """Плана нет, он не resolved или определения нет — прежний калькулятор.

    Тот же обход у ADSCR, dscr_min и dscr_avg, когда план — план DSCR.
    Чужой план не становится использованием этого определения:
    https://www.w3.org/TR/prov-dm/#term-Usage
    """

    from finance_analysis.domain import metric_dispatch
    from finance_analysis.domain.cover_metrics import adscr, dscr_reductions

    seen: list[str] = []
    real_bound = metric_dispatch.execute_bound

    def execute_bound_spy(executor, definition, plan, **kwargs):
        seen.append("bound")
        return real_bound(executor, definition, plan, **kwargs)

    monkeypatch.setattr(metric_dispatch, "execute_bound", execute_bound_spy)
    dscr = _coverage("dscr", _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)))
    legacy_facts = [_fact("cfads", "80"), _fact("debt_service", "-10")]
    legacy_bindings = [_bind("cfads", "cfads"), _bind("debt_service", "debt_service")]
    resolved = _plan(dscr, ("cfads", "debt_service"))

    missing_plan = run_calculation("select_ratio", _request("dscr", [], []), _context(dscr, None))
    assert missing_plan.result["status"] == "missing_input"
    assert missing_plan.result.get("reason") not in _BOUND_REASONS

    unresolved = _plan(dscr, ("cfads", "debt_service"), manual=True, status="needs_input")
    held = run_calculation("select_ratio", _request("dscr", [], []), _context(dscr, unresolved))
    assert held.result["status"] == "needs_input"
    assert held.result.get("reason") != "plan_not_resolved"

    open_definition = run_calculation(
        "select_ratio",
        _request("dscr", legacy_facts, legacy_bindings),
        _context(None, resolved),
    )
    assert open_definition.result["rows"][0]["value"] == _EIGHT
    assert open_definition.result.get("reason") not in _BOUND_REASONS

    assert seen == []
    for metric in ("adscr", "dscr_min", "dscr_avg"):
        route = "adscr" if metric == "adscr" else "reduced"
        derived = _definition(
            metric,
            _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)),
            executor_key=route,
        )
        common = {
            "facts": [],
            "bindings": [],
            "periods": _periods(1),
            "period_phase": {},
            "explicit_phases": False,
            "sign_convention": "outflow_negative",
            "marker_class": None,
            "absent": frozenset(),
        }
        if metric == "adscr":
            direct = adscr(direction="lookback", plan=resolved, collect=None, **common)
            request = CalculationRequest(metric=metric, direction="lookback", common=common)
        else:
            direct = dscr_reductions(metric, plan=resolved, collect=None, **common)
            request = CalculationRequest(metric=metric, common=common)
        outcome = run_calculation(route, request, _context(derived, resolved))
        assert outcome.result == direct
        assert outcome.result.get("reason") != "metric_mismatch"
    assert seen == []
