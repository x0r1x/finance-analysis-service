"""Правила фазы 3 по метрикам покрытия (§6.1): скульптинг, длина периода, нет итога.

Пороги и цели — только ячейки книги (§5.7): `target_dscr` берётся из
привязанной строки, константа извне не задаётся.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from finance_analysis.domain.audit import ROWS, AuditInput, Finding, Location, Rule
from finance_analysis.domain.cover_metrics import (
    METRIC_INPUTS,
    add_months,
    grain_months,
)
from finance_analysis.domain.metrics import (
    _groups,
    _primaries,
    absent_concepts,
    coverage_ratio,
)

_BOUND = frozenset({"bound", "bound_with_warning"})
SCULPT_TOLERANCE = Decimal("0.01")
# Без `target_dscr`: скульптинг виден, если ≥ 2/3 тестовых периодов у медианы.
SCULPT_SHARE = Decimal(2) / Decimal(3)
SCULPT_MIN_PERIODS = 3


def _phases(data: AuditInput) -> dict[tuple[str, str], str]:
    found = {}
    for row in data.periods:
        phase = row.get("phase")
        if not phase:
            continue
        found[(row["axis_id"], row["period_id"])] = phase
        if row.get("period_key_base"):
            found[(row["axis_id"], row["period_key_base"])] = phase
    return found


def dscr_rows(data: AuditInput) -> list[dict]:
    """DSCR FAS по тестовым периодам книги, как в `…/analyses` `ratios`."""

    if not data.bindings:
        return []
    if data.applicable_metrics is not None and "dscr" not in data.applicable_metrics:
        return []
    phases = _phases(data)
    result = coverage_ratio(
        metric="dscr",
        facts=data.facts,
        bindings=data.bindings,
        periods=data.periods,
        period_phase=phases,
        explicit_phases=bool(phases),
        sign_convention=data.profile.get("sign_convention") or "outflow_negative",
        marker_class=data.profile.get("marker_class"),
        absent=data.absent,
    )
    return result["rows"]


def _primary(data: AuditInput, concept: str) -> dict | None:
    """Основная строка понятия; `concept.absent` отменяет только привязка человека, как в DSCR."""

    if len(_groups(data.bindings).get(concept, ())) > 1:
        return None
    return _primaries(data.bindings, data.absent).get(concept)


def _scalar(data: AuditInput, row_key: str) -> Decimal | None:
    values = set()
    for fact in data.facts_by_row.get(row_key, ()):
        number = fact.get("normalized_value")
        if number is None:
            number = fact.get("value_dec")
        if number is not None:
            values.add(Decimal(str(number)))
    return values.pop() if len(values) == 1 else None


@dataclass(frozen=True)
class SculptingDeviation(Rule):
    """DSCR тестовых периодов далеко от `target_dscr` книги (или от своей медианы).

    С целью из книги — периоды с |DSCR − цель| > 0.01. Без цели — только если
    книга похожа на скульптированную (≥ 2/3 периодов у медианы): выбросы
    относительно медианы. Иначе разброс — норма, находки нет.
    """

    def check(self, data: AuditInput) -> list[Finding]:
        rows = [row for row in dscr_rows(data) if row.get("status") == "computed"]
        debt = _primary(data, "debt_service")
        if not rows or debt is None:
            return []
        target_row = _primary(data, "target_dscr")
        target = _scalar(data, target_row["row_key"]) if target_row else None
        basis = "target_dscr"
        if target is None:
            if len(rows) < SCULPT_MIN_PERIODS:
                return []
            values = sorted(row["value"] for row in rows)
            target = values[len(values) // 2]
            near = sum(1 for value in values if abs(value - target) <= SCULPT_TOLERANCE)
            if Decimal(near) < SCULPT_SHARE * len(values):
                return []
            basis = "median"
        off = [row for row in rows if abs(row["value"] - target) > SCULPT_TOLERANCE]
        if not off:
            return []
        return [
            self.finding(
                data,
                locations=[Location(None, debt["row_key"], row["axis_id"], row["period_id"]) for row in off],
                row_key=debt["row_key"],
                params={
                    "basis": basis,
                    "target": str(target),
                    "periods": len(off),
                    "max_deviation": str(max(abs(row["value"] - target) for row in off)),
                },
            )
        ]


@dataclass(frozen=True)
class PeriodGrainMismatch(Rule):
    """Тестовый период DSCR по датам короче `grain` оси (§0 п. 2). Без обеих дат — не проверяется."""

    def check(self, data: AuditInput) -> list[Finding]:
        periods = {(period["axis_id"], period["period_id"]): period for period in data.periods}
        findings = []
        for row in dscr_rows(data):
            period = periods.get((row["axis_id"], row["period_id"]))
            if period is None:
                continue
            start, end = period.get("period_start"), period.get("period_end")
            months = grain_months(period.get("grain"))
            if start is None or end is None or months is None:
                continue
            expected = (add_months(start, months) - timedelta(days=1) - start).days + 1
            actual = (end - start).days + 1
            if actual >= expected:
                continue
            findings.append(
                self.finding(
                    data,
                    axis_id=row["axis_id"],
                    period_id=row["period_id"],
                    params={"grain": period.get("grain"), "period_days": actual, "expected_days": expected},
                )
            )
        return findings


@dataclass(frozen=True)
class MissingTotalRow(Rule):
    """Понятие метрики отмечено `concept.absent`: итоговой строки в книге нет (§5.10.5).

    Места — строки, привязанные к составу понятия (`composition` таксономии),
    если они есть: из них агент может собрать вход через `…/expression`.
    """

    def check(self, data: AuditInput) -> list[Finding]:
        absent = sorted(concept for concept in absent_concepts(data.bindings, data.absent) if concept in METRIC_INPUTS)
        findings = []
        for concept in absent:
            needed = [
                metric
                for metric in METRIC_INPUTS[concept]
                if data.applicable_metrics is None or metric in data.applicable_metrics
            ]
            if not needed:
                continue
            parts = data.composition.get(concept, ())
            locations = [
                Location(None, row["row_key"], None, None)
                for row in data.bindings
                if row.get("is_primary") and row.get("status") in _BOUND and row.get("effective_concept") in parts
            ]
            findings.append(
                self.finding(
                    data,
                    locations=locations,
                    subject=f"concept:{concept}",
                    params={"concept": concept, "needed_by": needed, "components": list(parts)},
                )
            )
        return findings


SCULPTING_DEVIATION = SculptingDeviation(
    "sculpting_deviation", "1", "quantitative", "info", ("Mazars DSCR",), "DSCR отходит от целевого", ROWS, 3,
)
PERIOD_GRAIN_MISMATCH = PeriodGrainMismatch(
    "period_grain_mismatch", "1", "qualitative", "medium", ("§0 п. 2",), "Тестовый период короче шага модели", ROWS, 3,
)
MISSING_TOTAL_ROW = MissingTotalRow(
    "missing_total_row", "1", "omission", "medium", ("§0 п. 2", "§5.5"), "Нет итоговой строки понятия метрики", ROWS, 3,
)
