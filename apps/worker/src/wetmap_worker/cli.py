from __future__ import annotations

import argparse
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .dmi import DmiClient
from .model import Frame, manifest
from .nowcast import generate_nowcast
from .processor import inspect_odim, process_hdf5
from .storage import (
    download_frames_r2,
    download_manifest_r2,
    download_previous_nowcast_r2,
    upload_nowcast_r2,
    upload_r2,
    write_json_atomic,
)
from .verification import append_verification_history, verify_previous_nowcast


def configure_logs() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")


def run(output: Path, limit: int, upload: bool) -> None:
    output.mkdir(parents=True, exist_ok=True)
    client = DmiClient(os.getenv("DMI_BASE_URL", "https://opendataapi.dmi.dk"))
    existing_path = output / "frames.json"
    if upload and not existing_path.exists():
        download_manifest_r2(existing_path)
    existing = {}
    if existing_path.exists():
        existing = {frame["id"]: frame for frame in json.loads(existing_path.read_text())["frames"]}

    fetched_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    frames: list[Frame] = []
    new_frame_paths: list[Path] = []
    with tempfile.TemporaryDirectory(prefix="wetmap-") as temporary_directory:
        temporary = Path(temporary_directory)
        for item in reversed(client.newest_composites(limit)):
            target = output / f"{item.id}.webp"
            if item.id in existing and (target.exists() or upload):
                frames.append(Frame(**existing[item.id]))
                continue
            hdf5 = temporary / f"{item.id}.h5"
            client.download(item, hdf5)
            processed = process_hdf5(hdf5, target)
            new_frame_paths.append(target)
            frames.append(
                Frame(
                    id=item.id,
                    observedAt=item.observed_at,
                    fetchedAt=fetched_at,
                    url=f"/frames/{target.name}",
                    bounds=processed.bounds,
                    product=processed.product,
                    unit=processed.unit,
                    sha256=processed.sha256,
                )
            )
    frames = sorted(frames, key=lambda frame: frame.observedAt)[-limit:]
    keep = {f"{frame.id}.webp" for frame in frames}
    for old_frame in output.glob("*.webp"):
        if old_frame.name not in keep:
            old_frame.unlink()
    write_json_atomic(existing_path, manifest(frames))

    nowcast_paths: list[Path] = []
    downloaded_source_paths: list[Path] = []
    source_frames = frames[-3:]
    if len(source_frames) >= 2:
        try:
            source_names = [Path(frame.url).name for frame in source_frames]
            if upload:
                source_paths = download_frames_r2(output, source_names)
                new_frame_set = {path.resolve() for path in new_frame_paths}
                downloaded_source_paths = [
                    path for path in source_paths if path.resolve() not in new_frame_set
                ]
            else:
                source_paths = [output / name for name in source_names]
            if all(path.exists() for path in source_paths):
                nowcast_directory = output / "nowcast"
                with tempfile.TemporaryDirectory(prefix="wetmap-previous-nowcast-") as previous:
                    previous_directory = Path(previous)
                    try:
                        if upload and download_previous_nowcast_r2(previous_directory):
                            verification = verify_previous_nowcast(
                                previous_directory / "point-risk.json",
                                previous_directory / "point-risk.bin",
                                source_paths[-1],
                                source_frames[-1].observedAt,
                            )
                            if verification:
                                previous_history = previous_directory / "verification.json"
                                history = append_verification_history(
                                    previous_history, verification
                                )
                                write_json_atomic(nowcast_directory / "verification.json", history)
                    except Exception:
                        # Verification is observability and must not block a fresh nowcast.
                        logging.exception("nowcast.verification.failed")
                nowcast, risk, nowcast_paths = generate_nowcast(
                    source_paths,
                    source_frames,
                    nowcast_directory,
                )
                write_json_atomic(nowcast_directory / "nowcast.json", nowcast)
                write_json_atomic(nowcast_directory / "risk.json", risk)
        except Exception:
            # A derived forecast must never prevent publication of fresh observations.
            logging.exception("nowcast.generation.failed")
    for downloaded_source in downloaded_source_paths:
        downloaded_source.unlink(missing_ok=True)
    if upload:
        upload_r2(output, new_frame_paths)
        if nowcast_paths:
            upload_nowcast_r2(output / "nowcast", nowcast_paths)
    logging.info(
        json.dumps(
            {
                "event": "worker.complete",
                "frames": len(frames),
                "newFrames": len(new_frame_paths),
                "nowcastFrames": len(nowcast_paths),
                "output": str(output),
            }
        )
    )


def main() -> None:
    configure_logs()
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument("--limit", type=int, default=13)
    parser.add_argument("--upload-r2", action="store_true")
    parser.add_argument("--inspect", type=Path)
    arguments = parser.parse_args()
    if arguments.inspect:
        print(json.dumps(inspect_odim(arguments.inspect), indent=2))
        return
    run(arguments.output, max(1, min(arguments.limit, 24)), arguments.upload_r2)


if __name__ == "__main__":
    main()
