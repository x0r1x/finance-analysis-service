import http from "k6/http";
import { check } from "k6";

http.setResponseCallback(http.expectedStatuses(200, 409));

const base = __ENV.BASE_URL || "http://127.0.0.1:8080";
const job = __ENV.JOB_ID;
const binding = __ENV.BINDING_KEY;
const concept = __ENV.CONCEPT || "cfads";

export const options = {
  setupTimeout: "180s",
  scenarios: {
    s3_confirm: {
      executor: "shared-iterations",
      vus: 20,
      iterations: 20,
      maxDuration: "120s",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.05"],
    checks: ["rate>0.95"],
  },
};

export default function () {
  const headers = {
    "X-User-Id": `u${__VU}`,
    "X-Client-Id": "k6",
    "Content-Type": "application/json",
  };
  const body = JSON.stringify({
    decisions: [{ kind: "concept.confirm", target: binding, value: concept }],
  });
  const response = http.post(`${base}/v1/books/${job}/decisions`, body, {
    headers,
    timeout: "60s",
  });
  check(response, {
    "принято или один конфликт": (item) => item.status === 200 || item.status === 409,
  });
}
