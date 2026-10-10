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
from .processor import inspect_odim, process_hdf5
from .storage import download_manifest_r2, upload_r2, write_json_atomic


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
    if upload:
        upload_r2(output, new_frame_paths)
    logging.info(json.dumps({
        "event": "worker.complete",
        "frames": len(frames),
        "newFrames": len(new_frame_paths),
        "output": str(output),
    }))


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
