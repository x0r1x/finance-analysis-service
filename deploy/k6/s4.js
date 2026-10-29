// S4: чтения многих книг держат снимок глоссария, пока идёт один transition.
// Запуск на стенде: k6 run -e BASE_URL=... -e JOB_IDS=id1,id2 deploy/k6/s4.js
import http from "k6/http";
import { check, sleep } from "k6";

const base = __ENV.BASE_URL || "http://127.0.0.1:8080";
const jobs = (__ENV.JOB_IDS || __ENV.JOB_ID || "").split(",").filter(Boolean);
const vus = Number(__ENV.VUS || 16);
const duration = __ENV.DURATION || "60s";

export const options = {
  setupTimeout: "300s",
  scenarios: {
    s4_snapshot: {
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

function headers(user) {
  return { "X-User-Id": user, "X-Client-Id": "k6" };
}

function loadReady(jobId, user) {
  const loaded = http.post(`${base}/v1/books/${jobId}:load`, null, { headers: headers(user), timeout: "180s" });
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
    const current = http.get(`${base}/v1/operations/${opId}?wait_ms=2000`, { headers: headers(user), timeout: "30s" });
    if (current.status === 200) {
      const status = current.json("status");
      if (status === "succeeded" || status === "failed") {
        break;
      }
    }
    sleep(0.5);
  }
  return http.get(`${base}/v1/books/${jobId}`, { headers: headers(user), timeout: "60s" });
}

function etagOf(response) {
  return response.headers.Etag || response.headers.ETag || response.headers.etag;
}

export function setup() {
  for (const job of jobs) {
    const loaded = loadReady(job, "s4-setup");
    check(loaded, { "load ok": (r) => r && r.status === 200 });
  }
  const state = http.get(`${base}/v1/glossary`, { headers: headers("s4-setup") });
  const made = http.post(
    `${base}/v1/glossary/releases`,
    JSON.stringify({
      ops: [{ op: "add_label", concept: "cfads", kind: "alt", lang: "en", text: "k6 s4 token" }],
    }),
    {
      headers: { ...headers("s4-setup"), "Content-Type": "application/json", "If-Match": etagOf(state) },
      timeout: "60s",
    },
  );
  const activated = http.post(
    `${base}/v1/glossary/transitions`,
    JSON.stringify({ version: made.json("version"), status: "active", force: true, reason: "s4" }),
    {
      headers: { ...headers("s4-setup"), "Content-Type": "application/json", "If-Match": etagOf(made) },
      timeout: "180s",
    },
  );
  check(activated, { "transition ok": (r) => r.status === 200 });
  const pins = {};
  for (const job of jobs) {
    const book = http.get(`${base}/v1/books/${job}`, { headers: headers("s4-setup"), timeout: "60s" });
    pins[job] = book.json("versions.glossary");
  }
  return { pins };
}

export default function (data) {
  const job = jobs[(__VU + __ITER) % jobs.length];
  const response = http.get(`${base}/v1/books/${job}`, { headers: headers(`s4-${__VU}`), timeout: "30s" });
  check(response, {
    "book 200": (r) => r.status === 200,
    "glossary pin stable": (r) => r.json("versions.glossary") === data.pins[job],
  });
  sleep(0.05);
}
