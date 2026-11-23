"""Вход формулы читается из плана. Кэш самой метрики — отдельная сверка."""

import ast
from dataclasses import fields
from pathlib import Path

import pytest

from finance_analysis.application.model_types import load_metric_catalog
from finance_analysis.domain.audit import AuditInput
from finance_analysis.domain.model_type import MetricExpression
from finance_analysis.domain.resolved_plan import bindings_for_plan
from finance_analysis.domain.semantic_input import resolve_metric_plan

EXPRESSIONS = {
    "icr": MetricExpression(
        one_of=frozenset({"ebitda", "ebit"}),
        one_of_order=("ebitda", "ebit"),
        denominator_plus=("interest",),
    ),
    "net_debt_ebitda": MetricExpression(
        numerator_plus=("net_debt",),
        denominator_plus=("ebitda",),
    ),
}

# Граница факта и прогноза. Это не вход формулы метрики, плана у этих понятий нет.
_STATEMENT_READS = frozenset(
    {
        "_reporting_traced",
        "_traced_boundary",
        "_form_starts_after",
        "_formula_cuts",
        "_span_cuts",
        "StatementReference.check",
        "_has_statement_pair",
    }
)
_SCAN = frozenset({"_primaries", "_groups", "_bound", "_bound_rows", "_legacy_bound_row"})
_MARKERS = (
    "bindings_for_plan",
    "bound_rows(",
    "plan.inputs",
    "_apply_plan",
    "_plan_rows",
    "_coverage_from_plan",
    "_core_rows",
)
_DISPATCHERS = frozenset(
    {
        "select_ratio",
        "dispatch_cover",
        "compute_metrics",
        "trace_metric",
    }
)
_SRC = Path(__file__).resolve().parents[2] / "src" / "finance_analysis"


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


def _concepts(key: str, expressions: dict, seen: set[str] | None = None) -> tuple[str, ...]:
    seen = set() if seen is None else seen
    if key in seen:
        return ()
    seen.add(key)
    expr = expressions[key]
    if expr.base:
        return _concepts(expr.base, expressions, seen)
    names = [
        *expr.numerator_plus,
        *expr.numerator_minus,
        *expr.denominator_plus,
        *expr.denominator_minus,
        *tuple(expr.one_of),
        *expr.rates,
    ]
    for item in (expr.rate, expr.terminal, expr.compare_with):
        if item:
            names.append(item)
    if expr.add_back:
        names.extend(expr.add_back)
    return tuple(dict.fromkeys(names))


def _catalog():
    _inputs, _variants, _composed, _bases, _rates, expressions = load_metric_catalog()
    return expressions


@pytest.mark.parametrize("key", sorted(_catalog()))
def test_an_unconfirmed_primary_is_not_left_beside_the_plan(key: str):
    """Две основные строки одного входа. План их не подтверждает — обе уходят из просмотра."""

    expressions = _catalog()
    concepts = _concepts(key, expressions)
    if not concepts:
        pytest.skip("у формулы нет понятия")
    concept = concepts[0]
    metric, _, variant = key.partition(".")
    rows = [
        _bind(concept, 1, row_key="row-a", binding_key="bk-b"),
        _bind(concept, 2, row_key="row-b", binding_key="bk-a"),
    ]
    plan = resolve_metric_plan(metric, rows, expressions, variant=variant or None)
    assert plan is not None, key
    assert concept not in {item.concept for item in plan.inputs}
    kept = {row["row_key"] for row in bindings_for_plan(rows, plan)}
    assert kept.isdisjoint({"row-a", "row-b"}), key


def test_stale_ebitda_and_interest_are_not_icr_inputs(monkeypatch):
    """План ICR их не подтвердил. Предпроверка и оси их не читают."""

    from finance_analysis.plugins.rules.ratios import ICR_REFERENCE

    stale_ebitda = _bind("ebitda", 1, stale=True, row_key="stale-ebitda")
    stale_interest = _bind("interest", 2, stale=True, row_key="stale-interest")
    model = _bind("icr", 3, row_key="model")
    plan = resolve_metric_plan("icr", [stale_ebitda, stale_interest, model], EXPRESSIONS)
    assert plan is not None
    assert "ebitda" not in {item.concept for item in plan.inputs}
    assert "interest" not in {item.concept for item in plan.inputs}
    assert "icr" not in {item.concept for item in plan.inputs}

    def forbidden(**_kwargs):
        raise AssertionError("формула не считается, пока план не подтвердил EBITDA и проценты")

    monkeypatch.setattr("finance_analysis.plugins.rules.ratios.coverage_ratio", forbidden)
    data = AuditInput(
        bindings=[stale_ebitda, stale_interest, model],
        plans={"icr": plan},
        periods=[{"axis_id": "a", "period_id": "p", "period_key": "p"}],
        applicable_metrics=frozenset({"icr"}),
    )
    assert ICR_REFERENCE.check(data) == []


def test_icr_reference_follows_the_numerator_the_plan_confirmed(monkeypatch):
    """Один из числителей. Правило берёт подтверждённый EBIT, не устаревшую EBITDA."""

    from finance_analysis.plugins.rules import ratios

    stale = _bind("ebitda", 1, stale=True, row_key="stale-ebitda")
    ebit = _bind("ebit", 2, row_key="ebit")
    interest = _bind("interest", 3, row_key="interest")
    model = _bind("icr", 4, row_key="model")
    plan = resolve_metric_plan("icr", [stale, ebit, interest, model], EXPRESSIONS)
    assert plan is not None
    assert {item.concept for item in plan.inputs} == {"ebit", "interest"}

    real_bound = ratios._bound_rows

    def spy_bound(data, concept):
        if concept == "ebitda":
            raise AssertionError("устаревшая EBITDA не ищется, пока план выбрал EBIT")
        return real_bound(data, concept)

    axes: list[str] = []
    real_axes = ratios._row_axes

    def spy_axes(data, row_key):
        axes.append(row_key)
        return real_axes(data, row_key)

    monkeypatch.setattr(ratios, "_bound_rows", spy_bound)
    monkeypatch.setattr(ratios, "_row_axes", spy_axes)
    data = AuditInput(
        bindings=[stale, ebit, interest, model],
        plans={"icr": plan},
        periods=[{"axis_id": "a", "period_id": "p", "period_key": "p"}],
        facts=[{"row_key": "ebit", "axis_id": "a", "period_id": "p", "value": "10"}],
        applicable_metrics=frozenset({"icr"}),
    )
    ratios.ICR_REFERENCE.check(data)
    assert "stale-ebitda" not in axes
    assert "ebit" in axes


def test_composed_metric_receives_the_plan(monkeypatch):
    from finance_analysis.domain.covenant import select_ratio
    from finance_analysis.domain.model_type import Composed, Side

    stale = _bind("net_debt", 1, stale=True, row_key="stale")
    fresh = _bind("ebitda", 2, row_key="ebitda")
    plan = resolve_metric_plan("net_debt_ebitda", [stale, fresh], EXPRESSIONS)
    assert plan is not None
    assert "net_debt" not in {item.concept for item in plan.inputs}
    seen: dict = {}

    def spy(*_args, **kwargs):
        seen["plan"] = kwargs.get("plan")
        return {
            "metric": "net_debt_ebitda",
            "rows": [],
            "needs_input": [],
            "warnings": [],
            "status": "missing_input",
        }

    monkeypatch.setattr("finance_analysis.domain.covenant.composed_ratio", spy)
    select_ratio(
        "net_debt_ebitda",
        None,
        {
            "facts": [],
            "bindings": [stale, fresh],
            "periods": [],
            "sign_convention": "outflow_negative",
            "marker_class": None,
            "absent": frozenset(),
        },
        profile=None,
        profile_ref=None,
        composed={
            "net_debt_ebitda": Composed(Side(("net_debt",), ()), Side(("ebitda",), ()), "LTM"),
        },
        concepts=frozenset(),
        money=frozenset(),
        plan=plan,
    )
    assert seen.get("plan") is plan


def _module_name(path: Path) -> str:
    relative = path.relative_to(_SRC.parent).with_suffix("")
    return ".".join(relative.parts)


def _functions():
    found = {}
    for path in _SRC.rglob("*.py"):
        module = _module_name(path)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = {}
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    imported[alias.asname or alias.name] = (node.module, alias.name)
        defined = {}
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defined[node.name] = node
            elif isinstance(node, ast.ClassDef):
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        defined[f"{node.name}.{child.name}"] = child
                        defined.setdefault(child.name, child)
        for name, node in defined.items():
            if "." in name:
                continue
            calls = []
            local_imports = dict(imported)
            for child in ast.walk(node):
                if isinstance(child, ast.ImportFrom) and child.module:
                    for alias in child.names:
                        local_imports[alias.asname or alias.name] = (child.module, alias.name)
                elif isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                    calls.append(child)
            found[(module, name)] = (node, calls, local_imports, module)
    return found


def _resolve(name: str, module: str, imported: dict, functions: dict):
    if (module, name) in functions:
        return module, name
    target = imported.get(name)
    if target and target in functions:
        return target
    return None


_ENGINE = frozenset(
    {
        "finance_analysis.domain.semantic_input",
        "finance_analysis.domain.binding_resolution",
        "finance_analysis.domain.resolved_plan",
    }
)


def _needs_plan(module: str, name: str, functions: dict, seen: set) -> bool:
    key = (module, name)
    if module in _ENGINE or key in seen or key not in functions:
        return False
    seen.add(key)
    node, calls, imported, owner = functions[key]
    source = ast.unparse(node)
    if any(marker in source for marker in _MARKERS):
        return True
    for call in calls:
        called = call.func.id
        if called in _SCAN:
            return True
        resolved = _resolve(called, owner, imported, functions)
        if resolved and _needs_plan(*resolved, functions, seen):
            return True
    return False


def _call_passes_plan(call: ast.Call) -> bool:
    return any(keyword.arg == "plan" for keyword in call.keywords)


def test_dispatchers_pass_the_plan_into_every_formula_reread():
    """Новая метрика, которая снова читает привязки, без плана не компилируется в этот список."""

    functions = _functions()
    missing = []
    for (module, name), (node, calls, imported, owner) in functions.items():
        if name not in _DISPATCHERS:
            continue
        for call in calls:
            called = call.func.id
            if called in _SCAN:
                missing.append(f"{module}.{name} вызывает {called} напрямую")
                continue
            resolved = _resolve(called, owner, imported, functions)
            if resolved is None:
                continue
            if resolved[1] in _DISPATCHERS:
                if not _call_passes_plan(call):
                    missing.append(f"{module}.{name} не передаёт plan в {called}")
                continue
            if not _needs_plan(*resolved, functions, set()):
                continue
            callee = functions[resolved][0]
            text = ast.unparse(callee)
            if not _call_passes_plan(call):
                missing.append(f"{module}.{name} не передаёт plan в {called}")
            elif not any(marker in text for marker in _MARKERS):
                missing.append(f"{resolved[0]}.{resolved[1]} читает привязки мимо плана")
    assert missing == []


def _under_missing_plan(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    current: ast.AST | None = node
    while current in parents:
        current = parents[current]
        if not isinstance(current, ast.If) or not isinstance(current.test, ast.Compare):
            continue
        test = current.test
        if not isinstance(test.left, ast.Name) or test.left.id != "plan":
            continue
        if any(isinstance(op, ast.Is) for op in test.ops) and any(
            isinstance(item, ast.Constant) and item.value is None for item in test.comparators
        ):
            return True
    return False


def test_passed_plan_reads_lineage_and_diagnostic_stays_narrow():
    """Докстрока и спека не шире типов: у диагноза нет role и source."""

    from finance_analysis.domain import formula_origin, graphs
    from finance_analysis.domain.resolved_plan import DiagnosticCandidate, LineageRow

    assert [item.name for item in fields(DiagnosticCandidate)] == [
        "concept",
        "binding_key",
        "row_key",
        "reason",
    ]
    assert [item.name for item in fields(LineageRow)] == [
        "concept",
        "source",
        "role",
        "row_key",
        "binding_key",
        "missing",
        "ambiguous",
    ]
    assert "plan.lineage" in (graphs.trace_metric.__doc__ or "")
    assert "plan.lineage" in (formula_origin.__doc__ or "")
    design = Path(__file__).resolve().parents[2].joinpath("docs/design-v0.23.md").read_text(encoding="utf-8")
    diagnostic = design.split("`DiagnosticCandidate`:", 1)[1].split(".", 1)[0]
    assert "role" not in diagnostic
    assert "source" not in diagnostic
    assert "`LineageRow`" in design
    assert "plan.lineage" in design


def test_a_rule_cannot_read_a_formula_input_without_a_metric():
    path = _SRC / "plugins" / "rules" / "ratios.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    missing = []
    for node in tree.body:
        owners = [(None, node)] if isinstance(node, ast.FunctionDef) else []
        if isinstance(node, ast.ClassDef):
            owners = [(node.name, child) for child in node.body if isinstance(child, ast.FunctionDef)]
        for class_name, func in owners:
            label = f"{class_name}.{func.name}" if class_name else func.name
            if label in _STATEMENT_READS:
                continue
            parents: dict[ast.AST, ast.AST] = {}
            for parent in ast.walk(func):
                for child in ast.iter_child_nodes(parent):
                    parents[child] = parent
            for child in ast.walk(func):
                if not isinstance(child, ast.Call) or not isinstance(child.func, ast.Name):
                    continue
                if child.func.id != "_primary":
                    continue
                named = {keyword.arg for keyword in child.keywords}
                if len(child.args) >= 3 or "metric" in named or _under_missing_plan(child, parents):
                    continue
                missing.append(label)
    assert missing == []
