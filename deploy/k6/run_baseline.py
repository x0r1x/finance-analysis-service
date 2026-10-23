"""Прогон S1/S2 не короче 60 секунд и запись базовой линии.

k6 берётся из K6_BIN или из PATH. Рабочий каталог — временный.
Книги — копии packt. Имя каталога и есть job_id, поэтому ключ сборки
у копий разный. Адаптер sidecar публикации не читает.
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


def _copy_job(source: Path, target: Path) -> None:
    shutil.copytree(source, target)


def slo_met(samples: list[dict], assumption_ms: float = 500) -> bool:
    """SLO засчитан, только если прогон жив, проверки прошли и p95 в допуске."""

    if not samples:
        return False
    for item in samples:
        if item.get("exit_code"):
            return False
        if (item.get("failed_rate") or 0) > 0:
            return False
        rate = item.get("check_rate")
        if rate is not None and rate < 0.99:
            return False
        if (item.get("p95_ms") or 0) > assumption_ms:
            return False
    return True


def _duration_sec(text: str) -> int:
    if text.endswith("s"):
        return int(text[:-1])
    return int(text)


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
        _copy_job(source, fixture / job)
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
            # Общий X-Client-Id. Квота выше потока S1, иначе 429 — это GCRA, не книга.
            "RATE_USER_RPS": "2000",
            "RATE_USER_BURST": "2000",
            "RATE_CLIENT_RPS": "2000",
            "RATE_CLIENT_BURST": "2000",
            "RATE_ANON_RPS": "2000",
            "SYNC_DEADLINE_MS": "15000",
            "LOAD_SYNC_SEC": "120",
        }
    )
    try:
        subprocess.run(["redis-cli", "-n", "14", "FLUSHDB"], check=False, timeout=30)
    except subprocess.TimeoutExpired:
        raise SystemExit("redis-cli FLUSHDB не уложился в 30 с") from None
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
            k6_timeout = _duration_sec(extra["DURATION"]) + 420
            try:
                proc = subprocess.run(
                    [k6, "run", "--summary-export", str(summary), str(Path(__file__).parent / script)],
                    env=env_k6,
                    cwd=ROOT,
                    check=False,
                    timeout=k6_timeout,
                )
                exit_code = proc.returncode
            except subprocess.TimeoutExpired:
                exit_code = 124
            if summary.is_file():
                payload = json.loads(summary.read_text(encoding="utf-8"))
                duration_metric = payload["metrics"]["http_req_duration"]
                failed = payload["metrics"].get("http_req_failed", {})
                checks = payload["metrics"].get("checks", {})
                reports[name] = {
                    "exit_code": exit_code,
                    "vus": int(extra["VUS"]),
                    "duration": extra["DURATION"],
                    "p95_ms": duration_metric.get("p(95)"),
                    "avg_ms": duration_metric.get("avg"),
                    "max_ms": duration_metric.get("max"),
                    "failed_rate": failed.get("value", failed.get("rate")),
                    "check_rate": checks.get("value", checks.get("rate")),
                    "count": payload["metrics"].get("http_reqs", {}).get("count"),
                    "book": "packt",
                    "row_key": PACKT_REVENUE_ROW,
                    "period": PACKT_PERIOD,
                }
            else:
                reports[name] = {
                    "exit_code": exit_code,
                    "vus": int(extra["VUS"]),
                    "duration": extra["DURATION"],
                    "p95_ms": None,
                    "failed_rate": 1,
                    "check_rate": 0,
                    "book": "packt",
                    "row_key": PACKT_REVENUE_ROW,
                    "period": PACKT_PERIOD,
                }
        samples = [item for key, item in reports.items() if key in {"s1", "s2"}]
        p95 = max(item["p95_ms"] or 0 for item in samples)
        assumption_ms = 500
        reports["slo"] = {
            "assumption_warm_p95_ms": assumption_ms,
            "met": slo_met(samples, assumption_ms),
            "revised_warm_p95_ms": None if p95 <= assumption_ms else round(p95, 1),
            "note": "прогон 60 с на копиях книги packt; цель §4.13.9 — тёплый p95 ≤ 500 мс; квота клиента на стенде 2000 rps",
            "stand_rate_client_rps": 2000,
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
