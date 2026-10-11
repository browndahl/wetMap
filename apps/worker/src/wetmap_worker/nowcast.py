from __future__ import annotations

import base64
import hashlib
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from .model import ATTRIBUTION, Frame

METHOD = "dense-optical-flow-extrapolation"
LEAD_MINUTES = tuple(range(5, 61, 5))
RISK_WIDTH = 128
RISK_HEIGHT = 96


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
    categories[reduced >= 94] = 1
    categories[reduced >= 146] = 2
    categories[reduced >= 198] = 3
    return base64.b64encode(categories.tobytes()).decode("ascii")


def generate_nowcast(
    source_paths: list[Path],
    source_frames: list[Frame],
    output_directory: Path,
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
    risk_entries: list[dict[str, Any]] = []
    output_paths: list[Path] = []
    for lead_minutes in LEAD_MINUTES:
        raw_prediction = _advect(latest, flow, lead_minutes)
        risk_entries.append(
            {
                "leadMinutes": lead_minutes,
                "predictedAt": (latest_time + timedelta(minutes=lead_minutes))
                .isoformat()
                .replace("+00:00", "Z"),
                "intensity": _risk_bucket(raw_prediction[..., 3]),
            }
        )
        prediction = raw_prediction.copy()
        confidence = max(0.25, math.exp(-lead_minutes / 75))
        prediction[..., 3] = np.rint(prediction[..., 3] * confidence).astype(np.uint8)
        identifier = f"{latest_frame.id}-plus-{lead_minutes:02d}m"
        target = output_directory / f"{identifier}.webp"
        Image.fromarray(prediction).save(target, "WEBP", lossless=True, method=6)
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
                "confidence": round(confidence, 2),
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
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
    return manifest, risk, output_paths
