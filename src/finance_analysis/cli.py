"""CLI: storage sync, возврат задач из DLQ, калибратор, eval, shadow и задачи обучения (фаза 2b)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from finance_analysis.adapters.queue.jobs import TaskiqJobs
from finance_analysis.adapters.queue.requeue import requeue_dlq
from finance_analysis.adapters.storage.store import build_storage
from finance_analysis.adapters.storage.sync import sync_stores
from finance_analysis.application.glossary_store import GlossaryStore
from finance_analysis.settings import Settings


def _settings_for(url: str) -> Settings:
    if url.startswith("file://"):
        path = url.removeprefix("file://")
        return Settings(
            FAS_DATA_DIR=path,
            FAS_S3_PREFIX="",
            FAS_S3_BUCKET=None,
            FAS_S3_ENDPOINT=None,
            FAS_S3_ACCESS_KEY=None,
            FAS_S3_SECRET_KEY=None,
            FAS_READ_ONLY=False,
        )
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
            FAS_READ_ONLY=False,
        )
    raise SystemExit(f"неизвестный URL {url}")


async def _sync(source: str, destination: str, *, dry_run: bool, verify: bool) -> None:
    src = build_storage(_settings_for(source))
    dst = build_storage(_settings_for(destination))
    report = await sync_stores(src, dst, dry_run=dry_run, verify=verify)
    if report.get("dry_run"):
        print(f"план: {report['objects']} объектов, {report['bytes']} байт")
    print(report)


async def _export() -> None:
    settings = Settings()
    store = build_storage(settings)
    print(await GlossaryStore(store).export_patch(), end="")


async def _requeue(entry_id: str | None) -> None:
    settings = Settings()
    jobs = await TaskiqJobs.open(settings)
    await jobs.startup()
    try:
        report = await requeue_dlq(jobs.redis, jobs.store, jobs.kick, entry_id=entry_id)
    finally:
        await jobs.shutdown()
    print(report)


async def _with_service(run):
    from finance_analysis.main import assemble

    service, support = await assemble(Settings())
    try:
        return await run(service)
    finally:
        await service.settle()
        await support.close()


def _print(payload) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str))


async def _calibrator(command: str, version: str | None) -> None:
    async def run(service):
        if command == "train":
            return await service.calibrators.train(await service.examples.all_rows(), max_risk=service.settings.calibrator_max_risk)
        if command == "activate":
            return await service.calibrators.activate(None if version in (None, "none") else version)
        return await service.calibrators.head()

    _print(await _with_service(run))


async def _eval(prune: str | None) -> None:
    from finance_analysis.domain.glossary_release import package_of

    async def run(service):
        state = await service.glossary.ensure()
        document = await service.glossary.document(state["active"])
        calibrator = await service.calibrators.active()
        report = await service.evaluator.run(package_of(document), calibrator=calibrator)
        report.pop("scores", None)
        if prune:
            report["pruned"] = await service.evaluator.pruned(document, [item for item in prune.split(",") if item], calibrator=calibrator)
        report["glossary"] = state["active"]
        report["calibrator"] = service.calibrators.version
        return report

    _print(await _with_service(run))


async def _shadow(version: str) -> None:
    _print(await _with_service(lambda service: service.evaluator.shadow(version)))


async def _learn(command: str) -> None:
    from finance_analysis.domain.glossary_release import package_of

    async def run(service):
        state = await service.glossary.ensure()
        document = await service.glossary.document(state["active"])
        if command == "cluster":
            return await service.learning.cluster_unmapped(package_of(document))
        if command == "mine":
            return await service.learning.mine(package_of(document), document)
        return await service.learning.compact()

    _print(await _with_service(run))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="fas")
    sub = parser.add_subparsers(dest="command")
    storage = sub.add_parser("storage")
    storage_sub = storage.add_subparsers(dest="storage_command")
    sync = storage_sub.add_parser("sync")
    sync.add_argument("source")
    sync.add_argument("destination")
    sync.add_argument("--dry-run", action="store_true")
    sync.add_argument("--verify", action="store_true")
    glossary = sub.add_parser("glossary")
    glossary_sub = glossary.add_subparsers(dest="glossary_command")
    export = glossary_sub.add_parser("export")
    export.add_argument("--since", action="store_true")
    shadow = glossary_sub.add_parser("shadow")
    shadow.add_argument("version")
    calibrator = sub.add_parser("calibrator")
    calibrator.add_argument("calibrator_command", choices=["train", "activate", "list"])
    calibrator.add_argument("version", nargs="?")
    evaluate = sub.add_parser("eval")
    evaluate.add_argument("eval_command", choices=["mapping"])
    evaluate.add_argument("--prune", help="понятия через запятую для eval с удалённым понятием")
    learn = sub.add_parser("learn")
    learn.add_argument("learn_command", choices=["cluster", "mine", "compact"])
    ops = sub.add_parser("ops")
    ops_sub = ops.add_subparsers(dest="ops_command")
    requeue = ops_sub.add_parser("requeue")
    requeue.add_argument("entry_id", nargs="?")
    args = parser.parse_args(argv)
    if args.command == "storage" and args.storage_command == "sync":
        asyncio.run(_sync(args.source, args.destination, dry_run=args.dry_run, verify=args.verify))
        return
    if args.command == "glossary" and args.glossary_command == "export":
        asyncio.run(_export())
        return
    if args.command == "glossary" and args.glossary_command == "shadow":
        asyncio.run(_shadow(args.version))
        return
    if args.command == "calibrator":
        asyncio.run(_calibrator(args.calibrator_command, args.version))
        return
    if args.command == "eval":
        asyncio.run(_eval(args.prune))
        return
    if args.command == "learn":
        asyncio.run(_learn(args.learn_command))
        return
    if args.command == "ops" and args.ops_command == "requeue":
        asyncio.run(_requeue(args.entry_id))
        return
    parser.print_help()
    sys.exit(2)


if __name__ == "__main__":
    main()
