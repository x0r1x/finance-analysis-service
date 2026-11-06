"""Единица и масштаб факта. Оба живут в книге и наследуются одним обходом источников.

Обход тот же, что у масштаба строки формы: множитель строки-источника важнее
пустого множителя факта, разные значения не угадываются, известный масштаб
дальше не разворачивается. Конкретная единица снимается с тех же узлов.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation

from finance_analysis.domain.audit import AuditInput


def metadata_factor(row: dict) -> Decimal | None:
    scale = row.get("scale_factor")
    if scale in (None, ""):
        return None
    try:
        return Decimal(str(scale))
    except InvalidOperation:
        return None


def concrete_unit(row: dict, unit_dimensions: Mapping[str, str]) -> str | None:
    """Единица каталога (RUB, MWh, year). Грубые money/rate/count единицей книги не считаются."""

    token = row.get("unit")
    if isinstance(token, str) and token in unit_dimensions:
        return token
    return None


def dependency_measure(
    data: AuditInput,
    row_key: str,
    unit_dimensions: Mapping[str, str] | None = None,
) -> tuple[Decimal | None, str | None]:
    """Общий масштаб и конкретная единица источников формулы. Разногласие даёт пустое значение."""

    factors: list[Decimal] = []
    units: list[str] = []
    seen: set[str] = set()
    stack = [fact.get("cell_id") for fact in data.facts if fact.get("row_key") == row_key and fact.get("cell_id")]
    while stack:
        cell = stack.pop()
        if not cell or cell in seen:
            continue
        seen.add(cell)
        for ref in _refs_of(data, cell):
            fact = data.facts_by_cell.get(ref)
            if fact is None:
                continue
            scale = metadata_factor(fact)
            row = data.rows_by_key.get(fact["row_key"]) or {} if fact.get("row_key") else {}
            if scale is None and fact.get("row_key"):
                scale = metadata_factor(row)
            if scale is not None:
                factors.append(scale)
                if unit_dimensions:
                    unit = concrete_unit(fact, unit_dimensions) or concrete_unit(row, unit_dimensions)
                    if unit is not None:
                        units.append(unit)
                continue
            if fact.get("cell_id"):
                stack.append(fact["cell_id"])
    scale = factors[0] if len(set(factors)) == 1 else None
    unit = units[0] if len(set(units)) == 1 else None
    return scale, unit


def stamp_facts(
    facts: list[dict],
    rows: list[dict],
    unit_dimensions: Mapping[str, str] | None = None,
) -> list[dict]:
    """Факт без своего масштаба берёт множитель строки. Конкретная единица копируется так же.

    Числовой масштаб не выводится из формул: это делает обход источников отдельно,
    чтобы справочные коэффициенты не сменили множитель.
    """

    units = unit_dimensions or {}
    scale_of: dict[str, object] = {}
    unit_of: dict[str, str] = {}
    for row in rows:
        key = row.get("row_key")
        if not key:
            continue
        if row.get("scale_factor") not in (None, ""):
            scale_of[str(key)] = row.get("scale_factor")
        unit = concrete_unit(row, units)
        if unit is not None:
            unit_of[str(key)] = unit
    if not scale_of and not unit_of:
        return facts
    stamped = []
    for fact in facts:
        key = str(fact.get("row_key") or "")
        updated = fact
        if fact.get("scale_factor") in (None, "") and key in scale_of:
            updated = {**updated, "scale_factor": scale_of[key]}
        if concrete_unit(fact, units) is None and key in unit_of:
            updated = {**updated, "unit": unit_of[key]}
        stamped.append(updated)
    return stamped


def _refs_of(data: AuditInput, cell: str) -> tuple[str, ...]:
    link = data.link_cells.get(cell)
    return link.refs if link is not None else ()
