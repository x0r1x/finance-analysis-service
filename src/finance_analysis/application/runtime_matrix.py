"""Runtime-матрица: definition, executor, plan, evidence и причина.

``evidence_matrix`` отвечает только ``evidence_available`` или
``evidence_not_supported``. ``plan_incomplete`` эту ячейку не затирает.
``generated`` значит, что формула строит план, а не что план держит каждый
вход исполнителя. Покрытие тестами сюда не входит: разные грани одной
деятельности не схлопываются в один статус.
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
    from finance_analysis.application.model_types import load_coverage_document
    from finance_analysis.domain.metric_contract import REGISTRY, load_implementations

    load_implementations()
    raw = load_coverage_document()
    metrics = raw.get("metrics") if isinstance(raw, dict) else None
    if not isinstance(metrics, dict):
        metrics = {}
    catalog = _catalog_formulas(metrics)
    keys = {key for key in catalog if key[0] in RATIO_METRICS}
    keys.update(key for key in REGISTRY if key[0] in RATIO_METRICS)
    rows = []
    for metric, formula_id in sorted(keys):
        rows.append(
            _row(
                metric,
                formula_id,
                catalog.get((metric, formula_id)),
                REGISTRY.get((metric, formula_id)),
                metrics,
                EVIDENCE_AVAILABLE,
            )
        )
    return tuple(rows)


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


def _row(metric, formula_id, body, item, metrics, available) -> RuntimeRow:
    definition = body is not None
    executor = item is not None
    version = ""
    if item is not None:
        version = item.implementation_version or formula_id
    evidence = "evidence_not_supported"
    if (metric, version) in available:
        evidence = "evidence_available"
    pinned = _pinned(body, metrics) if definition else frozenset()
    incomplete = _debt_service_unpinned(item, pinned)
    return RuntimeRow(
        metric=metric,
        implementation_version=version,
        definition=definition,
        executor=executor,
        plan="generated" if definition else "missing",
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


def _debt_service_unpinned(item, pinned: frozenset[str]) -> bool:
    """Контроль исполнения, которого нет среди терминов формулы.

    Исполнитель LLCR и PLCR требует ``debt_service``, чтобы выбрать тестовый
    период и, у LLCR, горизонт. Частное на него не делится, и каталог его не
    называет. Запас DSCR и ICR этим не является: там ``debt_service`` уже
    термин формулы или приходит через ``base``.
    """

    if item is None or item.mode != "registered":
        return False
    return "debt_service" in item.inputs and "debt_service" not in pinned


def _pinned(body: dict, metrics: dict, seen: frozenset[str] | None = None) -> frozenset[str]:
    from finance_analysis.domain.metric_contract import composition_concepts

    names = composition_concepts(body)
    base = body.get("base")
    walked = seen or frozenset()
    if not isinstance(base, str) or not base or base in walked:
        return names
    parent = metrics.get(base)
    if not isinstance(parent, dict):
        return names
    return names | _pinned(parent, metrics, walked | {base})
