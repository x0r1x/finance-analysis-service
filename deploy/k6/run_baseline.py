"""Прогон S1/S2 не короче 60 секунд и запись базовой линии.

k6 берётся из K6_BIN или из PATH. Рабочий каталог — временный.
Книги — копии packt: у каждой свой job_id и content_sha256, чтобы токен
согласованности отличался.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.books import ALIASES, BUILDER_ROOT, PACKT_PERIOD, PACKT_REVENUE_ROW, PACKT_REVENUE_VALUE

PRIMARY = ALIASES["packt"]
OUT = Path(__file__).resolve().parent / "baseline.json"
DURATION = "60s"


def _k6() -> str:
    chosen = os.environ.get("K6_BIN") or shutil.which("k6")
    if not chosen:
        raise SystemExit("k6 не найден: задайте K6_BIN или поставьте k6 в PATH")
    return chosen


def _jobs(count: int) -> list[str]:
    jobs = [PRIMARY]
    for index in range(1, count):
        jobs.append(f"{index:064x}")
    return jobs


def _copy_job(source: Path, target: Path, job: str) -> None:
    shutil.copytree(source, target)
    meta_path = target / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["job_id"] = job
    meta["content_sha256"] = f"{int(job, 16):064x}"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")


def main() -> None:
    k6 = _k6()
    work = Path(tempfile.mkdtemp(prefix="fas-k6-"))
    fixture = work / "fixtures"
    data = work / "data"
    fixture.mkdir(parents=True)
    data.mkdir()
    jobs = _jobs(16)
    source = BUILDER_ROOT / PRIMARY
    for job in jobs:
        _copy_job(source, fixture / job, job)
    env = os.environ.copy()
    env.update(
        {
            "FAS_REDIS_URL": "redis://127.0.0.1:6379/14",
            "FAS_DATA_DIR": str(data),
            "FAS_FIXTURE_DIR": str(fixture),
            "FAS_PORT": "8080",
            "FAS_HOST": "127.0.0.1",
            "WREN_DUCKDB_MEMORY_MB": "256",
            "WREN_POOL_MEMORY_MB": "1024",
            "WREN_ENGINE_POOL": "4",
            "WREN_THREADS": "4",
            "RATE_USER_RPS": "500",
            "RATE_USER_BURST": "500",
            "RATE_CLIENT_RPS": "500",
            "RATE_CLIENT_BURST": "500",
            "RATE_ANON_RPS": "500",
            "SYNC_DEADLINE_MS": "15000",
            "LOAD_SYNC_SEC": "120",
        }
    )
    subprocess.run(["redis-cli", "-n", "14", "FLUSHDB"], check=False)
    log = open(work / "api.log", "w", encoding="utf-8")
    server = subprocess.Popen(
        [sys.executable, "-m", "finance_analysis.main"],
        cwd=ROOT,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.time() + 30
        while time.time() < deadline:
            if server.poll() is not None:
                log.flush()
                raise SystemExit((work / "api.log").read_text(encoding="utf-8")[-4000:] or f"api exit {server.returncode}")
            try:
                with urllib.request.urlopen("http://127.0.0.1:8080/health/ready", timeout=0.5) as response:
                    if response.status == 200:
                        break
            except Exception:
                time.sleep(0.2)
        else:
            raise SystemExit("api не поднялся")
        reports = {}
        scenarios = (
            ("s1", "s1.js", {"VUS": "50", "DURATION": DURATION, "JOB_ID": PRIMARY}),
            ("s2", "s2.js", {"VUS": "16", "DURATION": DURATION, "JOB_IDS": ",".join(jobs)}),
        )
        for name, script, extra in scenarios:
            summary = work / f"{name}.json"
            env_k6 = env.copy()
            env_k6.update(
                {
                    "BASE_URL": "http://127.0.0.1:8080",
                    "ROW_KEY": PACKT_REVENUE_ROW,
                    "PERIOD": PACKT_PERIOD,
                    "EXPECT_VALUE": PACKT_REVENUE_VALUE,
                    **extra,
                }
            )
            proc = subprocess.run(
                [k6, "run", "--summary-export", str(summary), str(Path(__file__).parent / script)],
                env=env_k6,
                cwd=ROOT,
                check=False,
            )
            payload = json.loads(summary.read_text(encoding="utf-8"))
            duration_metric = payload["metrics"]["http_req_duration"]
            failed = payload["metrics"].get("http_req_failed", {})
            reports[name] = {
                "exit_code": proc.returncode,
                "vus": int(extra["VUS"]),
                "duration": extra["DURATION"],
                "p95_ms": duration_metric.get("p(95)"),
                "avg_ms": duration_metric.get("avg"),
                "max_ms": duration_metric.get("max"),
                "failed_rate": failed.get("value", failed.get("rate")),
                "count": payload["metrics"].get("http_reqs", {}).get("count"),
                "book": "packt",
                "row_key": PACKT_REVENUE_ROW,
                "period": PACKT_PERIOD,
            }
        p95 = max(item["p95_ms"] or 0 for item in reports.values())
        assumption_ms = 500
        reports["slo"] = {
            "assumption_warm_p95_ms": assumption_ms,
            "met": p95 <= assumption_ms,
            "revised_warm_p95_ms": None if p95 <= assumption_ms else round(p95, 1),
            "note": "прогон 60 с на копиях книги packt; цель §4.13.9 — тёплый p95 ≤ 500 мс",
        }
        OUT.write_text(json.dumps(reports, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(OUT.read_text(encoding="utf-8"))
        failed_runs = [name for name, item in reports.items() if isinstance(item, dict) and item.get("exit_code")]
        if failed_runs:
            raise SystemExit(f"k6 завершился с ошибкой: {', '.join(failed_runs)}; лог API {work / 'api.log'}")
    finally:
        server.send_signal(signal.SIGTERM)
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    main()
