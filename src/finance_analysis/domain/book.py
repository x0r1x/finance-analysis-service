"""Снимок книги, ключи и ссылки (§4.2, §5.3)."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime

FAS_VERSION = "0.22.0"
FAS_SCHEMA_VERSION = "1.0"
FAS_PROJECTION_VERSION = "1"
FAS_DERIVE_VERSION = "1"
SEP = "›"

_WS = re.compile(r"\s+")


def norm(value: str) -> str:
    return _WS.sub(" ", value.casefold()).strip()


def binding_key(sheet: str, label_path: list[str], label: str, occurrence: int) -> str:
    path = norm(" › ".join(label_path))
    material = SEP.join([norm(sheet), path, norm(label), str(occurrence)])
    return hashlib.sha1(material.encode("utf-8")).hexdigest()


def build_key_for(
    content_sha256: str,
    context_schema_version: str,
    graph_schema_version: str,
    summary_etag: str,
    projection_version: str = FAS_PROJECTION_VERSION,
) -> str:
    material = SEP.join(
        [
            content_sha256,
            context_schema_version,
            graph_schema_version,
            summary_etag,
            projection_version,
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def canonical_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def derive_key_for(
    *,
    state_seq: int,
    glossary_version: str,
    taxonomy_version: str,
    calibrator_version: str,
    embed_model: str,
    rerank_model: str,
    clm_model: str,
    profile_version: str,
    fas_derive_version: str = FAS_DERIVE_VERSION,
) -> str:
    payload = {
        "state_seq": state_seq,
        "glossary_version": glossary_version,
        "taxonomy_version": taxonomy_version,
        "calibrator_version": calibrator_version,
        "embed_model": embed_model,
        "rerank_model": rerank_model,
        "clm_model": clm_model,
        "profile_version": profile_version,
        "fas_derive_version": fas_derive_version,
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:16]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def excel_col(number: int) -> str:
    if number < 1:
        raise ValueError("колонка Excel нумеруется с 1")
    letters = ""
    n = number
    while n:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def cell_id(sheet: str, col: int, row: int) -> str:
    return f"{sheet}!{excel_col(col)}{row}"


@dataclass(frozen=True)
class Actor:
    user_id: str = "anonymous"
    client_id: str = "anonymous"


@dataclass(frozen=True)
class BuilderRef:
    job_id: str
    content_sha256: str
    context_schema_version: str
    graph_schema_version: str
    summary_etag: str
    builder_status: str = "succeeded"

    def as_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "content_sha256": self.content_sha256,
            "context_schema_version": self.context_schema_version,
            "graph_schema_version": self.graph_schema_version,
            "summary_etag": self.summary_etag,
            "builder_status": self.builder_status,
        }


@dataclass(frozen=True)
class Versions:
    glossary: str = "none"
    taxonomy: str = "core-1"
    calibrator: str = "none"
    profile: str = "p-0"
    embed_model: str = ""
    rerank_model: str = ""
    clm_model: str = ""
    fas: str = FAS_VERSION

    def as_dict(self) -> dict:
        return {
            "glossary": self.glossary,
            "taxonomy": self.taxonomy,
            "calibrator": self.calibrator,
            "profile": self.profile,
            "models": {
                "embed": self.embed_model,
                "rerank": self.rerank_model,
                "clm": self.clm_model,
            },
            "fas": self.fas,
        }

    def derive(self, state_seq: int) -> str:
        return derive_key_for(
            state_seq=state_seq,
            glossary_version=self.glossary,
            taxonomy_version=self.taxonomy,
            calibrator_version=self.calibrator,
            embed_model=self.embed_model,
            rerank_model=self.rerank_model,
            clm_model=self.clm_model,
            profile_version=self.profile,
        )


@dataclass
class Head:
    build_key: str
    state_seq: int
    derive_key: str
    versions: dict
    mdl_version: str = "1"
    fence: int = 0
    token: str | None = None

    def as_dict(self) -> dict:
        return {
            "build_key": self.build_key,
            "state_seq": self.state_seq,
            "derive_key": self.derive_key,
            "versions": self.versions,
            "mdl_version": self.mdl_version,
            "fence": self.fence,
        }


@dataclass(frozen=True)
class SnapshotPeriod:
    col: int
    text: str
    period_key: str
    index: int
    calendar_year: int | None = None
    start_date: date | None = None
    end_date: date | None = None
    group_key: str | None = None
    flags: dict = field(default_factory=dict)
    hidden: bool = False


@dataclass(frozen=True)
class SnapshotAxis:
    id: str
    sheet: str
    grain: str | None
    header_row: int | None
    timeline_id: str | None
    periods: tuple[SnapshotPeriod, ...]


@dataclass(frozen=True)
class SnapshotSeries:
    axis_id: str
    values: tuple[str | None, ...]
    value_statuses: tuple[str, ...]
    normalized_values: tuple[str | None, ...]
    formula: str | None = None


@dataclass(frozen=True)
class SnapshotRow:
    row_key: str
    sheet: str
    row: int
    label: str
    parent_label: str | None
    label_path: tuple[str, ...]
    kind: str
    unit: str | None
    formula: str | None
    indent: int
    hidden: bool
    check_row: bool
    hints: dict
    scale_factor: int | None
    series: tuple[SnapshotSeries, ...]
    values: tuple[str | None, ...]
    value_statuses: tuple[str, ...]
    normalized_values: tuple[str | None, ...]
    block_id: str
    block_kind: str


@dataclass(frozen=True)
class GraphLink:
    cell: str | None
    formula: str | None
    formula_class: str | None
    refs: tuple[str, ...]
    row_key: str | None
    period_id: str | None


@dataclass(frozen=True)
class WorkbookSnapshot:
    axes: dict[str, SnapshotAxis]
    rows: tuple[SnapshotRow, ...]
    links: tuple[GraphLink, ...] = ()
    used_range: dict[str, tuple[int, int]] = field(default_factory=dict)


@dataclass(frozen=True)
class Summary:
    etag: str
    content_sha256: str
    context_schema_version: str
    graph_schema_version: str
    status: str
    context_etag: str | None = None
    graph_etag: str | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class NotModified:
    etag: str


def parse_decimal_text(raw: str | None):
    from decimal import Decimal, InvalidOperation

    if raw is None:
        return None
    text = str(raw).strip()
    if text == "":
        return None
    try:
        return Decimal(text.replace(" ", "").replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def utc_now() -> datetime:
    return datetime.now(tz=__import__("datetime").timezone.utc)
