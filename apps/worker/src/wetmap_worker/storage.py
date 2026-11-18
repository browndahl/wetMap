from __future__ import annotations

import json
import logging
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
    from botocore.config import Config

    account = os.environ["R2_ACCOUNT_ID"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
        config=Config(
            connect_timeout=5,
            read_timeout=20,
            retries={"mode": "standard", "total_max_attempts": 3},
            max_pool_connections=4,
        ),
    )


def _transfer_config():
    from boto3.s3.transfer import TransferConfig

    # R2 ledger writes used to fan out into ten multipart threads with 60-second
    # socket retries, exhausting the eight-minute workflow. Preserve exact JSON
    # bytes/keys but use a single PUT for ordinary ledgers and bounded concurrency
    # for genuinely large transfers. Never truncate history to solve a timeout.
    return TransferConfig(
        multipart_threshold=128 * 1024 * 1024,
        multipart_chunksize=16 * 1024 * 1024,
        max_concurrency=2,
        # Successful-HTTP body/socket failures otherwise retry five times in a
        # second loop outside botocore's API budget, blocking the live pipeline.
        # Keep API throttling/5xx retries, but don't restart a broken stream here.
        num_download_attempts=1,
        preferred_transfer_client="classic",
    )


def download_manifest_r2(destination: Path) -> bool:
    """Seed a stateless run with the last manifest, if one exists."""
    from botocore.exceptions import ClientError

    temporary = destination.with_suffix(".download")
    try:
        _r2_client().download_file(
            os.environ["R2_BUCKET"], "frames/frames.json", str(temporary), Config=_transfer_config()
        )
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
            client.download_file(
                bucket, f"frames/{name}", str(temporary), Config=_transfer_config()
            )
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
            temporary = (destination / name).with_suffix(".download")
            client.download_file(bucket, key, str(temporary), Config=_transfer_config())
            temporary.replace(destination / name)
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
    _r2_client().download_file(
        os.environ["R2_BUCKET"], data_key, str(target), Config=_transfer_config()
    )
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
            Config=_transfer_config(),
            ExtraArgs={
                "ContentType": "image/webp",
                "CacheControl": "public,max-age=31536000,immutable",
            },
        )
    client.upload_file(
        str(output_directory / "frames.json"),
        bucket,
        "frames/frames.json",
        Config=_transfer_config(),
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
    from botocore.exceptions import ClientError

    point_metadata_path = nowcast_directory / "point-risk.json"
    point_metadata = json.loads(point_metadata_path.read_text())
    proposed_key = point_metadata.get("dataKey", "nowcast/point-risk-0.bin")
    if not isinstance(proposed_key, str) or not re.fullmatch(
        r"nowcast/point-risk-[01]\.bin", proposed_key
    ):
        raise ValueError("Invalid point-grid output key")
    try:
        previous = client.get_object(Bucket=bucket, Key="nowcast/point-risk.json")
        with previous["Body"] as body:
            previous_bytes = body.read(65_537)
        if len(previous_bytes) > 65_536:
            raise ValueError("Point-grid pointer exceeds metadata budget")
        previous_metadata = json.loads(previous_bytes)
        active_key = previous_metadata.get("dataKey", "nowcast/point-risk.bin")
        if active_key not in (
            "nowcast/point-risk-0.bin",
            "nowcast/point-risk-1.bin",
            "nowcast/point-risk.bin",
        ):
            raise ValueError("Invalid active point-grid key")
        # Observation parity does not alternate when ingestion skips a scan.
        # Choose against the actual pointer, never overwrite its active bytes.
        proposed_key = (
            "nowcast/point-risk-1.bin"
            if active_key == "nowcast/point-risk-0.bin"
            else "nowcast/point-risk-0.bin"
        )
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") not in {"404", "NoSuchKey", "NotFound"}:
            raise
    for frame in frame_paths:
        client.upload_file(
            str(frame),
            bucket,
            f"nowcast/{frame.name}",
            Config=_transfer_config(),
            ExtraArgs={"ContentType": "image/webp", "CacheControl": "public,max-age=300"},
        )
    with (nowcast_directory / "point-risk.bin").open("rb") as point_data:
        uploaded = client.put_object(
            Bucket=bucket,
            Key=proposed_key,
            Body=point_data,
            ContentType="application/octet-stream",
            CacheControl="no-cache",
        )
    etag = uploaded.get("ETag", "").strip('"')
    if not re.fullmatch(r"[a-fA-F0-9]{32}(?:-\d+)?", etag):
        raise ValueError("Point-grid upload returned no usable object version")
    point_metadata.update(schemaVersion=2, dataKey=proposed_key, dataEtag=etag)
    write_json_atomic(point_metadata_path, point_metadata)
    verification_forecast_path = nowcast_directory / "verification-forecast.json"
    verification_cube_path = nowcast_directory / "verification-cube.npz"
    if (
        upload_verification
        and verification_forecast_path.exists()
        and verification_cube_path.exists()
    ):
        verification_forecast = json.loads(verification_forecast_path.read_text(encoding="utf-8"))
        client.upload_file(
            str(verification_cube_path),
            bucket,
            verification_forecast["dataKey"],
            Config=_transfer_config(),
            ExtraArgs={
                "ContentType": "application/octet-stream",
                "CacheControl": "no-store",
            },
        )
    metadata_names = ["nowcast.json", "risk.json", "point-risk.json", "consistency.json"]
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
            Config=_transfer_config(),
            ExtraArgs={
                "ContentType": "application/json",
                "CacheControl": "public,max-age=60,stale-while-revalidate=300",
            },
        )
    logging.getLogger(__name__).info("point-grid.published version-bound=true")
