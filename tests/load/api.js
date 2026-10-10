import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  scenarios: { cached_reads: { executor: "constant-vus", vus: 10, duration: "30s" } },
  thresholds: { http_req_failed: ["rate<0.01"], http_req_duration: ["p(95)<300"] }
};

const base = __ENV.BASE_URL || "http://localhost:8080";

export default function () {
  const response = http.get(`${base}/api/v1/radar/frames`);
  check(response, { "manifest 200": (result) => result.status === 200, "has attribution": (result) => result.body.includes("Baseret på data fra DMI") });
  sleep(1);
}
