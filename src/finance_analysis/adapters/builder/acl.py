"""Anti-Corruption Layer builder @7676f62 (§2)."""

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
)
from finance_analysis.domain.errors import UnsupportedBuilderShape

_AXIS = ("id", "sheet", "periods")
_PERIOD = ("col", "text", "period_key", "index")
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


def parse_summary(payload: dict, *, etag: str, job_id: str) -> Summary:
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
    )


def parse_context(payload: dict) -> WorkbookSnapshot:
    missing: list[str] = []
    if not isinstance(payload, dict):
        raise UnsupportedBuilderShape("context.json не объект")
    axes_raw = payload.get("axes")
    blocks_raw = payload.get("blocks")
    if not isinstance(axes_raw, dict) or not axes_raw:
        missing.append("axes")
        axes_raw = {}
    if not isinstance(blocks_raw, list):
        missing.append("blocks")
        blocks_raw = []
    axes: dict[str, SnapshotAxis] = {}
    max_row: dict[str, int] = {}
    max_col: dict[str, int] = {}
    for key, axis in axes_raw.items():
        if not isinstance(axis, dict):
            missing.append(f"axes.{key}")
            continue
        _missing(axis, _AXIS, f"axes.{key}", missing)
        periods_raw = axis.get("periods") or []
        periods: list[SnapshotPeriod] = []
        if not isinstance(periods_raw, list):
            missing.append(f"axes.{key}.periods")
            periods_raw = []
        for index, period in enumerate(periods_raw):
            if not isinstance(period, dict):
                missing.append(f"axes.{key}.periods[{index}]")
                continue
            _missing(period, _PERIOD, f"axes.{key}.periods[{index}]", missing)
            if missing:
                continue
            col = int(period["col"])
            sheet = str(axis.get("sheet") or "")
            max_col[sheet] = max(max_col.get(sheet, 1), col)
            periods.append(
                SnapshotPeriod(
                    col=col,
                    text=str(period.get("text") or ""),
                    period_key=str(period["period_key"]),
                    index=int(period["index"]),
                    calendar_year=(
                        int(period["calendar_year"]) if period.get("calendar_year") not in (None, "") else None
                    ),
                    start_date=_as_date(period.get("start_date")),
                    end_date=_as_date(period.get("end_date")),
                    group_key=None if period.get("group_key") is None else str(period.get("group_key")),
                    flags=dict(period.get("flags") or {}),
                    hidden=bool(period.get("hidden") or False),
                )
            )
        if missing:
            continue
        axis_id = str(axis.get("id") or key)
        axes[axis_id] = SnapshotAxis(
            id=axis_id,
            sheet=str(axis.get("sheet") or ""),
            grain=None if axis.get("grain") is None else str(axis.get("grain")),
            header_row=None if axis.get("header_row") is None else int(axis["header_row"]),
            timeline_id=None if axis.get("timeline_id") is None else str(axis.get("timeline_id")),
            periods=tuple(periods),
        )
    rows: list[SnapshotRow] = []
    for bindex, block in enumerate(blocks_raw):
        if not isinstance(block, dict):
            missing.append(f"blocks[{bindex}]")
            continue
        _missing(block, _BLOCK, f"blocks[{bindex}]", missing)
        block_rows = block.get("rows") or []
        if not isinstance(block_rows, list):
            missing.append(f"blocks[{bindex}].rows")
            continue
        for rindex, row in enumerate(block_rows):
            path = f"blocks[{bindex}].rows[{rindex}]"
            if not isinstance(row, dict):
                missing.append(path)
                continue
            _missing(row, _ROW, path, missing)
            if any(item.startswith(path) for item in missing):
                continue
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
            rows.append(
                SnapshotRow(
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
                    scale_factor=(
                        int(row["scale_factor"]) if row.get("scale_factor") not in (None, "") else None
                    ),
                    series=tuple(series),
                    values=_seq(row.get("values")),
                    value_statuses=_seq(row.get("value_statuses")),
                    normalized_values=_seq(row.get("normalized_values")),
                    block_id=str(block.get("block_id")),
                    block_kind=str(block.get("kind")),
                )
            )
    if missing:
        raise UnsupportedBuilderShape(
            "форма context.json не поддерживается",
            extra={"fields": missing},
        )
    used = {sheet: (max_row.get(sheet, 1), max_col.get(sheet, 1)) for sheet in set(max_row) | set(max_col)}
    return WorkbookSnapshot(axes=axes, rows=tuple(rows), links=(), used_range=used)


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
