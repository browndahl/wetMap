from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from wetmap_worker.backtest import BacktestPlan, load_backtest_plan
from wetmap_worker.nowcast import (
    CALIBRATION_MINIMUM_ABSOLUTE_RECALL,
    CALIBRATION_MINIMUM_CSI_GAIN,
    CALIBRATION_MINIMUM_EVENT_PIXELS,
    CALIBRATION_MINIMUM_RECALL_RETENTION,
    CALIBRATION_MINIMUM_SAMPLES,
    CALIBRATION_PROBABILITY_THRESHOLDS,
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
    correct_negatives = sum(int(entry["correctNegatives"]) for entry in entries)
    valid_pixels = sum(int(entry["validPixels"]) for entry in entries)
    mae = [float(entry["dbzMeanAbsoluteError"]) for entry in entries]
    union = hits + misses + false_alarms
    return {
        "sampleCount": len(entries),
        "validPixels": valid_pixels,
        "hits": hits,
        "misses": misses,
        "falseAlarms": false_alarms,
        "correctNegatives": correct_negatives,
        "criticalSuccessIndex": hits / union if union else 0.0,
        "recall": hits / (hits + misses) if hits + misses else 0.0,
        "precision": hits / (hits + false_alarms) if hits + false_alarms else 0.0,
        "falseAlarmRate": (false_alarms / (hits + false_alarms) if hits + false_alarms else 0.0),
        "meanDbzMeanAbsoluteError": sum(mae) / len(mae) if mae else 0.0,
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


def _candidate_summaries(
    scores: dict[tuple[str, str, int], list[dict[str, Any]]],
    split_name: str,
    lead_minutes: int,
    candidate_names: tuple[str, ...],
) -> dict[str, dict[str, int | float]]:
    summaries = {
        name: _summary(scores[(split_name, name, lead_minutes)]) for name in candidate_names
    }
    persistence_csi = float(summaries["persistence"]["criticalSuccessIndex"])
    incumbent_csi = float(summaries["optical-flow"]["criticalSuccessIndex"])
    for summary in summaries.values():
        csi = float(summary["criticalSuccessIndex"])
        summary["criticalSuccessIndexSkill"] = csi - persistence_csi
        summary["criticalSuccessIndexImprovement"] = csi - incumbent_csi
    return summaries


def backtest(frame_directory: Path, plan: BacktestPlan) -> dict[str, Any]:
    images = {
        _timestamp(path): cv2.resize(
            np.asarray(Image.open(path).convert("RGBA")),
            (VERIFICATION_GRID_WIDTH, VERIFICATION_GRID_HEIGHT),
            interpolation=cv2.INTER_AREA,
        )
        for path in sorted(frame_directory.glob("*.webp"))
        if FRAME_PATTERN.search(path.name)
    }
    candidate_names = (
        "optical-flow",
        "persistence",
        "trajectory-recency-flow-v1",
        "trajectory-speed-bias-v2",
        "regime-adaptive-ensemble-v3",
        "probability-gated-ensemble-v4",
        "recall-calibrated-ensemble-v5",
    )
    scores: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    calibration_scores: dict[tuple[int, float], list[dict[str, Any]]] = defaultdict(list)
    frozen_gates: dict[str, dict[int, float]] = {}
    evaluated_base_times: dict[str, int] = defaultdict(int)
    skipped = defaultdict(int)
    for base_time in sorted(images):
        # Production forecasts are archived on the :05/:15/... ten-minute cadence.
        if base_time.minute % 10 != 5:
            continue
        split = plan.split_for(base_time)
        if split is None:
            skipped["outsideSplit"] += 1
            continue
        source_times = [
            base_time - timedelta(minutes=10),
            base_time - timedelta(minutes=5),
            base_time,
        ]
        if not all(value in images for value in source_times):
            skipped["missingSourceFrame"] += 1
            continue
        if not all(plan.split_for(value) == split for value in source_times):
            skipped["crossSplitSource"] += 1
            continue
        if split.name not in frozen_gates:
            frozen_gates[split.name] = {
                lead: _select_calibrated_gate(calibration_scores, lead)
                for lead in plan.lead_minutes
            }
        evaluated_base_times[split.name] += 1
        source = [images[value] for value in source_times]
        baseline_flow = _dense_motion(source, [5.0, 5.0])
        trajectory_flow = _dense_motion(source, [5.0, 5.0], recency_weighted=True)
        regime_selector = _regime_selector(source, [5.0, 5.0], 20)
        for lead_minutes in plan.lead_minutes:
            target_time = base_time + timedelta(minutes=lead_minutes)
            target = images.get(target_time)
            if target is None:
                skipped["missingTargetFrame"] += 1
                continue
            if plan.split_for(target_time) != split:
                skipped["crossSplitTarget"] += 1
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
            calibrated_gate = (
                _select_calibrated_gate(calibration_scores, lead_minutes)
                if split.name == "train"
                else frozen_gates[split.name][lead_minutes]
            )
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
                scores[(split.name, name, lead_minutes)].append(
                    _categorical_scores(
                        _reflectivity_grid(
                            prediction[..., 3],
                            VERIFICATION_GRID_WIDTH,
                            VERIFICATION_GRID_HEIGHT,
                        ),
                        actual,
                    )
                )
            if split.may_tune:
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
    timestamps = sorted(images)
    return {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "dataset": {
            "id": plan.dataset_id,
            "splitConfigSha256": plan.sha256,
            "source": plan.source,
        },
        "inputs": {
            "frameCount": len(images),
            "firstObservedAt": (
                timestamps[0].isoformat().replace("+00:00", "Z") if timestamps else None
            ),
            "lastObservedAt": (
                timestamps[-1].isoformat().replace("+00:00", "Z") if timestamps else None
            ),
            "evaluatedBaseTimes": dict(evaluated_base_times),
            "skipped": dict(skipped),
        },
        "calibration": {
            split_name: {str(lead): gate for lead, gate in gates.items()}
            for split_name, gates in frozen_gates.items()
        },
        "results": {
            split.name: {
                str(lead): _candidate_summaries(scores, split.name, lead, candidate_names)
                for lead in plan.lead_minutes
            }
            for split in plan.splits
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backtest WetMap nowcast candidates against processed radar frames."
    )
    parser.add_argument("frame_directory", type=Path)
    parser.add_argument(
        "--split",
        type=Path,
        default=Path(__file__).parents[1] / "backtest" / "split-v1.json",
    )
    parser.add_argument("--json", type=Path, dest="json_output")
    args = parser.parse_args()
    plan = load_backtest_plan(args.split)
    report = backtest(args.frame_directory, plan)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for split_name, leads in report["results"].items():
        print(split_name)
        for lead_minutes, candidates in leads.items():
            print(f"  +{lead_minutes} minutes")
            for name, summary in candidates.items():
                print(
                    f"    {name:31s} CSI {float(summary['criticalSuccessIndex']):.4f} "
                    f"Δ {float(summary['criticalSuccessIndexImprovement']):+.4f} "
                    f"FAR {float(summary['falseAlarmRate']):.4f} "
                    f"n={summary['sampleCount']}"
                )


if __name__ == "__main__":
    main()
