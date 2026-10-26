"""Расхождения коэффициента, смесь маркеров и дыра в цепочке (§6.1, фаза 2)."""

from __future__ import annotations

from decimal import Decimal

from finance_analysis.domain.audit import ROWS, ROWS_LINKS, AuditInput, Finding, Rule
from finance_analysis.domain.metrics import coverage_ratio

_TOLERANCE = Decimal("0.005")
_BOUND = frozenset({"bound", "bound_with_warning"})


def _primary(data: AuditInput, concept: str) -> dict | None:
    found = [
        row
        for row in data.bindings
        if row.get("is_primary") and row.get("status") in _BOUND and (row.get("effective_concept") or row.get("concept")) == concept
    ]
    return found[0] if len(found) == 1 else None


def _cached(data: AuditInput, row_key: str) -> dict[tuple[str, str], Decimal]:
    values = {}
    for fact in data.facts:
        if fact.get("row_key") != row_key:
            continue
        number = fact.get("normalized_value")
        if number is None:
            number = fact.get("value_dec")
        if number is None:
            continue
        values[(fact["axis_id"], fact["period_id"])] = Decimal(str(number))
    return values


class RatioMismatch(Rule):
    def check(self, data: AuditInput) -> list[Finding]:
        if not data.bindings:
            return []
        model = _primary(data, "dscr")
        if model is None or _primary(data, "cfads") is None or _primary(data, "debt_service") is None:
            return []
        phases = {}
        for row in data.periods:
            phase = row.get("phase")
            if not phase:
                continue
            phases[(row["axis_id"], row["period_id"])] = phase
            base = row.get("period_key_base")
            if base:
                phases[(row["axis_id"], base)] = phase
        result = coverage_ratio(
            metric="dscr",
            facts=data.facts,
            bindings=data.bindings,
            periods=data.periods,
            period_phase=phases,
            explicit_phases=bool(phases),
        )
        cached = _cached(data, model["row_key"])
        findings = []
        for row in result["rows"]:
            if row.get("value") is None:
                continue
            key = (row["axis_id"], row["period_id"])
            other = cached.get(key)
            if other is None or abs(Decimal(row["value"]) - other) <= _TOLERANCE:
                continue
            findings.append(
                self.finding(
                    data,
                    row_key=model["row_key"],
                    axis_id=row["axis_id"],
                    period_id=row["period_id"],
                    params={"metric": "dscr", "fas": str(row["value"]), "model": str(other)},
                )
            )
        return findings


def _marker_of(data: AuditInput) -> dict[str, str]:
    period_marker = {
        (row.get("axis_id"), row.get("period_id")): row.get("marker_class")
        for row in data.periods
        if row.get("marker_class")
    }
    found = {}
    for fact in data.facts:
        cell = fact.get("cell_id")
        marker = period_marker.get((fact.get("axis_id"), fact.get("period_id")))
        if cell and marker:
            found[cell] = marker
    return found


def _parents(data: AuditInput) -> dict[str, set[str]]:
    cell_row = {fact.get("cell_id"): fact.get("row_key") for fact in data.facts if fact.get("cell_id")}
    parents: dict[str, set[str]] = {}
    for link in data.links:
        parent = link.get("row_key")
        child = cell_row.get(link.get("ref_cell"))
        if parent and child and parent != child:
            parents.setdefault(child, set()).add(parent)
    return parents


def _ancestors(parents: dict[str, set[str]], row_key: str) -> set[str]:
    seen: set[str] = set()
    stack = list(parents.get(row_key, ()))
    while stack:
        parent = stack.pop()
        if parent in seen:
            continue
        seen.add(parent)
        stack.extend(parents.get(parent, ()))
    return seen


class MarkerMix(Rule):
    def check(self, data: AuditInput) -> list[Finding]:
        markers_of = _marker_of(data)
        by_formula: dict[tuple[str, str], set[str]] = {}
        owners: dict[tuple[str, str], str] = {}
        for link in data.links:
            row_key = link.get("row_key")
            marker = markers_of.get(link.get("ref_cell"))
            if not row_key or not marker:
                continue
            key = (row_key, str(link.get("cell") or ""))
            by_formula.setdefault(key, set()).add(marker)
            owners[key] = row_key
        return [
            self.finding(data, row_key=owners[key], params={"markers": sorted(markers)})
            for key, markers in by_formula.items()
            if len(markers) > 1
        ]


class UnmappedInMetricChain(Rule):
    def check(self, data: AuditInput) -> list[Finding]:
        if not data.bindings:
            return []
        concept_of = {
            row["row_key"]: row.get("effective_concept") or row.get("concept")
            for row in data.bindings
            if row.get("is_primary") and row.get("status") in _BOUND and row.get("row_key")
        }
        if not {"dscr", "icr"} & set(concept_of.values()):
            return []
        parents = _parents(data)
        findings = []
        for row in data.bindings:
            if row.get("status") != "unknown" or not row.get("row_key"):
                continue
            reached = {concept_of[key] for key in _ancestors(parents, row["row_key"]) if key in concept_of}
            if "debt_service" in reached or "interest" in reached:
                severity = "high"
            elif "dscr" in reached or "icr" in reached:
                severity = "medium"
            else:
                continue
            findings.append(
                self.finding(
                    data,
                    row_key=row["row_key"],
                    severity=severity,
                    params={"status": "unknown"},
                )
            )
        return findings


RATIO_MISMATCH = RatioMismatch(
    "ratio_mismatch", "1", "quantitative", "high", ("DSCR model cache",),
    "Коэффициент расходится с кэшем модели", ROWS, 2,
)
MARKER_MIX = MarkerMix(
    "marker_mix", "1", "logic", "medium", ("period marker",),
    "В одном окне смешаны маркеры", ROWS_LINKS, 2,
)
UNMAPPED_IN_METRIC_CHAIN = UnmappedInMetricChain(
    "unmapped_in_metric_chain", "1", "omission", "medium", ("metric chain",),
    "В цепочке коэффициента есть непривязанная строка", ROWS_LINKS, 2,
)
