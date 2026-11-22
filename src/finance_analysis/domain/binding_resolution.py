"""Выбор одной не-stale основной привязки.

Ниже по слою: semantic_input, затем след, происхождение формулы и расчёт.
Этот модуль их не импортирует.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_BOUND = frozenset({"bound", "bound_with_warning"})
MISSING_NO_PRIMARY = "no_primary_binding"
MISSING_STALE = "stale_binding"


def select_primary(
    bindings: Sequence[Mapping[str, Any]], concept: str
) -> tuple[Mapping[str, Any] | None, str | None, bool]:
    """Вернуть (primary, missing_code, ambiguous).

    Учитываются только не-stale основные bound-привязки. При нескольких —
    детерминированно выбирается минимальный ``binding_key``.
    """

    fresh = [
        row
        for row in bindings
        if row.get("is_primary")
        and row.get("status") in _BOUND
        and not row.get("stale")
        and str(row.get("effective_concept") or row.get("concept") or "") == concept
    ]
    if fresh:
        ordered = sorted(fresh, key=lambda row: str(row.get("binding_key") or ""))
        return ordered[0], None, len(ordered) > 1

    stale = [
        row
        for row in bindings
        if row.get("is_primary")
        and row.get("status") in _BOUND
        and row.get("stale")
        and str(row.get("effective_concept") or row.get("concept") or "") == concept
    ]
    if stale:
        return None, MISSING_STALE, False
    return None, MISSING_NO_PRIMARY, False
