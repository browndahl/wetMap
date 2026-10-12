from __future__ import annotations

import json
import os
import re
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


def download_verification_r2(destination: Path) -> bool:
    """Download the compact verification ledger and pending forecast state."""
    from botocore.exceptions import ClientError

    destination.mkdir(parents=True, exist_ok=True)
    client = _r2_client()
    bucket = os.environ["R2_BUCKET"]
    downloaded = False
    for key, name in (
        ("nowcast/verification-state.json", "verification-state.json"),
        ("nowcast/verification-history.json", "verification-history.json"),
        ("nowcast/verification.json", "verification.json"),
        ("nowcast/gauge-verification-history.json", "gauge-verification-history.json"),
    ):
        try:
            client.download_file(bucket, key, str(destination / name))
            downloaded = True
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in {
                "404",
                "NoSuchKey",
                "NotFound",
            }:
                continue
            raise
    return downloaded


def download_verification_cube_r2(destination: Path, data_key: str) -> Path:
    """Download one bounded ring-buffer cube referenced by verified state."""
    if not re.fullmatch(r"nowcast/verification-cubes/cube-\d{2}\.npz", data_key):
        raise ValueError("Invalid verification cube key")
    target = destination / Path(data_key).name
    _r2_client().download_file(os.environ["R2_BUCKET"], data_key, str(target))
    return target


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


def upload_nowcast_r2(
    nowcast_directory: Path,
    frame_paths: Iterable[Path],
    upload_verification: bool = True,
) -> None:
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
    verification_forecast_path = nowcast_directory / "verification-forecast.json"
    verification_cube_path = nowcast_directory / "verification-cube.npz"
    if (
        upload_verification
        and verification_forecast_path.exists()
        and verification_cube_path.exists()
    ):
        verification_forecast = json.loads(
            verification_forecast_path.read_text(encoding="utf-8")
        )
        client.upload_file(
            str(verification_cube_path),
            bucket,
            verification_forecast["dataKey"],
            ExtraArgs={
                "ContentType": "application/octet-stream",
                "CacheControl": "no-store",
            },
        )
    metadata_names = ["nowcast.json", "risk.json", "point-risk.json"]
    for optional_name in (
        "verification.json",
        "verification-history.json",
        "verification-state.json",
        "gauge-verification-history.json",
    ):
        if upload_verification and (nowcast_directory / optional_name).exists():
            metadata_names.append(optional_name)
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
