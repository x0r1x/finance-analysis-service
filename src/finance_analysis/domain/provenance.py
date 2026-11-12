"""Сборка логической записи FinancialFactProvenance поверх датасетов §4.4.

Контракт: docs/financial-fact-provenance.md. Не пишет новый датасет и не
дублирует value*/concept — только join существующих строк.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any


class ProvenanceJoinError(ValueError):
    """Не удалось собрать провенанс: отсутствует строка справочника по ключу join."""


class ProvenanceIntegrityError(ValueError):
    """Несколько primary bindings на один ключ. Сборка не выбирает строку."""

    reason: str = "multiple_primary_bindings"


@dataclass(frozen=True)
class UndefinedFinancialFact:
    """Нет primary binding. Поля кандидата не копируются."""

    model_id: str
    build_key: str
    row_key: str
    binding_key: str
    reason: str = "no_primary_binding"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FinancialFactProvenance:
    """Логический view финансового факта (не строка Parquet)."""

    model_id: str
    build_key: str
    row_key: str
    binding_key: str
    cell_id: str
    axis_id: str
    axis_kind: str
    period_id: str
    value_status: str
    sheet: str
    binding_status: str
    is_primary: bool
    binding_stale: bool
    state_seq: int
    derive_key: str
    period_index: int
    value_raw: str | None = None
    value: float | None = None
    value_dec: Any = None
    normalized_value: Any = None
    label: str | None = None
    unit: str | None = None
    currency: str | None = None
    scale: str | None = None
    concept: str | None = None
    effective_concept: str | None = None
    binding_source: str | None = None
    binding_confidence: float | None = None
    matched_label_id: str | None = None
    glossary_version: str | None = None
    taxonomy_version: str | None = None
    decided_by: str | None = None
    period_key_base: str | None = None
    grain: str | None = None
    header_text: str | None = None
    calendar_year: int | None = None
    timeline_id: str | None = None
    sign: str | None = None
    nature: str | None = None
    aggregation: str | None = None
    excluded: bool | None = None
    semantic_model_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def assemble_financial_fact_provenance(
    fact: Mapping[str, Any],
    *,
    rows: Sequence[Mapping[str, Any]],
    periods: Sequence[Mapping[str, Any]],
    bindings: Sequence[Mapping[str, Any]],
    row_semantics: Sequence[Mapping[str, Any]] | None = None,
    semantic_model_version: str | None = None,
) -> FinancialFactProvenance | UndefinedFinancialFact:
    """Собрать провенанс одной ячейки из справочников §4.4.

    Ровно одна primary binding. Ноль primary — UndefinedFinancialFact.
    Несколько primary — ProvenanceIntegrityError. Семантика в этом слое
    по-прежнему присоединяется отдельно. semantic_model_version — публичный
    SMV, переданный снаружи; он не выбирает binding и не подменяет derive_key.
    """

    model_id = _req(fact, "model_id")
    build_key = _req(fact, "build_key")
    row_key = _req(fact, "row_key")
    axis_id = _req(fact, "axis_id")
    period_id = _req(fact, "period_id")

    row = _find_one(
        rows,
        {"model_id": model_id, "build_key": build_key, "row_key": row_key},
        dataset="dim_row",
    )
    binding_key = _req(row, "binding_key")

    resolved = _resolve_binding(
        bindings,
        model_id=model_id,
        build_key=build_key,
        row_key=row_key,
        binding_key=binding_key,
    )
    if isinstance(resolved, UndefinedFinancialFact):
        return resolved
    binding = resolved
    period = _find_one(
        periods,
        {
            "model_id": model_id,
            "build_key": build_key,
            "axis_id": axis_id,
            "period_id": period_id,
        },
        dataset="dim_period",
    )
    semantics = _find_semantics(
        row_semantics or (),
        model_id=model_id,
        build_key=build_key,
        binding_key=binding_key,
        derive_key=str(binding["derive_key"]),
    )

    return FinancialFactProvenance(
        model_id=model_id,
        build_key=build_key,
        row_key=row_key,
        binding_key=binding_key,
        cell_id=_req(fact, "cell_id"),
        axis_id=axis_id,
        axis_kind=_req(fact, "axis_kind"),
        period_id=period_id,
        value_raw=_opt(fact, "value_raw"),
        value=_opt(fact, "value"),
        value_dec=_opt(fact, "value_dec"),
        normalized_value=_opt(fact, "normalized_value"),
        value_status=_req(fact, "value_status"),
        sheet=_req(row, "sheet"),
        label=_opt(row, "label"),
        unit=_opt(row, "unit"),
        currency=_opt(row, "currency"),
        scale=_opt(row, "scale"),
        concept=_opt(binding, "concept"),
        effective_concept=_opt(binding, "effective_concept"),
        binding_status=_req(binding, "status"),
        binding_source=_opt(binding, "source"),
        binding_confidence=_opt(binding, "confidence"),
        matched_label_id=_opt(binding, "matched_label_id"),
        is_primary=bool(binding["is_primary"]),
        glossary_version=_opt(binding, "glossary_version"),
        taxonomy_version=_opt(binding, "taxonomy_version"),
        decided_by=_opt(binding, "decided_by"),
        binding_stale=bool(binding["stale"]),
        state_seq=int(binding["state_seq"]),
        derive_key=str(binding["derive_key"]),
        period_index=int(period["period_index"]),
        period_key_base=_opt(period, "period_key_base"),
        grain=_opt(period, "grain"),
        header_text=_opt(period, "header_text"),
        calendar_year=_opt(period, "calendar_year"),
        timeline_id=_opt(period, "timeline_id"),
        sign=_opt(semantics, "sign") if semantics else None,
        nature=_opt(semantics, "nature") if semantics else None,
        aggregation=_opt(semantics, "aggregation") if semantics else None,
        excluded=bool(semantics["excluded"]) if semantics and "excluded" in semantics else None,
        semantic_model_version=semantic_model_version,
    )


def _req(row: Mapping[str, Any], name: str) -> str:
    if name not in row or row[name] is None or row[name] == "":
        raise ProvenanceJoinError(f"missing required field {name!r}")
    return str(row[name])


def _opt(row: Mapping[str, Any], name: str) -> Any:
    return row.get(name)


def _matches(row: Mapping[str, Any], keys: Mapping[str, str]) -> bool:
    return all(str(row.get(name)) == value for name, value in keys.items())


def _find_one(
    rows: Sequence[Mapping[str, Any]],
    keys: Mapping[str, str],
    *,
    dataset: str,
) -> Mapping[str, Any]:
    matched = [row for row in rows if _matches(row, keys)]
    if not matched:
        raise ProvenanceJoinError(f"{dataset}: no row for {dict(keys)}")
    if len(matched) > 1:
        raise ProvenanceJoinError(f"{dataset}: ambiguous join for {dict(keys)}")
    return matched[0]


def _resolve_binding(
    bindings: Sequence[Mapping[str, Any]],
    *,
    model_id: str,
    build_key: str,
    row_key: str,
    binding_key: str,
) -> Mapping[str, Any] | UndefinedFinancialFact:
    matched = [
        row
        for row in bindings
        if _matches(
            row,
            {"model_id": model_id, "build_key": build_key, "binding_key": binding_key},
        )
    ]
    if not matched:
        raise ProvenanceJoinError(
            f"bindings: no row for model_id={model_id!r} build_key={build_key!r} "
            f"binding_key={binding_key!r}"
        )
    primary = [row for row in matched if row.get("is_primary")]
    if len(primary) > 1:
        raise ProvenanceIntegrityError(
            "bindings: multiple primary rows for "
            f"model_id={model_id!r} build_key={build_key!r} "
            f"binding_key={binding_key!r}"
        )
    if not primary:
        return UndefinedFinancialFact(
            model_id=model_id,
            build_key=build_key,
            row_key=row_key,
            binding_key=binding_key,
        )
    return primary[0]


def _find_semantics(
    rows: Sequence[Mapping[str, Any]],
    *,
    model_id: str,
    build_key: str,
    binding_key: str,
    derive_key: str,
) -> Mapping[str, Any] | None:
    if not rows:
        return None
    matched = [
        row
        for row in rows
        if _matches(
            row,
            {
                "model_id": model_id,
                "build_key": build_key,
                "binding_key": binding_key,
            },
        )
    ]
    if not matched:
        return None
    same_derive = [row for row in matched if str(row.get("derive_key")) == derive_key]
    return (same_derive or matched)[0]
