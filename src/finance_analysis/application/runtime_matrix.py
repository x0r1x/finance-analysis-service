"""Runtime-матрица: definition, executor, plan, evidence и причина.

``evidence_matrix`` отвечает только ``evidence_available`` или
``evidence_not_supported``. ``plan_incomplete`` эту ячейку не затирает.
``declared`` значит, что формула записана и выбранная ветвь её принимает.
Это не построенный план: ``generated`` оставлен для плана, который прогон
подтвердил.
https://www.w3.org/TR/prov-dm/#term-Plan
https://openlineage.io/docs/spec/object-model/
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RuntimeRow:
    metric: str
    implementation_version: str
    definition: bool
    executor: bool
    plan: str
    evidence: str
    reason: str


def runtime_matrix() -> tuple[RuntimeRow, ...]:
    """Формулы коэффициентов каталога вместе с реализациями реестра."""

    from finance_analysis.application.analyses import EVIDENCE_AVAILABLE, RATIO_METRICS
    from finance_analysis.application.model_types import (
        load_coverage_document,
        load_metric_catalog,
    )
    from finance_analysis.domain.metric_contract import REGISTRY, load_implementations

    load_implementations()
    raw = load_coverage_document()
    metrics = raw.get("metrics") if isinstance(raw, dict) else None
    if not isinstance(metrics, dict):
        metrics = {}
    expressions = load_metric_catalog()[5]
    windows = _windows(metrics)
    catalog = _catalog_formulas(metrics)
    keys = {key for key in catalog if key[0] in RATIO_METRICS}
    keys.update(key for key in REGISTRY if key[0] in RATIO_METRICS)
    rows = []
    for metric, formula_id in sorted(keys):
        rows.append(
            runtime_row(
                metric,
                formula_id,
                expressions.get(formula_id),
                REGISTRY.get((metric, formula_id)),
                expressions=expressions,
                windows=windows,
                available=EVIDENCE_AVAILABLE,
            )
        )
    return tuple(rows)


def runtime_row(
    metric: str,
    formula_id: str,
    expression,
    implementation,
    *,
    expressions: dict | None = None,
    windows: dict | None = None,
    available: frozenset[tuple[str, str]] | None = None,
) -> RuntimeRow:
    """Одна строка. План declared или refused: построенного плана здесь нет."""

    definition = expression is not None
    executor = implementation is not None
    version = ""
    if implementation is not None:
        version = implementation.implementation_version or formula_id
    known = available or frozenset()
    evidence = "evidence_not_supported"
    if (metric, version) in known:
        evidence = "evidence_available"
    plan = "missing"
    incomplete = False
    if definition:
        plan, incomplete = _plan(metric, formula_id, expression, implementation, expressions, windows)
    return RuntimeRow(
        metric=metric,
        implementation_version=version,
        definition=definition,
        executor=executor,
        plan=plan,
        evidence=evidence,
        reason=_reason(definition, executor, incomplete, evidence),
    )


def _reason(definition: bool, executor: bool, incomplete: bool, evidence: str) -> str:
    if not definition:
        return "missing_definition"
    if not executor:
        return "missing_executor"
    if incomplete:
        return "plan_incomplete"
    if evidence == "evidence_not_supported":
        return "evidence_not_supported"
    return ""


def _plan(metric, formula_id, expression, implementation, expressions, windows):
    from dataclasses import replace
    from types import SimpleNamespace

    from finance_analysis.domain.execution_branches import branch_for, refuse_definition
    from finance_analysis.domain.execution_contract import _from_expression
    from finance_analysis.domain.semantic_input import _active

    table = dict(expressions or {})
    table.setdefault(formula_id, expression)
    variant = _variant(metric, formula_id)
    active = _active(metric, variant, table)
    if active is None:
        expr, key = expression, formula_id
    else:
        expr, _source, key = active
    window = None if windows is None else windows.get(key)
    norm = _from_expression(expr, window if isinstance(window, str) else None)
    # shortcut: каталог пишет одну ставку и в rate, и в rates, а форма ветви
    # считает непустой rates другой формулой. Убрать, когда форма читает повтор
    # как ту же ставку.
    if norm.rate and norm.rates == (norm.rate,):
        norm = replace(norm, rates=())
    branch = branch_for(metric, variant=variant)
    refused = branch is not None and refuse_definition(
        metric, branch, SimpleNamespace(normalized_expression=norm), None
    ) is not None
    if refused:
        return "refused", False
    return "declared", _unpinned(implementation, branch, _pins(norm))


def _unpinned(implementation, branch, pins: frozenset[str]) -> bool:
    if implementation is None or implementation.mode != "registered" or branch is None:
        return False
    return any(name not in pins for name in branch.required_inputs)


def _pins(expr) -> frozenset[str]:
    names = set(expr.numerator_plus)
    names.update(
        expr.numerator_minus,
        expr.denominator_plus,
        expr.denominator_minus,
        expr.one_of,
        expr.rates,
    )
    for name in (expr.rate, expr.terminal, expr.compare_with):
        if isinstance(name, str) and name:
            names.add(name)
    if expr.add_back:
        names.update(expr.add_back)
    return frozenset(names)


def _variant(metric: str, formula_id: str) -> str | None:
    prefix = f"{metric}."
    if formula_id.startswith(prefix):
        return formula_id[len(prefix) :]
    return None


def _windows(metrics: dict) -> dict[str, str | None]:
    found: dict[str, str | None] = {}
    for metric, body in metrics.items():
        if not isinstance(body, dict):
            continue
        name = str(metric)
        raw = body.get("window")
        found[name] = raw if isinstance(raw, str) else None
        variants = body.get("variants") or {}
        if not isinstance(variants, dict):
            continue
        for variant, spec in variants.items():
            if not isinstance(spec, dict):
                continue
            raw = spec.get("window")
            found[f"{name}.{variant}"] = raw if isinstance(raw, str) else None
    return found


def _catalog_formulas(metrics: dict) -> dict[tuple[str, str], dict]:
    from finance_analysis.domain.metric_contract import formula_id_of

    found: dict[tuple[str, str], dict] = {}
    for metric, body in metrics.items():
        if not isinstance(body, dict):
            continue
        name = str(metric)
        found[(name, formula_id_of(name, None, body))] = body
        variants = body.get("variants") or {}
        if not isinstance(variants, dict):
            continue
        for variant, spec in variants.items():
            if isinstance(spec, dict):
                found[(name, formula_id_of(name, str(variant), spec))] = spec
    return found
