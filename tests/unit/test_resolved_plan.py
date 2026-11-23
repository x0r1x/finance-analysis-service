"""План разрешения: один объект, три списка, полный хеш."""

from decimal import Decimal

import pytest

from finance_analysis.domain.audit import AuditInput
from finance_analysis.domain.formula_origin import origin_view
from finance_analysis.domain.free_cash_flow import free_cash_flow
from finance_analysis.domain.graphs import trace_metric
from finance_analysis.domain.metrics import coverage_ratio
from finance_analysis.domain.model_type import MetricExpression
from finance_analysis.domain.semantic_input import (
    resolve_metric_plan,
    resolve_semantic_inputs,
)

EXPRESSIONS = {
    "dscr": MetricExpression(numerator_plus=("cfads",), denominator_plus=("debt_service",)),
    "icr": MetricExpression(
        one_of=frozenset({"ebitda", "ebit"}),
        one_of_order=("ebitda", "ebit"),
        denominator_plus=("interest",),
    ),
}


def _bind(concept: str, number: int, **extra) -> dict:
    return {
        "status": "bound",
        "is_primary": True,
        "effective_concept": concept,
        "row_key": extra.pop("row_key", f"S|{number}|a"),
        "binding_key": extra.pop("binding_key", f"bk-{concept}-{number}"),
        "source": "inferred",
        **extra,
    }


def test_confirmed_inputs_match_the_resolver_and_diagnostic_is_separate():
    first = _bind("cfads", 1, binding_key="bk-b", row_key="row-b")
    second = _bind("cfads", 2, binding_key="bk-a", row_key="row-a")
    debt = _bind("debt_service", 3)
    bindings = [first, second, debt]
    plan = resolve_metric_plan("dscr", bindings, EXPRESSIONS, catalog_version="cat", build_key="bld")
    resolved = resolve_semantic_inputs("dscr", bindings, EXPRESSIONS)
    assert plan is not None and resolved is not None
    assert plan.status == "needs_input"
    assert [item.concept for item in plan.inputs] == ["debt_service"]
    assert all(item.confirmed and not item.ambiguous for item in plan.inputs)
    assert plan.diagnostic[0].concept == "cfads"
    assert plan.diagnostic[0].binding_key == "bk-a"
    assert plan.diagnostic[0].reason == "ambiguous_primary_binding"
    assert {item.binding_key for item in plan.rejected} == {"bk-b"}
    assert plan.needs_input[0].subject == "cfads"
    assert plan.needs_input[0].reason == "ambiguous"
    confirmed = {item.concept for item in resolved if not item.ambiguous and item.row_key}
    assert {item.concept for item in plan.inputs} == confirmed


def test_hash_uses_engine_version_and_ignores_semantic_model_version_and_array_order():
    bindings = [_bind("cfads", 1), _bind("debt_service", 2)]
    left = resolve_metric_plan(
        "dscr",
        bindings,
        EXPRESSIONS,
        semantic_model_version="smv-a",
    )
    right = resolve_metric_plan(
        "dscr",
        list(reversed(bindings)),
        EXPRESSIONS,
        semantic_model_version="smv-b",
    )
    assert left is not None and right is not None
    assert left.content_sha256 == right.content_sha256
    assert left.plan_id == left.content_sha256[:16]
    assert len(left.plan_id) == 16
    assert left.semantic_model_version == "smv-a"
    assert left.resolution_engine_version
    assert "semantic_model_version" not in left.content_sha256


def test_missing_input_source_and_role_change_plan_identity():
    """Строка без row_key живёт только в lineage. Её source и role меняют хеш."""

    from finance_analysis.domain.resolved_plan import LineageRow, NeedsInput, seal

    common = {
        "metric_id": "dscr",
        "variant": None,
        "variant_source": "formula",
        "catalog_version": None,
        "semantic_model_version": "smv-a",
        "build_key": None,
        "model_id": None,
        "status": "missing_input",
        "inputs": (),
        "diagnostic": (),
        "rejected": (),
        "fallbacks": (),
        "warnings": (),
        "needs_input": (NeedsInput("concept", "concept_unknown", "cfads"),),
        "shield": None,
    }
    formula = LineageRow("cfads", "formula", "all_of", None, None, "concept_unknown", False)
    fallback = LineageRow("cfads", "fallback", "one_of", None, None, "concept_unknown", False)
    left = seal(**common, lineage=(formula,))
    right = seal(**common, lineage=(fallback,))
    other_version = seal(**{**common, "semantic_model_version": "smv-b"}, lineage=(formula,))
    reordered = seal(
        **common,
        lineage=(
            LineageRow("debt_service", "formula", "all_of", None, None, "concept_unknown", False),
            formula,
        ),
    )
    same = seal(
        **common,
        lineage=(
            formula,
            LineageRow("debt_service", "formula", "all_of", None, None, "concept_unknown", False),
        ),
    )
    assert left.content_sha256 != right.content_sha256
    assert left.content_sha256 == other_version.content_sha256
    assert reordered.content_sha256 == same.content_sha256


def test_engine_version_changes_the_digest():
    from finance_analysis.domain.resolved_plan import content_digest

    body = {"resolution_engine_version": "1", "metric_id": "dscr", "inputs": []}
    assert content_digest(body) != content_digest({**body, "resolution_engine_version": "2"})


def test_reader_stamp_is_in_the_hash_and_semantic_model_version_is_not():
    """Как читается строка, входит в хеш. Целый SMV — нет."""

    from finance_analysis.domain.resolved_plan import (
        content_digest,
        hashed_body,
        input_read_stamp,
    )

    assert input_read_stamp()
    bindings = [_bind("cfads", 1), _bind("debt_service", 2)]
    left = resolve_metric_plan("dscr", bindings, EXPRESSIONS, semantic_model_version="smv-a")
    right = resolve_metric_plan("dscr", bindings, EXPRESSIONS, semantic_model_version="smv-b")
    assert left is not None and right is not None
    assert left.content_sha256 == right.content_sha256
    body = hashed_body(
        resolution_engine_version=left.resolution_engine_version,
        metric_id=left.metric_id,
        variant=left.variant,
        variant_source=left.variant_source,
        catalog_version=left.catalog_version,
        build_key=left.build_key,
        model_id=left.model_id,
        status=left.status,
        inputs=left.inputs,
        diagnostic=left.diagnostic,
        rejected=left.rejected,
        fallbacks=left.fallbacks,
        warnings=left.warnings,
        needs_input=left.needs_input,
        shield=left.shield,
        lineage=left.lineage,
    )
    assert body["input_read_stamp"] == input_read_stamp()
    assert "semantic_model_version" not in body
    assert content_digest(body) == left.content_sha256
    changed = {**body, "input_read_stamp": "0" * 16}
    assert content_digest(changed) != left.content_sha256


def test_resolution_stamp_covers_every_selection_function():
    """Штамп входит в content_sha256. Смена версии движка двигает штамп при тех же исходниках."""

    import hashlib
    import inspect

    import finance_analysis.domain.semantic_input as engine
    from finance_analysis.domain.resolved_plan import (
        RESOLUTION_ENGINE_VERSION,
        content_digest,
        declared_resolution_dependencies,
        hashed_body,
        input_read_stamp,
    )

    source = inspect.getsource(engine)
    text = "\n".join(
        [
            RESOLUTION_ENGINE_VERSION,
            source,
            *(f"{name}\n{_dependency_text(obj)}" for name, obj in declared_resolution_dependencies()),
        ]
    )
    stamp = input_read_stamp()
    assert stamp == hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    assert len(stamp) == 16
    body = hashed_body(
        resolution_engine_version=RESOLUTION_ENGINE_VERSION,
        metric_id="dscr",
        variant=None,
        variant_source="formula",
        catalog_version=None,
        build_key=None,
        model_id=None,
        status="resolved",
        inputs=(),
        diagnostic=(),
        rejected=(),
        fallbacks=(),
        warnings=(),
        needs_input=(),
        shield=None,
    )
    assert body["input_read_stamp"] == stamp
    assert "semantic_model_version" not in body
    assert content_digest(body) != content_digest({**body, "input_read_stamp": "0" * 16})
    bumped = text.replace(RESOLUTION_ENGINE_VERSION, RESOLUTION_ENGINE_VERSION + "-other", 1)
    assert hashlib.sha256(bumped.encode("utf-8")).hexdigest()[:16] != stamp


def test_stamp_hashes_the_engine_module_and_declared_dependencies():
    """Новая функция модуля меняет штамп сама. Новый внешний вызов без объявления не проходит."""

    import ast
    import hashlib
    import inspect

    import finance_analysis.domain.semantic_input as engine
    from finance_analysis.domain.resolved_plan import (
        RESOLUTION_ENGINE_VERSION,
        declared_resolution_dependencies,
        input_read_stamp,
    )

    source = inspect.getsource(engine)
    for name in (
        "_visible",
        "_materialize",
        "_with_confirmed_paid",
        "_with_shield",
        "_active",
        "_split",
        "_outcome",
        "_coverage_status",
    ):
        assert f"def {name}(" in source
    dependencies = declared_resolution_dependencies()
    text = "\n".join(
        [
            RESOLUTION_ENGINE_VERSION,
            source,
            *(f"{name}\n{_dependency_text(obj)}" for name, obj in dependencies),
        ]
    )
    stamp = input_read_stamp()
    assert stamp == hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    added = text + "\ndef _new_influence():\n    return None\n"
    assert hashlib.sha256(added.encode("utf-8")).hexdigest()[:16] != stamp

    imported = _imported_project_names(ast.parse(source))
    used = _loaded_names(ast.parse(source), imported)
    used.discard("RESOLUTION_ENGINE_VERSION")
    assert used == {name for name, _obj in dependencies}


def _dependency_text(obj: object) -> str:
    import inspect

    if inspect.isfunction(obj) or inspect.isclass(obj):
        return inspect.getsource(obj)
    if isinstance(obj, (set, frozenset)):
        return repr(tuple(sorted(obj)))
    raise TypeError(type(obj))


def _imported_project_names(tree: object) -> set[str]:
    import ast

    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("finance_analysis."):
            names.update(alias.asname or alias.name for alias in node.names)
    return names


def _loaded_names(tree: object, imported: set[str]) -> set[str]:
    import ast

    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id in imported:
            found.add(node.id)
    return found


def test_trace_and_origin_read_one_plan_and_do_not_select(monkeypatch):
    bindings = [_bind("ebitda", 1), _bind("ebit", 2), _bind("interest", 3)]
    facts = [{"row_key": "S|1|a", "cell_id": "P&L!D12"}]
    plan = resolve_metric_plan("icr", bindings, EXPRESSIONS, facts=facts)
    assert plan is not None
    before = trace_metric(
        "icr",
        inputs=None,
        bindings=bindings,
        facts=facts,
        expressions=EXPRESSIONS,
    )

    def boom(*_args, **_kwargs):
        raise AssertionError("selection repeated")

    for module, name in (
        ("finance_analysis.domain.binding_resolution", "select_primary"),
        ("finance_analysis.domain.metrics", "choose_one_of"),
        ("finance_analysis.domain.metrics", "dscr_denominator_plan"),
        ("finance_analysis.domain.metrics", "interest_choice"),
        ("finance_analysis.domain.metrics", "confirm_paid_interest"),
        ("finance_analysis.domain.free_cash_flow", "shield_concepts"),
        ("finance_analysis.domain.free_cash_flow", "_basis"),
        ("finance_analysis.domain.semantic_input", "resolve_semantic_inputs"),
        ("finance_analysis.domain.semantic_input", "resolve_metric_plan"),
        ("finance_analysis.domain.formula_origin", "resolve_semantic_inputs"),
    ):
        monkeypatch.setattr(f"{module}.{name}", boom)

    traced = trace_metric(
        "icr",
        inputs=None,
        bindings=bindings,
        facts=facts,
        expressions=EXPRESSIONS,
        plan=plan,
    )
    assert [(step.concept, step.row_key) for step in traced.steps] == [
        (step.concept, step.row_key) for step in before.steps
    ]
    ebitda = next(step for step in traced.steps if step.concept == "ebitda")
    assert ebitda.cell_ids == ("P&L!D12",)
    assert "plan_id" not in traced.as_dict()
    view = origin_view(
        AuditInput(bindings=list(bindings), facts=list(facts), applicable_metrics=frozenset({"icr"})),
        [],
        EXPRESSIONS,
        plans={"icr": plan},
    )
    assert "plan_id" not in view
    with pytest.raises(AssertionError, match="selection repeated"):
        origin_view(
            AuditInput(bindings=list(bindings), applicable_metrics=frozenset({"icr"})),
            [],
            EXPRESSIONS,
        )


def _period() -> dict:
    return {"axis_id": "a", "period_id": "Y1", "period_index": 1, "grain": "year", "timeline_id": "t"}


def _fact(row_key: str, concept: str) -> dict:
    return {
        "row_key": row_key,
        "axis_id": "a",
        "period_id": "Y1",
        "normalized_value": "40",
        "cell_id": f"S!{concept}",
    }


def _silence(monkeypatch) -> None:
    def boom(*_args, **_kwargs):
        raise AssertionError("selection repeated")

    for module, name in (
        ("finance_analysis.domain.binding_resolution", "select_primary"),
        ("finance_analysis.domain.metrics", "choose_one_of"),
        ("finance_analysis.domain.metrics", "dscr_denominator_plan"),
        ("finance_analysis.domain.metrics", "interest_choice"),
        ("finance_analysis.domain.metrics", "confirm_paid_interest"),
        ("finance_analysis.domain.free_cash_flow", "shield_concepts"),
        ("finance_analysis.domain.free_cash_flow", "_basis"),
        ("finance_analysis.domain.semantic_input", "resolve_metric_plan"),
    ):
        monkeypatch.setattr(f"{module}.{name}", boom)


def test_calculators_read_the_plan_and_do_not_select(monkeypatch):
    bindings = [_bind("ebitda", 1), _bind("ebit", 2), _bind("interest", 3)]
    facts = [_fact(row["row_key"], row["effective_concept"]) for row in bindings]
    periods = [_period()]
    plan = resolve_metric_plan("icr", bindings, EXPRESSIONS)
    assert plan is not None and plan.status == "resolved"
    assert plan.shield is None
    before = coverage_ratio(
        metric="icr",
        facts=facts,
        bindings=bindings,
        periods=periods,
        period_phase={},
        explicit_phases=False,
    )
    blocked = [
        _bind("cfads", 1, binding_key="bk-b", row_key="row-b"),
        _bind("cfads", 2, binding_key="bk-a", row_key="row-a"),
        _bind("debt_service", 3),
    ]
    blocked_plan = resolve_metric_plan("dscr", blocked, EXPRESSIONS)
    blocked_before = coverage_ratio(
        metric="dscr",
        facts=[_fact(row["row_key"], "cfads") for row in blocked],
        bindings=blocked,
        periods=periods,
        period_phase={},
        explicit_phases=False,
    )
    ocf = _bind("operating_cash_flow", 1)
    capex = _bind("capex", 2)
    fcff_bindings = [ocf, capex]
    fcff_facts = [_fact(row["row_key"], row["effective_concept"]) for row in fcff_bindings]
    fcff_plan = resolve_metric_plan(
        "fcff",
        fcff_bindings,
        None,
        inputs={"all_of": ("operating_cash_flow", "capex")},
    )
    assert fcff_plan is not None and fcff_plan.shield is not None
    assert fcff_plan.shield.basis == "unknown"
    fcff_before = free_cash_flow(facts=fcff_facts, bindings=fcff_bindings, periods=periods)
    _silence(monkeypatch)
    after = coverage_ratio(
        metric="icr",
        facts=facts,
        bindings=bindings,
        periods=periods,
        period_phase={},
        explicit_phases=False,
        plan=plan,
    )
    assert after["status"] == before["status"] == "succeeded"
    assert after["rows"] == before["rows"]
    assert after["warnings"] == before["warnings"]
    blocked_after = coverage_ratio(
        metric="dscr",
        facts=[_fact(row["row_key"], "cfads") for row in blocked],
        bindings=blocked,
        periods=periods,
        period_phase={},
        explicit_phases=False,
        plan=blocked_plan,
    )
    assert blocked_after["status"] == blocked_before["status"] == "needs_input"
    assert blocked_after["needs_input"] == blocked_before["needs_input"]
    assert blocked_after["missing_inputs"] == blocked_before["missing_inputs"]
    fcff_after = free_cash_flow(
        facts=fcff_facts,
        bindings=fcff_bindings,
        periods=periods,
        plan=fcff_plan,
    )
    assert fcff_after["status"] == fcff_before["status"]
    assert [row["status"] for row in fcff_after["rows"]] == [row["status"] for row in fcff_before["rows"]]


def test_covenant_reads_the_plan_and_ratios_primary_does_not_select(monkeypatch):
    from finance_analysis.application.model_types import (
        load_metric_catalog,
        load_model_types,
    )
    from finance_analysis.domain.covenant import covenant_dscr
    from finance_analysis.plugins.rules.ratios import _primary

    catalog = load_model_types()
    _inputs, _variants, _composed, _bases, _rates, expressions = load_metric_catalog()
    bindings = [
        _bind("ebitda", 1, row_key="e"),
        _bind("cash_taxes", 2, row_key="t"),
        _bind("capex", 3, row_key="c"),
        _bind("interest", 4, row_key="i"),
        _bind("principal", 5, row_key="p"),
    ]
    facts = [
        _fact("e", "ebitda") | {"normalized_value": "100"},
        _fact("t", "cash_taxes") | {"normalized_value": "10"},
        _fact("c", "capex") | {"normalized_value": "20"},
        _fact("i", "interest") | {"normalized_value": "15"},
        _fact("p", "principal") | {"normalized_value": "5"},
    ]
    periods = [_period()]
    plan = resolve_metric_plan(
        "dscr",
        bindings,
        expressions,
        variant="corporate_covenant",
        interest_order=catalog.interest_order,
        row_fallbacks=catalog.row_fallbacks,
    )
    assert plan is not None and plan.status == "resolved"
    before = covenant_dscr(
        facts=facts,
        bindings=bindings,
        periods=periods,
        default=catalog.composed["dscr.corporate_covenant"],
        concepts=frozenset({"ebitda", "cash_taxes", "capex", "interest", "principal", "dscr"}),
        money=frozenset({"ebitda", "cash_taxes", "capex", "interest", "principal"}),
        interest_order=catalog.interest_order,
        row_fallbacks=catalog.row_fallbacks,
    )
    data = AuditInput(bindings=list(bindings), plans={"dscr": plan})
    stale = _bind("cfads", 9, stale=True, row_key="stale")
    stale_data = AuditInput(bindings=[stale])
    assert _primary(stale_data, "cfads")["row_key"] == "stale"
    _silence(monkeypatch)

    def boom(*_args, **_kwargs):
        raise AssertionError("selection repeated")

    monkeypatch.setattr("finance_analysis.domain.covenant.confirm_paid_interest", boom)
    monkeypatch.setattr("finance_analysis.domain.covenant.interest_choice", boom)
    after = covenant_dscr(
        facts=facts,
        bindings=bindings,
        periods=periods,
        default=catalog.composed["dscr.corporate_covenant"],
        concepts=frozenset({"ebitda", "cash_taxes", "capex", "interest", "principal", "dscr"}),
        money=frozenset({"ebitda", "cash_taxes", "capex", "interest", "principal"}),
        interest_order=catalog.interest_order,
        row_fallbacks=catalog.row_fallbacks,
        plan=plan,
    )
    assert after["rows"] == before["rows"]
    assert after["definition_source"] == before["definition_source"]
    assert _primary(data, "ebitda", metric="dscr")["row_key"] == "e"
    assert _primary(data, "dscr", metric="dscr") is None


def _corporate():
    from finance_analysis.application.model_types import (
        load_metric_catalog,
        load_model_types,
    )

    catalog = load_model_types()
    _inputs, _variants, composed, _bases, _rates, expressions = load_metric_catalog()
    return catalog, composed, expressions


def _covenant(catalog, composed, **extra):
    from finance_analysis.domain.covenant import covenant_dscr

    body = {
        "facts": extra.pop("facts"),
        "bindings": extra.pop("bindings"),
        "periods": [_period()],
        "default": composed["dscr.corporate_covenant"],
        "concepts": frozenset({"ebitda", "cash_taxes", "capex", "interest", "principal", "operating_cash_flow", "dscr"}),
        "money": frozenset({"ebitda", "cash_taxes", "capex", "interest", "principal", "operating_cash_flow"}),
        "interest_order": catalog.interest_order,
        "row_fallbacks": catalog.row_fallbacks,
        "composed": composed,
    }
    body.update(extra)
    return covenant_dscr(**body)


def test_ambiguous_covenant_binding_is_not_calculated(monkeypatch):
    """Неоднозначный вход ковенанта не даёт число, и выбор не повторяется."""

    catalog, composed, expressions = _corporate()
    bindings = [
        _bind("ebitda", 1, row_key="e"),
        _bind("ebitda", 2, row_key="e2"),
        _bind("cash_taxes", 3, row_key="t"),
        _bind("capex", 4, row_key="c"),
        _bind("interest", 5, row_key="i"),
        _bind("principal", 6, row_key="p"),
    ]
    facts = [
        _fact("e", "ebitda") | {"normalized_value": "100"},
        _fact("e2", "ebitda") | {"normalized_value": "999"},
        _fact("t", "cash_taxes") | {"normalized_value": "10"},
        _fact("c", "capex") | {"normalized_value": "20"},
        _fact("i", "interest") | {"normalized_value": "15"},
        _fact("p", "principal") | {"normalized_value": "5"},
    ]
    plan = resolve_metric_plan(
        "dscr",
        bindings,
        expressions,
        variant="corporate_covenant",
        interest_order=catalog.interest_order,
        row_fallbacks=catalog.row_fallbacks,
    )
    assert plan is not None and plan.status == "needs_input"

    def boom(*_args, **_kwargs):
        raise AssertionError("selection repeated")

    monkeypatch.setattr("finance_analysis.domain.covenant._primaries", boom)
    monkeypatch.setattr("finance_analysis.domain.cover_metrics._primaries", boom)
    got = _covenant(catalog, composed, facts=facts, bindings=bindings, plan=plan)
    assert got["status"] == "needs_input"
    assert got["rows"] == []


def test_missing_plan_blocks_a_profile_formula_that_could_still_be_divided():
    """missing_input плана не доходит до деления, даже если состав профиля полный."""

    catalog, composed, expressions = _corporate()
    bindings = [
        _bind("ebitda", 1, row_key="e"),
        _bind("cash_taxes", 2, row_key="t"),
        _bind("capex", 3, row_key="c"),
        _bind("interest", 4, row_key="i"),
    ]
    facts = [
        _fact("e", "ebitda") | {"normalized_value": "100"},
        _fact("t", "cash_taxes") | {"normalized_value": "10"},
        _fact("c", "capex") | {"normalized_value": "20"},
        _fact("i", "interest") | {"normalized_value": "15"},
    ]
    plan = resolve_metric_plan(
        "dscr",
        bindings,
        expressions,
        variant="corporate_covenant",
        interest_order=catalog.interest_order,
        row_fallbacks=catalog.row_fallbacks,
    )
    assert plan is not None and plan.status == "missing_input"
    profile = {
        "dscr_definition": {
            "numerator": {"plus": ["ebitda"], "minus": []},
            "denominator": {"plus": ["interest"], "minus": []},
            "window": "period",
        }
    }
    got = _covenant(
        catalog,
        composed,
        facts=facts,
        bindings=bindings,
        profile=profile,
        plan=plan,
    )
    assert got["status"] == "missing_input"
    assert got["rows"] == []


def test_profile_definition_builds_a_plan_from_that_composition():
    """Состав профиля строит план из своих понятий, а не из формулы каталога."""

    from finance_analysis.domain.covenant import profile_dscr_expression
    from finance_analysis.domain.semantic_input import plans_for

    catalog, composed, expressions = _corporate()
    profile = {
        "dscr_definition": {
            "numerator": {"plus": ["ebitda"], "minus": []},
            "denominator": {"plus": ["interest"], "minus": []},
            "window": "period",
        }
    }
    bindings = [
        _bind("ebitda", 1, row_key="e"),
        _bind("cash_taxes", 2, row_key="t"),
        _bind("interest", 3, row_key="i"),
    ]
    facts = [
        _fact("e", "ebitda") | {"normalized_value": "100"},
        _fact("t", "cash_taxes") | {"normalized_value": "10"},
        _fact("i", "interest") | {"normalized_value": "15"},
    ]
    plans = plans_for(
        ["dscr"],
        bindings,
        expressions,
        dscr_variant="corporate_covenant",
        dscr_expression=profile_dscr_expression(profile),
        interest_order=catalog.interest_order,
        row_fallbacks=catalog.row_fallbacks,
    )
    plan = plans["dscr"]
    assert {item.concept for item in plan.inputs} == {"ebitda", "interest"}
    assert plan.status == "resolved"
    got = _covenant(
        catalog,
        composed,
        facts=facts,
        bindings=bindings,
        profile=profile,
        plan=plan,
    )
    assert got["status"] == "succeeded"
    assert got["definition_source"] == "profile"
    assert got["rows"][0]["value"] == Decimal("6.6666666667")
    assert got["rows"][0]["inputs"] == ["ebitda", "interest"]


def test_composed_ratio_does_not_enlarge_confirmed_inputs():
    """Формула шире плана не подтягивает лишнее понятие из привязок."""

    from finance_analysis.domain.covenant import composed_ratio
    from finance_analysis.domain.model_type import Composed, Side

    bindings = [
        _bind("ebitda", 1, row_key="e"),
        _bind("interest", 2, row_key="i"),
        _bind("operating_cash_flow", 3, row_key="o"),
    ]
    facts = [
        _fact("e", "ebitda") | {"normalized_value": "100"},
        _fact("i", "interest") | {"normalized_value": "15"},
        _fact("o", "operating_cash_flow") | {"normalized_value": "40"},
    ]
    plan = resolve_metric_plan(
        "dscr",
        bindings,
        None,
        inputs={"all_of": ("ebitda", "interest")},
    )
    assert plan is not None and plan.status == "resolved"
    formula = Composed(Side(("ebitda", "operating_cash_flow"), ()), Side(("interest",), ()), "period")
    got = composed_ratio(
        "dscr",
        formula,
        facts=facts,
        bindings=bindings,
        periods=[_period()],
        plan=plan,
    )
    assert got["status"] == "missing_input"
    assert got["rows"] == []
    assert "operating_cash_flow" in got["missing_inputs"]


def test_one_plan_is_reused_and_trace_keeps_the_full_context(monkeypatch):
    from finance_analysis.domain.semantic_input import plans_for

    bindings = [_bind("ebitda", 1), _bind("interest", 2)]
    facts = [_fact(row["row_key"], row["effective_concept"]) for row in bindings]
    plans = plans_for(
        ["icr"],
        bindings,
        EXPRESSIONS,
        facts=facts,
        links=[{"cell": "S!ebitda", "ref_cell": "S!A1"}],
        statement_sheets=frozenset({"ОПиУ"}),
        interest_order={"icr": ("interest",)},
        catalog_version="cat",
        build_key="bld",
    )
    plan = plans["icr"]
    assert plan is plans["icr"]
    assert plan.catalog_version == "cat"
    assert plan.build_key == "bld"

    def boom(*_args, **_kwargs):
        raise AssertionError("selection repeated")

    monkeypatch.setattr("finance_analysis.domain.semantic_input.resolve_metric_plan", boom)
    monkeypatch.setattr("finance_analysis.domain.formula_origin.resolve_semantic_inputs", boom)
    traced = trace_metric(
        "icr",
        inputs=None,
        bindings=bindings,
        facts=facts,
        expressions=EXPRESSIONS,
        plan=plan,
    )
    assert any(step.cell_ids for step in traced.steps)
    origin_view(
        AuditInput(bindings=list(bindings), facts=list(facts), applicable_metrics=frozenset({"icr"})),
        [],
        EXPRESSIONS,
        plans=plans,
    )


def test_icr_keeps_only_the_chosen_numerator_in_inputs():
    bindings = [_bind("ebitda", 1), _bind("ebit", 2), _bind("interest", 3)]
    plan = resolve_metric_plan("icr", bindings, EXPRESSIONS)
    assert plan is not None
    assert plan.status == "resolved"
    assert {item.concept for item in plan.inputs} == {"ebitda", "interest"}
    assert {item.concept for item in plan.rejected} >= {"ebit"}
    assert any(item.reason == "not_selected_one_of" for item in plan.rejected)


def test_unused_alternative_ambiguity_does_not_set_status():
    """Статус — проекция выбранных входов. Вторая группировка ebit статус не меняет."""

    bindings = [
        _bind("ebitda", 1),
        _bind("ebit", 2),
        _bind("ebit", 3),
        _bind("interest", 4),
    ]
    plan = resolve_metric_plan("icr", bindings, EXPRESSIONS)
    assert plan is not None
    assert plan.status == "resolved"
    assert {item.concept for item in plan.inputs} == {"ebitda", "interest"}
    assert all(item.subject != "ebit" for item in plan.needs_input)


def test_stale_sole_row_is_not_an_input_when_a_plan_exists():
    """Правило одно: план подтверждает вход. Без плана остаётся старый просмотр."""

    from finance_analysis.plugins.rules.ratios import _primary

    stale = _bind("cfads", 1, stale=True, row_key="stale")
    debt = _bind("debt_service", 2, row_key="debt")
    plan = resolve_metric_plan("dscr", [stale, debt], EXPRESSIONS)
    assert plan is not None
    assert "cfads" not in {item.concept for item in plan.inputs}
    legacy = _primary(AuditInput(bindings=[stale]), "cfads")
    assert legacy is not None and legacy["row_key"] == "stale"
    assert _primary(AuditInput(bindings=[stale, debt], plans={"dscr": plan}), "cfads", "dscr") is None


def test_stale_cfads_fails_ratio_precheck_when_the_plan_does_not_confirm_it(monkeypatch):
    """Предпроверка DSCR читает план. Кэшированная строка модели в inputs не входит."""

    from finance_analysis.plugins.rules.ratios import RATIO_MISMATCH

    stale = _bind("cfads", 1, stale=True, row_key="stale")
    debt = _bind("debt_service", 2, row_key="debt")
    model = _bind("dscr", 3, row_key="model")
    plan = resolve_metric_plan("dscr", [stale, debt, model], EXPRESSIONS)
    assert plan is not None
    assert "cfads" not in {item.concept for item in plan.inputs}
    assert "dscr" not in {item.concept for item in plan.inputs}

    def _forbidden(**_kwargs):
        raise AssertionError("формула не считается, пока план не подтвердил CFADS")

    monkeypatch.setattr("finance_analysis.plugins.rules.ratios.coverage_ratio", _forbidden)
    data = AuditInput(bindings=[stale, debt, model], plans={"dscr": plan})
    assert RATIO_MISMATCH.check(data) == []


def test_concept_outside_the_plan_is_not_selected_again():
    """Понятие вне плана не читается через _groups и _primaries."""

    from finance_analysis.plugins.rules.coverage import _primary

    bindings = [
        _bind("cfads", 1, row_key="c"),
        _bind("debt_service", 2, row_key="d"),
        _bind("target_dscr", 3, row_key="target"),
    ]
    plan = resolve_metric_plan("dscr", bindings, EXPRESSIONS)
    assert plan is not None
    assert "target_dscr" not in {item.concept for item in plan.inputs}
    with_plan = AuditInput(bindings=list(bindings), plans={"dscr": plan})
    assert _primary(with_plan, "target_dscr") is None
    assert _primary(with_plan, "cfads")["row_key"] == "c"
    assert _primary(AuditInput(bindings=list(bindings)), "target_dscr")["row_key"] == "target"


def test_ambiguous_row_without_binding_key_is_not_calculated():
    """Неоднозначная строка без binding_key не становится подтверждённым входом."""

    first = _bind("cfads", 1, binding_key="", row_key="row-cfads-a")
    second = _bind("cfads", 2, binding_key="", row_key="row-cfads-b")
    debt = _bind("debt_service", 3)
    bindings = [first, second, debt]
    plan = resolve_metric_plan("dscr", bindings, EXPRESSIONS)
    assert plan is not None
    assert "cfads" not in {item.concept for item in plan.inputs}
    assert all(item.binding_key for item in plan.inputs)
    diagnostic = next(item for item in plan.diagnostic if item.concept == "cfads")
    assert diagnostic.binding_key is None
    assert diagnostic.row_key in {"row-cfads-a", "row-cfads-b"}
    got = coverage_ratio(
        metric="dscr",
        facts=[_fact(row["row_key"], row["effective_concept"]) for row in bindings],
        bindings=bindings,
        periods=[_period()],
        period_phase={},
        explicit_phases=False,
        plan=plan,
    )
    assert got["rows"] == []
    assert got["status"] == "needs_input"
    assert "row-cfads-a" not in str(got)
    assert "row-cfads-b" not in str(got)


def test_plan_uses_row_key_when_binding_key_is_absent():
    """План без binding_key находит строку по row_key и считает её."""

    from finance_analysis.domain.resolved_plan import bound_rows

    cfads = _bind("cfads", 1, binding_key="", row_key="row-cfads")
    debt = _bind("debt_service", 2, row_key="row-debt")
    bindings = [cfads, debt]
    plan = resolve_metric_plan("dscr", bindings, EXPRESSIONS)
    assert plan is not None and plan.status == "resolved"
    chosen = next(item for item in plan.inputs if item.concept == "cfads")
    assert chosen.binding_key is None
    assert chosen.row_key == "row-cfads"
    rows = bound_rows(plan, bindings)
    assert rows["cfads"]["row_key"] == "row-cfads"
    assert rows["debt_service"]["row_key"] == "row-debt"
    got = coverage_ratio(
        metric="dscr",
        facts=[
            _fact("row-cfads", "cfads") | {"normalized_value": "40"},
            _fact("row-debt", "debt_service") | {"normalized_value": "10"},
        ],
        bindings=bindings,
        periods=[_period()],
        period_phase={},
        explicit_phases=False,
        plan=plan,
    )
    from decimal import Decimal

    assert got["status"] == "succeeded"
    assert got["rows"][0]["value"] == Decimal("4.0000000000")
    assert got["rows"][0]["components"]["cfads"] == ["S!cfads"]


def test_missing_confirmed_binding_is_not_replaced_by_the_same_row_key():
    """План подтвердил A/R. Привязки A нет, B с тем же row_key расчёт не берёт."""

    from finance_analysis.domain.resolved_plan import (
        bindings_for_plan,
        bound_rows,
        recover_row,
    )
    from finance_analysis.plugins.rules.ratios import _primary

    confirmed = _bind("cfads", 1, binding_key="A", row_key="R")
    debt = _bind("debt_service", 2, binding_key="D", row_key="debt")
    plan = resolve_metric_plan("dscr", [confirmed, debt], EXPRESSIONS)
    assert plan is not None and plan.status == "resolved"
    chosen = next(item for item in plan.inputs if item.concept == "cfads")
    assert chosen.binding_key == "A" and chosen.row_key == "R"

    other = _bind("cfads", 3, binding_key="B", row_key="R")
    later = [other, debt]
    assert recover_row(later, chosen) is None
    assert "cfads" not in bound_rows(plan, later)
    assert all(row.get("binding_key") != "B" for row in bindings_for_plan(later, plan))

    got = coverage_ratio(
        metric="dscr",
        facts=[
            _fact("R", "cfads") | {"normalized_value": "40"},
            _fact("debt", "debt_service") | {"normalized_value": "10"},
        ],
        bindings=later,
        periods=[_period()],
        period_phase={},
        explicit_phases=False,
        plan=plan,
    )
    assert got["rows"] == []
    assert got["status"] in {"needs_input", "missing_input"}
    assert _primary(AuditInput(bindings=later, plans={"dscr": plan}), "cfads", "dscr") is None


def _rule_counts(monkeypatch) -> dict[str, int]:
    counts: dict[str, int] = {}

    def wrap(fn, key):
        def inner(*args, **kwargs):
            counts[key] = counts.get(key, 0) + 1
            return fn(*args, **kwargs)

        return inner

    targets = (
        ("finance_analysis.domain.semantic_input", "choose_one_of"),
        ("finance_analysis.domain.semantic_input", "dscr_denominator_plan"),
        ("finance_analysis.domain.semantic_input", "interest_choice"),
        ("finance_analysis.domain.semantic_input", "confirm_paid_interest"),
        ("finance_analysis.domain.semantic_input", "_primaries"),
        ("finance_analysis.domain.semantic_input", "_basis"),
        ("finance_analysis.domain.semantic_input", "_select_primary"),
        ("finance_analysis.domain.free_cash_flow", "shield_concepts"),
    )
    for module, name in targets:
        host = __import__(module, fromlist=[name])
        monkeypatch.setattr(host, name, wrap(getattr(host, name), name))
    return counts


def test_each_selection_rule_runs_once_inside_resolve_metric_plan(monkeypatch):
    """Правила выбора внутри resolve_metric_plan не повторяются вторым проходом."""

    counts = _rule_counts(monkeypatch)

    def take() -> dict[str, int]:
        found = dict(counts)
        counts.clear()
        return found

    resolve_metric_plan(
        "dscr",
        [_bind("cfads", 1), _bind("debt_service", 2)],
        EXPRESSIONS,
    )
    dscr = take()
    assert dscr["dscr_denominator_plan"] == 1
    assert dscr["confirm_paid_interest"] == 1
    assert dscr["_primaries"] == 1
    assert dscr.get("choose_one_of", 0) == 0
    assert dscr.get("interest_choice", 0) == 0
    assert dscr.get("_basis", 0) == 0
    assert dscr.get("shield_concepts", 0) == 0

    resolve_metric_plan(
        "icr",
        [_bind("ebitda", 1), _bind("ebit", 2), _bind("interest", 3)],
        EXPRESSIONS,
    )
    icr = take()
    assert icr["choose_one_of"] == 1
    assert icr["confirm_paid_interest"] == 1
    assert icr["_primaries"] == 1
    assert icr.get("dscr_denominator_plan", 0) == 0
    assert icr.get("interest_choice", 0) == 0
    assert icr.get("_basis", 0) == 0

    resolve_metric_plan(
        "icr",
        [_bind("ebitda", 1), _bind("interest_paid", 2)],
        EXPRESSIONS,
        interest_order={"icr": ("interest", "interest_paid")},
    )
    fallback = take()
    assert fallback["interest_choice"] == 1
    assert fallback["choose_one_of"] == 1
    assert fallback["confirm_paid_interest"] == 1
    assert fallback["_primaries"] == 1

    resolve_metric_plan(
        "fcff",
        [_bind("operating_cash_flow", 1), _bind("capex", 2)],
        None,
        inputs={"all_of": ("operating_cash_flow", "capex")},
    )
    fcff = take()
    assert fcff["_basis"] == 1
    assert fcff["_primaries"] == 1
    assert fcff["confirm_paid_interest"] == 1
    assert fcff.get("shield_concepts", 0) == 0
    assert fcff.get("dscr_denominator_plan", 0) == 0


async def test_analyses_passes_one_plan_object(monkeypatch):
    """Analyses строит план один раз на метрику и отдаёт тот же объект читателям."""

    import anyio

    import finance_analysis.application.analyses as analyses_mod
    from finance_analysis.application.analyses import Analyses, Target
    from finance_analysis.application.catalog import load_catalog
    from finance_analysis.application.model_types import load_model_types
    from finance_analysis.domain.audit import AuditInput
    from finance_analysis.domain.book import Actor, Head
    from finance_analysis.domain.errors import NotFound
    from finance_analysis.domain.model_type import Effective

    bindings = [_bind("ebitda", 1), _bind("ebit", 2), _bind("interest", 3)]
    facts = [_fact(row["row_key"], row["effective_concept"]) for row in bindings]
    periods = [_period()]
    catalog = load_catalog()
    types = load_model_types()

    class _Guard:
        async def read_all(self, _job_id):
            return []

    class _Service:
        def __init__(self):
            self.catalog = catalog
            self.model_types = types
            self.guard = _Guard()
            self._cpu = anyio.CapacityLimiter(1)

        async def _dataset_rows(self, _job_id, _head, dataset):
            if dataset == "bindings":
                return list(bindings)
            if dataset == "fact_observation":
                return list(facts)
            if dataset == "dim_period":
                return list(periods)
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

    def allow(_catalog, _labels, metric):
        return "required" if metric == "icr" else "not_applicable"

    monkeypatch.setattr(analyses_mod, "applicability", allow)

    phase = {"freeze": False}
    held: dict = {}
    calls: list[tuple[str, ...]] = []
    resolves: list[str] = []

    from finance_analysis.domain.semantic_input import plans_for as real_plans_for
    from finance_analysis.domain.semantic_input import (
        resolve_metric_plan as real_resolve,
    )

    def spy_plans_for(metrics, *args, **kwargs):
        if phase["freeze"]:
            raise AssertionError("selection repeated")
        calls.append(tuple(metrics))
        built = real_plans_for(metrics, *args, **kwargs)
        phase["freeze"] = True
        held["plans"] = built
        return built

    def spy_resolve(metric, *args, **kwargs):
        resolves.append(metric)
        return real_resolve(metric, *args, **kwargs)

    monkeypatch.setattr(analyses_mod, "plans_for", spy_plans_for)
    monkeypatch.setattr(
        "finance_analysis.domain.semantic_input.resolve_metric_plan", spy_resolve
    )

    def guard(fn):
        def inner(*args, **kwargs):
            if phase["freeze"]:
                raise AssertionError("selection repeated")
            return fn(*args, **kwargs)

        return inner

    guarded = (
        ("finance_analysis.domain.semantic_input", "choose_one_of"),
        ("finance_analysis.domain.semantic_input", "dscr_denominator_plan"),
        ("finance_analysis.domain.semantic_input", "interest_choice"),
        ("finance_analysis.domain.semantic_input", "confirm_paid_interest"),
        ("finance_analysis.domain.semantic_input", "_primaries"),
        ("finance_analysis.domain.semantic_input", "_basis"),
        ("finance_analysis.domain.semantic_input", "_select_primary"),
        ("finance_analysis.domain.semantic_input", "resolve_semantic_inputs"),
        ("finance_analysis.domain.metrics", "choose_one_of"),
        ("finance_analysis.domain.metrics", "dscr_denominator_plan"),
        ("finance_analysis.domain.metrics", "interest_choice"),
        ("finance_analysis.domain.metrics", "confirm_paid_interest"),
        ("finance_analysis.domain.metrics", "_primaries"),
        ("finance_analysis.domain.binding_resolution", "select_primary"),
        ("finance_analysis.domain.free_cash_flow", "shield_concepts"),
        ("finance_analysis.domain.free_cash_flow", "_basis"),
        ("finance_analysis.domain.formula_origin", "resolve_semantic_inputs"),
    )
    for module, name in guarded:
        host = __import__(module, fromlist=[name])
        monkeypatch.setattr(host, name, guard(getattr(host, name)))

    real_select = analyses_mod.select_ratio

    def spy_select_ratio(*args, **kwargs):
        held["calc"] = kwargs.get("plan")
        return real_select(*args, **kwargs)

    real_origin = analyses_mod.origin_view

    def spy_origin(data, findings, expressions, **kwargs):
        plans = kwargs["plans"] if kwargs.get("plans") is not None else data.plans
        held["origin"] = (plans or {}).get("icr")
        return real_origin(data, findings, expressions, **kwargs)

    real_rules = analyses_mod.run_rules

    def spy_rules(rules, data):
        held["audit"] = (data.plans or {}).get("icr")
        return real_rules(rules, data)

    from finance_analysis.domain import graphs

    real_trace = graphs.trace_metric

    def spy_trace(*args, **kwargs):
        held["trace"] = kwargs.get("plan")
        return real_trace(*args, **kwargs)

    monkeypatch.setattr(analyses_mod, "select_ratio", spy_select_ratio)
    monkeypatch.setattr(analyses_mod, "origin_view", spy_origin)
    monkeypatch.setattr(analyses_mod, "run_rules", spy_rules)
    monkeypatch.setattr(graphs, "trace_metric", spy_trace)

    analyses = Analyses(_Service())

    async def _input(*_args, **_kwargs):
        return AuditInput(
            bindings=list(bindings),
            facts=list(facts),
            periods=list(periods),
            applicable_metrics=frozenset({"icr"}),
        )

    async def _noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(analyses, "_input", _input)
    monkeypatch.setattr(analyses, "_annotate", _noop)
    monkeypatch.setattr(analyses, "_save_tables", _noop)
    head = Head(build_key="build", state_seq=1, derive_key="derive", versions={})
    target = Target(head=head, build="build", manifest={}, fresh=True)
    await analyses._execute_full(
        "job", target, "analysis", ["icr"], None, {"rules": []}, Actor(), ""
    )
    assert calls == [("icr",)]
    assert resolves == ["icr"]
    plan = held["plans"]["icr"]
    assert held["calc"] is plan
    assert held["trace"] is plan
    assert held["origin"] is plan
    assert held["audit"] is plan
