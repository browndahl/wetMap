from __future__ import annotations

import argparse
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .dmi import DmiClient
from .gauges import (
    append_gauge_history,
    compare_radar_to_gauges,
    fetch_recent_gauge_observations,
    public_gauge_report,
)
from .model import Frame, manifest
from .nowcast import generate_nowcast
from .processor import inspect_odim, process_hdf5
from .storage import (
    download_frames_r2,
    download_manifest_r2,
    download_verification_cube_r2,
    download_verification_r2,
    upload_nowcast_r2,
    upload_r2,
    write_json_atomic,
)
from .verification import (
    append_verification_history,
    public_verification_report,
    quality_by_lead,
    update_verification_state,
    verification_candidates,
    verify_previous_nowcast,
)


def configure_logs() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")


def operational_radar_calibration(
    gauge_history: dict | None,
    verification_history: dict | None,
) -> tuple[int, int]:
    calibration = (gauge_history or {}).get("calibration", {})
    recommended_threshold = calibration.get("recommendedThresholdDbz")
    recommended_radius = calibration.get("recommendedSpatialRadiusPixels")
    threshold_observatory = next(
        (
            entry
            for entry in (verification_history or {}).get("observatoryByThresholdDbz", [])
            if entry.get("thresholdDbz") == recommended_threshold
        ),
        None,
    )
    forecast_quality_status = (
        threshold_observatory.get("overallStatus", "collecting")
        if threshold_observatory
        else "collecting"
    )
    promote = bool(
        calibration.get("safeToPromote")
        and recommended_threshold in (5, 10, 15, 20)
        and recommended_radius in (1, 3, 5)
        and forecast_quality_status == "verified"
    )
    threshold = int(recommended_threshold if promote else 20)
    radius = int(recommended_radius if promote else 1)
    if calibration:
        calibration["forecastQualityStatus"] = forecast_quality_status
        calibration["appliedThresholdDbz"] = threshold
        calibration["appliedSpatialRadiusPixels"] = radius
    return threshold, radius


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
    upload_verification_assets = False
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
                previous_state: dict = {}
                full_history: dict | None = None
                gauge_history: dict | None = None
                verification_results_added = False
                gauge_result_added = False
                with tempfile.TemporaryDirectory(prefix="wetmap-previous-nowcast-") as previous:
                    previous_directory = Path(previous)
                    if upload:
                        try:
                            download_verification_r2(previous_directory)
                            state_path = previous_directory / "verification-state.json"
                            if state_path.exists():
                                previous_state = json.loads(state_path.read_text(encoding="utf-8"))
                            history_path = previous_directory / "verification-history.json"
                            if not history_path.exists():
                                history_path = previous_directory / "verification.json"
                            if history_path.exists():
                                full_history = append_verification_history(history_path, [])
                            verified_pairs = {
                                (
                                    entry.get("basedOnObservedAt"),
                                    entry.get("observedAt"),
                                )
                                for entry in (full_history or {}).get("results", [])
                            }
                            verifications: list[dict] = []
                            for candidate in verification_candidates(
                                previous_state, source_frames[-1].observedAt
                            ):
                                if (
                                    candidate.get("basedOnObservedAt"),
                                    source_frames[-1].observedAt,
                                ) in verified_pairs:
                                    continue
                                try:
                                    cube_path = download_verification_cube_r2(
                                        previous_directory, candidate["dataKey"]
                                    )
                                    verification = verify_previous_nowcast(
                                        candidate,
                                        cube_path,
                                        source_paths[-1],
                                        source_frames[-1].observedAt,
                                    )
                                    if verification:
                                        verifications.append(verification)
                                except Exception:
                                    logging.exception(
                                        "nowcast.verification.candidate.failed",
                                        extra={
                                            "basedOnObservedAt": candidate.get("basedOnObservedAt")
                                        },
                                    )
                            if verifications:
                                verification_results_added = True
                                full_history = append_verification_history(
                                    history_path, verifications
                                )
                        except Exception:
                            # Verification is observability and must not block fresh radar.
                            logging.exception("nowcast.verification.failed")
                        gauge_history_path = previous_directory / "gauge-verification-history.json"
                        if gauge_history_path.exists():
                            try:
                                gauge_history = json.loads(
                                    gauge_history_path.read_text(encoding="utf-8")
                                )
                            except json.JSONDecodeError:
                                gauge_history = None
                        gauge_already_verified = any(
                            entry.get("radarObservedAt") == source_frames[-1].observedAt
                            for entry in (gauge_history or {}).get("results", [])
                        )
                        if not gauge_already_verified:
                            try:
                                gauge_result = compare_radar_to_gauges(
                                    fetch_recent_gauge_observations(
                                        os.getenv(
                                            "DMI_METOBS_URL",
                                            "https://opendataapi.dmi.dk/v2/metObs/collections/observation/items",
                                        )
                                    ),
                                    source_paths[-1],
                                    source_frames[-1].observedAt,
                                    source_frames[-1].bounds,
                                    radar_frames=list(
                                        zip(
                                            source_paths,
                                            (frame.observedAt for frame in source_frames),
                                            strict=True,
                                        )
                                    ),
                                )
                                gauge_history = append_gauge_history(
                                    gauge_history_path,
                                    gauge_result,
                                )
                                gauge_result_added = True
                            except Exception:
                                # Raw station data is secondary and cannot block radar.
                                logging.exception("radar.gauge-verification.failed")
                rain_threshold_dbz, rain_radius_pixels = operational_radar_calibration(
                    gauge_history, full_history
                )
                nowcast, risk, nowcast_paths = generate_nowcast(
                    source_paths,
                    source_frames,
                    nowcast_directory,
                    quality_by_lead(full_history, rain_threshold_dbz),
                    rain_threshold_dbz=rain_threshold_dbz,
                    rain_radius_pixels=rain_radius_pixels,
                )
                write_json_atomic(nowcast_directory / "nowcast.json", nowcast)
                write_json_atomic(nowcast_directory / "risk.json", risk)
                verification_forecast_path = nowcast_directory / "verification-forecast.json"
                if verification_forecast_path.exists():
                    verification_forecast = json.loads(
                        verification_forecast_path.read_text(encoding="utf-8")
                    )
                    verification_state = update_verification_state(
                        previous_state, verification_forecast
                    )
                    is_new_forecast = not any(
                        entry.get("basedOnObservedAt") == verification_forecast["basedOnObservedAt"]
                        for entry in previous_state.get("forecasts", [])
                    )
                    upload_verification_assets = (
                        is_new_forecast or verification_results_added or gauge_result_added
                    )
                    write_json_atomic(
                        nowcast_directory / "verification-state.json",
                        verification_state,
                    )
                if gauge_history:
                    write_json_atomic(
                        nowcast_directory / "gauge-verification-history.json",
                        gauge_history,
                    )
                if full_history or gauge_history:
                    if not full_history:
                        full_history = append_verification_history(
                            nowcast_directory / "verification-history.json", []
                        )
                    write_json_atomic(nowcast_directory / "verification-history.json", full_history)
                    public_report = public_verification_report(full_history)
                    if gauge_history:
                        public_report["groundGauge"] = public_gauge_report(gauge_history)
                    consistency_path = nowcast_directory / "consistency.json"
                    if consistency_path.exists():
                        public_report["geographicConsistency"] = json.loads(
                            consistency_path.read_text(encoding="utf-8")
                        )
                    write_json_atomic(
                        nowcast_directory / "verification.json",
                        public_report,
                    )
        except Exception:
            # A derived forecast must never prevent publication of fresh observations.
            logging.exception("nowcast.generation.failed")
    for downloaded_source in downloaded_source_paths:
        downloaded_source.unlink(missing_ok=True)
    if upload:
        upload_r2(output, new_frame_paths)
        if nowcast_paths:
            upload_nowcast_r2(
                output / "nowcast",
                nowcast_paths,
                upload_verification_assets,
            )
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
