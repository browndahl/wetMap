from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from PIL import Image

from .nowcast import ALGORITHM_VERSION, _parse_time, _reflectivity_grid

SIGNIFICANT_ECHO_DBZ = 20
LEGACY_ALGORITHM_VERSION = "legacy-unversioned"
VERIFICATION_THRESHOLDS_DBZ = (10, 20, 35)
FORECAST_MATCH_TOLERANCE_SECONDS = 180
FORECAST_RETENTION_MINUTES = 65


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _categorical_scores(
    predicted: np.ndarray,
    actual: np.ndarray,
    threshold_dbz: int = SIGNIFICANT_ECHO_DBZ,
) -> dict[str, Any]:
    valid = (predicted > 0) & (actual > 0)
    encoded_threshold = threshold_dbz + 32
    predicted_echo = (predicted >= encoded_threshold) & valid
    actual_echo = (actual >= encoded_threshold) & valid
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

    return {
        "thresholdDbz": threshold_dbz,
        "validPixels": int(np.count_nonzero(valid)),
        "hits": hits,
        "misses": misses,
        "falseAlarms": false_alarms,
        "correctNegatives": correct_negatives,
        "precision": _ratio(hits, hits + false_alarms),
        "recall": _ratio(hits, hits + misses),
        "criticalSuccessIndex": _ratio(hits, union),
        "dbzMeanAbsoluteError": round(dbz_mae, 2),
    }


def verification_candidates(
    state: dict[str, Any], observed_at: str
) -> list[dict[str, Any]]:
    """Return archived forecasts with an exact lead frame for this observation."""
    observed_time = _parse_time(observed_at)
    candidates: list[dict[str, Any]] = []
    for forecast in state.get("forecasts", []):
        based_on = _parse_time(forecast["basedOnObservedAt"])
        age_minutes = (observed_time - based_on).total_seconds() / 60
        if age_minutes <= 0 or age_minutes > FORECAST_RETENTION_MINUTES:
            continue
        if any(
            frame.get("leadMinutes", 0) > 0
            and abs(
                (_parse_time(frame["predictedAt"]) - observed_time).total_seconds()
            )
            <= FORECAST_MATCH_TOLERANCE_SECONDS
            for frame in forecast.get("frames", [])
        ):
            candidates.append(forecast)
    return candidates


def verify_previous_nowcast(
    metadata: Path | dict[str, Any],
    cube_path: Path,
    observed_frame_path: Path,
    observed_at: str,
) -> dict[str, Any] | None:
    """Score one archived nowcast generation against a newly arrived observation."""
    if isinstance(metadata, Path):
        metadata = json.loads(metadata.read_text(encoding="utf-8"))
    frames = metadata.get("frames", [])
    if not frames:
        return None
    observed_time = _parse_time(observed_at)
    candidate_index, candidate = min(
        enumerate(frames),
        key=lambda item: abs(
            (_parse_time(item[1]["predictedAt"]) - observed_time).total_seconds()
        ),
    )
    offset_seconds = abs(
        (_parse_time(candidate["predictedAt"]) - observed_time).total_seconds()
    )
    if (
        offset_seconds > FORECAST_MATCH_TOLERANCE_SECONDS
        or candidate.get("leadMinutes", 0) <= 0
    ):
        return None

    width = int(metadata["width"])
    height = int(metadata["height"])
    frame_count = int(metadata["frameCount"])
    cube_bytes = cube_path.read_bytes()
    if metadata.get("sha256") and hashlib.sha256(cube_bytes).hexdigest() != metadata["sha256"]:
        raise ValueError("Archived verification cube checksum mismatch")
    if metadata.get("encoding") == "npz-pixel-major-uint8-dbz-plus-32":
        with np.load(cube_path, allow_pickle=False) as archive:
            cube = archive["cube"]
    else:
        cube = np.frombuffer(cube_bytes, dtype=np.uint8)
        if cube.size != width * height * frame_count:
            raise ValueError("Previous point nowcast has an unexpected size")
        cube = cube.reshape(height, width, frame_count)
    if cube.shape != (height, width, frame_count) or cube.dtype != np.uint8:
        raise ValueError("Archived verification cube has an unexpected shape or type")

    predicted = cube[..., candidate_index]
    observed_rgba = np.asarray(Image.open(observed_frame_path).convert("RGBA"))
    actual = _reflectivity_grid(observed_rgba[..., 3], width, height)
    persistence = cube[..., 0]

    threshold_scores: list[dict[str, Any]] = []
    for threshold in VERIFICATION_THRESHOLDS_DBZ:
        score = _categorical_scores(predicted, actual, threshold)
        persistence_score = _categorical_scores(persistence, actual, threshold)
        forecast_csi = score["criticalSuccessIndex"]
        persistence_csi = persistence_score["criticalSuccessIndex"]
        score["persistenceCriticalSuccessIndex"] = persistence_csi
        score["criticalSuccessIndexSkill"] = (
            round(forecast_csi - persistence_csi, 4)
            if forecast_csi is not None and persistence_csi is not None
            else None
        )
        threshold_scores.append(score)

    primary = next(
        score for score in threshold_scores if score["thresholdDbz"] == SIGNIFICANT_ECHO_DBZ
    )
    return {
        "verifiedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "basedOnObservedAt": metadata["basedOnObservedAt"],
        "predictedAt": candidate["predictedAt"],
        "observedAt": observed_at,
        "leadMinutes": candidate["leadMinutes"],
        "forecastMethod": candidate.get("forecastMethod", "optical-flow"),
        "algorithmVersion": metadata.get(
            "algorithmVersion", LEGACY_ALGORITHM_VERSION
        ),
        **{key: value for key, value in primary.items() if key != "thresholdDbz"},
        "thresholdDbz": SIGNIFICANT_ECHO_DBZ,
        "thresholdScores": threshold_scores,
    }


def _aggregate_scores(entries: Iterable[dict[str, Any]]) -> dict[str, Any]:
    entries = list(entries)
    hits = sum(int(entry.get("hits", 0)) for entry in entries)
    misses = sum(int(entry.get("misses", 0)) for entry in entries)
    false_alarms = sum(int(entry.get("falseAlarms", 0)) for entry in entries)
    valid_pixels = sum(int(entry.get("validPixels", 0)) for entry in entries)
    mae_entries = [
        float(entry["dbzMeanAbsoluteError"])
        for entry in entries
        if entry.get("dbzMeanAbsoluteError") is not None
    ]
    skills = [
        float(entry["criticalSuccessIndexSkill"])
        for entry in entries
        if entry.get("criticalSuccessIndexSkill") is not None
    ]
    persistence_csi = [
        float(entry["persistenceCriticalSuccessIndex"])
        for entry in entries
        if entry.get("persistenceCriticalSuccessIndex") is not None
    ]
    return {
        "sampleCount": len(entries),
        "validPixels": valid_pixels,
        "hits": hits,
        "misses": misses,
        "falseAlarms": false_alarms,
        "precision": _ratio(hits, hits + false_alarms),
        "recall": _ratio(hits, hits + misses),
        "criticalSuccessIndex": _ratio(hits, hits + misses + false_alarms),
        "meanDbzMeanAbsoluteError": (
            round(sum(mae_entries) / len(mae_entries), 2) if mae_entries else None
        ),
        "meanCriticalSuccessIndexSkill": (
            round(sum(skills) / len(skills), 4) if skills else None
        ),
        "meanPersistenceCriticalSuccessIndex": (
            round(sum(persistence_csi) / len(persistence_csi), 4)
            if persistence_csi
            else None
        ),
    }


def _algorithm_version(entry: dict[str, Any]) -> str:
    value = entry.get("algorithmVersion")
    return str(value) if value else LEGACY_ALGORITHM_VERSION


def _cohort_summary(history: list[dict[str, Any]]) -> dict[str, Any]:
    primary_scored = [
        entry for entry in history if entry.get("criticalSuccessIndex") is not None
    ]
    mean_csi = (
        round(
            sum(float(entry["criticalSuccessIndex"]) for entry in primary_scored)
            / len(primary_scored),
            4,
        )
        if primary_scored
        else None
    )
    skills = [
        float(entry["criticalSuccessIndexSkill"])
        for entry in history
        if entry.get("criticalSuccessIndexSkill") is not None
    ]
    by_lead: dict[int, list[dict[str, Any]]] = defaultdict(list)
    by_threshold: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for entry in history:
        by_lead[int(entry["leadMinutes"])].append(entry)
        for threshold_score in entry.get("thresholdScores", []):
            by_threshold[int(threshold_score["thresholdDbz"])].append(threshold_score)
    return {
        "sampleCount": len(history),
        "meanCriticalSuccessIndex": mean_csi,
        "meanCriticalSuccessIndexSkill": (
            round(sum(skills) / len(skills), 4) if skills else None
        ),
        "byLeadMinutes": [
            {
                "leadMinutes": lead,
                **_aggregate_scores(entries),
                "byForecastMethod": [
                    {
                        "forecastMethod": method,
                        **_aggregate_scores(method_entries),
                    }
                    for method, method_entries in sorted(
                        (
                            (
                                method,
                                [
                                    entry
                                    for entry in entries
                                    if entry.get("forecastMethod", "optical-flow")
                                    == method
                                ],
                            )
                            for method in {
                                entry.get("forecastMethod", "optical-flow")
                                for entry in entries
                            }
                        ),
                        key=lambda item: item[0],
                    )
                ],
            }
            for lead, entries in sorted(by_lead.items())
        ],
        "byThresholdDbz": [
            {"thresholdDbz": threshold, **_aggregate_scores(entries)}
            for threshold, entries in sorted(by_threshold.items())
        ],
    }


def _report(history: list[dict[str, Any]], recent_limit: int | None = None) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    cohorts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in history:
        cohorts[_algorithm_version(entry)].append(entry)

    active_version = (
        _algorithm_version(history[-1]) if history else ALGORITHM_VERSION
    )
    active_history = cohorts.get(active_version, [])
    active_summary = _cohort_summary(active_history)
    result_slice = history[-recent_limit:] if recent_limit is not None else history
    return {
        "schemaVersion": 3,
        "generatedAt": history[-1]["verifiedAt"] if history else now,
        "algorithmVersion": active_version,
        "thresholdDbz": SIGNIFICANT_ECHO_DBZ,
        "thresholdsDbz": list(VERIFICATION_THRESHOLDS_DBZ),
        "totalSampleCount": len(history),
        **active_summary,
        "byAlgorithmVersion": [
            {
                "algorithmVersion": version,
                "latestVerifiedAt": entries[-1]["verifiedAt"],
                **_cohort_summary(entries),
            }
            for version, entries in sorted(cohorts.items())
        ],
        "results": result_slice,
    }


def append_verification_history(
    history_path: Path,
    result: dict[str, Any] | list[dict[str, Any]],
    maximum_entries: int = 5200,
) -> dict[str, Any]:
    history: list[dict[str, Any]] = []
    if history_path.exists():
        try:
            history = json.loads(history_path.read_text(encoding="utf-8")).get("results", [])
        except (json.JSONDecodeError, AttributeError):
            history = []
    incoming = result if isinstance(result, list) else [result]
    incoming_keys = {
        (
            entry["basedOnObservedAt"],
            entry["observedAt"],
            _algorithm_version(entry),
        )
        for entry in incoming
    }
    history = [
        entry
        for entry in history
        if (
            entry.get("basedOnObservedAt"),
            entry.get("observedAt"),
            _algorithm_version(entry),
        )
        not in incoming_keys
    ]
    history.extend(incoming)
    history.sort(key=lambda entry: (entry["observedAt"], entry["leadMinutes"]))
    return _report(history[-maximum_entries:])


def public_verification_report(
    full_history: dict[str, Any], recent_results: int = 288
) -> dict[str, Any]:
    report = dict(full_history)
    report["latestVerifiedAt"] = full_history.get("generatedAt")
    report["generatedAt"] = datetime.now(timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )
    active_version = full_history.get("algorithmVersion", ALGORITHM_VERSION)
    active_results = [
        entry
        for entry in full_history.get("results", [])
        if _algorithm_version(entry) == active_version
    ]
    report["results"] = active_results[-recent_results:]
    report["returnedResultCount"] = len(report["results"])
    return report


def quality_by_lead(history: dict[str, Any] | None) -> dict[int, dict[str, Any]]:
    if not history:
        return {}
    profiles: dict[int, dict[str, Any]] = {}
    for entry in history.get("byLeadMinutes", []):
        profile = dict(entry)
        methods = {
            method["forecastMethod"]: method
            for method in entry.get("byForecastMethod", [])
        }
        optical = methods.get("optical-flow")
        persistence = methods.get("persistence")
        if optical:
            profile["opticalFlowSampleCount"] = optical["sampleCount"]
            profile["opticalFlowCriticalSuccessIndex"] = optical[
                "criticalSuccessIndex"
            ]
            profile["opticalFlowMeanCriticalSuccessIndexSkill"] = optical[
                "meanCriticalSuccessIndexSkill"
            ]
        if persistence:
            profile["persistenceSampleCount"] = persistence["sampleCount"]
            profile["persistenceCriticalSuccessIndex"] = persistence[
                "criticalSuccessIndex"
            ]
        profiles[int(entry["leadMinutes"])] = profile
    return profiles


def update_verification_state(
    previous_state: dict[str, Any] | None,
    forecast: dict[str, Any],
) -> dict[str, Any]:
    based_on = _parse_time(forecast["basedOnObservedAt"])
    earliest = based_on - timedelta(minutes=FORECAST_RETENTION_MINUTES)
    previous = (previous_state or {}).get("forecasts", [])
    forecasts = [
        entry
        for entry in previous
        if entry.get("basedOnObservedAt") != forecast["basedOnObservedAt"]
        and _parse_time(entry["basedOnObservedAt"]) >= earliest
    ]
    forecasts.append(forecast)
    forecasts.sort(key=lambda entry: entry["basedOnObservedAt"])
    return {
        "schemaVersion": 1,
        "generatedAt": forecast["generatedAt"],
        "retentionMinutes": FORECAST_RETENTION_MINUTES,
        "forecasts": forecasts,
    }
