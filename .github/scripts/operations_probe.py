"""External diagnostics, authenticated heartbeat, and incident-based Actions alerts.

A green execution can report an ongoing degraded service. The public status endpoint
remains 503; the summary and warning never imply that stale radar became healthy.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from check_freshness import age_minutes, radar_status
from check_live_performance import check_live_performance


def get_document(url: str):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json, text/html",
            "User-Agent": "wetmap-operations/1.0",
        },
    )
    for attempt in range(3):
        try:
            try:
                response = urllib.request.urlopen(request, timeout=15)
            except urllib.error.HTTPError as error:
                if error.code != 503 or not url.endswith("/operations/status"):
                    raise
                response = error
            with response:
                content = response.read(4_000_001)
            if len(content) > 4_000_000:
                raise ValueError("Response too large")
            return content.decode("utf-8") if url.endswith("/") else json.loads(content)
        except (OSError, ValueError):
            if attempt == 2:
                raise
            time.sleep(1 + attempt)
    raise RuntimeError("No response")


def validate_quality(report: dict) -> None:
    # Retain the complete existing quality/gate contract rather than a weaker
    # monitoring-specific approximation. This process never mutates forecasts.
    with tempfile.TemporaryDirectory(prefix="wetmap-quality-probe-") as directory:
        path = Path(directory) / "quality.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        subprocess.run(
            [
                sys.executable,
                str(Path(__file__).with_name("check_nowcast_quality.py")),
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )


def collect_checks(
    public_url: str, api_url: str, *, now: datetime | None = None
) -> list[dict]:
    current = now or datetime.now(timezone.utc)
    checks = []

    def check(name, operation):
        started = time.perf_counter()
        try:
            code = operation() or "ok"
        except (Exception, SystemExit):
            code = "probe-failed"
        checks.append(
            {
                "name": name,
                "ok": code == "ok",
                "code": code,
                "durationMs": min(
                    300_000, round((time.perf_counter() - started) * 1000)
                ),
            }
        )

    def web():
        body = get_document(public_url.rstrip("/") + "/")
        return (
            "ok"
            if isinstance(body, str) and 'id="root"' in body
            else "invalid-web-shell"
        )

    def api():
        return (
            "ok"
            if get_document(api_url + "/health/live").get("status") == "ok"
            else "invalid-health"
        )

    def radar():
        return radar_status(
            get_document(api_url + "/api/v1/radar/frames"), 25, current
        )["code"]

    def scheduler():
        status = get_document(api_url + "/api/v1/operations/status")
        try:
            fresh = -2 <= age_minutes(status["scheduler"]["checkedAt"], current) <= 10
        except (KeyError, ValueError, TypeError):
            fresh = False
        if not status.get("monitoringEnabled") or not fresh:
            return "scheduler-missed"
        if status["scheduler"].get("dispatchError"):
            return "dispatch-failed"
        previous_probe = (status.get("probe") or {}).get("receivedAt")
        if previous_probe and age_minutes(previous_probe, current) > 35:
            return "probe-missed"
        return "ok"

    check("web", web)
    check("api", api)
    check("radar", radar)
    check(
        "quality",
        lambda: validate_quality(
            get_document(api_url + "/api/v1/radar/nowcast/quality")
        ),
    )

    # The validator returns a list on success, so deliberately discard it.
    def performance():
        check_live_performance(api_url)

    check("performance", performance)
    check("scheduler", scheduler)
    return checks


def send_report(api_url: str, payload: dict, token: str) -> dict:
    request = urllib.request.Request(
        api_url + "/api/v1/operations/report",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "wetmap-operations/1.0",
        },
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.load(response)
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("No acknowledgement")


def report_exit_code(checks: list[dict], acknowledgement: dict) -> int:
    accepted = acknowledgement.get("accepted")
    should_fail = acknowledgement.get("shouldFail")
    transition = acknowledgement.get("transition")
    if (
        not isinstance(accepted, bool)
        or not isinstance(should_fail, bool)
        or transition not in {"opened", "ongoing", "healthy", "recovered", "superseded"}
    ):
        raise ValueError("Invalid monitor acknowledgement")
    if not accepted and transition != "superseded":
        raise ValueError("Report was not recorded")
    if any(not check["ok"] for check in checks):
        print(
            "::warning::Service remains DEGRADED. An ongoing incident may have a green diagnostic execution; see the operational status and job summary."
        )
    return 1 if should_fail else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args()
    public_url = os.environ.get("PUBLIC_URL", "").rstrip("/")
    api_url = os.environ.get("API_URL", "").rstrip("/")
    token = os.environ.get("MONITOR_REPORT_TOKEN", "")
    if (
        not public_url.startswith("https://")
        or not api_url.startswith("https://")
        or (not arguments.dry_run and not token)
    ):
        raise SystemExit("Missing HTTPS monitoring configuration or report secret")
    checks = collect_checks(public_url, api_url)
    payload = {
        "runId": os.environ.get("GITHUB_RUN_ID", "0")
        + "-"
        + os.environ.get("GITHUB_RUN_ATTEMPT", "1"),
        "checkedAt": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }
    print(json.dumps(payload, sort_keys=True))
    if arguments.dry_run:
        return 0 if all(check["ok"] for check in checks) else 1
    acknowledgement = send_report(api_url, payload, token)
    print(json.dumps(acknowledgement, sort_keys=True))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as output:
            output.write(
                "## Service health: "
                + ("HEALTHY" if all(check["ok"] for check in checks) else "DEGRADED")
                + "\n\n"
            )
            output.write(
                "Execution success is not service health. Repeated incidents are grouped; stale data remain unhealthy.\n\n"
            )
            output.write(
                "| Check | Result | Code | Duration |\n| --- | --- | --- | --- |\n"
            )
            for check in checks:
                output.write(
                    f"| {check['name']} | {'OK' if check['ok'] else 'FAILED'} | {check['code']} | {check['durationMs']} ms |\n"
                )
            output.write(
                f"\nTransition: {acknowledgement['transition']}. [Current operational status]({api_url}/api/v1/operations/status).\n"
            )
    return report_exit_code(checks, acknowledgement)


if __name__ == "__main__":
    raise SystemExit(main())
