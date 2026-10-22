import http from "k6/http";
import { check, sleep } from "k6";

const base = __ENV.BASE_URL || "http://127.0.0.1:8080";
const jobs = (__ENV.JOB_IDS || __ENV.JOB_ID || "").split(",").filter(Boolean);
const vus = Number(__ENV.VUS || 16);
const duration = __ENV.DURATION || "60s";
const rowKey = __ENV.ROW_KEY;
const period = __ENV.PERIOD;
const expectValue = __ENV.EXPECT_VALUE;

export const options = {
  setupTimeout: "300s",
  scenarios: {
    s2_many_books: {
      executor: "constant-vus",
      vus,
      duration,
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.05"],
    checks: ["rate>0.99"],
  },
};

export function setup() {
  for (const job of jobs) {
    const loaded = http.post(`${base}/v1/books/${job}:load`, null, {
      headers: { "X-User-Id": "s2-setup", "X-Client-Id": "k6" },
      timeout: "180s",
    });
    check(loaded, { "load ok": (r) => r.status === 200 || r.status === 202 });
  }
}

export default function () {
  const job = jobs[(__VU + __ITER) % jobs.length];
  const response = http.post(
    `${base}/v1/books/${job}/series`,
    JSON.stringify({ row_keys: [rowKey], periods: [period] }),
    { headers: { "Content-Type": "application/json", "X-User-Id": `s2-${__VU}`, "X-Client-Id": "k6" }, timeout: "30s" },
  );
  check(response, {
    "series 200": (r) => r.status === 200,
    "cell present": (r) => String(r.body).includes(expectValue),
  });
  sleep(0.05);
}
