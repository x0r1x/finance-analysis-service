"""Три ответа о строке и понятии. В одну вероятность они не складываются.

Likelihood — число, которое уже посчитал калибратор, либо пусто на лексическом пути.
Compatibility — единица, поток или остаток, знак. Жёсткий гейт единицы остаётся
внутри вероятности и здесь только подписывается. Положение в графе и раздел листа
объясняют строку и понятие не выбирают.
"""

from __future__ import annotations

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
