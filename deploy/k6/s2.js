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

function loadReady(jobId, user) {
  const headers = { "X-User-Id": user, "X-Client-Id": "k6" };
  const loaded = http.post(`${base}/v1/books/${jobId}:load`, null, { headers, timeout: "180s" });
  if (loaded.status === 200) {
    return loaded;
  }
  if (loaded.status !== 202) {
    return loaded;
  }
  let opId = "";
  try {
    opId = loaded.json("id");
  } catch (error) {
    return loaded;
  }
  const deadline = Date.now() + 120000;
  while (Date.now() < deadline) {
    const current = http.get(`${base}/v1/operations/${opId}?wait_ms=2000`, { headers, timeout: "30s" });
    if (current.status === 200) {
      const status = current.json("status");
      if (status === "succeeded" || status === "failed") {
        break;
      }
    }
    sleep(0.5);
  }
  return http.get(`${base}/v1/books/${jobId}`, { headers, timeout: "60s" });
}

export function setup() {
  for (const job of jobs) {
    const loaded = loadReady(job, "s2-setup");
    check(loaded, { "load ok": (r) => r && r.status === 200 });
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
