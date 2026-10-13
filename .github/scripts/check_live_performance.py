import json
import sys
import time
import urllib.request
from datetime import datetime, timezone


api_url = sys.argv[1].rstrip("/")
slot = int(datetime.now(timezone.utc).timestamp() // (15 * 60))
# Rotate the cache coordinate every 15 minutes so the first probe normally
# exercises the complete radar/model path and the second proves edge caching.
latitude = 56.10 + (slot % 70) / 1000
longitude = 10.10 + ((slot // 70) % 70) / 1000
url = (
    f"{api_url}/api/v1/weather/precipitation"
    f"?lat={latitude:.5f}&lon={longitude:.5f}&v=2"
)


def probe() -> tuple[float, dict[str, str], dict]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "wetmap-synthetic/1.0"},
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.load(response)
        headers = {name.lower(): value for name, value in response.headers.items()}
    return time.perf_counter() - started, headers, payload


first_seconds, first_headers, first_payload = probe()
time.sleep(0.5)
warm_seconds, warm_headers, warm_payload = probe()

if "radar-nowcast" not in str(first_payload.get("source", "")):
    raise SystemExit("Live precipitation probe did not use the radar-nowcast path")
if first_payload.get("basedOnObservedAt") != warm_payload.get("basedOnObservedAt"):
    raise SystemExit("Cold and warm probes did not use the same radar generation")
if warm_headers.get("x-wetmap-point-cache") != "HIT":
    raise SystemExit("Repeated point forecast did not hit the edge cache")

warm_timing = warm_headers.get("server-timing", "")
if "point_cache;dur=" not in warm_timing or "total;dur=" not in warm_timing:
    raise SystemExit("Warm response is missing point-cache performance telemetry")

if first_headers.get("x-wetmap-point-cache") == "MISS":
    first_timing = first_headers.get("server-timing", "")
    if "radar;dur=" not in first_timing or "combined_total;dur=" not in first_timing:
        raise SystemExit("Full response is missing radar performance telemetry")

if warm_seconds > 5:
    raise SystemExit(f"Warm point forecast is too slow ({warm_seconds:.2f}s)")

print(
    "Live point forecast: "
    f"first={first_seconds * 1000:.0f}ms "
    f"({first_headers.get('x-wetmap-point-cache', 'unknown')}), "
    f"warm={warm_seconds * 1000:.0f}ms "
    f"({warm_headers.get('x-wetmap-point-cache', 'unknown')})"
)
