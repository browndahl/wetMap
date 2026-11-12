"""Owner-approved cleanup of retired derived images, never verification/history.

Dry-run by default. Both upload time and forecast-valid time must be >48h old;
the current manifest is re-read before each deletion batch. No broad prefix delete.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from .storage import _r2_client

IMAGE = re.compile(r"^nowcast/(?:images/)?dk\.com\.(\d{12})\.500_max-plus-(\d{2})m\.webp$")


def protected_images(client, bucket: str) -> set[str]:
    data = json.loads(client.get_object(Bucket=bucket, Key="nowcast/nowcast.json")["Body"].read())
    frames = data.get("frames")
    if not isinstance(frames, list) or not 1 <= len(frames) <= 13:
        raise ValueError("Missing/invalid active nowcast manifest; refusing deletion")
    keys = set()
    for frame in frames:
        key = urlparse(frame["url"]).path.lstrip("/")
        if not IMAGE.fullmatch(key):
            raise ValueError("Unexpected active image key; refusing deletion")
        keys.add(key)
    return keys


def expired_image(entry: dict, cutoff: datetime) -> bool:
    match = IMAGE.fullmatch(entry.get("Key", ""))
    if not match:
        return False
    lead = int(match[2])
    if lead not in range(5, 61, 5):
        return False
    try:
        valid_at = datetime.strptime(match[1], "%Y%m%d%H%M").replace(
            tzinfo=timezone.utc
        ) + timedelta(minutes=lead)
        uploaded = entry["LastModified"]
        return uploaded.tzinfo is not None and uploaded < cutoff and valid_at < cutoff
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def retire_images(
    client,
    bucket: str,
    *,
    apply: bool = False,
    max_delete: int = 50_000,
    now: datetime | None = None,
) -> dict:
    current = now or datetime.now(timezone.utc)
    cutoff = current - timedelta(hours=48)
    protected = protected_images(client, bucket)
    candidates = []
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix="nowcast/"):
        for entry in page.get("Contents", []):
            if entry["Key"] not in protected and expired_image(entry, cutoff):
                candidates.append(
                    {
                        "key": entry["Key"],
                        "size": entry["Size"],
                        "lastModified": entry["LastModified"].isoformat(),
                    }
                )
    report = {
        "generatedAt": current.isoformat(),
        "cutoff": cutoff.isoformat(),
        "apply": apply,
        "candidateCount": len(candidates),
        "candidateBytes": sum(x["size"] for x in candidates),
        "protectedCount": len(protected),
        "deletedCount": 0,
        "deletedBytes": 0,
        "errors": [],
        "candidates": candidates,
    }
    if not apply:
        return report
    if not 1 <= max_delete <= 100_000 or len(candidates) > max_delete:
        raise ValueError(
            "Candidate count exceeds explicit deletion budget; dry-run and review first"
        )
    for offset in range(0, len(candidates), 500):
        protected = protected_images(client, bucket)
        batch = [item for item in candidates[offset : offset + 500] if item["key"] not in protected]
        if not batch:
            continue
        result = client.delete_objects(
            Bucket=bucket,
            Delete={"Objects": [{"Key": item["key"]} for item in batch], "Quiet": False},
        )
        deleted = {item["Key"] for item in result.get("Deleted", [])}
        report["deletedCount"] += sum(item["key"] in deleted for item in batch)
        report["deletedBytes"] += sum(item["size"] for item in batch if item["key"] in deleted)
        report["errors"].extend(
            {"key": item.get("Key"), "code": item.get("Code")} for item in result.get("Errors", [])
        )
        if len(deleted) + len(result.get("Errors", [])) != len(batch):
            report["errors"].append({"code": "unconfirmed-delete-response"})
        print(
            json.dumps(
                {
                    "event": "retention.progress",
                    "deletedCount": report["deletedCount"],
                    "deletedBytes": report["deletedBytes"],
                }
            )
        )
        if report["errors"]:
            break
    return report


def main() -> int:
    import os

    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--once-per-day", action="store_true")
    parser.add_argument("--max-delete", type=int, default=50_000)
    parser.add_argument("--report", type=Path, required=True)
    arguments = parser.parse_args()
    client = _r2_client()
    bucket = os.environ["R2_BUCKET"]
    current = datetime.now(timezone.utc)
    if arguments.once_per_day:
        from botocore.exceptions import ClientError

        try:
            previous = json.loads(
                client.get_object(Bucket=bucket, Key="maintenance/nowcast-retention.json")[
                    "Body"
                ].read()
            )
            completed = datetime.fromisoformat(previous["completedAt"])
            if timedelta(0) <= current - completed < timedelta(hours=24):
                print(
                    json.dumps(
                        {"event": "retention.skipped", "lastCompletedAt": previous["completedAt"]}
                    )
                )
                return 0
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") not in {"404", "NoSuchKey", "NotFound"}:
                raise
    report = retire_images(
        client,
        bucket,
        apply=arguments.apply,
        max_delete=arguments.max_delete,
    )
    arguments.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if arguments.apply and not report["errors"]:
        client.put_object(
            Bucket=bucket,
            Key="maintenance/nowcast-retention.json",
            Body=json.dumps(
                {
                    "completedAt": current.isoformat(),
                    "deletedCount": report["deletedCount"],
                    "deletedBytes": report["deletedBytes"],
                }
            ).encode(),
            ContentType="application/json",
            CacheControl="no-store",
        )
    print(json.dumps({key: value for key, value in report.items() if key != "candidates"}))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
