"""Один резолвер: след, происхождение и расчёт читают одни входные строки.

Правило общее для каждой метрики каталога. ICR с двумя числителями, устаревшая
и неосновная привязки, варианты DSCR/ADSCR и запасной путь — случаи того же правила.
"""

from finance_analysis.application.model_types import (
    load_metric_catalog,
    load_model_types,
)
from finance_analysis.domain.audit import AuditInput, Finding, Location
from finance_analysis.domain.formula_origin import origin_view
from finance_analysis.domain.graphs import trace_metric
from finance_analysis.domain.metrics import coverage_ratio
from finance_analysis.domain.model_type import MetricExpression
from finance_analysis.domain.semantic_input import resolve_semantic_inputs


def _catalog():
    return load_model_types()


def _expressions() -> dict[str, MetricExpression]:
    _inputs, _variants, _composed, _bases, _rates, expressions = load_metric_catalog()
    return expressions


def _bind(concept: str, number: int, **extra) -> dict:
    row_key = extra.pop("row_key", f"S|{number}|a")
    return {
        "status": "bound",
        "is_primary": True,
        "effective_concept": concept,
        "row_key": row_key,
        "binding_key": f"bk-{concept}-{number}",
        "source": "inferred",
        **extra,
    }


def _fact(row_key: str, concept: str) -> dict:
    return {
        "row_key": row_key,
        "axis_id": "a",
        "period_id": "Y1",
        "normalized_value": "40",
        "cell_id": f"S!{concept}",
    }


def _period() -> dict:
    return {
        "axis_id": "a",
        "period_id": "Y1",
        "period_index": 1,
        "grain": "year",
        "timeline_id": "t",
    }


def _names(expressions: dict[str, MetricExpression]) -> list[str]:
    found: list[str] = []
    for expr in expressions.values():
        found.extend(
            (
                *expr.numerator_plus,
                *expr.numerator_minus,
                *expr.denominator_plus,
                *expr.denominator_minus,
                *expr.one_of_order,
                *sorted(expr.one_of),
                *expr.rates,
            )
        )
        for name in (expr.rate, expr.terminal, expr.compare_with):
            if name:
                found.append(name)
        if expr.add_back:
            found.extend(expr.add_back)
    found.extend(("interest_paid", "principal"))
    return list(dict.fromkeys(name for name in found if name))


def _book(concepts: list[str], *, extra: list[dict] | None = None, variant: str | None = None, metrics: frozenset[str] | None = None):
    bindings = [_bind(name, index) for index, name in enumerate(concepts, start=1)]
    if extra:
        bindings.extend(extra)
    facts = [_fact(row["row_key"], row["effective_concept"]) for row in bindings if row.get("row_key")]
    data = AuditInput(
        rows=[{"row_key": row["row_key"], "label": row["effective_concept"]} for row in bindings if row.get("row_key")],
        facts=facts,
        bindings=bindings,
        applicable_metrics=metrics,
        dscr_variant=variant,
        graph_links_available=True,
    )
    return data, bindings, facts


def _rows(pairs) -> set[tuple[str, str]]:
    return {(concept, row_key) for concept, row_key in pairs if row_key}


def _trace_rows(metric: str, data: AuditInput, expressions, catalog) -> set[tuple[str, str]]:
    trace = trace_metric(
        metric,
        inputs=None,
        bindings=data.bindings,
        facts=data.facts,
        expressions=expressions,
        interest_order=catalog.interest_order,
        row_fallbacks=catalog.row_fallbacks,
        dscr_variant=data.dscr_variant,
        absent=data.absent,
    )
    return _rows((step.concept, step.row_key) for step in trace.steps if not step.note)


def _marked(data: AuditInput) -> list[Finding]:
    """Пометка на каждой строке, чтобы отчёт отдал входы метрики без прогона правил."""

    return [
        Finding(
            code="literal_in_formula",
            version="t",
            error_class="logic",
            severity="low",
            params={},
            locations=(Location(None, row["row_key"], None, None),),
            fingerprint=row["row_key"],
            binding_key=row.get("binding_key"),
            truncated=False,
            basis=(),
            finding_kind="warning",
        )
        for row in data.bindings
        if row.get("row_key")
    ]


def _origin_rows(metric: str, data: AuditInput, expressions, catalog) -> set[tuple[str, str]]:
    view = origin_view(
        data,
        _marked(data),
        expressions,
        interest_order=catalog.interest_order,
        row_fallbacks=catalog.row_fallbacks,
    )
    found = [item for item in view["metrics"] if item["metric"] == metric]
    if not found:
        return set()
    return _rows((item["concept"], item["row_key"]) for item in found[0]["inputs"])


def _resolved_rows(metric: str, data: AuditInput, expressions, catalog) -> set[tuple[str, str]]:
    resolved = resolve_semantic_inputs(
        metric,
        data.bindings,
        expressions,
        dscr_variant=data.dscr_variant,
        interest_order=catalog.interest_order,
        row_fallbacks=catalog.row_fallbacks,
        absent=data.absent,
    )
    assert resolved is not None
    return _rows((item.concept, item.row_key) for item in resolved)


def _core_rows(metric: str, bindings: list[dict], facts: list[dict], catalog) -> set[str]:
    got = coverage_ratio(
        metric=metric,
        facts=facts,
        bindings=bindings,
        periods=[_period()],
        period_phase={},
        explicit_phases=False,
        interest_order=catalog.interest_order,
        row_fallbacks=catalog.row_fallbacks,
    )
    concepts: set[str] = set()
    for row in got["rows"]:
        concepts.update(row.get("components") or {})
    return concepts


def test_every_metric_trace_origin_and_resolver_share_rows():
    catalog = _catalog()
    expressions = _expressions()
    concepts = _names(expressions)
    data, _bindings, _facts = _book(concepts, metrics=frozenset(name for name in expressions if "." not in name))
    for metric in sorted(name for name in expressions if "." not in name):
        assert _trace_rows(metric, data, expressions, catalog) == _origin_rows(metric, data, expressions, catalog)
        assert _trace_rows(metric, data, expressions, catalog) == _resolved_rows(metric, data, expressions, catalog)


def test_icr_with_two_numerators_uses_ebitda_row_in_trace_origin_and_calculation():
    catalog = _catalog()
    expressions = _expressions()
    concepts = ["ebitda", "ebit", "interest"]
    data, bindings, facts = _book(concepts, metrics=frozenset({"icr"}))
    rows = _trace_rows("icr", data, expressions, catalog)
    assert rows == _origin_rows("icr", data, expressions, catalog) == _resolved_rows("icr", data, expressions, catalog)
    assert {concept for concept, _row in rows} == {"ebitda", "interest"}
    assert {concept for concept, _row in rows} == _core_rows("icr", bindings, facts, catalog)
    by_concept = {concept: row for concept, row in rows}
    assert by_concept["ebitda"] == bindings[0]["row_key"]
    assert all(row != bindings[1]["row_key"] for _concept, row in rows)


def test_stale_and_non_primary_rows_are_not_inputs():
    catalog = _catalog()
    expressions = {"dscr": MetricExpression(numerator_plus=("cfads",), denominator_plus=("debt_service",))}
    fresh = _bind("cfads", 1)
    secondary = _bind("cfads", 2, is_primary=False, binding_key="bk-secondary")
    stale = _bind("cfads", 3, stale=True, binding_key="bk-stale")
    debt = _bind("debt_service", 4)
    data, bindings, facts = _book([], extra=[fresh, secondary, stale, debt], metrics=frozenset({"dscr"}))
    rows = _trace_rows("dscr", data, expressions, catalog)
    assert rows == _origin_rows("dscr", data, expressions, catalog) == _resolved_rows("dscr", data, expressions, catalog)
    assert {row for _concept, row in rows} == {fresh["row_key"], debt["row_key"]}
    assert {concept for concept, _row in rows} == _core_rows("dscr", bindings, facts, catalog)


def test_dscr_and_adscr_variants_share_the_same_rows():
    catalog = _catalog()
    expressions = _expressions()
    concepts = _names(expressions)
    cases = (
        ("dscr", "corporate_covenant", {"ebitda", "cash_taxes", "capex", "interest", "principal"}),
        ("dscr", "pf", {"cfads", "debt_service"}),
        ("adscr", "housing", {"cfo_statement", "cfi_statement", "financing_inflows", "senior_principal", "senior_interest_paid"}),
        ("adscr", "corporate_covenant", {"cfads", "debt_service"}),
    )
    for metric, variant, expected in cases:
        data, _bindings, _facts = _book(concepts, variant=variant, metrics=frozenset({metric}))
        rows = _trace_rows(metric, data, expressions, catalog)
        assert rows == _origin_rows(metric, data, expressions, catalog) == _resolved_rows(metric, data, expressions, catalog)
        assert {concept for concept, _row in rows} == expected


def test_dscr_fallback_rows_match_the_calculation():
    catalog = _catalog()
    expressions = _expressions()
    concepts = ["cfads", "interest_paid", "principal", "ebitda"]
    data, bindings, facts = _book(concepts, variant="pf", metrics=frozenset({"dscr"}))
    rows = _trace_rows("dscr", data, expressions, catalog)
    assert rows == _origin_rows("dscr", data, expressions, catalog) == _resolved_rows("dscr", data, expressions, catalog)
    assert {concept for concept, _row in rows} == {"cfads", "interest_paid", "principal"}
    assert {concept for concept, _row in rows} == _core_rows("dscr", bindings, facts, catalog)


def test_truncated_lineage_is_incomplete_for_trace_and_origin():
    expressions = {"dscr": MetricExpression(numerator_plus=("cfads",), denominator_plus=("debt_service",))}
    binding = _bind("cfads", 1)
    link = {
        "cell": "S!C1",
        "formula": "SUM(A1:A9)",
        "formula_class": "same_period",
        "ref_cell": "S!A1",
        "row_key": binding["row_key"],
        "truncated": True,
    }
    data = AuditInput(
        bindings=[binding],
        links=[link],
        applicable_metrics=frozenset({"dscr"}),
        graph_links_available=True,
    )
    view = origin_view(data, [], expressions)
    trace = trace_metric(
        "dscr",
        inputs=None,
        bindings=data.bindings,
        graph_links=[link],
        expressions=expressions,
        graph_links_available=True,
    )
    assert view["physical_lineage_complete"] is False
    assert view["truncated_links"] == 1
    assert trace.physical_lineage_complete is False
    assert view["physical_lineage_complete"] is trace.physical_lineage_complete
