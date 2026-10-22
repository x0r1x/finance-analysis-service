"""Anti-Corruption Layer builder @7676f62 (§2).

Имена `Summary` и `builder_ref` остаются проектными. Реальный дамп builder
отдаёт не `summary.json`, а `meta.json`: `context_schema_version` берётся из
`meta.schema_version`, `graph_schema_version` — из `graph.json.schema_version`,
а `summary_etag` — это sha256 канонического JSON полей
`status`, `generation`, `content_sha256`, `stages`.
"""

from __future__ import annotations

from datetime import date

from finance_analysis.domain.book import (
    GraphLink,
    SnapshotAxis,
    SnapshotPeriod,
    SnapshotRow,
    SnapshotSeries,
    Summary,
    WorkbookSnapshot,
    canonical_json,
    sha256_bytes,
)
from finance_analysis.domain.errors import UnsupportedBuilderShape

_AXIS = ("id", "sheet", "periods")
_PERIOD = ("col", "text", "period_key")
_BLOCK = ("block_id", "sheet", "kind", "rows")
_ROW = ("row_key", "sheet", "row", "label", "kind")


def _missing(obj: dict, fields: tuple[str, ...], path: str, out: list[str]) -> None:
    for name in fields:
        if name not in obj or obj[name] is None:
            out.append(f"{path}.{name}" if path else name)


def _as_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _seq(value) -> tuple:
    if value is None:
        return ()
    if not isinstance(value, list):
        return ()
    return tuple(None if item is None else str(item) for item in value)


def _warnings(payload: dict) -> tuple[str, ...]:
    raw = payload.get("warnings") or []
    if not isinstance(raw, list):
        return ()
    return tuple(str(item) for item in raw)


def is_meta_payload(payload: dict) -> bool:
    """Реальный meta.json. Проектный summary узнаётся по context_schema_version."""

    if not isinstance(payload, dict):
        return False
    if payload.get("context_schema_version"):
        return False
    return "stages" in payload or "schema_version" in payload


def consistency_token(
    *,
    status: str,
    generation: int | str,
    content_sha256: str,
    stages: dict,
) -> str:
    payload = {
        "content_sha256": str(content_sha256),
        "generation": int(generation),
        "stages": {str(key): str(value) for key, value in stages.items()},
        "status": str(status),
    }
    return sha256_bytes(canonical_json(payload).encode("utf-8"))


def parse_summary(
    payload: dict,
    *,
    etag: str,
    job_id: str,
    graph_schema_version: str | None = None,
) -> Summary:
    del job_id
    if is_meta_payload(payload):
        return _parse_meta(payload, graph_schema_version=graph_schema_version)
    missing: list[str] = []
    for name in ("content_sha256", "context_schema_version", "graph_schema_version"):
        if name not in payload or payload[name] in (None, ""):
            missing.append(name)
    if missing:
        raise UnsupportedBuilderShape(
            "в summary не хватает полей",
            extra={"fields": missing},
        )
    return Summary(
        etag=etag,
        content_sha256=str(payload["content_sha256"]),
        context_schema_version=str(payload["context_schema_version"]),
        graph_schema_version=str(payload["graph_schema_version"]),
        status=str(payload.get("status") or "succeeded"),
        warnings=_warnings(payload),
    )


def _parse_meta(payload: dict, *, graph_schema_version: str | None) -> Summary:
    missing: list[str] = []
    for name in ("content_sha256", "status", "schema_version"):
        if name not in payload or payload[name] in (None, ""):
            missing.append(name)
    if "generation" not in payload or payload["generation"] in (None, ""):
        missing.append("generation")
    stages = payload.get("stages")
    if not isinstance(stages, dict) or not stages:
        missing.append("stages")
        stages = {}
    version = str(graph_schema_version or "")
    if not version:
        missing.append("graph.json.schema_version")
    if missing:
        raise UnsupportedBuilderShape(
            "в meta не хватает полей согласованного чтения",
            extra={"fields": missing},
        )
    token = consistency_token(
        status=str(payload["status"]),
        generation=payload["generation"],
        content_sha256=str(payload["content_sha256"]),
        stages=stages,
    )
    return Summary(
        etag=token,
        content_sha256=str(payload["content_sha256"]),
        context_schema_version=str(payload["schema_version"]),
        graph_schema_version=version,
        status=str(payload["status"]),
        warnings=_warnings(payload),
    )


def _axis_pairs(axes_raw, missing: list[str]) -> list[tuple[str, dict]]:
    if isinstance(axes_raw, dict) and axes_raw:
        pairs: list[tuple[str, dict]] = []
        for key, axis in axes_raw.items():
            if not isinstance(axis, dict):
                missing.append(f"axes.{key}")
                continue
            pairs.append((str(key), axis))
        return pairs
    if isinstance(axes_raw, list) and axes_raw:
        pairs = []
        for index, axis in enumerate(axes_raw):
            if not isinstance(axis, dict):
                missing.append(f"axes[{index}]")
                continue
            key = str(axis.get("id") or index)
            pairs.append((key, axis))
        return pairs
    missing.append("axes")
    return []


def _read_period(
    period,
    path: str,
    sheet: str,
    missing: list[str],
    fallback_index: int,
    max_col: dict[str, int],
) -> SnapshotPeriod | None:
    if not isinstance(period, dict):
        missing.append(path)
        return None
    before = len(missing)
    _missing(period, _PERIOD, path, missing)
    if len(missing) > before:
        return None
    col = int(period["col"])
    max_col[sheet] = max(max_col.get(sheet, 1), col)
    index = fallback_index if period.get("index") in (None, "") else int(period["index"])
    return SnapshotPeriod(
        col=col,
        text=str(period.get("text") or ""),
        period_key=str(period["period_key"]),
        index=index,
        calendar_year=(
            int(period["calendar_year"]) if period.get("calendar_year") not in (None, "") else None
        ),
        start_date=_as_date(period.get("start_date")),
        end_date=_as_date(period.get("end_date")),
        group_key=None if period.get("group_key") is None else str(period.get("group_key")),
        flags=dict(period.get("flags") or {}),
        hidden=bool(period.get("hidden") or False),
    )


def _read_periods(
    periods_raw,
    path: str,
    sheet: str,
    missing: list[str],
    max_col: dict[str, int],
) -> list[SnapshotPeriod]:
    periods: list[SnapshotPeriod] = []
    if not isinstance(periods_raw, list):
        missing.append(f"{path}.periods")
        return periods
    for index, period in enumerate(periods_raw):
        item = _read_period(period, f"{path}.periods[{index}]", sheet, missing, index, max_col)
        if item is not None:
            periods.append(item)
    return periods


def _axis_from(
    key: str,
    axis: dict,
    missing: list[str],
    max_col: dict[str, int],
) -> SnapshotAxis | None:
    path = f"axes.{key}"
    before = len(missing)
    _missing(axis, _AXIS, path, missing)
    if len(missing) > before:
        return None
    sheet = str(axis.get("sheet") or "")
    periods = _read_periods(axis.get("periods") or [], path, sheet, missing, max_col)
    if any(item.startswith(path) for item in missing[before:]):
        return None
    axis_id = str(axis.get("id") or key)
    return SnapshotAxis(
        id=axis_id,
        sheet=sheet,
        grain=None if axis.get("grain") is None else str(axis.get("grain")),
        header_row=None if axis.get("header_row") is None else int(axis["header_row"]),
        timeline_id=None if axis.get("timeline_id") is None else str(axis.get("timeline_id")),
        periods=tuple(periods),
    )


def parse_context(payload: dict) -> WorkbookSnapshot:
    missing: list[str] = []
    if not isinstance(payload, dict):
        raise UnsupportedBuilderShape("context.json не объект")
    max_row: dict[str, int] = {}
    max_col: dict[str, int] = {}
    axes: dict[str, SnapshotAxis] = {}
    for key, axis in _axis_pairs(payload.get("axes"), missing):
        built = _axis_from(key, axis, missing, max_col)
        if built is not None:
            axes[built.id] = built
    blocks_raw = payload.get("blocks")
    if not isinstance(blocks_raw, list):
        missing.append("blocks")
        blocks_raw = []
    rows: list[SnapshotRow] = []
    for bindex, block in enumerate(blocks_raw):
        if not isinstance(block, dict):
            missing.append(f"blocks[{bindex}]")
            continue
        _missing(block, _BLOCK, f"blocks[{bindex}]", missing)
        _synthesize_axis(block, bindex, axes, missing, max_col)
        block_rows = block.get("rows") or []
        if not isinstance(block_rows, list):
            missing.append(f"blocks[{bindex}].rows")
            continue
        for rindex, row in enumerate(block_rows):
            built = _read_row(row, block, bindex, rindex, missing, max_row)
            if built is not None:
                rows.append(built)
    if missing:
        raise UnsupportedBuilderShape(
            "форма context.json не поддерживается",
            extra={"fields": missing},
        )
    used = {sheet: (max_row.get(sheet, 1), max_col.get(sheet, 1)) for sheet in set(max_row) | set(max_col)}
    return WorkbookSnapshot(axes=axes, rows=tuple(rows), links=(), used_range=used)


def _synthesize_axis(
    block: dict,
    bindex: int,
    axes: dict[str, SnapshotAxis],
    missing: list[str],
    max_col: dict[str, int],
) -> None:
    """Ось params не лежит в `axes`: её периоды — на блоке, часто без `index`."""

    block_id = str(block.get("block_id") or "")
    periods_raw = block.get("periods")
    if not block_id or block_id in axes or not isinstance(periods_raw, list) or not periods_raw:
        return
    sheet = str(block.get("sheet") or "")
    periods = _read_periods(periods_raw, f"blocks[{bindex}]", sheet, missing, max_col)
    if not periods:
        return
    axes[block_id] = SnapshotAxis(
        id=block_id,
        sheet=sheet,
        grain=None,
        header_row=None,
        timeline_id=None,
        periods=tuple(periods),
    )


def _read_row(
    row,
    block: dict,
    bindex: int,
    rindex: int,
    missing: list[str],
    max_row: dict[str, int],
) -> SnapshotRow | None:
    path = f"blocks[{bindex}].rows[{rindex}]"
    if not isinstance(row, dict):
        missing.append(path)
        return None
    before = len(missing)
    _missing(row, _ROW, path, missing)
    if len(missing) > before:
        return None
    hints = dict(row.get("hints") or {})
    series_raw = row.get("series") or []
    series: list[SnapshotSeries] = []
    if isinstance(series_raw, list) and series_raw:
        for sindex, item in enumerate(series_raw):
            if not isinstance(item, dict) or "axis_id" not in item:
                missing.append(f"{path}.series[{sindex}].axis_id")
                continue
            values = _seq(item.get("values"))
            statuses = _seq(item.get("value_statuses"))
            if not statuses:
                statuses = tuple("cached" for _ in values)
            series.append(
                SnapshotSeries(
                    axis_id=str(item["axis_id"]),
                    values=values,
                    value_statuses=tuple(statuses),
                    normalized_values=_seq(item.get("normalized_values")),
                    formula=None if item.get("formula") is None else str(item.get("formula")),
                )
            )
    label_path = tuple(str(part) for part in (row.get("label_path") or []))
    sheet = str(row["sheet"])
    row_num = int(row["row"])
    max_row[sheet] = max(max_row.get(sheet, 1), row_num)
    return SnapshotRow(
        row_key=str(row["row_key"]),
        sheet=sheet,
        row=row_num,
        label=str(row["label"]),
        parent_label=None if row.get("parent_label") is None else str(row.get("parent_label")),
        label_path=label_path,
        kind=str(row["kind"]),
        unit=None if row.get("unit") is None else str(row.get("unit")),
        formula=None if row.get("formula") is None else str(row.get("formula")),
        indent=int(row.get("indent") or 0),
        hidden=bool(row.get("hidden") or False),
        check_row=bool(row.get("check_row") or False),
        hints=hints,
        scale_factor=(int(row["scale_factor"]) if row.get("scale_factor") not in (None, "") else None),
        series=tuple(series),
        values=_seq(row.get("values")),
        value_statuses=_seq(row.get("value_statuses")),
        normalized_values=_seq(row.get("normalized_values")),
        block_id=str(block.get("block_id")),
        block_kind=str(block.get("kind")),
    )


def parse_graph(payload: dict | None, snapshot: WorkbookSnapshot) -> WorkbookSnapshot:
    if not payload:
        return snapshot
    links_raw = payload.get("links") or []
    links: list[GraphLink] = []
    if isinstance(links_raw, list):
        for item in links_raw:
            if not isinstance(item, dict):
                continue
            refs = item.get("refs") or []
            links.append(
                GraphLink(
                    cell=None if item.get("cell") is None else str(item.get("cell")),
                    formula=None if item.get("formula") is None else str(item.get("formula")),
                    formula_class=None if item.get("formula_class") is None else str(item.get("formula_class")),
                    refs=tuple(str(ref) for ref in refs),
                    row_key=None if item.get("row_key") is None else str(item.get("row_key")),
                    period_id=None if item.get("period_id") is None else str(item.get("period_id")),
                )
            )
    return WorkbookSnapshot(
        axes=snapshot.axes,
        rows=snapshot.rows,
        links=tuple(links),
        used_range=snapshot.used_range,
    )
