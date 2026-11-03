import http from "k6/http";
import { check } from "k6";

// S5 (§4.13.9): медленный или падающий сервер модели. FAS запущен с EMBED/RERANK/CLM_BASE_URL
// на scripts/k6/fake_models.py в FAKE_MODE=slow|fail|flaky. Ждём: привязка заканчивается в пределах
// MAPPING_DEADLINE_MS, синхронные чтения не страдают (bulkhead), цепь модели открыта (circuit breaker),
// в evidence привязок есть degraded.

const base = __ENV.BASE_URL || "http://127.0.0.1:8080";
const job = __ENV.JOB_ID;
const rowKey = __ENV.ROW_KEY;
const vus = Number(__ENV.VUS || 20);
const duration = __ENV.DURATION || "60s";

export const options = {
  setupTimeout: "180s",
  scenarios: {
    s5_reads: { executor: "constant-arrival-rate", rate: 20, timeUnit: "1s", duration, preAllocatedVUs: vus, exec: "reads" },
    s5_remap: { executor: "constant-arrival-rate", rate: 1, timeUnit: "5s", duration, preAllocatedVUs: 2, exec: "remap" },
  },
  thresholds: {
    "http_req_duration{scenario:s5_reads}": ["p(95)<2000"],
    "checks{scenario:s5_reads}": ["rate>0.99"],
    "checks{scenario:s5_remap}": ["rate>0.95"],
  },
};

const headers = (user) => ({ "X-User-Id": user, "X-Client-Id": "k6", "Content-Type": "application/json" });

export function setup() {
  const loaded = http.post(`${base}/v1/books/${job}:load`, null, { headers: headers("setup"), timeout: "180s" });
  check(loaded, { "книга загружена": (r) => r.status === 200 || r.status === 202 });
}

export function reads() {
  const body = JSON.stringify({ row_keys: [rowKey] });
  const response = http.post(`${base}/v1/books/${job}/series`, body, { headers: headers(`u${__VU}`), timeout: "10s" });
  check(response, { "серия читается при деградации моделей": (r) => r.status === 200 });
}

export function remap() {
  const started = http.post(`${base}/v1/books/${job}/mapping:infer`, null, { headers: headers("remap"), timeout: "10s" });
  check(started, { "привязка принята": (r) => r.status === 202 });
  if (started.status !== 202) {
    return;
  }
  const op = started.json("id");
  const done = http.get(`${base}/v1/operations/${op}?wait_ms=30000`, { headers: headers("remap"), timeout: "40s" });
  check(done, { "привязка завершилась без ошибки модели": (r) => r.json("status") === "succeeded" });
}

export function teardown() {
  const ready = http.get(`${base}/health/ready`);
  check(ready, { "готовность не зависит от моделей": (r) => r.status === 200 && r.json("status") === "ok" });
}
