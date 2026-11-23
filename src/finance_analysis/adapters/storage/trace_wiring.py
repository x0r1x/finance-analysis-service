"""Сборка указателя и замка. Application этот модуль не импортирует."""

from __future__ import annotations

from pathlib import Path


def open_trace_tail(settings):
    from finance_analysis.adapters.storage.trace_pointer import DuckDBTracePointer

    pointer = DuckDBTracePointer(Path(settings.fas_data_dir) / "trace_pointer.duckdb")
    retainer = None
    if (
        settings.fas_s3_bucket
        and settings.fas_trace_retention != "analysis"
        and settings.fas_s3_access_key
        and settings.fas_s3_secret_key
    ):
        from finance_analysis.adapters.storage.trace_retention import (
            S3GovernanceRetainer,
        )

        retainer = S3GovernanceRetainer(
            bucket=settings.fas_s3_bucket,
            prefix=settings.fas_s3_prefix,
            endpoint=settings.fas_s3_endpoint,
            region=settings.fas_s3_region,
            access_key=settings.fas_s3_access_key,
            secret_key=settings.fas_s3_secret_key,
        )
    return pointer, retainer
