import http from "k6/http";
import { check, sleep } from "k6";

const base = __ENV.BASE_URL || "http://127.0.0.1:8080";
const jobs = (__ENV.JOB_IDS || __ENV.JOB_ID || "").split(",").filter(Boolean);
const vus = Number(__ENV.VUS || 20);
const duration = __ENV.DURATION || "30s";

export const options = {
  scenarios: {
    s2_many_books: {
      executor: "constant-vus",
      vus,
      duration,
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.05"],
  },
};

export default function () {
  const job = jobs[(__VU + __ITER) % jobs.length];
  const response = http.post(
    `${base}/v1/books/${job}/series`,
    JSON.stringify({ row_keys: ["rev"], periods: ["2024"] }),
    { headers: { "Content-Type": "application/json", "X-User-Id": `s2-${__VU}`, "X-Client-Id": "k6" } },
  );
  check(response, { "series 200": (r) => r.status === 200 });
  sleep(0.05);
}
