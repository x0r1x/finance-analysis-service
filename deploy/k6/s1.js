import http from "k6/http";
import { check, sleep } from "k6";

const base = __ENV.BASE_URL || "http://127.0.0.1:8080";
const job = __ENV.JOB_ID;
const vus = Number(__ENV.VUS || 50);
const duration = __ENV.DURATION || "30s";

export const options = {
  scenarios: {
    s1_hot_book: {
      executor: "constant-vus",
      vus,
      duration,
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.05"],
  },
};

export function setup() {
  const loaded = http.post(`${base}/v1/books/${job}:load`, null, {
    headers: { "X-User-Id": "s1", "X-Client-Id": "k6" },
  });
  check(loaded, { "load ok": (r) => r.status === 200 || r.status === 202 });
}

export default function () {
  const response = http.post(
    `${base}/v1/books/${job}/series`,
    JSON.stringify({ row_keys: ["rev"], periods: ["2024"] }),
    { headers: { "Content-Type": "application/json", "X-User-Id": `s1-${__VU}`, "X-Client-Id": "k6" } },
  );
  check(response, { "series 200": (r) => r.status === 200 });
  sleep(0.05);
}
