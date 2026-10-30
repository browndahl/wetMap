from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def age_minutes(value: Any, now: datetime) -> float:
    if not isinstance(value, str):
        raise ValueError("missing timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp lacks timezone")
    return (now - parsed).total_seconds() / 60


def radar_status(manifest: dict, limit: int = 25, now: datetime | None = None) -> dict:
    current = now or datetime.now(timezone.utc)
    try:
        observed_at = manifest["frames"][-1]["observedAt"]
        age = age_minutes(observed_at, current)
        if age < -2:
            raise ValueError("future observation")
    except (KeyError, IndexError, TypeError, ValueError):
        return {
            "ok": False,
            "code": "invalid-manifest",
            "observedAt": None,
            "ageMinutes": None,
        }
    publication_age = float("inf")
    try:
        publication_age = age_minutes(manifest.get("generatedAt"), current)
    except (ValueError, TypeError):
        pass
    return {
        "ok": age <= limit,
        "code": "ok"
        if age <= limit
        else "source-delayed"
        if -2 <= publication_age <= 15
        else "ingestion-stalled",
        "observedAt": observed_at,
        "ageMinutes": round(age, 1),
    }


def managed_source_delay(
    status: dict, monitoring: dict, now: datetime | None = None
) -> bool:
    """Only hand off a source incident already recorded by a live alert owner."""
    current = now or datetime.now(timezone.utc)
    try:
        return bool(
            status["code"] == "source-delayed"
            and monitoring.get("monitoringActive") is True
            and -2 <= age_minutes(monitoring["scheduler"]["checkedAt"], current) <= 10
            and -2 <= age_minutes(monitoring["probe"]["receivedAt"], current) <= 35
            and monitoring["radar"]["observedAt"] == status["observedAt"]
            and "radar:source-delayed"
            in monitoring["activeIncident"]["signature"].split(",")
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("limit_minutes", type=int)
    parser.add_argument("--managed-status-url")
    arguments = parser.parse_args()
    status = radar_status(
        json.loads(arguments.manifest.read_text(encoding="utf-8")),
        arguments.limit_minutes,
    )
    print(json.dumps(status))
    if status["ok"]:
        return 0
    if arguments.managed_status_url and status["code"] == "source-delayed":
        try:
            try:
                response = urllib.request.urlopen(
                    arguments.managed_status_url, timeout=10
                )
            except urllib.error.HTTPError as error:
                if error.code != 503:
                    raise
                response = error
            with response:
                monitoring = json.load(response)
            if managed_source_delay(status, monitoring):
                print(
                    "::warning::Radar remains stale. The active operations incident owns repeated source-delay notifications; service status remains HTTP 503."
                )
                return 0
        except (OSError, ValueError):
            pass
    print(
        f"Radar data is unhealthy: {status['code']} (limit {arguments.limit_minutes} minutes)"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
