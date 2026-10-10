from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)


def upload_r2(output_directory: Path) -> None:
    """Upload the immutable frames first and the short-lived manifest last."""
    import boto3

    account = os.environ["R2_ACCOUNT_ID"]
    bucket = os.environ["R2_BUCKET"]
    client = boto3.client(
        "s3",
        endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    for frame in output_directory.glob("*.webp"):
        client.upload_file(
            str(frame), bucket, f"frames/{frame.name}",
            ExtraArgs={"ContentType": "image/webp", "CacheControl": "public,max-age=31536000,immutable"},
        )
    client.upload_file(
        str(output_directory / "frames.json"), bucket, "frames/frames.json",
        ExtraArgs={"ContentType": "application/json", "CacheControl": "public,max-age=60,stale-while-revalidate=300"},
    )
