"""Один резолвер: след, происхождение и расчёт читают одни входные строки.

Правило общее для каждой метрики каталога. ICR с двумя числителями, устаревшая
и неосновная привязки, варианты DSCR/ADSCR и запасной путь — случаи того же правила.
"""

import itertools

import pytest

from finance_analysis.application.model_types import (
    load_metric_catalog,
    load_model_types,
)
from finance_analysis.application.report import render_markdown
from finance_analysis.domain.audit import AuditInput, Finding, Location
from finance_analysis.domain.formula_origin import origin_view
from finance_analysis.domain.free_cash_flow import free_cash_flow
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
    facts = [
        _fact(row["row_key"], row.get("effective_concept") or row.get("concept") or "")
        for row in bindings
        if row.get("row_key")
    ]
    data = AuditInput(
        rows=[
            {"row_key": row["row_key"], "label": row.get("effective_concept") or row.get("concept") or ""}
            for row in bindings
            if row.get("row_key")
        ],
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
        statement_sheets=data.statement_sheets,
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
        facts=data.facts,
        links=data.links,
        statement_sheets=data.statement_sheets,
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
    assert view["graph_available"] is True
    assert view["graph_truncation_free"] is False
    assert view["truncated_links"] == 1
    assert trace.physical_lineage_complete is False
    assert trace.graph_available is view["graph_available"]
    assert trace.graph_truncation_free is view["graph_truncation_free"]
    assert view["physical_lineage_complete"] is trace.physical_lineage_complete


def _coverage(metric: str, bindings: list[dict], facts: list[dict], catalog):
    return coverage_ratio(
        metric=metric,
        facts=facts,
        bindings=bindings,
        periods=[_period()],
        period_phase={},
        explicit_phases=False,
        interest_order=catalog.interest_order,
        row_fallbacks=catalog.row_fallbacks,
    )


def _components(got: dict) -> set[str]:
    found: set[str] = set()
    for row in got["rows"]:
        found.update(row.get("components") or {})
    return found


def _confirmed(resolved) -> set[tuple[str, str]]:
    return _rows((item.concept, item.row_key) for item in resolved if item.row_key and not item.ambiguous)


_CATALOG_METRICS = sorted(name for name in _expressions() if "." not in name)


def _concept_only(rows: list[dict]) -> list[dict]:
    """То же понятие в ``concept``, без ``effective_concept``."""

    found = []
    for row in rows:
        item = dict(row)
        name = item.get("effective_concept") or item.get("concept")
        item.pop("effective_concept", None)
        if name:
            item["concept"] = name
        found.append(item)
    return found


@pytest.mark.parametrize("metric", _CATALOG_METRICS)
@pytest.mark.parametrize("concept_only", [False, True], ids=["effective", "concept_only"])
def test_catalog_metric_trace_origin_and_coverage_inputs(metric: str, concept_only: bool):
    catalog = _catalog()
    expressions = _expressions()
    data, bindings, facts = _book(_names(expressions), metrics=frozenset({metric}))
    if concept_only:
        bindings = _concept_only(bindings)
        data.bindings = bindings
    rows = _trace_rows(metric, data, expressions, catalog)
    assert rows == _origin_rows(metric, data, expressions, catalog) == _resolved_rows(metric, data, expressions, catalog)
    if metric in {"dscr", "icr", "icr_ebit"}:
        assert {concept for concept, _row in rows} == _components(_coverage(metric, bindings, facts, catalog))


def _dscr_expected(present: set[str]) -> set[str]:
    """Ветки coverage_ratio для DSCR без debt_service и с ним. Порядок объявления не участвует."""

    if "debt_service" in present:
        return {"cfads", "debt_service"}
    if "cfads" not in present:
        return {"cfads"}
    if "interest" not in present:
        return {"cfads", "debt_service"}
    if "principal" not in present:
        return {"cfads", "principal"}
    return {"cfads", "interest", "principal"}


def _flag_id(flags: tuple[bool, ...]) -> str:
    names = ("cfads", "debt_service", "interest", "principal")
    picked = [name for name, flag in zip(names, flags, strict=True) if flag]
    return "+".join(picked) or "none"


@pytest.mark.parametrize(
    "flags",
    list(itertools.product((False, True), repeat=4)),
    ids=_flag_id,
)
def test_every_dscr_input_combination_matches_coverage_ratio(flags):
    present = {name for name, flag in zip(("cfads", "debt_service", "interest", "principal"), flags, strict=True) if flag}
    catalog = _catalog()
    expressions = _expressions()
    data, bindings, facts = _book(sorted(present), variant="pf", metrics=frozenset({"dscr"}))
    resolved = resolve_semantic_inputs(
        "dscr",
        bindings,
        expressions,
        dscr_variant="pf",
        interest_order=catalog.interest_order,
        row_fallbacks=catalog.row_fallbacks,
    )
    assert resolved is not None
    expected = _dscr_expected(present)
    assert {item.concept for item in resolved} == expected
    got = _coverage("dscr", bindings, facts, catalog)
    assert set(got.get("missing_inputs") or []) == expected - present
    if got["status"] == "succeeded":
        assert _components(got) == expected
    rows = _trace_rows("dscr", data, expressions, catalog)
    assert rows == _origin_rows("dscr", data, expressions, catalog)
    assert {concept for concept, row in rows} == {item.concept for item in resolved if item.row_key}


@pytest.mark.parametrize(
    ("order", "bound", "numerator"),
    [
        (("ebit", "ebitda"), ("ebit", "ebitda"), "ebitda"),
        (("ebitda", "ebit"), ("ebit", "ebitda"), "ebitda"),
        (("ebit", "ebitda"), (), "ebitda"),
        (("ebitda", "ebit"), (), "ebitda"),
        (("ebit", "ebitda"), ("ebit",), "ebit"),
        (("ebitda", "ebit"), ("ebit",), "ebit"),
        (("ebit", "ebitda"), ("ebitda",), "ebitda"),
        (("ebitda", "ebit"), ("ebitda",), "ebitda"),
    ],
)
def test_one_of_follows_coverage_numerator_not_declaration_order(order, bound, numerator):
    catalog = _catalog()
    expressions = {
        "icr": MetricExpression(
            denominator_plus=("interest",),
            one_of=frozenset(order),
            one_of_order=tuple(order),
        )
    }
    concepts = [*bound, "interest"]
    data, bindings, facts = _book(concepts, metrics=frozenset({"icr"}))
    resolved = resolve_semantic_inputs(
        "icr",
        bindings,
        expressions,
        interest_order=catalog.interest_order,
        row_fallbacks=catalog.row_fallbacks,
    )
    assert resolved is not None
    chosen = [item for item in resolved if item.role == "one_of"]
    assert [item.concept for item in chosen] == [numerator]
    assert chosen[0].source == "formula"
    got = _coverage("icr", bindings, facts, catalog)
    if numerator in bound:
        assert _components(got) == {numerator, "interest"}
        view = origin_view(
            data,
            _marked(data),
            expressions,
            interest_order=catalog.interest_order,
            row_fallbacks=catalog.row_fallbacks,
        )
        sources = {item["source"] for item in view["chain"] if item["input"] == numerator}
        assert sources == {"formula"}
    else:
        assert "ebitda" in set(got.get("missing_inputs") or [])
        assert numerator == "ebitda"
    assert _trace_rows("icr", data, expressions, catalog) == _origin_rows("icr", data, expressions, catalog)


def test_adscr_housing_inherits_housing_and_not_the_dscr_fallback():
    catalog = _catalog()
    expressions = _expressions()
    housing = {"cfo_statement", "cfi_statement", "financing_inflows", "senior_principal", "senior_interest_paid"}
    data, _bindings, _facts = _book(sorted(housing), variant="housing", metrics=frozenset({"adscr"}))
    rows = _trace_rows("adscr", data, expressions, catalog)
    assert rows == _origin_rows("adscr", data, expressions, catalog)
    assert {concept for concept, _row in rows} == housing

    fallback_book, bindings, _facts = _book(
        ["interest", "principal"],
        variant="pf",
        metrics=frozenset({"adscr"}),
    )
    resolved = resolve_semantic_inputs(
        "adscr",
        bindings,
        expressions,
        dscr_variant="pf",
        interest_order=catalog.interest_order,
        row_fallbacks=catalog.row_fallbacks,
    )
    assert resolved is not None
    assert {item.concept for item in resolved} == {"cfads", "debt_service"}
    assert _trace_rows("adscr", fallback_book, expressions, catalog) == _origin_rows(
        "adscr", fallback_book, expressions, catalog
    )


def test_two_primaries_are_visible_in_the_trace_and_not_a_confirmed_origin_input():
    catalog = _catalog()
    expressions = {"dscr": MetricExpression(numerator_plus=("cfads",), denominator_plus=("debt_service",))}
    later = _bind("cfads", 1, binding_key="bk-b", row_key="row-b")
    earlier = _bind("cfads", 2, binding_key="bk-a", row_key="row-a")
    debt = _bind("debt_service", 3)
    data, bindings, facts = _book([], extra=[later, earlier, debt], metrics=frozenset({"dscr"}))
    trace = trace_metric(
        "dscr",
        inputs=None,
        bindings=bindings,
        facts=data.facts,
        expressions=expressions,
        interest_order=catalog.interest_order,
        row_fallbacks=catalog.row_fallbacks,
    )
    step = next(item for item in trace.steps if item.concept == "cfads")
    assert (step.binding_key, step.row_key) == (earlier["binding_key"], earlier["row_key"])
    assert any(item.reason == "ambiguous_primary_binding" and item.binding_key == "bk-a" for item in trace.integrity)
    got = _coverage("dscr", bindings, facts, catalog)
    assert got["status"] == "needs_input"
    assert _components(got) == set()
    view = origin_view(data, _marked(data), expressions, interest_order=catalog.interest_order)
    marked = [item for item in view["metrics"][0]["inputs"] if item["concept"] == "cfads"]
    assert marked and marked[0]["confirmed"] is False and marked[0]["ambiguous"] is True
    assert all(item.get("confirmed") is not False or item["concept"] == "cfads" for item in view["metrics"][0]["inputs"])
    assert any(item.get("ambiguous") is True and item.get("confirmed") is False for item in view["chain"])
    text = render_markdown({"analysis_id": "a", "status": "succeeded", "result_data": {"formula_origin": view}})
    assert "вход cfads: formula" not in text
    assert "не подтверждён" in text


def test_stale_fresh_several_stale_and_missing_row_key():
    catalog = _catalog()
    expressions = {"dscr": MetricExpression(numerator_plus=("cfads",), denominator_plus=("debt_service",))}
    fresh = _bind("cfads", 1, binding_key="bk-fresh", row_key="row-fresh")
    stale = _bind("cfads", 2, stale=True, binding_key="bk-stale", row_key="row-stale")
    debt = _bind("debt_service", 3)
    data, bindings, facts = _book([], extra=[stale, fresh, debt], metrics=frozenset({"dscr"}))
    rows = _trace_rows("dscr", data, expressions, catalog)
    assert rows == {( "cfads", "row-fresh"), ("debt_service", debt["row_key"])}
    assert _components(_coverage("dscr", bindings, facts, catalog)) == {"cfads", "debt_service"}

    only_stale = [_bind("cfads", index, stale=True, binding_key=f"bk-stale-{index}") for index in range(1, 4)]
    debt = _bind("debt_service", 9)
    resolved = resolve_semantic_inputs("dscr", [*only_stale, debt], expressions)
    assert resolved is not None
    cfads = next(item for item in resolved if item.concept == "cfads")
    assert cfads.row_key is None and cfads.missing == "stale_binding"
    assert _components(_coverage("dscr", [*only_stale, debt], [], catalog)) == set()

    bare = _bind("cfads", 1, binding_key="bk-bare", row_key=None)
    other = _bind("debt_service", 2, binding_key="bk-debt", row_key="row-debt")
    traced = trace_metric(
        "dscr",
        inputs=None,
        bindings=[bare, other],
        rows=[{"binding_key": "bk-debt", "row_key": "row-foreign"}],
        expressions=expressions,
    )
    bare_step = next(item for item in traced.steps if item.concept == "cfads")
    debt_step = next(item for item in traced.steps if item.concept == "debt_service")
    assert bare_step.binding_key == "bk-bare" and bare_step.row_key is None
    assert (debt_step.binding_key, debt_step.row_key) == ("bk-debt", "row-debt")


def test_absent_drops_inferred_and_keeps_confirmed():
    catalog = _catalog()
    expressions = {"dscr": MetricExpression(numerator_plus=("cfads",), denominator_plus=("debt_service",))}
    inferred = _bind("cfads", 1, source="inferred", row_key="row-auto")
    confirmed = _bind("debt_service", 2, source="confirmed", row_key="row-manual")
    data = AuditInput(
        bindings=[inferred, confirmed],
        facts=[_fact("row-manual", "debt_service"), _fact("row-auto", "cfads")],
        applicable_metrics=frozenset({"dscr"}),
        absent=frozenset({"cfads", "debt_service"}),
        graph_links_available=True,
    )
    resolved = resolve_semantic_inputs(
        "dscr",
        data.bindings,
        expressions,
        absent=data.absent,
        interest_order=catalog.interest_order,
    )
    assert resolved is not None
    by_concept = {item.concept: item for item in resolved}
    assert by_concept["cfads"].row_key is None
    assert by_concept["debt_service"].row_key == "row-manual"
    assert _confirmed(resolved) == {("debt_service", "row-manual")}
    assert _trace_rows("dscr", data, expressions, catalog) == _origin_rows("dscr", data, expressions, catalog)


def test_unknown_variant_falls_back_and_explicit_variant_beats_dscr_variant():
    catalog = _catalog()
    expressions = _expressions()
    concepts = ["cfads", "debt_service", "ebitda", "cash_taxes", "capex", "interest", "principal"]
    _data, bindings, _facts = _book(concepts)
    unknown = resolve_semantic_inputs("dscr", bindings, expressions, variant="not-a-variant")
    assert unknown is not None
    assert {item.concept for item in unknown} == {"cfads", "debt_service"}
    assert {item.source for item in unknown} == {"formula"}
    corporate = resolve_semantic_inputs(
        "dscr",
        bindings,
        expressions,
        variant="corporate_covenant",
        dscr_variant="pf",
        interest_order=catalog.interest_order,
    )
    assert corporate is not None
    assert {item.concept for item in corporate} == {"ebitda", "cash_taxes", "capex", "interest", "principal"}
    base = resolve_semantic_inputs("adscr", bindings, expressions)
    assert base is not None
    assert {item.source for item in base} == {"base:dscr"}


def test_lineage_truncated_empty_missing_and_other_build():
    expressions = {"dscr": MetricExpression(numerator_plus=("cfads",), denominator_plus=("debt_service",))}
    binding = _bind("cfads", 1, build_key="this", row_key="row-cfads")
    debt = _bind("debt_service", 2, build_key="this", row_key="row-debt")
    fact = _fact("row-cfads", "cfads")
    fact["cell_id"] = "S!C1"
    fact["build_key"] = "this"
    own = {
        "cell": "S!C1",
        "ref_cell": "S!A1",
        "truncated": True,
        "build_key": "this",
        "formula_class": "same_period",
    }
    foreign = {**own, "build_key": "other", "ref_cell": "S!Z9"}
    truncated = trace_metric(
        "dscr",
        inputs=None,
        bindings=[binding, debt],
        facts=[fact],
        graph_links=[own],
        expressions=expressions,
        build_key="this",
        graph_links_available=True,
    )
    assert truncated.physical_lineage_complete is False
    assert truncated.graph_available is True
    assert truncated.graph_truncation_free is False
    empty = trace_metric(
        "dscr",
        inputs=None,
        bindings=[binding, debt],
        facts=[fact],
        graph_links=[],
        expressions=expressions,
        build_key="this",
        graph_links_available=True,
    )
    assert empty.physical_lineage_complete is True
    assert empty.graph_available is True
    assert empty.graph_truncation_free is True
    missing = trace_metric(
        "dscr",
        inputs=None,
        bindings=[binding, debt],
        graph_links=[],
        expressions=expressions,
        build_key="this",
        graph_links_available=False,
    )
    assert missing.physical_lineage_complete is False
    assert missing.graph_available is False
    assert missing.graph_truncation_free is False
    other = trace_metric(
        "dscr",
        inputs=None,
        bindings=[binding, debt],
        facts=[fact],
        graph_links=[foreign],
        expressions=expressions,
        build_key="this",
        graph_links_available=True,
    )
    assert other.physical_lineage_complete is True
    assert other.graph_available is True
    assert other.graph_truncation_free is True
    assert all(link.ref_cell != "S!Z9" for step in other.steps for link in step.excel_links)
    step = next(item for item in other.steps if item.concept == "cfads")
    assert (step.binding_key, step.row_key) == (binding["binding_key"], binding["row_key"])


def _line(concept: str, number: int, code: str, **extra) -> dict:
    row = _bind(concept, number, evidence={"line_code": code}, **extra)
    return row


def _fcff_book(*, statement: bool, absent: frozenset[str] = frozenset()):
    ocf = _line("operating_cash_flow", 1, "стр. 4100", row_key="row-ocf", sheet="ОДДС" if statement else None)
    capex = _bind("capex", 2, row_key="row-capex")
    rate = _bind("income_tax_rate", 3, row_key="row-rate")
    paid = _line(
        "interest",
        4,
        "стр. 4123",
        is_primary=False,
        row_key="row-paid",
        binding_key="bk-paid",
    )
    facts = [
        {**_fact("row-ocf", "operating_cash_flow"), "normalized_value": "100", "cell_id": "S!A1"},
        {**_fact("row-capex", "capex"), "normalized_value": "-30", "cell_id": "S!B1"},
        {**_fact("row-paid", "interest"), "normalized_value": "-10", "cell_id": "S!C1"},
        {**_fact("row-rate", "income_tax_rate"), "normalized_value": "0.2", "cell_id": "S!D1"},
    ]
    sheets = frozenset({"ОДДС"}) if statement else frozenset()
    data = AuditInput(
        bindings=[ocf, capex, rate, paid],
        facts=facts,
        applicable_metrics=frozenset({"fcff"}),
        absent=absent,
        statement_sheets=sheets,
        graph_links_available=True,
    )
    return data


def _used_concepts(got: dict) -> set[str]:
    found: set[str] = set()
    for row in got.get("rows") or []:
        found.update(row.get("components") or {})
        found.update(row.get("inputs") or [])
    return found


def test_row_with_concept_and_no_effective_concept_matches_calculation_and_resolver():
    catalog = _catalog()
    expressions = {"dscr": MetricExpression(numerator_plus=("cfads",), denominator_plus=("debt_service",))}
    cfads = {
        "status": "bound",
        "is_primary": True,
        "concept": "cfads",
        "row_key": "row-cfads",
        "binding_key": "bk-cfads",
        "source": "inferred",
    }
    debt = {
        "status": "bound",
        "is_primary": True,
        "concept": "debt_service",
        "row_key": "row-debt",
        "binding_key": "bk-debt",
        "source": "inferred",
    }
    facts = [_fact("row-cfads", "cfads"), _fact("row-debt", "debt_service")]
    data = AuditInput(
        rows=[{"row_key": "row-cfads", "label": "cfads"}, {"row_key": "row-debt", "label": "debt"}],
        facts=facts,
        bindings=[cfads, debt],
        applicable_metrics=frozenset({"dscr"}),
        graph_links_available=True,
    )
    rows = _trace_rows("dscr", data, expressions, catalog)
    assert rows == {("cfads", "row-cfads"), ("debt_service", "row-debt")}
    assert rows == _origin_rows("dscr", data, expressions, catalog) == _resolved_rows("dscr", data, expressions, catalog)
    assert {concept for concept, _row in rows} == _core_rows("dscr", [cfads, debt], facts, catalog)


def test_two_concept_only_primaries_block_calculation_and_stay_ambiguous_on_the_trace():
    expressions = {"dscr": MetricExpression(numerator_plus=("cfads",), denominator_plus=("debt_service",))}
    first = {
        "status": "bound",
        "is_primary": True,
        "concept": "cfads",
        "row_key": "row-b",
        "binding_key": "bk-b",
        "source": "inferred",
    }
    second = {
        "status": "bound",
        "is_primary": True,
        "concept": "cfads",
        "row_key": "row-a",
        "binding_key": "bk-a",
        "source": "inferred",
    }
    debt = {
        "status": "bound",
        "is_primary": True,
        "concept": "debt_service",
        "row_key": "row-debt",
        "binding_key": "bk-debt",
        "source": "inferred",
    }
    facts = [_fact("row-a", "cfads"), _fact("row-b", "cfads"), _fact("row-debt", "debt_service")]
    got = coverage_ratio(
        metric="dscr",
        facts=facts,
        bindings=[first, second, debt],
        periods=[_period()],
        period_phase={},
        explicit_phases=False,
    )
    assert got["status"] == "needs_input"
    trace = trace_metric(
        "dscr",
        inputs=None,
        bindings=[first, second, debt],
        facts=facts,
        expressions=expressions,
    )
    step = next(item for item in trace.steps if item.concept == "cfads")
    assert step.binding_key == "bk-a"
    assert any(
        item.reason == "ambiguous_primary_binding" and item.binding_key == "bk-a"
        for item in trace.integrity
    )
    resolved = resolve_semantic_inputs("dscr", [first, second, debt], expressions)
    assert resolved is not None
    chosen = next(item for item in resolved if item.concept == "cfads")
    assert chosen.ambiguous is True
    assert chosen.binding_key == "bk-a"


def test_concept_only_4123_row_is_interest_paid_in_trace_origin_resolver_and_calculation():
    catalog = _catalog()
    expressions = _expressions()
    cfads = _bind("cfads", 1, row_key="row-cfads")
    principal = _bind("principal", 2, row_key="row-principal")
    paid = _concept_only([
        _line("interest", 3, "стр. 4123", is_primary=False, row_key="row-paid", binding_key="bk-paid")
    ])[0]
    data, bindings, facts = _book(
        [],
        extra=[cfads, principal, paid],
        variant="pf",
        metrics=frozenset({"dscr"}),
    )
    rows = _trace_rows("dscr", data, expressions, catalog)
    assert ("interest_paid", "row-paid") in rows
    assert rows == _origin_rows("dscr", data, expressions, catalog) == _resolved_rows("dscr", data, expressions, catalog)
    assert {concept for concept, _row in rows} == {"cfads", "interest_paid", "principal"}
    assert {concept for concept, _row in rows} == _components(_coverage("dscr", bindings, facts, catalog))


def test_fcff_shield_sees_concept_only_4123_row():
    catalog = _catalog()
    expressions = _expressions()
    data = _fcff_book(statement=True)
    paid = next(row for row in data.bindings if row["row_key"] == "row-paid")
    paid.pop("effective_concept")
    paid["concept"] = "interest"
    got = free_cash_flow(
        facts=data.facts,
        bindings=data.bindings,
        periods=[_period()],
        statement_sheets=data.statement_sheets,
    )
    assert "interest_paid" in _used_concepts(got)
    rows = _trace_rows("fcff", data, expressions, catalog)
    assert ("interest_paid", "row-paid") in rows
    assert rows == _origin_rows("fcff", data, expressions, catalog) == _resolved_rows("fcff", data, expressions, catalog)
    assert {concept for concept, _row in rows} == _used_concepts(got)


def test_dscr_fallback_uses_the_4123_row_in_trace_origin_resolver_and_calculation():
    catalog = _catalog()
    expressions = _expressions()
    cfads = _bind("cfads", 1, row_key="row-cfads")
    principal = _bind("principal", 2, row_key="row-principal")
    paid = _line("interest", 3, "стр. 4123", is_primary=False, row_key="row-paid", binding_key="bk-paid")
    data, bindings, facts = _book(
        [],
        extra=[cfads, principal, paid],
        variant="pf",
        metrics=frozenset({"dscr"}),
    )
    rows = _trace_rows("dscr", data, expressions, catalog)
    assert rows == _origin_rows("dscr", data, expressions, catalog) == _resolved_rows("dscr", data, expressions, catalog)
    assert {concept for concept, _row in rows} == {"cfads", "interest_paid", "principal"}
    assert ("interest_paid", "row-paid") in rows
    assert {concept for concept, _row in rows} == _components(_coverage("dscr", bindings, facts, catalog))


def test_existing_interest_paid_beats_a_4123_row_and_two_codes_inject_nothing():
    catalog = _catalog()
    expressions = _expressions()
    cfads = _bind("cfads", 1)
    principal = _bind("principal", 2)
    own = _bind("interest_paid", 3, row_key="row-own", binding_key="bk-own")
    coded = _line("interest", 4, "стр. 4123", is_primary=False, row_key="row-coded", binding_key="bk-coded")
    data, bindings, facts = _book([], extra=[cfads, principal, own, coded], variant="pf", metrics=frozenset({"dscr"}))
    rows = _trace_rows("dscr", data, expressions, catalog)
    assert ("interest_paid", "row-own") in rows
    assert ("interest_paid", "row-coded") not in rows
    assert rows == _origin_rows("dscr", data, expressions, catalog) == _resolved_rows("dscr", data, expressions, catalog)
    assert {concept for concept, _row in rows} == _components(_coverage("dscr", bindings, facts, catalog))

    first = _line("interest", 5, "стр. 4123", is_primary=False, row_key="row-a", binding_key="bk-a")
    second = _line("interest", 6, "стр. 4123", is_primary=False, row_key="row-b", binding_key="bk-b")
    empty, empty_bindings, empty_facts = _book(
        [],
        extra=[_bind("cfads", 7), _bind("principal", 8), first, second],
        variant="pf",
        metrics=frozenset({"dscr"}),
    )
    missed = _resolved_rows("dscr", empty, expressions, catalog)
    assert "row-a" not in {row for _concept, row in missed}
    assert "row-b" not in {row for _concept, row in missed}
    refused = _coverage("dscr", empty_bindings, empty_facts, catalog)
    assert _components(refused) == set()
    assert "interest_paid" not in set(refused.get("missing_inputs") or [])
    assert missed == _trace_rows("dscr", empty, expressions, catalog) == _origin_rows("dscr", empty, expressions, catalog)


def test_fcff_shield_uses_the_same_4123_row_everywhere():
    catalog = _catalog()
    expressions = _expressions()
    data = _fcff_book(statement=True)
    got = free_cash_flow(
        facts=data.facts,
        bindings=data.bindings,
        periods=[_period()],
        statement_sheets=data.statement_sheets,
    )
    core = _used_concepts(got)
    assert "interest_paid" in core
    rows = _trace_rows("fcff", data, expressions, catalog)
    assert rows == _origin_rows("fcff", data, expressions, catalog) == _resolved_rows("fcff", data, expressions, catalog)
    assert {concept for concept, _row in rows} == core
    assert ("interest_paid", "row-paid") in rows
    trace = trace_metric(
        "fcff",
        inputs=None,
        bindings=data.bindings,
        facts=data.facts,
        expressions=expressions,
        statement_sheets=data.statement_sheets,
        interest_order=catalog.interest_order,
        row_fallbacks=catalog.row_fallbacks,
    )
    assert [step.concept for step in trace.steps if step.row_key == "row-paid"] == ["interest_paid"]


def test_fcff_without_a_shield_does_not_take_the_4123_row():
    catalog = _catalog()
    expressions = _expressions()
    data = _fcff_book(statement=False)
    got = free_cash_flow(
        facts=data.facts,
        bindings=data.bindings,
        periods=[_period()],
        statement_sheets=data.statement_sheets,
    )
    assert "interest_paid" not in _used_concepts(got)
    rows = _trace_rows("fcff", data, expressions, catalog)
    assert "interest_paid" not in {concept for concept, _row in rows}
    assert ("interest_paid", "row-paid") not in rows
    assert rows == _origin_rows("fcff", data, expressions, catalog) == _resolved_rows("fcff", data, expressions, catalog)


# Строки, которые читают сохранённое поле не как понятие расчёта.
_STORED_CONCEPT_READS = (
    'return str(row.get("effective_concept") or row.get("concept") or "")',
    '_concept(row.get("concept")), _concept(row.get("effective_concept"))',
    'concept not in {row.get("concept"), row.get("effective_concept")}',
    'prev.get("effective_concept")',
    '"to": {"status": row.get("status"), "concept": row.get("effective_concept")}',
)


def test_row_concept_is_not_read_beside_declared_concept():
    """Понятие строки решает declared_concept. Прямое чтение поля остаётся только у определения и у сверки сохранённой колонки."""

    import re
    from pathlib import Path

    pattern = re.compile(r"""\.get\(\s*["']effective_concept["']\s*\)""")
    root = Path("src/finance_analysis")
    offenders = []
    for path in sorted(root.rglob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not pattern.search(line):
                continue
            if any(snippet in line for snippet in _STORED_CONCEPT_READS):
                continue
            offenders.append(f"{path.relative_to(root)}:{number}: {line.strip()}")
    assert offenders == []
