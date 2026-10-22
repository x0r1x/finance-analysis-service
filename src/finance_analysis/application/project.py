"""Проекция снимка builder в строки звезды (§4.3, §4.4, §4.8)."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal

from finance_analysis.domain.book import (
    WorkbookSnapshot,
    binding_key,
    cell_id,
    parse_decimal_text,
)
from finance_analysis.domain.periods import (
    expand_ref,
    marker_class,
    phase_from_flags,
    resolve_period_dates,
    split_period_key,
)


def _text(value: str | None) -> str | None:
    if value is None:
        return None
    return str(value)


def project(snapshot: WorkbookSnapshot, *, model_id: str, build: str) -> dict[str, list[dict]]:
    occurrences: Counter[tuple] = Counter()
    dim_rows: list[dict] = []
    dim_periods: list[dict] = []
    facts: list[dict] = []
    seen_periods: set[tuple[str, str]] = set()
    previous_end: dict[str, object] = {}

    for axis in snapshot.axes.values():
        for period in sorted(axis.periods, key=lambda item: item.index):
            base, marker = split_period_key(period.period_key)
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
            dim_periods.append(
                {
                    "model_id": model_id,
                    "build_key": build,
                    "axis_id": axis.id,
                    "period_id": period.period_key,
                    "period_index": period.index,
                    "col": period.col,
                    "header_text": period.text,
                    "grain": axis.grain,
                    "period_key_base": base,
                    "period_marker": marker,
                    "marker_class": marker_class(marker),
                    "calendar_year": period.calendar_year,
                    "group_key": period.group_key,
                    "flags_json": __import__("json").dumps(period.flags, ensure_ascii=False, sort_keys=True),
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
                        "period_id": period.period_key,
                        "cell_id": cell_id(row.sheet, period.col, row.row),
                        "value_raw": None if raw is None else str(raw),
                        "value": value_dec,
                        "value_dec": value_dec,
                        "normalized_value": normalized if normalized is not None else value_dec,
                        "value_status": status or "empty",
                    }
                )

    return {
        "dim_row": dim_rows,
        "dim_period": dim_periods,
        "fact_observation": facts,
        "graph_links": _links(snapshot, model_id, build),
    }


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


def derive_rows(
    projected: dict[str, list[dict]],
    *,
    state_seq: int,
    derive: str,
    versions: dict,
) -> dict[str, list[dict]]:
    now = datetime.now(timezone.utc)
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
        bindings.append(
            {
                "model_id": row["model_id"],
                "build_key": row["build_key"],
                "state_seq": state_seq,
                "derive_key": derive,
                "concept": None,
                "effective_concept": None,
                "is_primary": False,
                "matched_label_id": None,
                "status": "unknown",
                "binding_key": row["binding_key"],
                "row_key": row["row_key"],
                "label_path_text": row["label_path_text"],
                "source": "inferred",
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
    phases: dict[tuple[str, str], str | None] = {}
    for period in projected["dim_period"]:
        flags = __import__("json").loads(period["flags_json"] or "{}")
        phases[(period["axis_id"], period["period_id"])] = phase_from_flags(flags)
    # Нумеруем phase_year внутри фазы по оси.
    counters: dict[tuple[str, str], int] = {}
    period_semantics = []
    for period in sorted(projected["dim_period"], key=lambda item: (item["axis_id"], item["period_index"])):
        phase = phases[(period["axis_id"], period["period_id"])]
        phase_year = None
        if phase:
            key = (period["axis_id"], phase)
            counters[key] = counters.get(key, 0) + 1
            phase_year = counters[key]
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
                "source": "inferred",
                "evidence_json": period["flags_json"],
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
