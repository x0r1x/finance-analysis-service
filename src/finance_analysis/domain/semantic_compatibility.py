"""Три ответа о строке и понятии. В одну вероятность они не складываются.

Likelihood — число, которое уже посчитал калибратор, либо пусто на лексическом пути.
Compatibility — единица, поток или остаток, знак. Жёсткий гейт единицы остаётся
внутри вероятности и здесь только подписывается. Положение в графе и раздел листа
объясняют строку и понятие не выбирают.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from finance_analysis.domain.candidates import Candidate
from finance_analysis.domain.glossary import Concept
from finance_analysis.domain.mapping import structure_failures


@dataclass(frozen=True, slots=True)
class Likelihood:
    """Вероятность тождества. None — лексический или человеческий путь, числа нет."""

    probability: float | None
    basis: tuple[str, ...]

    def as_dict(self) -> dict:
        return {"probability": self.probability, "basis": list(self.basis)}


@dataclass(frozen=True, slots=True)
class Check:
    """Одна сверка. context не меняет вердикт и не меняет сохранённое понятие."""

    code: str
    severity: str
    expected: str | None = None
    observed: str | None = None

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "expected": self.expected,
            "observed": self.observed,
        }


@dataclass(frozen=True, slots=True)
class Compatibility:
    """compatible, soft, incompatible или unknown."""

    verdict: str
    checks: tuple[Check, ...]

    def as_dict(self) -> dict:
        return {"verdict": self.verdict, "checks": [item.as_dict() for item in self.checks]}


@dataclass(frozen=True, slots=True)
class MetricUse:
    """Можно ли взять понятие в формулу. Отчёт, не выбор строки.

    usable — выбранный вход. fallback — запасной вход interest_order.
    declared_inactive — имя объявлено, но сейчас не выбрано.
    undeclared — имени нет в кортежах реализации.
    """

    formula_id: str
    verdict: str
    role: str | None
    codes: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "formula_id": self.formula_id,
            "verdict": self.verdict,
            "role": self.role,
            "codes": list(self.codes),
        }


@dataclass(frozen=True, slots=True)
class SemanticCompatibility:
    concept: str
    likelihood: Likelihood
    compatibility: Compatibility
    uses: tuple[MetricUse, ...] = ()

    def as_dict(self) -> dict:
        return {
            "concept": self.concept,
            "likelihood": self.likelihood.as_dict(),
            "compatibility": self.compatibility.as_dict(),
            "uses": [item.as_dict() for item in self.uses],
        }


def basis_of(candidate: Candidate) -> tuple[str, ...]:
    """Источники числа. Порядок фиксированный, пустые источники не пишутся."""

    names: list[str] = []
    if candidate.lexical:
        names.append("lexical")
    if candidate.recall_cos is not None:
        names.append("recall")
    if candidate.knn_cos is not None:
        names.append("knn")
    if candidate.rerank_rank is not None:
        names.append("rerank")
    if candidate.clm_prob is not None:
        names.append("clm")
    return tuple(names)


def assess(
    concept: Concept,
    *,
    row: dict,
    label: str,
    probability: float | None,
    basis: tuple[str, ...] = (),
    notes: tuple[str, ...] = (),
    uses: tuple[MetricUse, ...] = (),
) -> SemanticCompatibility:
    """Собирает три ответа. Вероятность не пересчитывает и понятие не подменяет."""

    checks = _economic(concept, row, label) + _context(row, notes)
    return SemanticCompatibility(
        concept.id,
        Likelihood(probability, basis),
        Compatibility(_verdict(checks), checks),
        uses,
    )


def _economic(concept: Concept, row: dict, label: str) -> tuple[Check, ...]:
    found: list[Check] = []
    for code in structure_failures(row, concept, label=label):
        if code == "unit_mismatch":
            found.append(Check(code, "hard", concept.unit, _unit_observed(row, label)))
        else:
            found.append(Check(code, "hard", None, label))
    nature = row.get("nature")
    if not nature:
        found.append(Check("flow_stock", "unknown", concept.temporal_nature, None))
    elif nature != concept.temporal_nature:
        found.append(Check("flow_stock", "hard", concept.temporal_nature, str(nature)))
    sign = row.get("sign")
    if concept.sign_conflict(sign if isinstance(sign, str) else None):
        found.append(Check("sign", "soft", concept.expected_sign, str(sign) if sign else None))
    return tuple(found)


def _unit_observed(row: dict, label: str) -> str:
    unit = str(row.get("unit_decision") or row.get("unit") or "")
    if "%" in label and "%" not in unit:
        return f"{unit} %".strip()
    return unit


def _context(row: dict, notes: tuple[str, ...]) -> tuple[Check, ...]:
    """Раздел, граф и способ показа. На вердикт не влияют."""

    found: list[Check] = []
    section = row.get("section")
    if section or "section" in notes:
        found.append(Check("section", "context", None, str(section) if section else None))
    role = row.get("role") or row.get("flow_role")
    if role == "component" or "graph_component" in notes:
        found.append(Check("graph_component", "context", None, str(role) if role else "component"))
    if role == "reference" or "graph_reference" in notes:
        found.append(Check("graph_reference", "context", None, str(role) if role else "reference"))
    period = row.get("period_basis")
    if period:
        found.append(Check("period_basis", "context", None, str(period)))
    return tuple(found)


def _verdict(checks: tuple[Check, ...]) -> str:
    severities = {item.severity for item in checks if item.severity != "context"}
    if "hard" in severities:
        return "incompatible"
    if "soft" in severities:
        return "soft"
    if "unknown" in severities:
        return "unknown"
    return "compatible"


def metric_use(
    concept: str,
    formula_id: str,
    *,
    primaries: Mapping[str, object],
    interest_order: Sequence[str] = (),
    row: dict | None = None,
) -> MetricUse:
    """Отчёт о пригодности имени для формулы.

    Читает кортежи `Implementation` и `interest_choice`. `confirm_paid_interest`
    не вызывает и основную строку не подменяет. `interest_paid` не становится
    синонимом `interest`.
    """

    if not formula_id:
        raise ValueError("formula_id пуст")
    from finance_analysis.domain.metric_contract import REGISTRY, load_implementations
    from finance_analysis.domain.metrics import _paid_interest_row, interest_choice

    load_implementations()
    item = _implementation(formula_id, REGISTRY)
    codes = _paid_codes(concept, row, _paid_interest_row)
    if item is None:
        return MetricUse(formula_id, "undeclared", None, codes)
    role = _role(concept, item, REGISTRY)
    if role is None:
        return MetricUse(formula_id, "undeclared", None, codes)
    if role == "dynamic_branch":
        return MetricUse(formula_id, "declared_inactive", "dynamic", codes)
    if concept in set(interest_order):
        chosen, warning = interest_choice(primaries, interest_order)
        if concept == chosen and isinstance(warning, dict) and warning.get("code") == "interest_basis_fallback":
            return MetricUse(formula_id, "fallback", role, ("interest_basis_fallback", *codes))
        if concept == chosen:
            return MetricUse(formula_id, "usable", role, codes)
        return MetricUse(formula_id, "declared_inactive", role, codes)
    if concept in primaries:
        return MetricUse(formula_id, "usable", role, codes)
    return MetricUse(formula_id, "declared_inactive", role, codes)


def _implementation(formula_id: str, registry: Mapping) -> object | None:
    exact = registry.get((formula_id, formula_id))
    if exact is not None:
        return exact
    found = [item for (_metric_id, name), item in registry.items() if name == formula_id]
    if not found:
        return None
    if len(found) > 1:
        raise ValueError(f"formula_id {formula_id} отвечает нескольким реализациям")
    return found[0]


def _role(concept: str, item, registry: Mapping) -> str | None:
    if concept in item.inputs:
        return "input"
    if concept in item.optional_inputs:
        return "optional"
    if item.profile_inputs and concept in item.profile_inputs:
        return "profile"
    spec = item.dynamic_inputs
    if spec is None:
        return None
    grouped = {name for group in spec.groups for name in group.concepts}
    if concept in grouped or concept in spec.arguments:
        return "dynamic"
    dependent = {name for branch in spec.dependencies for name in branch.concepts}
    if concept in dependent:
        return "dynamic_branch"
    from finance_analysis.domain.metric_contract import _dynamic_names

    names, _missing = _dynamic_names(item, registry, set())
    if concept in names:
        return "dynamic_branch"
    return None


def _paid_codes(concept: str, row: dict | None, paid_row) -> tuple[str, ...]:
    """Код 4123 объясняет строку. 4224 этим кодом не является."""

    if concept not in {"interest", "interest_paid"} or row is None:
        return ()
    if paid_row(row, frozenset()):
        return ("paid_line_4123",)
    return ()
