from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .nowcast import _parse_time, _reflectivity_grid

SIGNIFICANT_ECHO_DBZ = 20
SIGNIFICANT_ECHO_ENCODED = SIGNIFICANT_ECHO_DBZ + 32


def verify_previous_nowcast(
    metadata_path: Path,
    cube_path: Path,
    observed_frame_path: Path,
    observed_at: str,
) -> dict[str, Any] | None:
    """Score the old point nowcast against the newly arrived observation."""
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    frames = metadata.get("frames", [])
    if not frames or metadata.get("encoding") != "pixel-major-uint8-dbz-plus-32":
        return None
    observed_time = _parse_time(observed_at)
    candidate_index, candidate = min(
        enumerate(frames),
        key=lambda item: abs((_parse_time(item[1]["predictedAt"]) - observed_time).total_seconds()),
    )
    offset_seconds = abs((_parse_time(candidate["predictedAt"]) - observed_time).total_seconds())
    if offset_seconds > 180 or candidate.get("leadMinutes", 0) <= 0:
        return None

    width = int(metadata["width"])
    height = int(metadata["height"])
    frame_count = int(metadata["frameCount"])
    cube_bytes = cube_path.read_bytes()
    if metadata.get("sha256") and hashlib.sha256(cube_bytes).hexdigest() != metadata["sha256"]:
        raise ValueError("Previous point nowcast checksum mismatch")
    cube = np.frombuffer(cube_bytes, dtype=np.uint8)
    if cube.size != width * height * frame_count:
        raise ValueError("Previous point nowcast has an unexpected size")
    predicted = cube.reshape(height, width, frame_count)[..., candidate_index]
    observed_rgba = np.asarray(Image.open(observed_frame_path).convert("RGBA"))
    actual = _reflectivity_grid(observed_rgba[..., 3])
    if actual.shape != predicted.shape:
        raise ValueError("Observed and predicted point grids have different dimensions")

    valid = (predicted > 0) & (actual > 0)
    predicted_echo = (predicted >= SIGNIFICANT_ECHO_ENCODED) & valid
    actual_echo = (actual >= SIGNIFICANT_ECHO_ENCODED) & valid
    hits = int(np.count_nonzero(predicted_echo & actual_echo))
    misses = int(np.count_nonzero(~predicted_echo & actual_echo & valid))
    false_alarms = int(np.count_nonzero(predicted_echo & ~actual_echo & valid))
    correct_negatives = int(np.count_nonzero(~predicted_echo & ~actual_echo & valid))
    union = hits + misses + false_alarms
    echo_pixels = valid & (predicted_echo | actual_echo)
    dbz_mae = (
        float(np.mean(np.abs(predicted[echo_pixels].astype(float) - actual[echo_pixels])))
        if np.any(echo_pixels)
        else 0.0
    )

    def ratio(numerator: int, denominator: int) -> float | None:
        return round(numerator / denominator, 4) if denominator else None

    return {
        "verifiedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "basedOnObservedAt": metadata["basedOnObservedAt"],
        "predictedAt": candidate["predictedAt"],
        "observedAt": observed_at,
        "leadMinutes": candidate["leadMinutes"],
        "thresholdDbz": SIGNIFICANT_ECHO_DBZ,
        "validPixels": int(np.count_nonzero(valid)),
        "hits": hits,
        "misses": misses,
        "falseAlarms": false_alarms,
        "correctNegatives": correct_negatives,
        "precision": ratio(hits, hits + false_alarms),
        "recall": ratio(hits, hits + misses),
        "criticalSuccessIndex": ratio(hits, union),
        "dbzMeanAbsoluteError": round(dbz_mae, 2),
    }


def append_verification_history(
    history_path: Path,
    result: dict[str, Any],
    maximum_entries: int = 288,
) -> dict[str, Any]:
    history: list[dict[str, Any]] = []
    if history_path.exists():
        try:
            history = json.loads(history_path.read_text(encoding="utf-8")).get("results", [])
        except (json.JSONDecodeError, AttributeError):
            history = []
    history = [entry for entry in history if entry.get("observedAt") != result["observedAt"]]
    history.append(result)
    history = history[-maximum_entries:]
    scored = [entry for entry in history if entry.get("criticalSuccessIndex") is not None]
    return {
        "schemaVersion": 1,
        "generatedAt": result["verifiedAt"],
        "thresholdDbz": SIGNIFICANT_ECHO_DBZ,
        "sampleCount": len(history),
        "meanCriticalSuccessIndex": (
            round(
                sum(entry["criticalSuccessIndex"] for entry in scored) / len(scored),
                4,
            )
            if scored
            else None
        ),
        "results": history,
    }
