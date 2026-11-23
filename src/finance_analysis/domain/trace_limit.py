"""Предел следа: 512 цитируемых ячеек и 64 следа. Хвост и замок живут снаружи."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from finance_analysis.domain.calculation_evidence import CalculationEvidence

CELL_LIMIT = 512
TRACE_LIMIT = 64
_COMPLIANCE = (
    "COMPLIANCE включает только оператор бакета: "
    "mc mb --with-lock ALIAS/BUCKET и "
    "mc retention set --default GOVERNANCE DURATION ALIAS/BUCKET"
)


class TraceLimitError(Exception):
    """Собранный след или анализ длиннее предела."""


@dataclass(frozen=True)
class TraceRetention:
    mode: str
    until: datetime
    profile: str


def check_retention_name(value: str) -> str:
    """Имя режима. COMPLIANCE продукт не принимает: его ставит оператор бакета."""

    text = str(value).strip()
    if text == "COMPLIANCE":
        raise ValueError(_COMPLIANCE)
    if text in {"analysis", "sec_17a4", "credit_org_395_1"}:
        return text
    if text.startswith("days:"):
        days = text.removeprefix("days:")
        if days.isdigit() and int(days) > 0:
            return text
    raise ValueError("FAS_TRACE_RETENTION: analysis, sec_17a4, credit_org_395_1 или days:N")


def retention_policy(value: str, *, now: datetime) -> TraceRetention | None:
    """`analysis` — без замка. Остальные режимы — GOVERNANCE на срок профиля."""

    name = check_retention_name(value)
    if name == "analysis":
        return None
    if name == "sec_17a4":
        return TraceRetention("GOVERNANCE", _add_years(now, 6), name)
    if name == "credit_org_395_1":
        return TraceRetention("GOVERNANCE", _add_years(now, 5), name)
    return TraceRetention("GOVERNANCE", now + timedelta(days=int(name.removeprefix("days:"))), name)


def guard_traces(views: list[dict]) -> None:
    """Падает, если анализ длиннее 64 следов или след цитирует больше 512 ячеек."""

    if len(views) > TRACE_LIMIT:
        raise TraceLimitError(f"следов {len(views)} больше {TRACE_LIMIT}")
    for view in views:
        count = _cited_count(view)
        if count > CELL_LIMIT:
            raise TraceLimitError(f"ячеек {count} больше {CELL_LIMIT}")


def limit_trace(periods: list[dict], *, fact_uses: list[dict] | None = None) -> dict:
    """Первые 512 ячеек остаются. Сверх предела — метка, ссылка `step:` не трогается.

    Отброшенные ссылки лежат в `dropped_cells`. Их забирает объект хвоста и
    снимает с DTO, чтобы урезанный след не выглядел полным.
    """

    uses = [dict(item) for item in fact_uses or []]
    copied = []
    for period in periods:
        item = {key: value for key, value in period.items() if key != "steps"}
        item["steps"] = [
            {**step, "input_refs": list(step.get("input_refs") or [])} for step in period.get("steps") or []
        ]
        copied.append(item)
    ordered: list[str] = []
    seen: set[str] = set()

    def take(ref: object) -> None:
        if not isinstance(ref, str) or not _cited(ref) or ref in seen:
            return
        seen.add(ref)
        ordered.append(ref)

    for period in copied:
        for step in period["steps"]:
            for ref in step["input_refs"]:
                take(ref)
    for use in uses:
        take(use.get("cell_ref"))
    kept = set(ordered[:CELL_LIMIT])
    dropped = ordered[CELL_LIMIT:]

    def rewrite(ref: object) -> object:
        if not isinstance(ref, str) or ref.startswith("step:"):
            return ref
        if _cited(ref) and ref not in kept:
            return f"truncated:{ref}"
        return ref

    for period in copied:
        for step in period["steps"]:
            step["input_refs"] = [rewrite(ref) for ref in step["input_refs"]]
    for use in uses:
        use["cell_ref"] = rewrite(use.get("cell_ref"))
    return {
        "status": "complete" if not dropped else "truncated",
        "evidence_complete": not dropped,
        "dropped_cell_count": len(dropped),
        "cited_cells": ordered[:CELL_LIMIT],
        "dropped_cells": dropped,
        "periods": copied,
        "fact_uses": uses,
    }


def view_from_evidence(evidence: CalculationEvidence) -> dict:
    """DTO из улики прохода. Роли, окно и ссылки шагов сохраняются."""

    periods = []
    for period in evidence.period_results:
        periods.append(
            {
                "axis_id": period.axis_id,
                "period_id": period.period_id,
                "status": period.status,
                "reason": period.reason,
                "window_periods": _lists(period.window_periods),
                "window_missing": _lists(period.window_missing),
                "missing_concepts": _lists(period.missing_concepts),
                "steps": [
                    {
                        "step_id": step.step_id,
                        "operation": step.operation,
                        "input_refs": list(step.input_refs),
                    }
                    for step in period.steps
                ],
            }
        )
    uses = []
    for item in evidence.fact_uses:
        ref = f"cell:{item.cell_id}" if item.cell_id else f"fact:{item.axis_id}:{item.period_id}"
        uses.append({"concept": item.concept, "cell_ref": ref, "operand": item.operand})
    return limit_trace(periods, fact_uses=uses)


def _cited(ref: str) -> bool:
    return ref.startswith(("cell:", "fact:"))


def _cited_count(view: dict) -> int:
    seen: set[str] = set()

    def take(ref: object) -> None:
        if isinstance(ref, str) and _cited(ref):
            seen.add(ref)

    for ref in view.get("cited_cells") or []:
        take(ref)
    for period in view.get("periods") or []:
        for step in period.get("steps") or []:
            for ref in step.get("input_refs") or []:
                take(ref)
    for use in view.get("fact_uses") or []:
        take(use.get("cell_ref"))
    return len(seen)


def _lists(value):
    if isinstance(value, tuple):
        return [_lists(item) for item in value]
    return value


def _add_years(moment: datetime, years: int) -> datetime:
    try:
        return moment.replace(year=moment.year + years)
    except ValueError:
        return moment.replace(year=moment.year + years, day=28)
