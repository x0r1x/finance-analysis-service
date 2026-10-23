"""Проекция снимка builder в строки звезды (§4.3, §4.4, §4.8)."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal

from finance_analysis.domain.book import (
    SnapshotAxis,
    SnapshotPeriod,
    WorkbookSnapshot,
    binding_key,
    cell_id,
    parse_decimal_text,
)
from finance_analysis.domain.currency import resolve_currencies
from finance_analysis.domain.periods import (
    expand_ref,
    marker_class,
    resolve_period_dates,
    split_period_key,
)
from finance_analysis.domain.phases import PHASES, split_phase_target
from finance_analysis.domain.state import fold


def _text(value: str | None) -> str | None:
    if value is None:
        return None
    return str(value)


def project(
    snapshot: WorkbookSnapshot, *, model_id: str, build: str
) -> tuple[dict[str, list[dict]], list[dict]]:
    occurrences: Counter[tuple] = Counter()
    dim_rows: list[dict] = []
    dim_periods: list[dict] = []
    facts: list[dict] = []
    seen_periods: set[tuple[str, str]] = set()
    previous_end: dict[str, object] = {}
    copied, warnings = _timeline_flags(snapshot.axes)

    for axis in snapshot.axes.values():
        for period in sorted(axis.periods, key=lambda item: item.index):
            base, marker = split_period_key(period.period_key)
            if axis.axis_kind == "params":
                start, end, source = None, None, "none"
            else:
                start, end, source = resolve_period_dates(
                    base,
                    calendar_year=period.calendar_year,
                    start_date=period.start_date,
                    end_date=period.end_date,
                    previous_end=previous_end.get(axis.id),  # type: ignore[arg-type]
                )
            if end is not None:
                previous_end[axis.id] = end
            if (axis.id, period.period_key) in seen_periods:
                continue
            seen_periods.add((axis.id, period.period_key))
            flags, flags_source = copied.get((axis.id, period.index), (period.flags, "own" if period.flags else None))
            dim_periods.append(
                {
                    "model_id": model_id,
                    "build_key": build,
                    "axis_id": axis.id,
                    "timeline_id": axis.timeline_id,
                    "axis_kind": axis.axis_kind,
                    "period_id": period.period_key,
                    "period_index": period.index,
                    "col": period.col,
                    "header_text": period.text,
                    "grain": axis.grain,
                    "period_key_base": base,
                    "period_marker": marker,
                    "marker_class": marker_class(marker),
                    "calendar_year": period.calendar_year,
                    "flags_json": __import__("json").dumps(flags, ensure_ascii=False, sort_keys=True),
                    "flags_source": flags_source,
                    "hidden": period.hidden,
                    "period_start": start,
                    "period_end": end,
                    "date_source": source,
                }
            )

    for row in snapshot.rows:
        path = list(row.label_path)
        occ_key = (row.sheet, tuple(path), row.label)
        occurrence = occurrences[occ_key]
        occurrences[occ_key] += 1
        bkey = binding_key(row.sheet, path, row.label, occurrence)
        hints = row.hints or {}
        dim_rows.append(
            {
                "model_id": model_id,
                "build_key": build,
                "row_key": row.row_key,
                "binding_key": bkey,
                "sheet": row.sheet,
                "row_num": row.row,
                "block_id": row.block_id,
                "block_kind": row.block_kind,
                "label": row.label,
                "parent_label": row.parent_label,
                "label_path_json": __import__("json").dumps(path, ensure_ascii=False),
                "label_path_text": " › ".join(path + [row.label]),
                "kind": row.kind,
                "indent": row.indent,
                "hidden": row.hidden,
                "check_row": row.check_row,
                "unit": hints.get("unit") or row.unit,
                "unit_per": hints.get("unit_per"),
                "currency": hints.get("currency"),
                "currency_source": None,
                "scale": hints.get("scale"),
                "scale_factor": row.scale_factor,
                "has_formula": bool(row.formula),
                "formula": row.formula,
            }
        )
        series_list = list(row.series)
        if not series_list and snapshot.axes:
            axis_id = next(iter(snapshot.axes))
            series_list = [
                type(row.series[0]) if False else __import__("finance_analysis.domain.book", fromlist=["SnapshotSeries"]).SnapshotSeries(
                    axis_id=axis_id,
                    values=row.values,
                    value_statuses=row.value_statuses or tuple("cached" for _ in row.values),
                    normalized_values=row.normalized_values or tuple(None for _ in row.values),
                    formula=row.formula,
                )
            ]
        for series in series_list:
            axis = snapshot.axes.get(series.axis_id)
            if axis is None:
                continue
            periods = sorted(axis.periods, key=lambda item: item.index)
            for index, period in enumerate(periods):
                raw = series.values[index] if index < len(series.values) else None
                status = (
                    series.value_statuses[index]
                    if index < len(series.value_statuses)
                    else "empty"
                )
                normalized_raw = (
                    series.normalized_values[index] if index < len(series.normalized_values) else None
                )
                value_dec = parse_decimal_text(None if raw is None else str(raw))
                normalized = parse_decimal_text(None if normalized_raw is None else str(normalized_raw))
                facts.append(
                    {
                        "model_id": model_id,
                        "build_key": build,
                        "row_key": row.row_key,
                        "axis_id": series.axis_id,
                        "axis_kind": axis.axis_kind,
                        "period_id": period.period_key,
                        "cell_id": cell_id(row.sheet, period.col, row.row),
                        "value_raw": None if raw is None else str(raw),
                        "value": value_dec,
                        "value_dec": value_dec,
                        "normalized_value": normalized if normalized is not None else value_dec,
                        "value_status": status or "empty",
                    }
                )

    resolved = resolve_currencies(
        [(row["kind"], row.get("currency"), row.get("unit")) for row in dim_rows]
    )
    for row, (currency, source) in zip(dim_rows, resolved, strict=True):
        row["currency"] = currency
        row["currency_source"] = source

    return {
        "dim_row": dim_rows,
        "dim_period": dim_periods,
        "fact_observation": facts,
        "graph_links": _links(snapshot, model_id, build),
    }, warnings


def _timeline_flags(
    axes: dict[str, SnapshotAxis],
) -> tuple[dict[tuple[str, int], tuple[dict, str | None]], list[dict]]:
    """Флаги канонической оси копируются по index. Фаза из них не выводится (§4.4)."""

    canonical: dict[str, dict[int, SnapshotPeriod]] = {}
    for axis in axes.values():
        if axis.timeline_id and axis.id == axis.timeline_id:
            canonical[axis.timeline_id] = {period.index: period for period in axis.periods}
    copied: dict[tuple[str, int], tuple[dict, str | None]] = {}
    warnings: list[dict] = []
    for axis in axes.values():
        if axis.axis_kind == "params":
            for period in axis.periods:
                copied[(axis.id, period.index)] = ({}, None)
            continue
        source_axis = canonical.get(axis.timeline_id or "")
        for period in axis.periods:
            own = dict(period.flags)
            if source_axis is None or axis.id == axis.timeline_id:
                copied[(axis.id, period.index)] = (own, "own" if own else None)
                continue
            other = source_axis.get(period.index)
            if other is None:
                copied[(axis.id, period.index)] = (own, "own" if own else None)
                continue
            if other.period_key != period.period_key:
                warnings.append(
                    {
                        "code": "timeline_mismatch",
                        "params": {
                            "axis_id": axis.id,
                            "index": period.index,
                            "period_key": period.period_key,
                            "timeline_period_key": other.period_key,
                        },
                    }
                )
                copied[(axis.id, period.index)] = (own, "own" if own else None)
                continue
            flags = dict(other.flags)
            copied[(axis.id, period.index)] = (flags, "timeline" if flags else None)
    return copied, warnings


def _links(snapshot: WorkbookSnapshot, model_id: str, build: str) -> list[dict]:
    used_rows = 1
    used_cols = 1
    for sheet, (rows, cols) in snapshot.used_range.items():
        used_rows = max(used_rows, rows)
        used_cols = max(used_cols, cols)
    out: list[dict] = []
    for link in snapshot.links:
        sheet = link.cell.split("!", 1)[0] if link.cell and "!" in link.cell else None
        for ref in link.refs:
            cells, truncated = expand_ref(
                ref,
                default_sheet=sheet,
                used_rows=used_rows,
                used_cols=used_cols,
            )
            for cell in cells:
                out.append(
                    {
                        "model_id": model_id,
                        "build_key": build,
                        "cell": link.cell,
                        "formula": link.formula,
                        "formula_class": link.formula_class,
                        "ref_cell": cell,
                        "row_key": link.row_key,
                        "period_id": link.period_id,
                        "truncated": truncated,
                    }
                )
    return out


def _decision_maps(events: list[dict]) -> tuple[dict[tuple[str, str], str], dict[str, str]]:
    phases: dict[tuple[str, str], str] = {}
    concepts: dict[str, str] = {}
    for target, event in fold(events).items():
        kind = event.get("type")
        if kind == "phase.set":
            parsed = split_phase_target(str(target))
            value = event.get("value")
            if parsed and isinstance(value, str) and value in PHASES:
                phases[parsed] = value
        elif kind in {"concept.set", "concept.confirmed"}:
            value = event.get("value")
            if isinstance(value, str) and value:
                concepts[str(target)] = value
    return phases, concepts


def derive_rows(
    projected: dict[str, list[dict]],
    *,
    state_seq: int,
    derive: str,
    versions: dict,
    events: list[dict] | None = None,
) -> dict[str, list[dict]]:
    now = datetime.now(UTC)
    phases, concepts = _decision_maps(events or [])
    glossary = versions.get("glossary", "none")
    taxonomy = versions.get("taxonomy", "core-1")
    calibrator = versions.get("calibrator", "none")
    row_semantics = []
    bindings = []
    for row in projected["dim_row"]:
        excluded = row["kind"] in {"helper", "flag", "index"} or row["hidden"] or row["check_row"]
        reason = None
        if row["kind"] in {"helper", "flag", "index"}:
            reason = row["kind"]
        elif row["hidden"]:
            reason = "hidden"
        elif row["check_row"]:
            reason = "check_row"
        row_semantics.append(
            {
                "model_id": row["model_id"],
                "build_key": row["build_key"],
                "state_seq": state_seq,
                "derive_key": derive,
                "binding_key": row["binding_key"],
                "row_key": row["row_key"],
                "sign": None,
                "nature": None,
                "aggregation": None,
                "period_position": None,
                "excluded": excluded,
                "exclusion_reason": reason,
                "is_check": row["check_row"],
                "source": "inferred",
                "confidence": None,
                "evidence_json": "{}",
                "stale": False,
            }
        )
        if row["kind"] != "fact":
            continue
        chosen = concepts.get(row["binding_key"])
        bindings.append(
            {
                "model_id": row["model_id"],
                "build_key": row["build_key"],
                "state_seq": state_seq,
                "derive_key": derive,
                "concept": chosen,
                "effective_concept": chosen,
                "is_primary": chosen is not None,
                "matched_label_id": None,
                "status": "bound" if chosen else "unknown",
                "binding_key": row["binding_key"],
                "row_key": row["row_key"],
                "label_path_text": row["label_path_text"],
                "source": "confirmed" if chosen else "inferred",
                "confidence": None,
                "evidence_json": "{}",
                "calibrator_version": calibrator,
                "glossary_version": glossary,
                "taxonomy_version": taxonomy,
                "decided_by": None,
                "stale": False,
                "importance": "normal",
                "updated_at_utc": now,
            }
        )
    # Фаза только из phase.set. Флаги в dim_period остаются для отображения и здесь не читаются.
    period_semantics = []
    counted: dict[tuple[str, str], int] = {}
    for period in sorted(projected["dim_period"], key=lambda item: (item["axis_id"], item["period_index"])):
        phase = phases.get((period["axis_id"], period.get("period_key_base") or period["period_id"]))
        phase_year = None
        source = "inferred"
        if phase:
            key = (period["axis_id"], phase)
            counted[key] = counted.get(key, 0) + 1
            phase_year = counted[key]
            source = "decision"
        period_semantics.append(
            {
                "model_id": period["model_id"],
                "build_key": period["build_key"],
                "state_seq": state_seq,
                "derive_key": derive,
                "axis_id": period["axis_id"],
                "period_id": period["period_id"],
                "phase": phase,
                "phase_year": phase_year,
                "source": source,
                "evidence_json": "{}",
            }
        )
    coverage_map: dict[tuple[str, str], int] = {}
    for binding in bindings:
        key = (binding["status"], binding["importance"])
        coverage_map[key] = coverage_map.get(key, 0) + 1
    coverage = [
        {
            "model_id": projected["dim_row"][0]["model_id"] if projected["dim_row"] else "",
            "build_key": build_of(projected),
            "state_seq": state_seq,
            "derive_key": derive,
            "glossary_version": glossary,
            "status": status,
            "importance": importance,
            "rows": count,
            "value_abs_sum": Decimal(0),
        }
        for (status, importance), count in sorted(coverage_map.items())
    ]
    return {
        "row_semantics": row_semantics,
        "period_semantics": period_semantics,
        "bindings": bindings,
        "coverage": coverage,
    }


def build_of(projected: dict[str, list[dict]]) -> str:
    for rows in projected.values():
        if rows:
            return rows[0]["build_key"]
    return ""
