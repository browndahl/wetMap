import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  scenarios: {
    cached_reads: { executor: "constant-vus", vus: 10, duration: "30s" },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    "http_req_duration{endpoint:radar}": ["p(95)<300"],
    "http_req_duration{endpoint:forecast}": ["p(95)<300"],
    "http_req_duration{endpoint:precipitation}": ["p(95)<300"],
  },
};

const base = __ENV.BASE_URL || "http://localhost:8080";
const point = "lat=56.16&lon=10.20";

export function setup() {
  const forecast = http.get(`${base}/api/v1/weather/forecast?${point}`);
  const precipitation = http.get(
    `${base}/api/v1/weather/precipitation?${point}`,
  );
  check(forecast, {
    "forecast warm-up 200": (result) => result.status === 200,
  });
  check(precipitation, {
    "precipitation warm-up 200": (result) => result.status === 200,
  });
}

export default function () {
  const responses = http.batch([
    [
      "GET",
      `${base}/api/v1/radar/frames`,
      null,
      { tags: { endpoint: "radar" } },
    ],
    [
      "GET",
      `${base}/api/v1/weather/forecast?${point}`,
      null,
      { tags: { endpoint: "forecast" } },
    ],
    [
      "GET",
      `${base}/api/v1/weather/precipitation?${point}`,
      null,
      { tags: { endpoint: "precipitation" } },
    ],
  ]);
  check(responses[0], {
    "manifest 200": (result) => result.status === 200,
    "has attribution": (result) =>
      result.body.includes("Baseret på data fra DMI"),
  });
  check(responses[1], {
    "forecast 200": (result) => result.status === 200,
    "forecast provider visible": (result) =>
      Boolean(
        result.headers["X-Wetmap-Provider"] ||
          result.headers["X-WetMap-Provider"],
      ),
    "forecast timing visible": (result) =>
      Boolean(result.headers["Server-Timing"]),
  });
  check(responses[2], {
    "precipitation 200": (result) => result.status === 200,
    "precipitation timing visible": (result) =>
      Boolean(result.headers["Server-Timing"]),
  });
  sleep(1);
}
