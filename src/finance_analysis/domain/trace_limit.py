"""Предел следа: 512 цитируемых ячеек и 64 следа. Хвост и замок живут снаружи."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal

from finance_analysis.domain.calculation_evidence import (
    CalculationEvidence,
    EvidenceBook,
)

CELL_LIMIT = 512
TRACE_LIMIT = 64
OBSERVATION_LIMIT = 512
OBJECT_BYTE_LIMIT = 1_048_576
_OBSERVATION_VALUES = ("raw_value", "effective_value", "scale_factor")
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
    """Полный DTO прохода. Урезанная ячейка в компактном виде помечена, не спрятана."""

    periods = []
    for period in evidence.period_results:
        item = _record(period)
        item["steps"] = [_record(step) for step in period.steps]
        periods.append(item)
    uses = [_record(item, cell_ref=_cell_ref(item)) for item in evidence.fact_uses]
    limited = limit_trace(periods, fact_uses=uses)
    dropped = set(limited["dropped_cells"])
    for use in limited["fact_uses"]:
        ref = use.get("cell_ref")
        if isinstance(ref, str) and ref.startswith("truncated:"):
            use["cell_id"] = None
    observations = [_observation(item, dropped) for item in evidence.fact_observations]
    kept, stripped = _cap_observations(observations, OBSERVATION_LIMIT)
    limited["fact_observations"] = kept
    limited["dropped_observations"] = stripped
    limited["observation_count"] = len(observations)
    limited["observation_dropped_count"] = len(stripped)
    limited["observation_status"] = "complete" if not stripped else "truncated"
    limited["metric"] = evidence.metric
    limited["evidence_status"] = evidence.evidence_status
    limited["execution_status"] = evidence.execution_status
    limited["implementation"] = evidence.implementation
    limited["calculation_stamp"] = evidence.calculation_stamp
    limited["plan_content_sha256"] = evidence.plan_content_sha256
    limited["sign_convention"] = evidence.sign_convention
    limited["marker_class"] = evidence.marker_class
    limited["explicit_phases"] = evidence.explicit_phases
    limited["sheet"] = evidence.sheet
    limited["sums_additions"] = evidence.sums_additions
    limited["basis_sides"] = [_record(side) for side in evidence.basis_sides]
    return limited


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


def _cell_ref(item) -> str:
    if item.cell_id:
        return f"cell:{item.cell_id}"
    return f"fact:{item.axis_id}:{item.period_id}"


def _observation(item, dropped: set[str]) -> dict:
    ref = _cell_ref(item)
    body = _record(item, cell_ref=ref)
    if ref in dropped:
        body = _strip_observation(body)
        body["cell_ref"] = f"truncated:{ref}"
        body["cell_id"] = None
    return body


def _strip_observation(item: dict) -> dict:
    body = dict(item)
    for key in _OBSERVATION_VALUES:
        body.pop(key, None)
    body["observation_status"] = "dropped"
    return body


def _cap_observations(observations: list[dict], limit: int) -> tuple[list[dict], list[dict]]:
    kept = []
    stripped = []
    for item in observations:
        if item.get("observation_status") == "dropped" or len(kept) >= limit:
            stripped.append(_strip_observation(item))
        else:
            kept.append(item)
    return kept, stripped


def fit_object(view: dict, envelope: dict, *, byte_limit: int = OBJECT_BYTE_LIMIT) -> bytes:
    """Держит объект не больше предела. Сверх предела наблюдение теряет значения."""

    view.setdefault("fact_observations", [])
    view.setdefault("dropped_observations", [])
    view.setdefault("observation_count", len(view["fact_observations"]) + len(view["dropped_observations"]))
    view.setdefault("observation_dropped_count", len(view["dropped_observations"]))
    view.setdefault("observation_status", "complete" if not view["dropped_observations"] else "truncated")
    body = _dump(view, envelope)
    for _ in range(int(view["observation_count"]) + 4):
        view["payload_bytes"] = len(body)
        nxt = _dump(view, envelope)
        if nxt == body and len(body) <= byte_limit:
            return body
        body = nxt
        if len(body) <= byte_limit:
            continue
        if not view["fact_observations"]:
            view["payload_bytes"] = len(body)
            return _dump(view, envelope)
        moved = view["fact_observations"].pop()
        view["dropped_observations"].append(_strip_observation(moved))
        view["observation_dropped_count"] = len(view["dropped_observations"])
        view["observation_status"] = "truncated"
        view["payload_bytes"] = 0
        body = _dump(view, envelope)
    view["payload_bytes"] = len(body)
    return _dump(view, envelope)


def _dump(view: dict, envelope: dict) -> bytes:
    payload = dict(envelope)
    payload["trace"] = view
    return json.dumps(payload, ensure_ascii=False).encode()


def not_supported_evidence(metric: str, implementation: str, sign_convention: str) -> CalculationEvidence:
    """Явная отметка: метрика опубликована, улики расчёта у этой реализации нет."""

    book = EvidenceBook(
        metric=metric,
        sign_convention=sign_convention,
        marker_class=None,
        explicit_phases=False,
        plan_content_sha256=None,
    )
    return replace(
        book.freeze("not_run", implementation),
        evidence_status="evidence_not_supported",
    )


def _record(item, **extra) -> dict:
    body = {field.name: _plain(getattr(item, field.name)) for field in fields(item)}
    body.update(extra)
    return body


def _plain(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if is_dataclass(value) and not isinstance(value, type):
        return _record(value)
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in dict(value).items()}
    if isinstance(value, tuple | list):
        return [_plain(item) for item in value]
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)


def _add_years(moment: datetime, years: int) -> datetime:
    try:
        return moment.replace(year=moment.year + years)
    except ValueError:
        return moment.replace(year=moment.year + years, day=28)
