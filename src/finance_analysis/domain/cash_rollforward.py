"""Сверка остатка денежных средств. Число ячейки не подменяется.

Формула читается из configs/identities/cash_corkscrew.yaml, ключ corkscrew.
Суммы lf.identity этот файл не кормит. Курс из остатка не выводится.
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
_BALANCE = "cash"


@dataclass(frozen=True)
class CashCorkscrew:
    closing: str
    opening: str | None
    inflow: str
    outflow: str
    net: str | None
    fx: str | None
    tolerance: Decimal


@dataclass(frozen=True)
class CashNote:
    tag: str
    row_key: str
    axis_id: str
    period_id: str
    params: dict


def corkscrew_file() -> Path:
    return configs_root() / "configs" / "identities" / "cash_corkscrew.yaml"


@lru_cache(maxsize=1)
def load_cash_corkscrew(path: str | None = None) -> CashCorkscrew:
    file = Path(path) if path else corkscrew_file()
    document = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
    raw = document.get("corkscrew")
    if not isinstance(raw, dict):
        raise InvalidArgument("corkscrew денежных средств не задан")
    return CashCorkscrew(
        closing=concept_id(str(raw.get("closing") or "")),
        opening=_optional(raw.get("opening")),
        inflow=concept_id(str(raw.get("inflow") or "")),
        outflow=concept_id(str(raw.get("outflow") or "")),
        net=_optional(raw.get("net")),
        fx=_optional(raw.get("fx")),
        tolerance=Decimal(str(raw.get("tolerance") or "0.005")),
    )


def check_cash(data: AuditInput, spec: CashCorkscrew | None = None) -> list[CashNote]:
    """Остаток на конец против открытия и движения. Пустой список — сверять не с чем или числа сошлись."""

    spec = spec or load_cash_corkscrew()
    close = _one(data, spec.closing)
    if close is None:
        return []
    basis = _basis(data, spec, close)
    if basis is None:
        return [CashNote("insufficient_data", close, "", "", {})]
    return _residuals(data, spec, close, basis)


def statement_tie(data: AuditInput, spec: CashCorkscrew | None = None) -> list[CashNote]:
    """Расхождение строки баланса и остатка отчёта. Это не выбор между РСБУ и МСФО."""

    spec = spec or load_cash_corkscrew()
    close = _one(data, spec.closing)
    balance = _one(data, _BALANCE)
    if close is None or balance is None:
        return []
    left = _by_period(_series(data, close))
    right = _by_period(_series(data, balance))
    periods = [
        period
        for period in sorted(set(left) & set(right))
        if left[period] is not None
        and right[period] is not None
        and abs(left[period] - right[period]) > spec.tolerance
    ]
    if not periods:
        return []
    return [CashNote("tie", close, "", periods[0], {"periods": periods})]


def _optional(raw: object) -> str | None:
    if raw in (None, ""):
        return None
    return concept_id(str(raw))


def _basis(data: AuditInput, spec: CashCorkscrew, close: str) -> str | None:
    """Прецеденты закрытия, если они делят движение без вложенного итога. Иначе вал, иначе сальдо."""

    inflow = _one(data, spec.inflow)
    outflow = _one(data, spec.outflow)
    net = _one(data, spec.net)
    named = _precedents(data, close) & {row for row in (inflow, outflow, net) if row}
    if inflow and outflow and named == {inflow, outflow} and not _nested(data, inflow, outflow):
        return "gross"
    if net and named == {net}:
        return "net"
    if inflow and outflow:
        return "gross"
    if net:
        return "net"
    return None


def _nested(data: AuditInput, left: str, right: str) -> bool:
    return right in _precedents(data, left) or left in _precedents(data, right)


def _residuals(data: AuditInput, spec: CashCorkscrew, close: str, basis: str) -> list[CashNote]:
    opening = _one(data, spec.opening)
    inflow = _one(data, spec.inflow) if basis == "gross" else None
    outflow = _one(data, spec.outflow) if basis == "gross" else None
    net = _one(data, spec.net) if basis == "net" else None
    fx_row = _one(data, spec.fx)
    close_values = _series(data, close)
    open_values = _series(data, opening) if opening else {}
    notes: list[CashNote] = []
    checked = False
    for axis, periods in _axes(data, close_values):
        for index, period in enumerate(periods):
            book = close_values.get((axis, period))
            if book is None:
                continue
            if opening:
                opened = open_values.get((axis, period))
            elif index == 0:
                opened = None
            else:
                opened = close_values.get((axis, periods[index - 1]))
            if opened is None:
                continue
            movement = _movement(data, basis, inflow, outflow, net, axis, period)
            if movement is None:
                continue
            fx_value = Decimal(0)
            if fx_row:
                raw_fx = _series(data, fx_row).get((axis, period))
                if raw_fx is None:
                    continue
                fx_value = raw_fx
            checked = True
            residual = book - (opened + movement + fx_value)
            if abs(residual) > spec.tolerance:
                notes.append(_break(close, axis, period, "residual", basis, fx_row is not None, residual))
            if opening and index:
                prior = close_values.get((axis, periods[index - 1]))
                if prior is not None and abs(opened - prior) > spec.tolerance:
                    notes.append(_break(opening, axis, period, "continuity", basis, fx_row is not None, opened - prior))
    if not checked and not notes:
        return [CashNote("insufficient_data", close, "", "", {})]
    return notes


def _break(row_key: str, axis: str, period: str, reason: str, basis: str, fx: bool, residual: Decimal) -> CashNote:
    return CashNote(
        "break",
        row_key,
        axis,
        period,
        {
            "periods": [period],
            "reason": reason,
            "basis": basis,
            "fx": fx,
            "residual": format(residual, "f"),
        },
    )


def _movement(
    data: AuditInput,
    basis: str,
    inflow: str | None,
    outflow: str | None,
    net: str | None,
    axis: str,
    period: str,
) -> Decimal | None:
    key = (axis, period)
    if basis == "gross":
        if inflow is None or outflow is None:
            return None
        received = _series(data, inflow).get(key)
        paid = _series(data, outflow).get(key)
        if received is None or paid is None:
            return None
        # Скобки в книге уже хранят отток со знаком минус. Вычитаем модуль, не второй раз минус.
        return received - abs(paid)
    if net is None:
        return None
    signed = _series(data, net).get(key)
    return signed


def _axes(data: AuditInput, series: dict[tuple[str, str], Decimal]) -> list[tuple[str, list[str]]]:
    return [(axis, _ordered(data, axis)) for axis in sorted({axis for axis, _period in series})]


def _ordered(data: AuditInput, axis: str) -> list[str]:
    rows = [
        (index, period)
        for index, period in enumerate(data.periods)
        if period.get("axis_id") == axis and period.get("axis_kind") != "params"
    ]

    def sort_key(pair: tuple[int, dict]) -> tuple[int, int]:
        index, period = pair
        raw = period.get("period_index")
        return (index if raw is None else int(raw), index)

    found: list[str] = []
    for _index, period in sorted(rows, key=sort_key):
        name = str(period.get("period_id") or "")
        if name and name not in found:
            found.append(name)
    return found


def _one(data: AuditInput, concept: str | None) -> str | None:
    if not concept:
        return None
    keys: list[str] = []
    for binding in data.bindings:
        if binding.get("status") not in _BOUND or binding.get("is_primary") is False:
            continue
        name = str(binding.get("effective_concept") or binding.get("concept") or "")
        key = binding.get("row_key")
        if name == concept and key and key not in keys:
            keys.append(str(key))
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


def _by_period(series: dict[tuple[str, str], Decimal]) -> dict[str, Decimal | None]:
    found: dict[str, Decimal | None] = {}
    for (_axis, period), value in series.items():
        if period not in found:
            found[period] = value
        elif found[period] != value:
            found[period] = None
    return found
