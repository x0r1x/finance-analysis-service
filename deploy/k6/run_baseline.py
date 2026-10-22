"""Короткий прогон S1/S2 и запись базовой линии."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests" / "fixtures" / "golden"
PRIMARY = "a" * 64
K6 = os.environ.get("K6_BIN", "/tmp/k6-v1.4.0-linux-amd64/k6")
OUT = Path(__file__).resolve().parent / "baseline.json"


def _jobs(count: int) -> list[str]:
    jobs = [PRIMARY]
    for index in range(1, count):
        jobs.append(f"{index:064x}")
    return jobs


def main() -> None:
    work = Path("/tmp/fas-k6")
    if work.exists():
        shutil.rmtree(work)
    fixture = work / "fixtures"
    data = work / "data"
    fixture.mkdir(parents=True)
    data.mkdir()
    jobs = _jobs(16)
    source = GOLDEN / PRIMARY
    for job in jobs:
        target = fixture / job
        shutil.copytree(source, target)
        summary = json.loads((target / "summary.json").read_text(encoding="utf-8"))
        summary["content_sha256"] = f"{int(job[:8], 16):064x}"
        (target / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
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
            "SYNC_DEADLINE_MS": "10000",
            "LOAD_SYNC_SEC": "20",
        }
    )
    subprocess.run(["redis-cli", "-n", "14", "FLUSHDB"], check=False)
    log = open(work / "api.log", "w", encoding="utf-8")
    server = subprocess.Popen(
        ["python3", "-m", "finance_analysis.main"],
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
        for name, script, extra in (
            ("s1", "s1.js", {"VUS": "50", "DURATION": "8s", "JOB_ID": PRIMARY}),
            ("s2", "s2.js", {"VUS": "16", "DURATION": "8s", "JOB_IDS": ",".join(jobs)}),
        ):
            summary = work / f"{name}.json"
            env_k6 = env.copy()
            env_k6.update({"BASE_URL": "http://127.0.0.1:8080", **extra})
            proc = subprocess.run(
                [K6, "run", "--summary-export", str(summary), str(Path(__file__).parent / script)],
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
            }
        p95 = max(item["p95_ms"] or 0 for item in reports.values())
        assumption_ms = 500
        reports["slo"] = {
            "assumption_warm_p95_ms": assumption_ms,
            "met": p95 <= assumption_ms,
            "revised_warm_p95_ms": None if p95 <= assumption_ms else round(p95, 1),
            "note": "короткий прогон стенда; цель §4.13.9 — тёплый p95 ≤ 500 мс",
        }
        verify = Path(__file__).parent / "must-verify.json"
        if verify.is_file():
            reports["must_verify"] = json.loads(verify.read_text(encoding="utf-8"))
        OUT.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
        print(OUT.read_text(encoding="utf-8"))
    finally:
        server.send_signal(signal.SIGTERM)
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    main()
