"""Запись индекса сборки `_builds/` (§4.10)."""

from __future__ import annotations

from finance_analysis.domain.book import (
    FAS_PROJECTION_VERSION,
    FAS_SCHEMA_VERSION,
    BuilderRef,
)

REASONS = {
    "initial",
    "builder_rebuild",
    "builder_schema_change",
    "fas_projection_upgrade",
    "manual_reload",
}


def projection_of(manifest: dict) -> str:
    """Версия проекции сборки. До проекции 2 manifest её не записывал."""

    return str(manifest.get("fas_projection_version") or "1")


def rebuild_reason(previous: dict | None, ref: BuilderRef, *, projection: str) -> str:
    if not previous:
        return "initial"
    prev_ref = previous.get("builder_ref") or {}
    if (
        prev_ref.get("context_schema_version") != ref.context_schema_version
        or prev_ref.get("graph_schema_version") != ref.graph_schema_version
    ):
        return "builder_schema_change"
    if projection_of(previous) != projection:
        return "fas_projection_upgrade"
    if prev_ref.get("summary_etag") != ref.summary_etag:
        return "builder_rebuild"
    return "manual_reload"


def index_document(
    build: str,
    manifest: dict,
    *,
    previous: str | None,
    reason: str,
    projection: str = FAS_PROJECTION_VERSION,
) -> dict:
    files = manifest.get("files") or {}
    rows = periods = observations = total = 0
    if isinstance(files, dict):
        for rel, meta in files.items():
            if not isinstance(meta, dict):
                continue
            total += int(meta.get("bytes") or 0)
            name = str(rel).rsplit("/", 1)[-1]
            count = int(meta.get("rows") or 0)
            if name.startswith("dim_row"):
                rows = count
            elif name.startswith("dim_period"):
                periods = count
            elif name.startswith("fact_observation"):
                observations = count
    if reason not in REASONS:
        reason = "initial"
    return {
        "build_key": build,
        "created_at_utc": manifest.get("loaded_at"),
        "previous_build_key": previous,
        "builder_ref": manifest.get("builder_ref"),
        "fas_projection_version": projection,
        "fas_schema_version": manifest.get("fas_schema_version") or FAS_SCHEMA_VERSION,
        "rebuild_reason": reason,
        "stats": {"rows": rows, "periods": periods, "observations": observations, "bytes": total},
    }
