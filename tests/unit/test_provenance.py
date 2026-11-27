"""Провенанс лежит на улике. Публичная строка коэффициента его не получает.

Версия определения и версия исполнителя — разные поля. Одно не подставляется вместо другого.
Родитель ADSCR — улика DSCR. У min и avg улика DSCR в parent_evidence_ids, периоды — в parent_period_ids.
https://www.w3.org/TR/prov-dm/#term-Communication
https://openlineage.io/docs/spec/facets/run-facets/parent_run/
"""

from decimal import Decimal

from finance_analysis.application.model_types import load_model_types
from finance_analysis.domain.calculation_evidence import (
    BasisSide,
    CalculationEvidence,
    EvidenceBook,
    FactObservation,
    FactUse,
    PeriodResult,
)
from finance_analysis.domain.covenant import select_ratio
from finance_analysis.domain.cover_metrics import adscr, dscr_reductions
from finance_analysis.domain.execution_contract import (
    CatalogMetricRecord,
    MetricExecutionContext,
    compile_definition,
)
from finance_analysis.domain.metrics import calculate_coverage
from finance_analysis.domain.model_type import MetricExpression
from finance_analysis.domain.semantic_input import resolve_metric_plan
from finance_analysis.domain.trace_limit import view_from_evidence
from tests.unit.test_cover_provenance import _common, _quarters

_ROW_FIELDS = (
    "definition_version",
    "definition_source",
    "definition_ref",
    "definition_hash",
    "executor_id",
    "executor_version",
    "branch_id",
    "actual_inputs",
    "actual_fact_uses",
    "actual_periods",
    "actual_period_slots",
    "profile_values",
    "parent_evidence_ids",
    "parent_period_ids",
    "calculation_origin",
    "evidence_id",
    "plan_content_sha256",
)


def _expr(**kwargs) -> MetricExpression:
    return MetricExpression(**kwargs)


def _definition(expression: MetricExpression, **kwargs) -> object:
    return compile_definition(
        CatalogMetricRecord(
            metric_id="dscr",
            expression=expression,
            executor_key="coverage",
            executor_id="calculate_coverage",
            executor_version="calculate_coverage@1",
            **kwargs,
        )
    )


def _plan(definition, bindings):
    expression = definition.normalized_expression
    return resolve_metric_plan(
        "dscr",
        bindings,
        {
            "dscr": _expr(
                numerator_plus=expression.numerator_plus,
                denominator_plus=expression.denominator_plus,
            )
        },
        definition=definition,
    )


def _bindings():
    return [
        {
            "effective_concept": "cfads",
            "row_key": "c",
            "binding_key": "c",
            "is_primary": True,
            "status": "bound",
            "source": "inferred",
        },
        {
            "effective_concept": "debt_service",
            "row_key": "d",
            "binding_key": "d",
            "is_primary": True,
            "status": "bound",
            "source": "inferred",
        },
    ]


def _facts():
    return [
        {"row_key": "c", "axis_id": "a", "period_id": "Y1", "normalized_value": "80"},
        {"row_key": "d", "axis_id": "a", "period_id": "Y1", "normalized_value": "-10"},
    ]


def _run(definition):
    from finance_analysis.domain.metric_dispatch import (
        CalculationRequest,
        run_calculation,
    )

    bindings = _bindings()
    plan = _plan(definition, bindings)
    collect: list = []
    outcome = run_calculation(
        "select_ratio",
        CalculationRequest(
            metric="dscr",
            common={
                "facts": _facts(),
                "bindings": bindings,
                "periods": [{"axis_id": "a", "period_id": "Y1", "period_index": 1, "grain": "year", "timeline_id": "t"}],
                "period_phase": {},
                "explicit_phases": False,
                "sign_convention": "outflow_negative",
                "marker_class": None,
                "absent": frozenset(),
            },
            definition=definition,
            composed={},
            concepts=frozenset({"cfads", "debt_service"}),
            money=frozenset({"cfads", "debt_service"}),
            collect=collect,
        ),
        MetricExecutionContext(definition=definition, plan=plan, calculation_origin="calculated"),
    )
    return outcome.result, collect[0], plan


def _row_is_public(row: dict) -> None:
    for name in _ROW_FIELDS:
        assert name not in row


def test_coverage_evidence_keeps_definition_and_executor_apart():
    definition = _definition(
        _expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)),
        definition_version="dscr@1",
        formula_id="dscr",
    )
    result, evidence, plan = _run(definition)
    assert result["rows"][0]["value"] == Decimal("8.0000000000")
    assert evidence.definition_version == "dscr@1"
    assert evidence.executor_id == "calculate_coverage"
    assert evidence.executor_version == "calculate_coverage@1"
    assert evidence.definition_version != evidence.executor_version
    assert evidence.definition_source == "catalog"
    assert evidence.definition_ref is None
    assert evidence.definition_hash == definition.definition_hash
    assert evidence.plan_content_sha256 == plan.content_sha256
    assert evidence.calculation_origin == "calculated"
    assert evidence.evidence_id
    for row in result["rows"]:
        _row_is_public(row)
    view = view_from_evidence(evidence)
    assert view["definition_version"] == "dscr@1"
    assert view["executor_version"] == "calculate_coverage@1"
    assert view["definition_hash"] == definition.definition_hash
    assert view["calculation_origin"] == "calculated"


def _identity_book(sign_convention: str = "outflow_negative", marker_class: str | None = None) -> EvidenceBook:
    return EvidenceBook(
        metric="dscr",
        sign_convention=sign_convention,
        marker_class=marker_class,
        explicit_phases=False,
        plan_content_sha256="same-plan",
    )


def _one_fact() -> FactUse:
    return FactUse(
        concept="cfads",
        cell_id="c!Y1",
        axis_id="a",
        period_id="Y1",
        timeline_id=None,
        period_index=1,
        field="value",
        sheet=False,
        raw_value=Decimal(80),
        effective_value=Decimal(80),
        scale_factor=None,
        scale_policy="plain",
        scale_applied=False,
        normalization_source="none",
        result_axis_id="a",
        result_period_id="Y1",
        operand="numerator",
    )


def test_same_plan_hash_with_a_different_definition_hash_does_not_share_an_evidence_id():
    """SHA-256 канонического тела, FIPS 180-4. Версия исполнителя не заполняет версию определения.

    https://csrc.nist.gov/publications/detail/fips/180/4/final
    """

    left = _identity_book().freeze(
        "succeeded",
        "dscr@1",
        definition_hash="def-a",
        definition_version="dscr@1",
        executor_id="calculate_coverage",
        executor_version="calculate_coverage@1",
        stamp="stamp",
    )
    right = _identity_book().freeze(
        "succeeded",
        "dscr@1",
        definition_hash="def-b",
        definition_version="dscr@1",
        executor_id="calculate_coverage",
        executor_version="calculate_coverage@1",
        stamp="stamp",
    )
    assert left.plan_content_sha256 == right.plan_content_sha256 == "same-plan"
    assert left.evidence_id != right.evidence_id
    assert left.definition_version == "dscr@1"
    assert left.executor_version == "calculate_coverage@1"
    assert left.definition_version != left.executor_version


def test_same_plan_hash_with_a_different_sign_convention_does_not_share_an_evidence_id():
    left = _identity_book("outflow_negative").freeze("succeeded", "dscr@1", stamp="stamp")
    right = _identity_book("outflow_positive").freeze("succeeded", "dscr@1", stamp="stamp")
    assert left.plan_content_sha256 == right.plan_content_sha256
    assert left.evidence_id != right.evidence_id


def test_stamp_marker_and_facts_change_the_evidence_id():
    plain = _identity_book().freeze("succeeded", "dscr@1", stamp="stamp-a")
    other_stamp = _identity_book().freeze("succeeded", "dscr@1", stamp="stamp-b")
    marked = _identity_book(marker_class="housing").freeze("succeeded", "dscr@1", stamp="stamp-a")
    used = _identity_book()
    used.fact_uses.append(_one_fact())
    with_fact = used.freeze("succeeded", "dscr@1", stamp="stamp-a")
    assert len({plain.evidence_id, other_stamp.evidence_id, marked.evidence_id, with_fact.evidence_id}) == 4


def _use(**overrides) -> FactUse:
    fields = {
        "concept": "cfads",
        "cell_id": "c!Y1",
        "axis_id": "a",
        "period_id": "Y1",
        "timeline_id": None,
        "period_index": 1,
        "field": "value",
        "sheet": False,
        "raw_value": Decimal(8),
        "effective_value": Decimal(80),
        "scale_factor": Decimal(10),
        "scale_policy": "thousands",
        "scale_applied": True,
        "normalization_source": "sheet",
        "result_axis_id": "a",
        "result_period_id": "Y1",
        "operand": "numerator",
    }
    fields.update(overrides)
    return FactUse(**fields)


def _observation(**overrides) -> FactObservation:
    used = _use(**overrides)
    return FactObservation(
        concept=used.concept,
        cell_id=used.cell_id,
        axis_id=used.axis_id,
        period_id=used.period_id,
        timeline_id=used.timeline_id,
        period_index=used.period_index,
        field=used.field,
        sheet=used.sheet,
        raw_value=used.raw_value,
        effective_value=used.effective_value,
        scale_factor=used.scale_factor,
        scale_policy=used.scale_policy,
        scale_applied=used.scale_applied,
        normalization_source=used.normalization_source,
    )


def _freeze_book(*, uses=(), observations=(), periods=()):
    book = _identity_book()
    book.fact_uses = list(uses)
    book.observations = list(observations)
    book.periods = list(periods)
    return book.freeze(
        "succeeded",
        "dscr@1",
        stamp="stamp",
        executor_id="calculate_coverage",
        executor_version="calculate_coverage@1",
    )


def test_same_cell_and_effective_value_with_a_different_raw_or_scale_does_not_share_an_evidence_id():
    """Сырое число и путь нормализации входят в идентификатор. Эффективное число одно.

    https://csrc.nist.gov/publications/detail/fips/180/4/final
    """

    other_raw = {"raw_value": Decimal(80)}
    other_scale = {
        "scale_factor": Decimal(1000),
        "scale_policy": "millions",
        "scale_applied": False,
        "normalization_source": "header",
    }
    pairs = (
        (_use(), _use(**other_raw)),
        (_use(), _use(**other_scale)),
        (_observation(), _observation(**other_raw)),
        (_observation(), _observation(**other_scale)),
    )
    for left_fact, right_fact in pairs:
        assert left_fact.cell_id == right_fact.cell_id
        assert left_fact.effective_value == right_fact.effective_value
        if isinstance(left_fact, FactUse):
            left = _freeze_book(uses=(left_fact,))
            right = _freeze_book(uses=(right_fact,))
        else:
            left = _freeze_book(observations=(left_fact,))
            right = _freeze_book(observations=(right_fact,))
        assert left.evidence_id != right.evidence_id
        assert left.definition_version is None
        assert left.executor_version == "calculate_coverage@1"


def _missing_period(**overrides) -> PeriodResult:
    fields = {
        "axis_id": "a",
        "period_id": "Y1",
        "status": "missing_input",
        "reason": "concept_unknown",
        "value": None,
        "numerator": None,
        "denominator": None,
        "steps": (),
        "window_periods": (),
        "window_missing": (),
        "missing_concepts": (("Y1", ("cfads",)),),
    }
    fields.update(overrides)
    return PeriodResult(**fields)


def test_missing_periods_with_a_different_reason_or_gap_do_not_share_an_evidence_id():
    """Причина отказа и окно, которого нет в шагах, входят в идентификатор периода.

    https://csrc.nist.gov/publications/detail/fips/180/4/final
    """

    base = _missing_period()
    variants = (
        _missing_period(reason="input_absent"),
        _missing_period(missing_concepts=(("Y1", ("debt_service",)),)),
        _missing_period(window_periods=("Y0",), window_missing=("Y2",)),
    )
    left = _freeze_book(periods=(base,))
    assert left.definition_version is None
    assert left.executor_version == "calculate_coverage@1"
    for period in variants:
        assert period.axis_id == base.axis_id
        assert period.period_id == base.period_id
        assert period.status == "missing_input"
        assert period.steps == ()
        right = _freeze_book(periods=(period,))
        assert left.evidence_id != right.evidence_id


def test_unset_definition_version_is_not_replaced_by_the_executor():
    definition = _definition(_expr(numerator_plus=("cfads",), denominator_plus=("debt_service",)))
    _result, evidence, _plan = _run(definition)
    assert evidence.definition_version is None
    assert evidence.executor_version == "calculate_coverage@1"
    assert evidence.executor_id == "calculate_coverage"
    assert view_from_evidence(evidence).get("definition_version") is None


def test_adscr_points_at_the_dscr_evidence_and_keeps_the_branch_trace():
    periods, facts = _quarters()
    common = _common(periods, facts)
    source = calculate_coverage(metric="dscr", evidence=True, **common).evidence
    assert isinstance(source, CalculationEvidence)
    collected: list = []
    traced = adscr(direction="lookback", collect=collected, **common)
    evidence = next(item for item in collected if item.metric == "adscr")
    assert evidence.parent_evidence_ids == (source.evidence_id,)
    assert evidence.evidence_id != source.evidence_id
    assert evidence.definition_version is None
    assert evidence.executor_id == "adscr"
    assert evidence.executor_version == "adscr@1"
    assert evidence.executor_version != evidence.definition_version
    assert evidence.branch_id == "adscr"
    assert ("adscr_direction", "lookback") in evidence.profile_values
    assert "cfads" in evidence.actual_inputs
    assert "debt_service" in evidence.actual_inputs
    assert evidence.actual_periods
    assert evidence.actual_period_slots
    assert evidence.plan_content_sha256 == source.plan_content_sha256
    assert evidence.calculation_origin == "calculated"
    for row in traced["rows"]:
        _row_is_public(row)


def test_reductions_point_at_the_periods_and_the_dscr_evidence():
    periods, facts = _quarters()
    common = _common(periods, facts)
    source = calculate_coverage(metric="dscr", evidence=True, **common).evidence
    period_ids = tuple(
        item.node_id or f"period:{item.axis_id}:{item.period_id}"
        for item in source.period_results
        if item.status == "computed" and item.period_id
    )
    assert period_ids
    for metric in ("dscr_min", "dscr_avg"):
        collected: list = []
        traced = dscr_reductions(metric, collect=collected, **common)
        evidence = next(item for item in collected if item.metric == metric)
        assert evidence.parent_period_ids == period_ids
        assert evidence.parent_evidence_ids == (source.evidence_id,)
        assert all(item == source.evidence_id for item in evidence.parent_evidence_ids)
        view = view_from_evidence(evidence)
        assert view["parent_period_ids"] == list(period_ids)
        assert view["parent_evidence_ids"] == [source.evidence_id]
        assert evidence.branch_id == metric
        assert evidence.executor_id == metric
        assert evidence.executor_version == f"{metric}@1"
        assert evidence.definition_version is None
        assert evidence.calculation_origin == "calculated"
        for row in traced["rows"]:
            _row_is_public(row)


def test_two_adscr_directions_do_not_share_an_evidence_id():
    """Окно и направление входят в идентификатор уже собранной улики.

    https://csrc.nist.gov/publications/detail/fips/180/4/final
    """

    periods, facts = _quarters()
    common = _common(periods, facts)
    found = {}
    for direction in ("lookback", "lookforward"):
        collected: list = []
        adscr(direction=direction, collect=collected, **common)
        evidence = next(item for item in collected if item.metric == "adscr")
        assert ("adscr_direction", direction) in evidence.profile_values
        found[direction] = evidence
    assert found["lookback"].evidence_id != found["lookforward"].evidence_id
    assert found["lookback"].definition_version is None
    assert found["lookback"].executor_version == "adscr@1"


def test_a_second_adscr_call_does_not_rewrite_the_first_evidence():
    """След пишется только на улики этого вызова. Предыдущее направление остаётся."""

    periods, facts = _quarters()
    common = _common(periods, facts)
    collected: list = []
    first = adscr(direction="lookback", collect=collected, **common)
    kept = tuple(collected)
    second = adscr(direction="lookforward", collect=collected, **common)
    assert collected[: len(kept)] == list(kept)
    for old, current in zip(kept, collected[: len(kept)], strict=True):
        assert current is old
    lookback = next(item for item in kept if item.metric == "adscr")
    lookforward = next(item for item in collected[len(kept) :] if item.metric == "adscr")
    assert ("adscr_direction", "lookback") in lookback.profile_values
    assert ("adscr_direction", "lookforward") in lookforward.profile_values
    assert lookback.evidence_id != lookforward.evidence_id
    assert lookback.definition_version is None
    assert lookback.executor_version == "adscr@1"
    for row in (*first["rows"], *second["rows"]):
        _row_is_public(row)


def test_basis_source_changes_the_evidence_id():
    """Источник способа показа входит в идентификатор. Факты и результат те же.

    https://csrc.nist.gov/publications/detail/fips/180/4/final
    """

    def frozen(source: str):
        book = _identity_book()
        book.fact_uses = [_one_fact()]
        book.basis_sides = [BasisSide("cfads", "period_end", source)]
        return book.freeze(
            "succeeded",
            "dscr@1",
            stamp="stamp",
            executor_id="calculate_coverage",
            executor_version="calculate_coverage@1",
        )

    header = frozen("header")
    formula = frozen("formula")
    assert header.basis_sides[0].concept == formula.basis_sides[0].concept
    assert header.basis_sides[0].period_basis == formula.basis_sides[0].period_basis
    assert header.fact_uses == formula.fact_uses
    assert header.period_results == formula.period_results
    assert header.evidence_id != formula.evidence_id
    assert header.definition_version is None
    assert header.executor_version == "calculate_coverage@1"
    assert header.executor_version != header.definition_version


def test_every_parent_evidence_id_is_in_the_same_collection():
    periods, facts = _quarters()
    common = _common(periods, facts)
    runs = [
        lambda collect: adscr(direction="lookback", collect=collect, **common),
        lambda collect: dscr_reductions("dscr_min", collect=collect, **common),
        lambda collect: dscr_reductions("dscr_avg", collect=collect, **common),
    ]
    for run in runs:
        collected: list = []
        traced = run(collected)
        by_id = {item.evidence_id for item in collected}
        parents = [parent for item in collected for parent in item.parent_evidence_ids]
        assert parents
        assert set(parents) <= by_id
        for row in traced["rows"]:
            _row_is_public(row)


def _published_read(value: str, cell_id: str):
    class _Need:
        subject = "cash_taxes"
        reason = "concept_unknown"

        def as_dict(self):
            return {"kind": "concept", "reason": self.reason, "subject": self.subject}

    class _Plan:
        status = "missing_input"
        content_sha256 = "plan-digest-corporate"
        needs_input = (_Need(),)
        warnings = ()
        inputs = ()
        diagnostic = ()
        rejected = ()
        fallbacks = ()

    types = load_model_types()
    collect: list = []
    got = select_ratio(
        "dscr",
        "corporate_covenant",
        {
            "facts": [
                {
                    "row_key": "book-dscr",
                    "axis_id": "Outputs!r1",
                    "period_id": "2016",
                    "cell_id": cell_id,
                    "normalized_value": value,
                    "value_status": "cached",
                }
            ],
            "bindings": [
                {
                    "row_key": "book-dscr",
                    "binding_key": "book-dscr",
                    "is_primary": True,
                    "status": "bound",
                    "effective_concept": "dscr",
                    "source": "inferred",
                }
            ],
            "periods": [{"axis_id": "Outputs!r1", "period_id": "2016", "period_key_base": "2016"}],
            "period_phase": {},
            "explicit_phases": False,
            "sign_convention": "outflow_negative",
            "marker_class": None,
            "absent": frozenset(),
        },
        profile=None,
        profile_ref=None,
        composed=types.composed,
        concepts=frozenset({"ebitda", "cash_taxes", "capex", "interest", "principal", "dscr"}),
        money=frozenset({"ebitda", "cash_taxes", "capex", "interest", "principal"}),
        interest_order=types.interest_order,
        row_fallbacks=types.row_fallbacks,
        plan=_Plan(),
        collect=collect,
    )
    published = next(item for item in collect if item.calculation_origin == "reported")
    return got, published


def test_reported_reads_with_a_different_cell_or_value_do_not_share_an_evidence_id():
    """Ячейка и опубликованное число входят в идентификатор улики reported.

    https://csrc.nist.gov/publications/detail/fips/180/4/final
    """

    first_got, first = _published_read("1.476", "Outputs!D20")
    other_cell_got, other_cell = _published_read("1.476", "Outputs!E20")
    other_value_got, other_value = _published_read("2.500", "Outputs!D20")
    assert first.plan_content_sha256 == other_cell.plan_content_sha256 == other_value.plan_content_sha256
    assert first.evidence_id != other_cell.evidence_id
    assert first.evidence_id != other_value.evidence_id
    assert first.definition_version is None
    assert first.executor_version is None
    for got in (first_got, other_cell_got, other_value_got):
        row = got["rows"][0]
        assert row["reason"] == "reported"
        assert row["variant"] == "reported"
        _row_is_public(row)


async def test_compute_metrics_keeps_the_select_ratio_trace_on_the_evidence():
    """След select_ratio пишется в исходный список улик, не в копию среза."""

    from finance_analysis.application.analyses import Analyses, Target
    from finance_analysis.application.catalog import load_catalog
    from finance_analysis.application.model_types import load_model_types
    from finance_analysis.domain.book import Head
    from finance_analysis.domain.errors import NotFound
    from finance_analysis.domain.model_type import Effective

    facts = [
        {
            "row_key": "project_fcf",
            "axis_id": "a",
            "period_id": "Y0",
            "period_index": 0,
            "normalized_value": "-100",
            "cell_id": "a!Y0",
        },
        {
            "row_key": "project_fcf",
            "axis_id": "a",
            "period_id": "Y1",
            "period_index": 1,
            "normalized_value": "60",
            "cell_id": "a!Y1",
        },
        {
            "row_key": "discount_rate",
            "axis_id": "p",
            "period_id": "R",
            "normalized_value": "0.10",
            "cell_id": "p!R",
        },
    ]
    bindings = [
        {
            "effective_concept": concept,
            "row_key": concept,
            "is_primary": True,
            "status": "bound",
            "source": "inferred",
        }
        for concept in ("project_fcf", "discount_rate")
    ]
    periods = [
        {"axis_id": "a", "period_id": "Y0", "period_index": 0},
        {"axis_id": "a", "period_id": "Y1", "period_index": 1},
        {"axis_id": "p", "period_id": "R", "period_index": None},
    ]

    class _Guard:
        async def read_all(self, _job_id):
            return []

    class _Glossary:
        async def profile_body(self, _profile_id):
            return {}

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

    service = _Service()
    service.model_types = load_model_types()
    service.catalog = load_catalog()
    service.financial_catalog = None
    service.guard = _Guard()
    service.glossary = _Glossary()
    head = Head(build_key="build", state_seq=1, derive_key="derive", versions={})
    got = await Analyses(service).compute_metrics(
        "job", Target(head=head, build="build", manifest={}, fresh=True), ["npv"]
    )
    trace = got["branch_traces"][0]["trace"]
    evidence = next(item for item in got["evidences"] if item.metric == "npv")
    assert trace.branch_id == "npv"
    assert evidence.branch_id == trace.branch_id
    assert evidence.actual_inputs == trace.actual_inputs
    assert "project_fcf" in evidence.actual_inputs
    assert "discount_rate" in evidence.actual_inputs
    assert evidence.actual_fact_uses == trace.actual_fact_uses
    assert "a!Y1" in evidence.actual_fact_uses
    assert evidence.actual_periods == trace.actual_periods
    assert evidence.actual_period_slots == trace.actual_period_slots
    assert evidence.profile_values == trace.profile_values
    for row in got["rows"]:
        _row_is_public(row)


def test_reported_origin_stays_on_the_publication_evidence():
    class _Need:
        subject = "cash_taxes"
        reason = "concept_unknown"

        def as_dict(self):
            return {"kind": "concept", "reason": self.reason, "subject": self.subject}

    class _Plan:
        status = "missing_input"
        content_sha256 = "plan-digest-corporate"
        needs_input = (_Need(),)
        warnings = ()
        inputs = ()
        diagnostic = ()
        rejected = ()
        fallbacks = ()

    types = load_model_types()
    collect: list = []
    got = select_ratio(
        "dscr",
        "corporate_covenant",
        {
            "facts": [
                {
                    "row_key": "book-dscr",
                    "axis_id": "Outputs!r1",
                    "period_id": "2016",
                    "cell_id": "Outputs!D20",
                    "normalized_value": "1.476",
                    "value_status": "cached",
                }
            ],
            "bindings": [
                {
                    "row_key": "book-dscr",
                    "binding_key": "book-dscr",
                    "is_primary": True,
                    "status": "bound",
                    "effective_concept": "dscr",
                    "source": "inferred",
                }
            ],
            "periods": [{"axis_id": "Outputs!r1", "period_id": "2016", "period_key_base": "2016"}],
            "period_phase": {},
            "explicit_phases": False,
            "sign_convention": "outflow_negative",
            "marker_class": None,
            "absent": frozenset(),
        },
        profile=None,
        profile_ref=None,
        composed=types.composed,
        concepts=frozenset({"ebitda", "cash_taxes", "capex", "interest", "principal", "dscr"}),
        money=frozenset({"ebitda", "cash_taxes", "capex", "interest", "principal"}),
        interest_order=types.interest_order,
        row_fallbacks=types.row_fallbacks,
        plan=_Plan(),
        collect=collect,
    )
    assert got["definition_source"] == "reported"
    row = got["rows"][0]
    assert row["reason"] == "reported"
    assert row["variant"] == "reported"
    assert row["status"] == "computed"
    _row_is_public(row)
    _attempt, published = collect
    assert published.execution_status == "published"
    assert published.calculation_origin == "reported"
    assert published.definition_source == "reported"
    assert published.definition_version is None
    assert published.executor_version is None
    assert view_from_evidence(published)["calculation_origin"] == "reported"


_AUDIT_FIELDS = (
    "evidence_id",
    "branch_id",
    "actual_inputs",
    "actual_fact_uses",
    "actual_periods",
    "actual_period_slots",
    "definition_hash",
    "parent_evidence_ids",
)


async def test_saved_evidence_walks_parents_for_adscr_and_reductions(tmp_path):
    """Аудитор читает сохранённую улику, а не список branch_traces у compute_metrics.

    Идентификатор родителя находится в той же сохранённой коллекции.
    https://www.w3.org/TR/prov-dm/#term-Communication
    https://csrc.nist.gov/publications/detail/fips/180/4/final
    """

    import json
    from contextlib import asynccontextmanager
    from dataclasses import replace

    from httpx import ASGITransport, AsyncClient

    from finance_analysis.adapters.api.app import create_app
    from finance_analysis.adapters.storage.store import LocalStore
    from finance_analysis.adapters.storage.trace_pointer import DuckDBTracePointer
    from finance_analysis.application.analyses import (
        Analyses,
        Target,
        _coverage_catalog,
    )
    from finance_analysis.application.catalog import load_catalog
    from finance_analysis.application.keys import report_index_key
    from finance_analysis.application.model_types import load_model_types
    from finance_analysis.domain.book import Head
    from finance_analysis.domain.errors import NotFound
    from finance_analysis.domain.execution_contract import compile_definition
    from finance_analysis.domain.metric_contract import REGISTRY
    from finance_analysis.domain.model_type import Effective
    from finance_analysis.settings import Settings
    from tests.unit.test_cover_provenance import _common, _quarters

    periods, facts = _quarters()
    common = _common(periods, facts)

    class _Guard:
        async def read_all(self, _job_id):
            return []

    class _Glossary:
        async def profile_body(self, _profile_id):
            return {}

    class _Service:
        async def _dataset_rows(self, _job_id, _head, dataset):
            if dataset == "bindings":
                return common["bindings"]
            if dataset == "fact_observation":
                return facts
            if dataset == "dim_period":
                return periods
            if dataset in {"dim_row", "period_semantics", "graph_links"}:
                return []
            raise NotFound(dataset)

        async def resolve_model_type(self, _job_id, _head):
            return Effective(
                ("project_finance",),
                "project_finance",
                "confirmed",
                None,
                1,
                None,
                1.0,
                {"project_finance": 1.0},
                (),
            )

    store = LocalStore(tmp_path / "objects")
    pointer = DuckDBTracePointer(tmp_path / "pointers.duckdb")
    service = _Service()
    service.model_types = load_model_types()
    service.catalog = load_catalog()
    service.financial_catalog = None
    service.guard = _Guard()
    service.glossary = _Glossary()
    service.store = store
    service.trace_pointer = pointer
    service.trace_retainer = None
    service.settings = Settings(_env_file=None)
    head = Head(build_key="build", state_seq=1, derive_key="derive", versions={})
    analyses = Analyses(service)
    service.analyses = analyses
    got = await analyses.compute_metrics(
        "job",
        Target(head=head, build="build", manifest={}, fresh=True),
        ["adscr", "dscr_min", "dscr_avg"],
    )
    for row in got["rows"]:
        _row_is_public(row)
    analysis_id = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
    job_id = "ab" * 32
    await analyses._publish_traces(analysis_id, got.get("evidences") or [], execution_source="ratios")
    await store.put(
        report_index_key(job_id, analysis_id),
        json.dumps({"analysis_id": analysis_id, "build_key": "b" * 16}).encode(),
    )

    class _Support:
        async def rate_limit(self, _who):
            return None

        @asynccontextmanager
        async def user_inflight(self, _who):
            yield

    app = create_app(service.settings, service=service, support=_Support())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fas") as client:
        listed = await client.get(f"/v1/books/{job_id}/analyses/{analysis_id}/traces")
        assert listed.status_code == 200, listed.text
        body = listed.json()
        assert "branch_traces" not in body
        assert body["items"]
        saved = []
        for item in body["items"]:
            assert item["execution_id"]
            one = await client.get(
                f"/v1/books/{job_id}/analyses/{analysis_id}/traces/{item['execution_id']}"
            )
            assert one.status_code == 200, one.text
            detail = one.json()
            assert "branch_traces" not in detail
            assert detail["branch_trace"] == item["branch_trace"]
            assert detail["execution_id"] == item["execution_id"]
            saved.append(detail["trace"])
        foreign = await client.get(f"/v1/books/{'cd' * 32}/analyses/{analysis_id}/traces")
        assert foreign.status_code == 404
    by_id = {item["evidence_id"] for item in saved if item.get("evidence_id")}
    parents = [parent for item in saved for parent in item.get("parent_evidence_ids") or []]
    assert parents
    assert set(parents) <= by_id
    catalog = _coverage_catalog(service.model_types, None)

    def _hash(key: str, executor_id: str, executor_version: str) -> str:
        record = catalog[key]
        specialized = replace(
            record,
            executor_key=executor_id,
            executor_id=executor_id,
            executor_version=executor_version,
        )
        return compile_definition(specialized, catalog).definition_hash

    for metric in ("adscr", "dscr_min", "dscr_avg"):
        view = next(item for item in saved if item.get("metric") == metric)
        for name in _AUDIT_FIELDS:
            assert name in view, metric
            assert view[name], metric
        assert view["branch_id"] == metric
        ran = REGISTRY[(metric, metric)]
        assert view["executor_id"] == metric
        assert view["executor_version"] == ran.implementation_version
        assert view["definition_hash"] == _hash(metric, metric, ran.implementation_version)
        assert view["definition_hash"] != compile_definition(catalog[metric], catalog).definition_hash
        assert "cfads" in view["actual_inputs"]
        assert "debt_service" in view["actual_inputs"]
        assert view["actual_period_slots"]
        assert all(parent in by_id for parent in view["parent_evidence_ids"])
        for parent_id in view["parent_evidence_ids"]:
            parent = next(item for item in saved if item.get("evidence_id") == parent_id)
            # calculate_coverage(metric="dscr") запечатывает dscr@1. План DSCR
            # не строился, вариант книги в этот проход не передавался. Хеш
            # dscr.pf при implementation dscr@1 называл бы другой путь.
            # https://csrc.nist.gov/publications/detail/fips/180/4/final
            ran_parent = REGISTRY[("dscr", "dscr")]
            assert parent["implementation"] == ran_parent.implementation_version
            assert "definition_hash" not in parent
            assert parent.get("definition_hash") != _hash(
                "dscr.pf",
                "dscr.pf",
                REGISTRY[("dscr", "dscr.pf")].implementation_version,
            )
            assert parent["periods"]
            assert "branch_id" not in parent
            assert "actual_inputs" not in parent
            listed_parent = next(item for item in body["items"] if item.get("evidence_id") == parent_id)
            assert listed_parent["branch_trace"] == "incomplete"
        listed_child = next(item for item in body["items"] if item.get("evidence_id") == view["evidence_id"])
        assert listed_child["branch_trace"] == "complete"
        if metric == "adscr":
            assert ["adscr_direction", "lookback"] in view["profile_values"]
        else:
            assert view["parent_period_ids"]
            assert "profile_values" not in view or view["profile_values"] == []


async def test_unfinished_pointer_is_not_published_evidence(tmp_path):
    """Незавершённый указатель не выглядит опубликованной уликой.

    Список называет стадию и не отдаёт тело. Чтение одного такого указателя
    не возвращает объект. Нет строки — «след не найден».
    https://microservices.io/patterns/data/transactional-outbox.html
    """

    import json
    from contextlib import asynccontextmanager

    from httpx import ASGITransport, AsyncClient

    from finance_analysis.adapters.api.app import create_app
    from finance_analysis.adapters.storage.store import LocalStore
    from finance_analysis.adapters.storage.trace_pointer import DuckDBTracePointer
    from finance_analysis.application.analyses import Analyses
    from finance_analysis.application.keys import report_index_key
    from finance_analysis.settings import Settings

    analysis_id = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
    job_id = "ab" * 32
    store = LocalStore(tmp_path / "objects")
    pointer = DuckDBTracePointer(tmp_path / "pointers.duckdb")

    class _Service:
        pass

    class _Support:
        async def rate_limit(self, _who):
            return None

        @asynccontextmanager
        async def user_inflight(self, _who):
            yield

    service = _Service()
    service.store = store
    service.trace_pointer = pointer
    service.settings = Settings(_env_file=None)
    service.analyses = Analyses(service)
    await store.put(
        report_index_key(job_id, analysis_id),
        json.dumps({"analysis_id": analysis_id}).encode(),
    )
    marker = "secret-uncommitted-cell"
    for state in ("pending_object", "pending_retention", "pending_commit"):
        execution_id = f"hold-{state}"
        key = f"traces/{analysis_id}/{execution_id}.json"
        pointer.put(
            {
                "analysis_id": analysis_id,
                "execution_id": execution_id,
                "object_key": key,
                "evidence_complete": True,
                "dropped_cell_count": 0,
                "retained_until": None,
                "state": state,
            }
        )
        await store.put(
            key,
            json.dumps(
                {
                    "trace": {
                        "metric": "adscr",
                        "evidence_id": marker,
                        "branch_id": "adscr",
                        "actual_inputs": ["cfads"],
                    }
                }
            ).encode(),
        )
    app = create_app(service.settings, service=service, support=_Support())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fas") as client:
        listed = await client.get(f"/v1/books/{job_id}/analyses/{analysis_id}/traces")
        assert listed.status_code == 200, listed.text
        assert marker not in listed.text
        body = listed.json()
        assert "branch_traces" not in body
        for state in ("pending_object", "pending_retention", "pending_commit"):
            execution_id = f"hold-{state}"
            item = next(row for row in body["items"] if row["execution_id"] == execution_id)
            assert item["publication"] == state
            assert "branch_trace" not in item
            assert "trace" not in item
            assert "evidence_id" not in item
            one = await client.get(
                f"/v1/books/{job_id}/analyses/{analysis_id}/traces/{execution_id}"
            )
            assert one.status_code == 404, one.text
            assert marker not in one.text
            problem = one.json()
            assert problem["detail"] == "след не опубликован"
            assert problem["publication"] == state
            assert "trace" not in problem
        missing = await client.get(f"/v1/books/{job_id}/analyses/{analysis_id}/traces/missing-0")
        assert missing.status_code == 404
        assert missing.json()["detail"] == "след не найден"
        assert "publication" not in missing.json()
