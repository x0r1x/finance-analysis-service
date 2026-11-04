"""Проекция снимка builder в строки звезды (§4.3, §4.4, §4.8)."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal

from finance_analysis.application.sheet_roles import load_sheet_roles
from finance_analysis.domain.book import (
    SnapshotAxis,
    SnapshotPeriod,
    WorkbookSnapshot,
    binding_key,
    cell_id,
    parse_decimal_text,
)
from finance_analysis.domain.currency import resolve_currencies
from finance_analysis.domain.glossary import label_features
from finance_analysis.domain.mapping import assign_rows, verify_numeric
from finance_analysis.domain.periods import (
    expand_ref,
    marker_class,
    resolve_period_dates,
    split_period_key,
)
from finance_analysis.domain.phases import PHASES, split_phase_target
from finance_analysis.domain.semantics import empty_series, exclusion, infer_row
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
                "formula_exceptions_json": __import__("json").dumps(_exceptions(row), ensure_ascii=False),
                "formula_exceptions_truncated": _exceptions_truncated(row),
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


# builder режет formula_exceptions до 8 ячеек на серию (§2.3). Ровно 8 не отличить
# от обрезки, поэтому флаг значит «мог быть урезан»; полный список — trace builder.
EXCEPTIONS_LIMIT = 8


def _exceptions(row) -> list[str]:
    found = set(row.formula_exceptions)
    for series in row.series:
        found.update(series.formula_exceptions)
    return sorted(found)


def _exceptions_truncated(row) -> bool:
    lists = [row.formula_exceptions, *(series.formula_exceptions for series in row.series)]
    return any(len(items) >= EXCEPTIONS_LIMIT for items in lists)


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
        if not link.refs:
            # Формула без ссылок (`=5*12`) тоже формула: строка связи без ref_cell.
            out.append(
                {
                    "model_id": model_id,
                    "build_key": build,
                    "cell": link.cell,
                    "formula": link.formula,
                    "formula_class": link.formula_class,
                    "ref_cell": None,
                    "row_key": link.row_key,
                    "period_id": link.period_id,
                    "truncated": False,
                }
            )
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
    for event in fold(events).values():
        kind = event.get("type")
        target = str(event.get("target") or "")
        if kind == "phase.set":
            parsed = split_phase_target(target)
            value = event.get("value")
            if parsed and isinstance(value, str) and value in PHASES:
                phases[parsed] = value
        elif kind in {"concept.set", "concept.confirmed"}:
            value = event.get("value")
            binding = str(event.get("binding_key") or target)
            if isinstance(value, str) and value and binding != "book":
                concepts[binding] = value
    return phases, concepts


def _by_type(events: list[dict], kind: str) -> dict[str, str]:
    found = {}
    for event in fold(events).values():
        if event.get("type") != kind or not isinstance(event.get("value"), str):
            continue
        found[str(event.get("binding_key") or event.get("target") or "")] = event["value"]
    return found


def _sign_map(events: list[dict]) -> dict[str, str]:
    return _by_type(events, "sign.set")


def _unit_map(events: list[dict]) -> dict[str, str]:
    return _by_type(events, "unit.set")


def _calendar(periods: list[dict] | None) -> dict[tuple[str, str], dict]:
    """Календарь оси для способа показа и покрытия: зерно, даты и заголовок колонки."""

    found: dict[tuple[str, str], dict] = {}
    for period in periods or []:
        found[(period["axis_id"], period["period_id"])] = {
            "grain": period.get("grain"),
            "period_start": period.get("period_start"),
            "period_end": period.get("period_end"),
            "header_text": period.get("header_text"),
            "calendar_year": period.get("calendar_year"),
            "period_index": period.get("period_index"),
        }
    return found


def _values_by_row(facts: list[dict] | None) -> dict[str, dict[tuple[str, str], Decimal]]:
    values: dict[str, dict[tuple[str, str], Decimal]] = {}
    for fact in facts or []:
        number = fact.get("normalized_value")
        if number is None:
            number = fact.get("value_dec")
        if number is None or not fact.get("row_key"):
            continue
        values.setdefault(fact["row_key"], {})[(fact["axis_id"], fact["period_id"])] = Decimal(str(number))
    return values


def _abs_by_row(facts: list[dict] | None) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = {}
    for fact in facts or []:
        number = fact.get("normalized_value")
        if number is None:
            number = fact.get("value_dec")
        if number is None or not fact.get("row_key"):
            continue
        key = fact["row_key"]
        totals[key] = totals.get(key, Decimal(0)) + abs(Decimal(str(number)))
    return totals


def prepare_rows(projected: dict[str, list[dict]], events: list[dict], glossary, facts: list[dict] | None) -> list[dict]:
    """Строки с исключением, знаком, природой и единицей из журнала — вход конвейера привязки."""

    signs = _sign_map(events)
    units = _unit_map(events)
    prepared = []
    for row in projected["dim_row"]:
        excluded, reason = exclusion(row, empty_series=empty_series(row["row_key"], facts))
        inferred = infer_row(row, glossary.flows)
        sign = signs.get(row["binding_key"], inferred["sign"])
        prepared.append(
            {
                **row,
                "excluded": excluded,
                "exclusion_reason": reason,
                "sign": sign,
                "nature": inferred["nature"],
                "aggregation": inferred["aggregation"],
                "unit_decision": units.get(row["binding_key"]),
            }
        )
    return prepared


def derive_rows(
    projected: dict[str, list[dict]],
    *,
    state_seq: int,
    derive: str,
    versions: dict,
    events: list[dict] | None = None,
    glossary=None,
    facts: list[dict] | None = None,
    evidence: dict | None = None,
    calibrator=None,
    prepared: list[dict] | None = None,
) -> dict[str, list[dict]]:
    now = datetime.now(UTC)
    journal = events or []
    phases, concepts = _decision_maps(journal)
    glossary_version = versions.get("glossary", "none")
    taxonomy = versions.get("taxonomy", "core-1")
    calibrator_version = versions.get("calibrator", "none")
    assigned = None
    if glossary is not None:
        if prepared is None:
            prepared = prepare_rows(projected, journal, glossary, facts)
        assigned = assign_rows(
            prepared,
            journal,
            glossary,
            abs_by_row={key: float(value) for key, value in _abs_by_row(facts).items()},
            evidence=evidence,
            calibrator=calibrator,
            roles=load_sheet_roles(),
            periods=_values_by_row(facts),
            links=projected.get("graph_links"),
            calendar=_calendar(projected.get("dim_period")),
        )
        assigned = verify_numeric(assigned, prepared, _values_by_row(facts))
    else:
        prepared = None
    row_semantics = []
    bindings = []
    rows = prepared if prepared is not None else projected["dim_row"]
    for row in rows:
        if prepared is None:
            excluded, reason = exclusion(row, empty_series=False)
            sign = nature = aggregation = None
        else:
            excluded = row["excluded"]
            reason = row["exclusion_reason"]
            sign, nature, aggregation = row["sign"], row["nature"], row["aggregation"]
        evidence = {}
        decided_unit = row.get("unit_decision")
        if isinstance(decided_unit, str) and decided_unit:
            evidence["unit"] = decided_unit
        # Хвост подписи не затирает unit/scale/currency и period_position: у тех колонок другой смысл.
        features = label_features(str(row.get("label") or ""))
        if features.unit and "label_unit" not in evidence:
            evidence["label_unit"] = features.unit
        if features.period and "label_period" not in evidence:
            evidence["label_period"] = features.period
        row_semantics.append(
            {
                "model_id": row["model_id"],
                "build_key": row["build_key"],
                "state_seq": state_seq,
                "derive_key": derive,
                "binding_key": row["binding_key"],
                "row_key": row["row_key"],
                "sign": sign,
                "nature": nature,
                "aggregation": aggregation,
                "period_position": None,
                "excluded": excluded,
                "exclusion_reason": reason,
                "is_check": row["check_row"],
                "source": "inferred",
                "confidence": None,
                "evidence_json": json.dumps(evidence, ensure_ascii=False),
                "stale": False,
            }
        )
        if row["kind"] != "fact":
            continue
        if assigned is None:
            chosen = concepts.get(row["binding_key"])
            concept, status, source = chosen, "bound" if chosen else "unknown", "confirmed" if chosen else "inferred"
            primary, label, importance = chosen is not None, None, "normal"
            confidence, binding_evidence = None, {}
        else:
            item = assigned[row["binding_key"]]
            concept, status, source = item.concept, item.status, item.source
            primary, label, importance = item.is_primary, item.matched_label, item.importance
            confidence, binding_evidence = item.confidence, item.evidence
        bindings.append(
            {
                "model_id": row["model_id"],
                "build_key": row["build_key"],
                "state_seq": state_seq,
                "derive_key": derive,
                "concept": concept,
                "effective_concept": concept,
                "is_primary": primary,
                "matched_label_id": label,
                "status": status,
                "binding_key": row["binding_key"],
                "row_key": row["row_key"],
                "label_path_text": row["label_path_text"],
                "source": source,
                "confidence": None if confidence is None else float(confidence),
                "evidence_json": json.dumps(binding_evidence, ensure_ascii=False, sort_keys=True),
                "calibrator_version": calibrator_version,
                "glossary_version": glossary_version,
                "taxonomy_version": taxonomy,
                "decided_by": None,
                "stale": False,
                "importance": importance,
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
    coverage_map: dict[tuple[str, str], list] = {}
    for binding in bindings:
        key = (binding["status"], binding["importance"])
        coverage_map.setdefault(key, []).append(binding["row_key"])
    amounts = _abs_by_row(facts) if facts is not None else {}
    coverage = [
        {
            "model_id": projected["dim_row"][0]["model_id"] if projected["dim_row"] else "",
            "build_key": build_of(projected),
            "state_seq": state_seq,
            "derive_key": derive,
            "glossary_version": glossary_version,
            "status": status,
            "importance": importance,
            "rows": len(keys),
            "value_abs_sum": sum((amounts.get(key, Decimal(0)) for key in keys), Decimal(0)) if facts is not None else Decimal(0),
        }
        for (status, importance), keys in sorted(coverage_map.items())
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
