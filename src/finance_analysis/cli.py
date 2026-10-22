"""CLI фазы 0: storage sync и проверка хранилища."""

from __future__ import annotations

import argparse
import asyncio
import sys

from finance_analysis.adapters.storage.store import build_storage
from finance_analysis.adapters.storage.sync import sync_stores
from finance_analysis.settings import Settings


def _settings_for(url: str) -> Settings:
    if url.startswith("file://"):
        path = url.removeprefix("file://")
        return Settings(FAS_DATA_DIR=path, FAS_S3_PREFIX="")
    if url.startswith("s3://"):
        rest = url.removeprefix("s3://")
        bucket, _, prefix = rest.partition("/")
        return Settings(
            FAS_S3_BUCKET=bucket,
            FAS_S3_PREFIX=prefix,
            FAS_S3_ENDPOINT=__import__("os").environ.get("FAS_S3_ENDPOINT"),
            FAS_S3_REGION=__import__("os").environ.get("FAS_S3_REGION", "us-east-1"),
            FAS_S3_ACCESS_KEY=__import__("os").environ.get("FAS_S3_ACCESS_KEY"),
            FAS_S3_SECRET_KEY=__import__("os").environ.get("FAS_S3_SECRET_KEY"),
            FAS_S3_SSL=__import__("os").environ.get("FAS_S3_SSL", "true").lower() == "true",
        )
    raise SystemExit(f"неизвестный URL {url}")


async def _sync(source: str, destination: str) -> None:
    src = build_storage(_settings_for(source))
    dst = build_storage(_settings_for(destination))
    report = await sync_stores(src, dst)
    print(report)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="fas")
    sub = parser.add_subparsers(dest="command")
    storage = sub.add_parser("storage")
    storage_sub = storage.add_subparsers(dest="storage_command")
    sync = storage_sub.add_parser("sync")
    sync.add_argument("source")
    sync.add_argument("destination")
    args = parser.parse_args(argv)
    if args.command == "storage" and args.storage_command == "sync":
        asyncio.run(_sync(args.source, args.destination))
        return
    parser.print_help()
    sys.exit(2)


if __name__ == "__main__":
    main()
