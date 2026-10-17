from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone


CACHE_RETRY_DELAYS_SECONDS = (0.5, 1.0, 2.0, 3.0)
MAX_CACHE_HIT_SECONDS = 5.0


@dataclass(frozen=True)
class ProbeResult:
    seconds: float
    headers: dict[str, str]
    payload: dict

    @property
    def cache_status(self) -> str:
        return self.headers.get("x-wetmap-point-cache", "unknown").upper()

    @property
    def edge_location(self) -> str:
        ray = self.headers.get("cf-ray", "")
        return ray.rsplit("-", 1)[-1] if "-" in ray else "unknown"


def probe_url(api_url: str, now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    slot = int(current.timestamp() // (15 * 60))
    # Rotate the cache coordinate every 15 minutes so scheduled probes normally
    # exercise both the complete radar/model path and the point cache.
    latitude = 56.10 + (slot % 70) / 1000
    longitude = 10.10 + ((slot // 70) % 70) / 1000
    return (
        f"{api_url.rstrip('/')}/api/v1/weather/precipitation"
        f"?lat={latitude:.5f}&lon={longitude:.5f}&v=2"
    )


def http_probe(url: str) -> ProbeResult:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "wetmap-synthetic/1.0"},
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.load(response)
        headers = {name.lower(): value for name, value in response.headers.items()}
    return ProbeResult(time.perf_counter() - started, headers, payload)


def validate_probe(result: ProbeResult) -> None:
    if "radar-nowcast" not in str(result.payload.get("source", "")):
        raise SystemExit("Live precipitation probe did not use the radar-nowcast path")

    timing = result.headers.get("server-timing", "")
    if result.cache_status == "HIT":
        if "point_cache;dur=" not in timing or "total;dur=" not in timing:
            raise SystemExit("Cached response is missing point-cache performance telemetry")
        if result.seconds > MAX_CACHE_HIT_SECONDS:
            raise SystemExit(
                f"Cached point forecast is too slow ({result.seconds:.2f}s)"
            )
    elif result.cache_status == "MISS":
        if "radar;dur=" not in timing or "combined_total;dur=" not in timing:
            raise SystemExit("Full response is missing radar performance telemetry")


def check_live_performance(
    api_url: str,
    *,
    probe: Callable[[str], ProbeResult] = http_probe,
    sleep: Callable[[float], None] = time.sleep,
    retry_delays: Sequence[float] = CACHE_RETRY_DELAYS_SECONDS,
    now: datetime | None = None,
) -> list[ProbeResult]:
    url = probe_url(api_url, now)
    results: list[ProbeResult] = []
    transient_errors: list[str] = []

    for delay in (0.0, *retry_delays):
        if delay:
            sleep(delay)
        try:
            result = probe(url)
        except (TimeoutError, urllib.error.URLError, json.JSONDecodeError) as error:
            transient_errors.append(type(error).__name__)
            continue

        validate_probe(result)
        results.append(result)
        if result.cache_status == "HIT":
            statuses = ", ".join(
                f"{item.cache_status}@{item.edge_location}:{item.seconds * 1000:.0f}ms"
                for item in results
            )
            print(f"Live point forecast cache sequence: {statuses}")
            return results

    if not results:
        errors = ", ".join(transient_errors) or "unknown errors"
        raise SystemExit(
            f"Live point forecast failed on all {1 + len(retry_delays)} attempts "
            f"({errors})"
        )

    statuses = ", ".join(
        f"{item.cache_status}@{item.edge_location}" for item in results
    )
    error_suffix = (
        f"; transient errors: {', '.join(transient_errors)}"
        if transient_errors
        else ""
    )
    raise SystemExit(
        "Point forecast cache did not produce a HIT after "
        f"{1 + len(retry_delays)} attempts ({statuses}{error_suffix})"
    )


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(argv if argv is not None else sys.argv[1:])
    if len(arguments) != 1:
        raise SystemExit("Usage: check_live_performance.py <api-url>")
    check_live_performance(arguments[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
