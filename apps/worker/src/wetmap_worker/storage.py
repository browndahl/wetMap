from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    temporary.replace(path)


def _r2_client():
    import boto3

    account = os.environ["R2_ACCOUNT_ID"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def download_manifest_r2(destination: Path) -> bool:
    """Seed a stateless run with the last manifest, if one exists."""
    from botocore.exceptions import ClientError

    temporary = destination.with_suffix(".download")
    try:
        _r2_client().download_file(os.environ["R2_BUCKET"], "frames/frames.json", str(temporary))
    except ClientError as error:
        temporary.unlink(missing_ok=True)
        if error.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise
    temporary.replace(destination)
    return True


def download_frames_r2(output_directory: Path, frame_names: Iterable[str]) -> list[Path]:
    """Download processed source frames needed for a stateless nowcast run."""
    bucket = os.environ["R2_BUCKET"]
    client = _r2_client()
    downloaded: list[Path] = []
    for name in frame_names:
        destination = output_directory / name
        if not destination.exists():
            temporary = destination.with_suffix(".download")
            client.download_file(bucket, f"frames/{name}", str(temporary))
            temporary.replace(destination)
        downloaded.append(destination)
    return downloaded


def download_previous_nowcast_r2(destination: Path) -> bool:
    """Download the prior point nowcast and optional verification history."""
    from botocore.exceptions import ClientError

    destination.mkdir(parents=True, exist_ok=True)
    client = _r2_client()
    bucket = os.environ["R2_BUCKET"]
    metadata_path = destination / "point-risk.json"
    try:
        client.download_file(bucket, "nowcast/point-risk.json", str(metadata_path))
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") in {
            "404",
            "NoSuchKey",
            "NotFound",
        }:
            return False
        raise
    point_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    data_key = point_metadata.get("dataKey", "nowcast/point-risk.bin")
    for key, name, required in (
        (data_key, "point-risk.bin", True),
        ("nowcast/verification.json", "verification.json", False),
    ):
        try:
            client.download_file(bucket, key, str(destination / name))
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in {
                "404",
                "NoSuchKey",
                "NotFound",
            }:
                if required:
                    return False
                continue
            raise
    return (destination / "point-risk.bin").exists()


def upload_r2(output_directory: Path, frame_paths: Iterable[Path] | None = None) -> None:
    """Upload the immutable frames first and the short-lived manifest last."""
    bucket = os.environ["R2_BUCKET"]
    client = _r2_client()
    frames = frame_paths if frame_paths is not None else output_directory.glob("*.webp")
    for frame in frames:
        client.upload_file(
            str(frame),
            bucket,
            f"frames/{frame.name}",
            ExtraArgs={
                "ContentType": "image/webp",
                "CacheControl": "public,max-age=31536000,immutable",
            },
        )
    client.upload_file(
        str(output_directory / "frames.json"),
        bucket,
        "frames/frames.json",
        ExtraArgs={
            "ContentType": "application/json",
            "CacheControl": "public,max-age=60,stale-while-revalidate=300",
        },
    )


def upload_nowcast_r2(nowcast_directory: Path, frame_paths: Iterable[Path]) -> None:
    """Replace short-lived nowcast assets, publishing manifests last."""
    bucket = os.environ["R2_BUCKET"]
    client = _r2_client()
    for frame in frame_paths:
        client.upload_file(
            str(frame),
            bucket,
            f"nowcast/{frame.name}",
            ExtraArgs={"ContentType": "image/webp", "CacheControl": "public,max-age=300"},
        )
    point_metadata = json.loads((nowcast_directory / "point-risk.json").read_text())
    client.upload_file(
        str(nowcast_directory / "point-risk.bin"),
        bucket,
        point_metadata["dataKey"],
        ExtraArgs={
            "ContentType": "application/octet-stream",
            "CacheControl": "no-cache",
        },
    )
    metadata_names = ["nowcast.json", "risk.json", "point-risk.json"]
    if (nowcast_directory / "verification.json").exists():
        metadata_names.append("verification.json")
    for name in metadata_names:
        client.upload_file(
            str(nowcast_directory / name),
            bucket,
            f"nowcast/{name}",
            ExtraArgs={
                "ContentType": "application/json",
                "CacheControl": "public,max-age=60,stale-while-revalidate=300",
            },
        )
