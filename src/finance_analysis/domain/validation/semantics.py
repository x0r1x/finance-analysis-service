"""Проверки §3.2 и §5.12. Синхронные, без ввода-вывода."""

from __future__ import annotations

from dataclasses import dataclass

EVENT_TYPES = frozenset(
    {
        "concept.confirmed",
        "concept.set",
        "concept.rejected",
        "concept.ignored",
        "concept.absent",
        "phase.set",
        "actuals_end.set",
        "sign.set",
        "unit.set",
        "profile.set",
        "model_type.set",
        "mapping.remapped",
        "semantics.inferred",
        "binding.suspended",
    }
)


@dataclass(frozen=True)
class Verdict:
    accepted: bool
    code: str | None = None
    detail: str = ""


def check_event(
    *,
    event_type: str,
    target: str,
    concept: str | None,
    catalog: frozenset[str],
    targets: frozenset[str],
) -> Verdict:
    if event_type not in EVENT_TYPES:
        return Verdict(False, "schema_invalid", "неизвестный тип записи")
    if not target:
        return Verdict(False, "schema_invalid", "нет цели")
    if target not in targets:
        return Verdict(False, "ref_not_found", "цель не найдена в книге")
    if concept is not None and concept not in catalog:
        return Verdict(False, "concept_not_in_catalog", "понятие вне каталога")
    return Verdict(True)


def _concept(value) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def check_derived(tables: dict, *, catalog: frozenset[str], row_keys: frozenset[str]) -> Verdict:
    for dataset in ("bindings", "row_semantics"):
        for row in tables.get(dataset) or []:
            key = row.get("row_key")
            if key and key not in row_keys:
                return Verdict(False, "ref_not_found", "строка не найдена в книге")
    primaries: dict[str, int] = {}
    for row in tables.get("bindings") or []:
        names = [_concept(row.get("concept")), _concept(row.get("effective_concept"))]
        for name in names:
            if name is not None and name not in catalog:
                return Verdict(False, "concept_not_in_catalog", "понятие вне каталога")
        if not row.get("is_primary"):
            continue
        bound = _concept(row.get("effective_concept")) or _concept(row.get("concept"))
        if bound is None:
            continue
        primaries[bound] = primaries.get(bound, 0) + 1
        if primaries[bound] > 1:
            return Verdict(False, "concept_already_bound", "у понятия больше одной основной строки")
    return Verdict(True)
