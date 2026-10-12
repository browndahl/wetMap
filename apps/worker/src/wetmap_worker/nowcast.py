from __future__ import annotations

import base64
import hashlib
import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from .model import ATTRIBUTION, Frame

METHOD = "adaptive-optical-flow-persistence"
LEAD_MINUTES = tuple(range(5, 61, 5))
RISK_WIDTH = 128
RISK_HEIGHT = 96
POINT_GRID_WIDTH = 768
POINT_GRID_HEIGHT = 512
VERIFICATION_GRID_WIDTH = 256
VERIFICATION_GRID_HEIGHT = 171
VERIFICATION_RING_SLOTS = 16


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _radar_signal(rgba: np.ndarray) -> np.ndarray:
    """Return the monotonic reflectivity signal encoded in frame alpha."""
    return cv2.GaussianBlur(rgba[..., 3], (5, 5), 0)


def _dense_motion(images: list[np.ndarray], intervals_minutes: list[float]) -> np.ndarray:
    height, width = images[-1].shape[:2]
    scale = min(1.0, 700 / max(height, width))
    signals = [
        cv2.resize(
            _radar_signal(image),
            (max(2, round(width * scale)), max(2, round(height * scale))),
            interpolation=cv2.INTER_AREA,
        )
        for image in images
    ]
    flows_per_minute = [
        cv2.calcOpticalFlowFarneback(
            previous,
            current,
            None,
            0.5,
            4,
            21,
            4,
            7,
            1.5,
            0,
        )
        / interval
        for previous, current, interval in zip(
            signals[:-1], signals[1:], intervals_minutes, strict=True
        )
    ]
    flow = np.mean(flows_per_minute, axis=0)
    if scale != 1:
        flow = cv2.resize(flow, (width, height), interpolation=cv2.INTER_LINEAR) / scale
    flow[..., 0] = cv2.GaussianBlur(flow[..., 0], (21, 21), 0)
    flow[..., 1] = cv2.GaussianBlur(flow[..., 1], (21, 21), 0)
    # Reject implausible per-minute vectors caused by isolated noise or frame edges.
    return np.clip(flow, -10, 10).astype(np.float32)


def _advect(rgba: np.ndarray, flow: np.ndarray, steps: float) -> np.ndarray:
    height, width = rgba.shape[:2]
    x, y = np.meshgrid(
        np.arange(width, dtype=np.float32),
        np.arange(height, dtype=np.float32),
    )
    return cv2.remap(
        rgba,
        x - flow[..., 0] * steps,
        y - flow[..., 1] * steps,
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )


def _risk_bucket(alpha: np.ndarray) -> str:
    reduced = cv2.resize(alpha, (RISK_WIDTH, RISK_HEIGHT), interpolation=cv2.INTER_AREA)
    categories = np.zeros(reduced.shape, dtype=np.uint8)
    # Processor alpha is monotonic in dBZ: these are approximately 0, 10 and 20 dBZ.
    categories[reduced >= 74] = 1
    categories[reduced >= 103] = 2
    categories[reduced >= 133] = 3
    return base64.b64encode(categories.tobytes()).decode("ascii")


def _reflectivity_grid(
    alpha: np.ndarray,
    width: int = POINT_GRID_WIDTH,
    height: int = POINT_GRID_HEIGHT,
) -> np.ndarray:
    """Encode dBZ + 32; zero is no coverage and 14 is covered/no echo."""
    reduced = cv2.resize(
        alpha,
        (width, height),
        interpolation=cv2.INTER_AREA,
    )
    dbz = np.rint((reduced.astype(np.float32) - 45) * (60 / 175) - 10)
    detected = reduced >= 44
    return np.where(
        detected,
        np.clip(dbz + 32, 1, 95),
        np.where(reduced > 0, 14, 0),
    ).astype(np.uint8)


def generate_nowcast(
    source_paths: list[Path],
    source_frames: list[Frame],
    output_directory: Path,
    quality_by_lead: dict[int, dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], list[Path]]:
    if len(source_paths) < 2 or len(source_paths) != len(source_frames):
        raise ValueError("Nowcast requires at least two matching radar frames")

    images = [np.asarray(Image.open(path).convert("RGBA")) for path in source_paths]
    if any(image.shape != images[-1].shape for image in images):
        raise ValueError("Nowcast source frames must have identical dimensions")
    latest = images[-1]
    latest_frame = source_frames[-1]
    latest_time = _parse_time(latest_frame.observedAt)
    observation_times = [_parse_time(frame.observedAt) for frame in source_frames]
    intervals_minutes = [
        max(1.0, (current - previous).total_seconds() / 60)
        for previous, current in zip(observation_times[:-1], observation_times[1:], strict=True)
    ]
    flow = _dense_motion(images, intervals_minutes)
    generated_at = datetime.now(latest_time.tzinfo).isoformat().replace("+00:00", "Z")
    output_directory.mkdir(parents=True, exist_ok=True)

    frame_entries: list[dict[str, Any]] = []
    latest_prediction_time = latest_time.isoformat().replace("+00:00", "Z")
    risk_entries: list[dict[str, Any]] = [
        {
            "leadMinutes": 0,
            "predictedAt": latest_prediction_time,
            "intensity": _risk_bucket(latest[..., 3]),
        }
    ]
    point_frames = [_reflectivity_grid(latest[..., 3])]
    verification_frames = [
        _reflectivity_grid(
            latest[..., 3], VERIFICATION_GRID_WIDTH, VERIFICATION_GRID_HEIGHT
        )
    ]
    point_frame_entries: list[dict[str, Any]] = [
        {
            "leadMinutes": 0,
            "predictedAt": latest_prediction_time,
            "confidence": 1.0,
        }
    ]
    output_paths: list[Path] = []
    for lead_minutes in LEAD_MINUTES:
        optical_flow_prediction = _advect(latest, flow, lead_minutes)
        quality = (quality_by_lead or {}).get(lead_minutes, {})
        validation_samples = int(
            quality.get("opticalFlowSampleCount", quality.get("sampleCount", 0)) or 0
        )
        skill = quality.get(
            "opticalFlowMeanCriticalSuccessIndexSkill",
            quality.get("meanCriticalSuccessIndexSkill"),
        )
        use_persistence = (
            validation_samples >= 12
            and isinstance(skill, (int, float))
            and skill <= -0.02
        )
        raw_prediction = latest.copy() if use_persistence else optical_flow_prediction
        forecast_method = "persistence" if use_persistence else "optical-flow"
        heuristic_confidence = max(0.25, math.exp(-lead_minutes / 75))
        if use_persistence:
            verified_csi = quality.get(
                "persistenceCriticalSuccessIndex",
                quality.get(
                    "meanPersistenceCriticalSuccessIndex",
                    quality.get("criticalSuccessIndex"),
                ),
            )
        else:
            verified_csi = quality.get(
                "opticalFlowCriticalSuccessIndex",
                quality.get("criticalSuccessIndex"),
            )
        if validation_samples >= 6 and isinstance(verified_csi, (int, float)):
            empirical_confidence = min(0.95, max(0.2, 0.2 + 0.75 * verified_csi))
            empirical_weight = min(0.8, validation_samples / 60)
            confidence = (
                heuristic_confidence * (1 - empirical_weight)
                + empirical_confidence * empirical_weight
            )
        else:
            confidence = heuristic_confidence
        confidence = round(min(0.95, max(0.2, confidence)), 2)
        risk_entries.append(
            {
                "leadMinutes": lead_minutes,
                "predictedAt": (latest_time + timedelta(minutes=lead_minutes))
                .isoformat()
                .replace("+00:00", "Z"),
                "intensity": _risk_bucket(raw_prediction[..., 3]),
            }
        )
        point_frames.append(_reflectivity_grid(raw_prediction[..., 3]))
        verification_frames.append(
            _reflectivity_grid(
                raw_prediction[..., 3],
                VERIFICATION_GRID_WIDTH,
                VERIFICATION_GRID_HEIGHT,
            )
        )
        identifier = f"{latest_frame.id}-plus-{lead_minutes:02d}m"
        target = output_directory / f"{identifier}.webp"
        # Confidence is metadata. It must never attenuate measured/predicted dBZ,
        # otherwise the map and point forecast would disagree about intensity.
        Image.fromarray(raw_prediction).save(target, "WEBP", lossless=True, method=6)
        output_paths.append(target)
        frame_entries.append(
            {
                "id": identifier,
                "predictedAt": risk_entries[-1]["predictedAt"],
                "generatedAt": generated_at,
                "basedOnObservedAt": latest_frame.observedAt,
                "leadMinutes": lead_minutes,
                "url": f"/nowcast/{target.name}",
                "bounds": latest_frame.bounds,
                "product": "DBZH_NOWCAST",
                "unit": "dBZ",
                "confidence": confidence,
                "forecastMethod": forecast_method,
                "validationSamples": validation_samples,
                "verificationCsi": verified_csi,
                "skillOverPersistence": skill,
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            }
        )
        point_frame_entries.append(
            {
                "leadMinutes": lead_minutes,
                "predictedAt": risk_entries[-1]["predictedAt"],
                "confidence": confidence,
                "forecastMethod": forecast_method,
                "validationSamples": validation_samples,
            }
        )

    manifest = {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "attribution": ATTRIBUTION,
        "method": METHOD,
        "basedOnObservedAt": latest_frame.observedAt,
        "sourceFrameCount": len(source_frames),
        "frames": frame_entries,
    }
    risk = {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "basedOnObservedAt": latest_frame.observedAt,
        "method": METHOD,
        "bounds": latest_frame.bounds,
        "width": RISK_WIDTH,
        "height": RISK_HEIGHT,
        "encoding": "uint8-base64",
        "thresholdsDbz": [0, 10, 20],
        "frames": risk_entries,
    }
    point_cube = np.stack(point_frames, axis=-1)
    point_grid_path = output_directory / "point-risk.bin"
    point_grid_path.write_bytes(point_cube.tobytes(order="C"))
    point_grid = {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "basedOnObservedAt": latest_frame.observedAt,
        "method": METHOD,
        "bounds": latest_frame.bounds,
        "width": POINT_GRID_WIDTH,
        "height": POINT_GRID_HEIGHT,
        "frameCount": len(point_frame_entries),
        "encoding": "pixel-major-uint8-dbz-plus-32",
        "dataKey": f"nowcast/point-risk-{int(latest_time.timestamp() // 300) % 2}.bin",
        "neighborhoodRadiusPixels": 1,
        "frames": point_frame_entries,
        "sha256": hashlib.sha256(point_grid_path.read_bytes()).hexdigest(),
    }
    (output_directory / "point-risk.json").write_text(
        json.dumps(point_grid, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    verification_cube_path = output_directory / "verification-cube.npz"
    np.savez_compressed(
        verification_cube_path,
        cube=np.stack(verification_frames, axis=-1),
    )
    verification_slot = int(latest_time.timestamp() // 300) % VERIFICATION_RING_SLOTS
    verification_forecast = {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "basedOnObservedAt": latest_frame.observedAt,
        "method": METHOD,
        "bounds": latest_frame.bounds,
        "width": VERIFICATION_GRID_WIDTH,
        "height": VERIFICATION_GRID_HEIGHT,
        "frameCount": len(point_frame_entries),
        "encoding": "npz-pixel-major-uint8-dbz-plus-32",
        "dataKey": f"nowcast/verification-cubes/cube-{verification_slot:02d}.npz",
        "frames": point_frame_entries,
        "sha256": hashlib.sha256(verification_cube_path.read_bytes()).hexdigest(),
    }
    (output_directory / "verification-forecast.json").write_text(
        json.dumps(verification_forecast, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    return manifest, risk, output_paths
