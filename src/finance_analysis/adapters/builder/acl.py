"""Anti-Corruption Layer builder (§2).

Имена `Summary` и `builder_ref` остаются проектными. Форма входа —
`summary-2`, `context.json`, `graph.json`. Лишние поля отбрасываются
(`extra="ignore"`). Нехватка обязательных полей — `unsupported_builder_shape`.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

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
from finance_analysis.domain.mapping import marked_line_code


class _In(BaseModel):
    model_config = ConfigDict(extra="ignore")


class PeriodIn(_In):
    col: int
    period_key: str
    index: int | None = None
    text: str | None = None
    calendar_year: int | None = None
    start_date: date | None = None
    end_date: date | None = None
    flags: dict[str, Any] | None = None
    hidden: bool | None = None


class AxisIn(_In):
    id: str
    sheet: str
    grain: str | None = None
    timeline_id: str | None = None
    kind: str | None = None
    periods: list[PeriodIn]


class SeriesIn(_In):
    axis_id: str
    values: list[Any] | None = None
    value_statuses: list[Any] | None = None
    normalized_values: list[Any] | None = None
    formula: str | None = None
    formula_exceptions: list[Any] | None = None


class CellIn(_In):
    col: int
    cached_value: Any = None
    role: str | None = None


class RowIn(_In):
    row_key: str
    sheet: str
    row: int
    label: str
    kind: str
    cells: list[CellIn] | None = None
    label_path: list[Any] | None = None
    parent_label: str | None = None
    unit: str | None = None
    hints: dict[str, Any] | None = None
    scale_factor: int | None = None
    formula: str | None = None
    formula_exceptions: list[Any] | None = None
    indent: int | None = None
    hidden: bool | None = None
    check_row: bool | None = None
    values: list[Any] | None = None
    value_statuses: list[Any] | None = None
    normalized_values: list[Any] | None = None
    series: list[SeriesIn] | None = None


class BlockIn(_In):
    block_id: str
    sheet: str
    kind: str
    rows: list[Any]
    label_col: int | None = None
    periods: list[Any] | None = None


class IdCountIn(_In):
    count: int = 0
    ids: list[Any] | None = None


class CycleIn(_In):
    id: str | None = None
    cycle_class: str | None = Field(default=None, alias="class")
    members: int | None = None


class SummaryIn(_In):
    status: str
    context_schema_version: str
    graph_schema_version: str
    warnings: list[Any] | None = None
    # Счётчики R1 для правил фазы 1 (§2.1). Необязательны: без них правило не срабатывает.
    iterate: bool | None = None
    missing_cached_values: int | None = None
    unresolved: IdCountIn | None = None
    external: IdCountIn | None = None
    dangling: IdCountIn | None = None
    dangling_classes: dict[str, int] | None = None
    cycles: list[CycleIn] | None = None


class LinkIn(_In):
    cell: str
    refs: list[Any]
    row_key: str | None = None
    period_id: str | None = None
    formula: str | None = None
    formula_class: str | None = None


def _seq(value) -> tuple:
    if value is None:
        return ()
    if not isinstance(value, list):
        return ()
    return tuple(None if item is None else str(item) for item in value)


def _fields(exc: ValidationError, path: str) -> list[str]:
    found = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err["loc"])
        found.append(f"{path}.{loc}" if path else loc)
    return found


def _counters(parsed: SummaryIn) -> dict:
    counters: dict = {
        "iterate": parsed.iterate,
        "missing_cached_values": parsed.missing_cached_values,
        "dangling_classes": dict(parsed.dangling_classes or {}),
        "cycles": [
            {"id": item.id, "class": item.cycle_class, "members": item.members} for item in parsed.cycles or []
        ],
    }
    if parsed.cycles is None:
        counters["cycles"] = None
    for name in ("unresolved", "external", "dangling"):
        found = getattr(parsed, name)
        counters[name] = None if found is None else {"count": found.count, "ids": _strings(found.ids)}
    return counters


def _strings(raw) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if item is not None]


def _warnings(raw) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return ()
    return tuple(str(item) for item in raw)


def parse_summary(payload: dict, *, etag: str, job_id: str | None = None) -> Summary:
    del job_id
    if not isinstance(payload, dict):
        raise UnsupportedBuilderShape("summary не объект", extra={"fields": ["summary"]})
    try:
        parsed = SummaryIn.model_validate(payload)
    except ValidationError as exc:
        raise UnsupportedBuilderShape(
            "в summary не хватает полей",
            extra={"fields": _fields(exc, "summary")},
        ) from exc
    return Summary(
        etag=etag,
        context_schema_version=parsed.context_schema_version,
        graph_schema_version=parsed.graph_schema_version,
        status=parsed.status,
        warnings=_warnings(parsed.warnings),
        counters=_counters(parsed),
    )


def _period(item: PeriodIn, *, index: int) -> SnapshotPeriod:
    return SnapshotPeriod(
        col=int(item.col),
        text="" if item.text is None else str(item.text),
        period_key=str(item.period_key),
        index=index,
        calendar_year=None if item.calendar_year is None else int(item.calendar_year),
        start_date=item.start_date,
        end_date=item.end_date,
        flags=dict(item.flags or {}),
        hidden=bool(item.hidden or False),
    )


def _periods(
    raw,
    path: str,
    missing: list[str],
    *,
    require_index: bool,
) -> list[SnapshotPeriod]:
    periods: list[SnapshotPeriod] = []
    if not isinstance(raw, list):
        missing.append(f"{path}.periods")
        return periods
    for index, item in enumerate(raw):
        item_path = f"{path}.periods[{index}]"
        if not isinstance(item, dict):
            missing.append(item_path)
            continue
        try:
            parsed = PeriodIn.model_validate(item)
        except ValidationError as exc:
            missing.extend(_fields(exc, item_path))
            continue
        if require_index and parsed.index is None:
            missing.append(f"{item_path}.index")
            continue
        periods.append(_period(parsed, index=parsed.index if parsed.index is not None else index))
    return periods


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
            pairs.append((str(axis.get("id") or index), axis))
        return pairs
    missing.append("axes")
    return []


def _axis_from(key: str, axis: dict, missing: list[str], max_col: dict[str, int]) -> SnapshotAxis | None:
    path = f"axes.{key}"
    before = len(missing)
    try:
        parsed = AxisIn.model_validate(axis)
    except ValidationError as exc:
        missing.extend(_fields(exc, path))
        return None
    periods = _periods(axis.get("periods") or [], path, missing, require_index=True)
    if len(missing) > before:
        return None
    for period in periods:
        max_col[parsed.sheet] = max(max_col.get(parsed.sheet, 1), period.col)
    kind = parsed.kind or "time"
    return SnapshotAxis(
        id=parsed.id,
        sheet=parsed.sheet,
        grain=parsed.grain,
        timeline_id=parsed.timeline_id,
        axis_kind=kind,
        periods=tuple(periods),
    )


def parse_context(payload: dict) -> WorkbookSnapshot:
    missing: list[str] = []
    if not isinstance(payload, dict):
        raise UnsupportedBuilderShape("context.json не объект", extra={"fields": ["context"]})
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
        path = f"blocks[{bindex}]"
        if not isinstance(block, dict):
            missing.append(path)
            continue
        try:
            parsed = BlockIn.model_validate(block)
        except ValidationError as exc:
            missing.extend(_fields(exc, path))
            continue
        _synthesize_axis(block, parsed, bindex, axes, missing, max_col)
        block_rows = parsed.rows
        if not isinstance(block_rows, list):
            missing.append(f"{path}.rows")
            continue
        for rindex, row in enumerate(block_rows):
            built = _read_row(row, parsed, bindex, rindex, missing, max_row)
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
    raw: dict,
    block: BlockIn,
    bindex: int,
    axes: dict[str, SnapshotAxis],
    missing: list[str],
    max_col: dict[str, int],
) -> None:
    """Ось params не лежит в `axes`: её периоды — на блоке, без `index`."""

    periods_raw = raw.get("periods")
    if not block.block_id or block.block_id in axes or not isinstance(periods_raw, list) or not periods_raw:
        return
    before = len(missing)
    periods = _periods(
        periods_raw,
        f"blocks[{bindex}]",
        missing,
        require_index=False,
    )
    if len(missing) > before or not periods:
        return
    for period in periods:
        max_col[block.sheet] = max(max_col.get(block.sheet, 1), period.col)
    kind = "params" if block.kind == "params" else "time"
    axes[block.block_id] = SnapshotAxis(
        id=block.block_id,
        sheet=block.sheet,
        grain=None,
        timeline_id=None,
        axis_kind=kind,
        periods=tuple(periods),
    )


def _read_row(
    row,
    block: BlockIn,
    bindex: int,
    rindex: int,
    missing: list[str],
    max_row: dict[str, int],
) -> SnapshotRow | None:
    path = f"blocks[{bindex}].rows[{rindex}]"
    if not isinstance(row, dict):
        missing.append(path)
        return None
    try:
        parsed = RowIn.model_validate(row)
    except ValidationError as exc:
        missing.extend(_fields(exc, path))
        return None
    series: list[SnapshotSeries] = []
    for sindex, item in enumerate(parsed.series or []):
        values = _seq(item.values)
        statuses = _seq(item.value_statuses)
        if not statuses:
            statuses = tuple("cached" for _ in values)
        series.append(
            SnapshotSeries(
                axis_id=item.axis_id,
                values=values,
                value_statuses=tuple(statuses),
                normalized_values=_seq(item.normalized_values),
                formula=item.formula,
                formula_exceptions=tuple(_strings(item.formula_exceptions)),
            )
        )
    label_path = tuple(str(part) for part in (parsed.label_path or []))
    max_row[parsed.sheet] = max(max_row.get(parsed.sheet, 1), parsed.row)
    return SnapshotRow(
        row_key=parsed.row_key,
        sheet=parsed.sheet,
        row=parsed.row,
        label=parsed.label,
        parent_label=parsed.parent_label,
        label_path=label_path,
        kind=parsed.kind,
        unit=parsed.unit,
        formula=parsed.formula,
        indent=int(parsed.indent or 0),
        hidden=bool(parsed.hidden or False),
        check_row=bool(parsed.check_row or False),
        hints=dict(parsed.hints or {}),
        scale_factor=parsed.scale_factor,
        series=tuple(series),
        values=_seq(parsed.values),
        value_statuses=_seq(parsed.value_statuses),
        normalized_values=_seq(parsed.normalized_values),
        block_id=block.block_id,
        block_kind=block.kind,
        formula_exceptions=tuple(_strings(parsed.formula_exceptions)),
        line_code=_line_code(parsed, block),
    )


def _line_code(row: RowIn, block: BlockIn) -> str | None:
    """Код строки — явная форма в столбце справа от подписи, не голое число."""

    if block.label_col is None:
        return None
    wanted = block.label_col + 1
    for cell in row.cells or []:
        if cell.col != wanted or cell.cached_value is None:
            continue
        return marked_line_code(cell.cached_value)
    return None


def parse_links(payload: dict | None) -> tuple[GraphLink, ...]:
    if not payload:
        return ()
    if not isinstance(payload, dict):
        raise UnsupportedBuilderShape("graph.json не объект", extra={"fields": ["graph"]})
    links_raw = payload.get("links") or []
    if not isinstance(links_raw, list):
        raise UnsupportedBuilderShape("graph.links не список", extra={"fields": ["links"]})
    links: list[GraphLink] = []
    missing: list[str] = []
    for index, item in enumerate(links_raw):
        path = f"links[{index}]"
        if not isinstance(item, dict):
            missing.append(path)
            continue
        try:
            parsed = LinkIn.model_validate(item)
        except ValidationError as exc:
            missing.extend(_fields(exc, path))
            continue
        links.append(
            GraphLink(
                cell=parsed.cell,
                formula=parsed.formula,
                formula_class=parsed.formula_class,
                refs=tuple(str(ref) for ref in parsed.refs),
                row_key=parsed.row_key,
                period_id=parsed.period_id,
            )
        )
    if missing:
        raise UnsupportedBuilderShape("форма graph.json не поддерживается", extra={"fields": missing})
    return tuple(links)


def parse_graph(payload: dict | None, snapshot: WorkbookSnapshot) -> WorkbookSnapshot:
    from finance_analysis.domain.book import with_links

    return with_links(snapshot, parse_links(payload))


class TraceNodeIn(_In):
    node_id: str
    sheet: str | None = None
    addr: str | None = None
    row_key: str | None = None
    period_id: str | None = None
    node_type: str | None = None
    formula: str | None = None
    cached_value: str | None = None
    depth: int = 0


class TraceEdgeIn(_In):
    source: str
    target: str
    kind: str | None = None
    members_total: int | None = None
    members_shown: int | None = None


class TraceIn(_In):
    origin: str
    direction: str
    depth: int
    stopped: str | None = None
    nodes: list[TraceNodeIn] = []
    edges: list[TraceEdgeIn] = []


def parse_trace(payload: dict) -> dict:
    """R5 `GET …/graph/trace` → `{origin, direction, depth, stopped, nodes[], edges[]}`."""

    try:
        parsed = TraceIn.model_validate(payload)
    except ValidationError as exc:
        raise UnsupportedBuilderShape("форма trace не поддерживается", extra={"fields": _fields(exc, "trace")}) from exc
    return parsed.model_dump()
