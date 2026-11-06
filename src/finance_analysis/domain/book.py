"""Снимок книги, ключи и ссылки (§4.2, §5.3)."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime

from finance_analysis.domain.derive_fingerprint import configs_root, derive_fingerprint

FAS_VERSION = "0.23.0"
FAS_SCHEMA_VERSION = "1.0"
SEP = "›"


def _dictionaries_stamp() -> str:
    """Короткий хеш dictionaries.yaml: правка маркеров меняет build_key после рестарта."""

    path = configs_root() / "configs" / "glossary" / "dictionaries.yaml"
    body = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(body).hexdigest()[:12]


# База 3 — SSOT маркеров из YAML; суффикс — содержимое dictionaries.yaml.
FAS_PROJECTION_VERSION = f"3:{_dictionaries_stamp()}"

_WS = re.compile(r"\s+")


def norm(value: str) -> str:
    return _WS.sub(" ", value.casefold()).strip()


def binding_key(sheet: str, label_path: list[str], label: str, occurrence: int) -> str:
    path = norm(" › ".join(label_path))
    material = SEP.join([norm(sheet), path, norm(label), str(occurrence)])
    return hashlib.sha1(material.encode("utf-8")).hexdigest()


def question_digest(kind: str, subject: str, scope: str) -> str:
    """sha1(kind › subject › scope). Стабилен между сборками (§5.10.5)."""

    return hashlib.sha1(SEP.join([kind, subject, scope]).encode()).hexdigest()


def build_key_for(
    job_id: str,
    summary_etag: str,
    projection_version: str = FAS_PROJECTION_VERSION,
) -> str:
    """sha256(job_id › summary_etag › fas_projection_version)[:16] (§4.2)."""

    material = SEP.join([job_id, summary_etag, projection_version])
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
    fas_derive_version: str | None = None,
    model_types_version: str = "none",
    model_type_seq: int = 0,
    sheet_roles_version: str = "none",
) -> str:
    """Возвращает ключ производного состояния.

    `fas_derive_version` — отпечаток файлов свёртки. Если аргумент не передан,
    берётся отпечаток текущего репозитория. Остальные аргументы — прежние
    входы ключа, включая версию глоссария и `sheet_roles_version`.
    """

    payload = {
        "state_seq": state_seq,
        "glossary_version": glossary_version,
        "taxonomy_version": taxonomy_version,
        "calibrator_version": calibrator_version,
        "embed_model": embed_model,
        "rerank_model": rerank_model,
        "clm_model": clm_model,
        "profile_version": profile_version,
        "fas_derive_version": derive_fingerprint() if fas_derive_version is None else fas_derive_version,
        "model_types_version": model_types_version,
        "model_type_seq": model_type_seq,
        "sheet_roles_version": sheet_roles_version,
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
    summary_etag: str
    context_schema_version: str
    graph_schema_version: str

    def as_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "summary_etag": self.summary_etag,
            "context_schema_version": self.context_schema_version,
            "graph_schema_version": self.graph_schema_version,
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
    model_types: str = "none"
    model_type_seq: int = 0
    sheet_roles: str = "none"

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
            "model_types": self.model_types,
            "model_type_seq": self.model_type_seq,
            "sheet_roles": self.sheet_roles,
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
            model_types_version=self.model_types,
            model_type_seq=self.model_type_seq,
            sheet_roles_version=self.sheet_roles,
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
    flags: dict = field(default_factory=dict)
    hidden: bool = False


@dataclass(frozen=True)
class SnapshotAxis:
    id: str
    sheet: str
    grain: str | None
    timeline_id: str | None
    axis_kind: str
    periods: tuple[SnapshotPeriod, ...]


@dataclass(frozen=True)
class SnapshotSeries:
    axis_id: str
    values: tuple[str | None, ...]
    value_statuses: tuple[str, ...]
    normalized_values: tuple[str | None, ...]
    formula: str | None = None
    formula_exceptions: tuple[str, ...] = ()


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
    formula_exceptions: tuple[str, ...] = ()


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
    context_schema_version: str
    graph_schema_version: str
    status: str
    warnings: tuple[str, ...] = ()
    counters: dict = field(default_factory=dict)


@dataclass(frozen=True)
class NotModified:
    """304. Тела нет, ETag тот же."""

    etag: str


@dataclass(frozen=True)
class Changed:
    """HEAD/GET ответили другим ETag."""

    etag: str


@dataclass(frozen=True)
class ReportNotReady:
    """409, пока builder пересобирает публикацию."""

    error: str = "report_not_ready"

    def as_dict(self) -> dict:
        return {"error": self.error}


def with_links(snapshot: WorkbookSnapshot, links: tuple[GraphLink, ...]) -> WorkbookSnapshot:
    return WorkbookSnapshot(
        axes=snapshot.axes,
        rows=snapshot.rows,
        links=links,
        used_range=snapshot.used_range,
    )


def publication_aligned(snapshot: WorkbookSnapshot) -> bool:
    """Каждый непустой links[].row_key есть среди rows[].row_key (§4.3)."""

    keys = {row.row_key for row in snapshot.rows}
    for link in snapshot.links:
        if link.row_key and link.row_key not in keys:
            return False
    return True


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
