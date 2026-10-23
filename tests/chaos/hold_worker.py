"""Worker, который держит лок перехвата и не возвращает его (§9, сценарий 7)."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from finance_analysis.adapters.queue.broker import FasStreamBroker
from finance_analysis.adapters.queue.worker import serve
from finance_analysis.settings import load_settings


class HoldBroker(FasStreamBroker):
    async def _autoclaim(self, redis) -> None:
        ready = os.environ.get("FAS_RECLAIM_READY")
        if ready:
            Path(ready).write_text(self.reclaim_lock_key())
        await asyncio.Event().wait()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="fas-hold-worker")
    parser.add_argument("--queue", required=True)
    parser.add_argument("--max-async-tasks", type=int, default=1)
    parser.add_argument("--ready-file", default=os.environ.get("FAS_WORKER_READY"))
    args = parser.parse_args(argv)
    asyncio.run(
        serve(
            load_settings(),
            queue=args.queue,
            max_async_tasks=args.max_async_tasks,
            ready_path=args.ready_file,
            broker_cls=HoldBroker,
        )
    )


if __name__ == "__main__":
    main()
