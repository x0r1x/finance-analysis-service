"""Сверка ЧОД с каскадом 568-р. Число ячейки не подменяется.

Формула читается из configs/identities/noi.yaml, ключ difference.
Суммы lf.identity этот файл не кормит.
shortcut: допуск — 1 единица value_dec, не доля коэффициента. Менять, когда книги округляют сильнее.
shortcut: пустая строка управления не получает рыночный процент. Доначисление — отдельная поставка.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import yaml

from finance_analysis.domain.audit import AuditInput
from finance_analysis.domain.derive_fingerprint import configs_root
from finance_analysis.domain.errors import InvalidArgument
from finance_analysis.domain.ids import concept_id

_BOUND = frozenset({"bound", "bound_with_warning"})
_VALUED = frozenset({"cached", "zero_explicit"})
_TOLERANCE = Decimal(1)


@dataclass(frozen=True)
class NoiDifference:
    result: str
    plus: tuple[str, ...]
    minus: tuple[str, ...]
    optional_minus: tuple[str, ...]
    forbid: tuple[str, ...]
    exclusive: tuple[str, ...]


@dataclass(frozen=True)
class NoiNote:
    tag: str
    row_key: str
    params: dict


def noi_file() -> Path:
    return configs_root() / "configs" / "identities" / "noi.yaml"


@lru_cache(maxsize=1)
def load_noi_difference(path: str | None = None) -> NoiDifference:
    file = Path(path) if path else noi_file()
    document = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
    raw = document.get("difference")
    if not isinstance(raw, dict):
        raise InvalidArgument("difference ЧОД не задана")
    return NoiDifference(
        result=concept_id(str(raw.get("result") or "")),
        plus=_names(raw.get("plus")),
        minus=_names(raw.get("minus")),
        optional_minus=_names(raw.get("optional_minus")),
        forbid=_names(raw.get("forbid")),
        exclusive=_names(raw.get("exclusive")),
    )


def reconcile(data: AuditInput, spec: NoiDifference | None = None) -> list[NoiNote]:
    """Находки сверки. Пустой список — сверять не с чем или числа сошлись."""

    spec = spec or load_noi_difference()
    notes: list[NoiNote] = []
    result = _one(data, spec.result)
    land = [(name, row) for name in spec.exclusive if (row := _one(data, name))]
    if len(spec.exclusive) >= 2 and len(land) == len(spec.exclusive):
        notes.append(NoiNote("double_land", result or land[0][1], {"concepts": [name for name, _row in land]}))
    if result:
        precedents = _precedents(data, result)
        for name in spec.forbid:
            row = _one(data, name)
            if row and row in precedents:
                notes.append(NoiNote("forbidden", result, {"concept": name}))
    required = {name: _one(data, name) for name in (spec.result, *spec.plus, *spec.minus)}
    if any(row is None for row in required.values()) or any(note.tag == "double_land" for note in notes):
        return notes
    expenses = required[spec.minus[0]]
    reserve = required[spec.minus[-1]]
    if expenses and reserve and reserve in _precedents(data, expenses):
        return [*notes, NoiNote("double_reserve", expenses, {"reserve": reserve})]
    optional: list[str] = []
    for name in spec.optional_minus:
        found = _bound(data, name)
        if len(found) > 1:
            return notes
        if found:
            optional.append(found[0])
    result_row = required[spec.result]
    broken = _broken(
        data,
        result_row or "",
        [required[name] or "" for name in spec.plus],
        [required[name] or "" for name in spec.minus],
        optional,
    )
    if broken and result_row:
        notes.append(NoiNote("mismatch", result_row, {"periods": broken}))
    return notes


def _names(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, list) or not raw:
        return ()
    return tuple(concept_id(str(item)) for item in raw)


def _bound(data: AuditInput, concept: str) -> list[str]:
    keys: list[str] = []
    for binding in data.bindings:
        if binding.get("status") not in _BOUND or binding.get("is_primary") is False:
            continue
        name = str(binding.get("effective_concept") or binding.get("concept") or "")
        key = binding.get("row_key")
        if name == concept and key and str(key) not in keys:
            keys.append(str(key))
    return keys


def _one(data: AuditInput, concept: str) -> str | None:
    keys = _bound(data, concept)
    if len(keys) == 1:
        return keys[0]
    return None


def _precedents(data: AuditInput, row_key: str) -> set[str]:
    found: set[str] = set()
    for fact in data.facts_by_row.get(row_key, ()):
        link = data.link_cells.get(fact.get("cell_id"))
        if link is None:
            continue
        for ref in link.refs:
            other = data.facts_by_cell.get(ref)
            if other and other.get("row_key"):
                found.add(str(other["row_key"]))
    return found


def _series(data: AuditInput, row_key: str) -> dict[tuple[str, str], Decimal]:
    found: dict[tuple[str, str], Decimal] = {}
    for fact in data.facts_by_row.get(row_key, ()):
        if fact.get("value_status") not in _VALUED or fact.get("value_dec") is None:
            continue
        found[(str(fact.get("axis_id")), str(fact.get("period_id")))] = Decimal(fact["value_dec"])
    return found


def _broken(
    data: AuditInput,
    result: str,
    plus: list[str],
    minus: list[str],
    optional: list[str],
) -> list[str]:
    target = _series(data, result)
    parts = [_series(data, row) for row in (*plus, *minus, *optional)]
    broken: list[str] = []
    for key, book in target.items():
        values = [series.get(key) for series in parts]
        if any(item is None for item in values):
            continue
        numbers = [item for item in values if item is not None]
        plus_n = len(plus)
        reconstructed = sum(numbers[:plus_n], Decimal(0)) - sum((abs(item) for item in numbers[plus_n:]), Decimal(0))
        if abs(reconstructed - book) > _TOLERANCE:
            broken.append(key[1])
    return broken
