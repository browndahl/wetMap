from __future__ import annotations

import argparse
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from wetmap_worker.nowcast import (
    CALIBRATION_MINIMUM_ABSOLUTE_RECALL,
    CALIBRATION_MINIMUM_CSI_GAIN,
    CALIBRATION_MINIMUM_EVENT_PIXELS,
    CALIBRATION_MINIMUM_RECALL_RETENTION,
    CALIBRATION_MINIMUM_SAMPLES,
    CALIBRATION_PROBABILITY_THRESHOLDS,
    SHADOW_VERIFICATION_LEAD_MINUTES,
    SPEED_CORRECTION_FACTOR,
    VERIFICATION_GRID_HEIGHT,
    VERIFICATION_GRID_WIDTH,
    _advect,
    _advect_trajectory,
    _dense_motion,
    _initial_calibrated_gate_for_lead,
    _probability_gate_for_lead,
    _probability_gated_prediction,
    _regime_prediction,
    _regime_rain_probability,
    _regime_selector,
    _reflectivity_grid,
)
from wetmap_worker.verification import _categorical_scores

FRAME_PATTERN = re.compile(r"dk\.com\.(\d{12})\.500_max\.webp$")


def _timestamp(path: Path) -> datetime:
    match = FRAME_PATTERN.search(path.name)
    if not match:
        raise ValueError(f"Unsupported radar frame name: {path.name}")
    return datetime.strptime(match.group(1), "%Y%m%d%H%M").replace(tzinfo=timezone.utc)


def _summary(entries: list[dict[str, Any]]) -> dict[str, int | float]:
    hits = sum(int(entry["hits"]) for entry in entries)
    misses = sum(int(entry["misses"]) for entry in entries)
    false_alarms = sum(int(entry["falseAlarms"]) for entry in entries)
    union = hits + misses + false_alarms
    return {
        "sampleCount": len(entries),
        "hits": hits,
        "misses": misses,
        "falseAlarms": false_alarms,
        "criticalSuccessIndex": hits / union if union else 0.0,
        "recall": hits / (hits + misses) if hits + misses else 0.0,
        "falseAlarmRate": (false_alarms / (hits + false_alarms) if hits + false_alarms else 0.0),
    }


def _select_calibrated_gate(
    scores: dict[tuple[int, float], list[dict[str, Any]]], lead_minutes: int
) -> float:
    control_entries = scores[(lead_minutes, 0.0)]
    if len(control_entries) < CALIBRATION_MINIMUM_SAMPLES:
        return _initial_calibrated_gate_for_lead(lead_minutes)
    control = _summary(control_entries)
    if (
        int(control["hits"]) + int(control["misses"]) + int(control["falseAlarms"])
        < CALIBRATION_MINIMUM_EVENT_PIXELS
    ):
        return _initial_calibrated_gate_for_lead(lead_minutes)
    control_recall = float(control["recall"])
    control_csi = float(control["criticalSuccessIndex"])
    recall_floor = max(
        CALIBRATION_MINIMUM_ABSOLUTE_RECALL,
        control_recall * CALIBRATION_MINIMUM_RECALL_RETENTION,
    )
    eligible: list[tuple[float, float]] = []
    for threshold in CALIBRATION_PROBABILITY_THRESHOLDS:
        if threshold <= 0:
            continue
        summary = _summary(scores[(lead_minutes, threshold)])
        csi = float(summary["criticalSuccessIndex"])
        if (
            float(summary["recall"]) >= recall_floor
            and csi >= control_csi + CALIBRATION_MINIMUM_CSI_GAIN
        ):
            eligible.append((threshold, csi))
    return max(eligible, key=lambda item: (item[1], item[0]))[0] if eligible else 0.0


def backtest(frame_directory: Path) -> dict[int, dict[str, dict[str, int | float]]]:
    images = {
        _timestamp(path): cv2.resize(
            np.asarray(Image.open(path).convert("RGBA")),
            (VERIFICATION_GRID_WIDTH, VERIFICATION_GRID_HEIGHT),
            interpolation=cv2.INTER_AREA,
        )
        for path in sorted(frame_directory.glob("*.webp"))
        if FRAME_PATTERN.search(path.name)
    }
    scores: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    calibration_scores: dict[tuple[int, float], list[dict[str, Any]]] = defaultdict(list)
    for base_time in sorted(images):
        # Production forecasts are archived on the :05/:15/... ten-minute cadence.
        if base_time.minute % 10 != 5:
            continue
        source_times = [
            base_time - timedelta(minutes=10),
            base_time - timedelta(minutes=5),
            base_time,
        ]
        if not all(value in images for value in source_times):
            continue
        source = [images[value] for value in source_times]
        baseline_flow = _dense_motion(source, [5.0, 5.0])
        trajectory_flow = _dense_motion(source, [5.0, 5.0], recency_weighted=True)
        regime_selector = _regime_selector(source, [5.0, 5.0], 20)
        for lead_minutes in SHADOW_VERIFICATION_LEAD_MINUTES:
            target = images.get(base_time + timedelta(minutes=lead_minutes))
            if target is None:
                continue
            actual = _reflectivity_grid(
                target[..., 3], VERIFICATION_GRID_WIDTH, VERIFICATION_GRID_HEIGHT
            )
            optical_prediction = _advect(source[-1], baseline_flow, lead_minutes)
            trajectory_prediction = _advect_trajectory(source[-1], trajectory_flow, lead_minutes)
            speed_prediction = _advect_trajectory(
                source[-1],
                trajectory_flow * SPEED_CORRECTION_FACTOR,
                lead_minutes,
            )
            regime_prediction = _regime_prediction(
                source[-1],
                optical_prediction,
                trajectory_prediction,
                speed_prediction,
                str(regime_selector["selectedMember"]),
            )
            regime_probability = _regime_rain_probability(
                source[-1],
                optical_prediction,
                trajectory_prediction,
                speed_prediction,
                regime_selector["weights"],
                20,
            )
            calibrated_gate = _select_calibrated_gate(calibration_scores, lead_minutes)
            predictions = {
                "persistence": source[-1],
                "optical-flow": optical_prediction,
                "trajectory-recency-flow-v1": trajectory_prediction,
                "trajectory-speed-bias-v2": speed_prediction,
                "regime-adaptive-ensemble-v3": regime_prediction,
                "probability-gated-ensemble-v4": _probability_gated_prediction(
                    regime_prediction,
                    regime_probability,
                    _probability_gate_for_lead(lead_minutes),
                    20,
                ),
                "recall-calibrated-ensemble-v5": _probability_gated_prediction(
                    regime_prediction,
                    regime_probability,
                    calibrated_gate,
                    20,
                ),
            }
            for name, prediction in predictions.items():
                scores[(name, lead_minutes)].append(
                    _categorical_scores(
                        _reflectivity_grid(
                            prediction[..., 3],
                            VERIFICATION_GRID_WIDTH,
                            VERIFICATION_GRID_HEIGHT,
                        ),
                        actual,
                    )
                )
            for threshold in CALIBRATION_PROBABILITY_THRESHOLDS:
                calibration_scores[(lead_minutes, threshold)].append(
                    _categorical_scores(
                        _reflectivity_grid(
                            _probability_gated_prediction(
                                regime_prediction,
                                regime_probability,
                                threshold,
                                20,
                            )[..., 3],
                            VERIFICATION_GRID_WIDTH,
                            VERIFICATION_GRID_HEIGHT,
                        ),
                        actual,
                    )
                )
    return {
        lead_minutes: {
            name: _summary(scores[(name, lead_minutes)])
            for name in (
                "optical-flow",
                "persistence",
                "trajectory-recency-flow-v1",
                "trajectory-speed-bias-v2",
                "regime-adaptive-ensemble-v3",
                "probability-gated-ensemble-v4",
                "recall-calibrated-ensemble-v5",
            )
        }
        for lead_minutes in SHADOW_VERIFICATION_LEAD_MINUTES
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backtest WetMap nowcast candidates against processed radar frames."
    )
    parser.add_argument("frame_directory", type=Path)
    args = parser.parse_args()
    report = backtest(args.frame_directory)
    for lead_minutes, candidates in report.items():
        baseline = float(candidates["optical-flow"]["criticalSuccessIndex"])
        print(f"+{lead_minutes} minutes")
        for name, summary in candidates.items():
            csi = float(summary["criticalSuccessIndex"])
            print(
                f"  {name:31s} CSI {csi:.4f} "
                f"Δ {csi - baseline:+.4f} "
                f"FAR {float(summary['falseAlarmRate']):.4f} "
                f"n={summary['sampleCount']}"
            )


if __name__ == "__main__":
    main()
