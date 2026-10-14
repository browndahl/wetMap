from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from PIL import Image

from .nowcast import (
    ALERT_MINIMUM_CSI,
    ALERT_MINIMUM_SKILL,
    ALERT_MINIMUM_VALIDATION_SAMPLES,
    ALGORITHM_VERSION,
    SHADOW_MINIMUM_LEAD_MINUTES,
    SHADOW_PROMOTION_MAX_FALSE_ALARM_RATE_INCREASE,
    SHADOW_PROMOTION_MINIMUM_CSI_IMPROVEMENT,
    SHADOW_PROMOTION_MINIMUM_EVENT_PIXELS,
    SHADOW_PROMOTION_MINIMUM_SAMPLES,
    SHADOW_VERIFICATION_LEAD_MINUTES,
    _parse_time,
    _reflectivity_grid,
)

SIGNIFICANT_ECHO_DBZ = 20
LEGACY_ALGORITHM_VERSION = "legacy-unversioned"
VERIFICATION_THRESHOLDS_DBZ = (5, 10, 15, 20, 35)
FORECAST_MATCH_TOLERANCE_SECONDS = 180
FORECAST_RETENTION_MINUTES = 65
OBSERVATORY_MINIMUM_EVENT_PIXELS = 100
OBSERVATORY_HORIZON_WINDOWS = (
    (15, 10, 20),
    (30, 25, 35),
    (45, 40, 50),
    (60, 55, 60),
)


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


def verification_candidates(state: dict[str, Any], observed_at: str) -> list[dict[str, Any]]:
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
            and abs((_parse_time(frame["predictedAt"]) - observed_time).total_seconds())
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
        key=lambda item: abs((_parse_time(item[1]["predictedAt"]) - observed_time).total_seconds()),
    )
    offset_seconds = abs((_parse_time(candidate["predictedAt"]) - observed_time).total_seconds())
    if offset_seconds > FORECAST_MATCH_TOLERANCE_SECONDS or candidate.get("leadMinutes", 0) <= 0:
        return None

    width = int(metadata["width"])
    height = int(metadata["height"])
    frame_count = int(metadata["frameCount"])
    cube_bytes = cube_path.read_bytes()
    if metadata.get("sha256") and hashlib.sha256(cube_bytes).hexdigest() != metadata["sha256"]:
        raise ValueError("Archived verification cube checksum mismatch")
    shadow_cubes: dict[str, np.ndarray] = {}
    if metadata.get("encoding") == "npz-pixel-major-uint8-dbz-plus-32":
        with np.load(cube_path, allow_pickle=False) as archive:
            cube = archive["cube"]
            for shadow_candidate in metadata.get("shadowCandidates", []):
                for key_name in ("cubeKey", "baselineCubeKey"):
                    cube_key = str(shadow_candidate.get(key_name, ""))
                    if cube_key and cube_key in archive:
                        shadow_cubes[cube_key] = archive[cube_key]
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
    shadow_candidate_scores: list[dict[str, Any]] = []
    for shadow_candidate in metadata.get("shadowCandidates", []):
        shadow_frame = next(
            (
                frame
                for frame in shadow_candidate.get("frames", [])
                if int(frame.get("leadMinutes", 0)) > 0
                and abs((_parse_time(frame["predictedAt"]) - observed_time).total_seconds())
                <= FORECAST_MATCH_TOLERANCE_SECONDS
            ),
            None,
        )
        candidate_cube = shadow_cubes.get(str(shadow_candidate.get("cubeKey", "")))
        baseline_cube = shadow_cubes.get(
            str(shadow_candidate.get("baselineCubeKey", "")), cube
        )
        if shadow_frame is None or candidate_cube is None:
            continue
        if candidate_cube.shape != (height, width, frame_count) or candidate_cube.dtype != np.uint8:
            raise ValueError("Archived shadow verification cube has an unexpected shape or type")
        if baseline_cube.shape != (height, width, frame_count) or baseline_cube.dtype != np.uint8:
            raise ValueError("Archived shadow baseline cube has an unexpected shape or type")
        shadow_index = int(shadow_frame.get("cubeFrameIndex", candidate_index))
        if shadow_index < 0 or shadow_index >= frame_count:
            raise ValueError("Archived shadow verification frame index is out of range")
        shadow_threshold_scores: list[dict[str, Any]] = []
        for threshold in VERIFICATION_THRESHOLDS_DBZ:
            shadow_score = _categorical_scores(candidate_cube[..., shadow_index], actual, threshold)
            persistence_score = _categorical_scores(persistence, actual, threshold)
            baseline_score = _categorical_scores(
                baseline_cube[..., shadow_index], actual, threshold
            )
            shadow_csi = shadow_score["criticalSuccessIndex"]
            persistence_csi = persistence_score["criticalSuccessIndex"]
            baseline_csi = baseline_score["criticalSuccessIndex"]
            shadow_score["persistenceCriticalSuccessIndex"] = persistence_csi
            shadow_score["criticalSuccessIndexSkill"] = (
                round(shadow_csi - persistence_csi, 4)
                if shadow_csi is not None and persistence_csi is not None
                else None
            )
            shadow_score["baselineCriticalSuccessIndex"] = baseline_csi
            shadow_score["criticalSuccessIndexImprovement"] = (
                round(shadow_csi - baseline_csi, 4)
                if shadow_csi is not None and baseline_csi is not None
                else None
            )
            shadow_score["baselineScore"] = baseline_score
            shadow_threshold_scores.append(shadow_score)
        shadow_primary = next(
            score
            for score in shadow_threshold_scores
            if score["thresholdDbz"] == SIGNIFICANT_ECHO_DBZ
        )
        shadow_candidate_scores.append(
            {
                "candidateId": shadow_candidate["candidateId"],
                "forecastMethod": shadow_candidate["forecastMethod"],
                "leadMinutes": int(shadow_frame["leadMinutes"]),
                **{key: value for key, value in shadow_primary.items() if key != "thresholdDbz"},
                "thresholdDbz": SIGNIFICANT_ECHO_DBZ,
                "thresholdScores": shadow_threshold_scores,
            }
        )
    result = {
        "verifiedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "basedOnObservedAt": metadata["basedOnObservedAt"],
        "predictedAt": candidate["predictedAt"],
        "observedAt": observed_at,
        "leadMinutes": candidate["leadMinutes"],
        "forecastMethod": candidate.get("forecastMethod", "optical-flow"),
        "algorithmVersion": metadata.get("algorithmVersion", LEGACY_ALGORITHM_VERSION),
        **{key: value for key, value in primary.items() if key != "thresholdDbz"},
        "thresholdDbz": SIGNIFICANT_ECHO_DBZ,
        "thresholdScores": threshold_scores,
    }
    if shadow_candidate_scores:
        result["shadowCandidateScores"] = shadow_candidate_scores
    return result


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
        "meanCriticalSuccessIndexSkill": (round(sum(skills) / len(skills), 4) if skills else None),
        "meanPersistenceCriticalSuccessIndex": (
            round(sum(persistence_csi) / len(persistence_csi), 4) if persistence_csi else None
        ),
    }


def _algorithm_version(entry: dict[str, Any]) -> str:
    value = entry.get("algorithmVersion")
    return str(value) if value else LEGACY_ALGORITHM_VERSION


def _shadow_candidate_summaries(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, int], list[tuple[dict[str, Any], dict[str, Any]]]] = (
        defaultdict(list)
    )
    for operational_entry in history:
        for candidate_entry in operational_entry.get("shadowCandidateScores", []):
            if int(candidate_entry["leadMinutes"]) not in SHADOW_VERIFICATION_LEAD_MINUTES:
                continue
            key = (
                str(candidate_entry["candidateId"]),
                str(candidate_entry["forecastMethod"]),
                int(candidate_entry["leadMinutes"]),
            )
            grouped[key].append((candidate_entry, operational_entry))

    candidates: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for (candidate_id, forecast_method, lead_minutes), pairs in sorted(grouped.items()):
        candidate_summary = _aggregate_scores(candidate for candidate, _operational in pairs)
        operational_summary = _aggregate_scores(
            candidate.get("baselineScore", operational)
            for candidate, operational in pairs
        )
        candidate_csi = candidate_summary["criticalSuccessIndex"]
        operational_csi = operational_summary["criticalSuccessIndex"]
        csi_improvement = (
            round(candidate_csi - operational_csi, 4)
            if isinstance(candidate_csi, (int, float))
            and isinstance(operational_csi, (int, float))
            else None
        )
        event_pixel_count = (
            candidate_summary["hits"]
            + candidate_summary["misses"]
            + candidate_summary["falseAlarms"]
        )
        false_alarm_rate = _ratio(
            candidate_summary["falseAlarms"],
            candidate_summary["hits"] + candidate_summary["falseAlarms"],
        )
        baseline_false_alarm_rate = _ratio(
            operational_summary["falseAlarms"],
            operational_summary["hits"] + operational_summary["falseAlarms"],
        )
        false_alarm_rate_increase = (
            round(false_alarm_rate - baseline_false_alarm_rate, 4)
            if false_alarm_rate is not None and baseline_false_alarm_rate is not None
            else None
        )
        enough_samples = candidate_summary["sampleCount"] >= SHADOW_PROMOTION_MINIMUM_SAMPLES
        enough_events = event_pixel_count >= SHADOW_PROMOTION_MINIMUM_EVENT_PIXELS
        skill = candidate_summary["meanCriticalSuccessIndexSkill"]
        meets_quality_gate = bool(
            enough_samples
            and enough_events
            and isinstance(candidate_csi, (int, float))
            and candidate_csi >= ALERT_MINIMUM_CSI
            and isinstance(csi_improvement, (int, float))
            and csi_improvement >= SHADOW_PROMOTION_MINIMUM_CSI_IMPROVEMENT
            and isinstance(skill, (int, float))
            and skill >= ALERT_MINIMUM_SKILL
            and isinstance(false_alarm_rate_increase, (int, float))
            and false_alarm_rate_increase <= SHADOW_PROMOTION_MAX_FALSE_ALARM_RATE_INCREASE
        )
        if not enough_samples:
            status = "collecting"
        elif not enough_events:
            status = "awaiting-rain"
        elif meets_quality_gate:
            status = "promotable"
        else:
            status = "held-back"
        candidates[(candidate_id, forecast_method)].append(
            {
                "leadMinutes": lead_minutes,
                "status": status,
                "safeToPromote": meets_quality_gate,
                "eventPixelCount": event_pixel_count,
                "falseAlarmRate": false_alarm_rate,
                "baselineFalseAlarmRate": baseline_false_alarm_rate,
                "falseAlarmRateIncrease": false_alarm_rate_increase,
                "baselineCriticalSuccessIndex": operational_csi,
                "criticalSuccessIndexImprovement": csi_improvement,
                **candidate_summary,
            }
        )

    return [
        {
            "candidateId": candidate_id,
            "forecastMethod": forecast_method,
            "minimumLeadMinutes": SHADOW_MINIMUM_LEAD_MINUTES,
            "promotionGate": {
                "minimumSamples": SHADOW_PROMOTION_MINIMUM_SAMPLES,
                "minimumEventPixels": SHADOW_PROMOTION_MINIMUM_EVENT_PIXELS,
                "minimumCriticalSuccessIndex": ALERT_MINIMUM_CSI,
                "minimumCriticalSuccessIndexImprovement": (
                    SHADOW_PROMOTION_MINIMUM_CSI_IMPROVEMENT
                ),
                "minimumSkillOverPersistence": ALERT_MINIMUM_SKILL,
                "maximumFalseAlarmRateIncrease": (
                    SHADOW_PROMOTION_MAX_FALSE_ALARM_RATE_INCREASE
                ),
            },
            "safeToPromoteLeadMinutes": [
                entry["leadMinutes"] for entry in leads if entry["safeToPromote"]
            ],
            "byLeadMinutes": leads,
        }
        for (candidate_id, forecast_method), leads in sorted(candidates.items())
    ]


def _cohort_summary(history: list[dict[str, Any]]) -> dict[str, Any]:
    primary_scored = [entry for entry in history if entry.get("criticalSuccessIndex") is not None]
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
        "meanCriticalSuccessIndexSkill": (round(sum(skills) / len(skills), 4) if skills else None),
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
                                    if entry.get("forecastMethod", "optical-flow") == method
                                ],
                            )
                            for method in {
                                entry.get("forecastMethod", "optical-flow") for entry in entries
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
        "shadowCandidates": _shadow_candidate_summaries(history),
    }


def _observatory_horizon(
    history: list[dict[str, Any]],
    target_lead_minutes: int,
    window_start_minutes: int,
    window_end_minutes: int,
    threshold_dbz: int = SIGNIFICANT_ECHO_DBZ,
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for entry in history:
        if not (window_start_minutes <= int(entry.get("leadMinutes", 0)) <= window_end_minutes):
            continue
        threshold_entry = next(
            (
                score
                for score in entry.get("thresholdScores", [])
                if int(score["thresholdDbz"]) == threshold_dbz
            ),
            entry if int(entry.get("thresholdDbz", -999)) == threshold_dbz else None,
        )
        if threshold_entry:
            entries.append(threshold_entry)
    summary = _aggregate_scores(entries)
    event_pixel_count = summary["hits"] + summary["misses"] + summary["falseAlarms"]
    has_enough_samples = summary["sampleCount"] >= ALERT_MINIMUM_VALIDATION_SAMPLES
    has_enough_events = event_pixel_count >= OBSERVATORY_MINIMUM_EVENT_PIXELS
    csi = summary["criticalSuccessIndex"]
    skill = summary["meanCriticalSuccessIndexSkill"]
    meets_quality_gate = bool(
        has_enough_samples
        and has_enough_events
        and isinstance(csi, (int, float))
        and csi >= ALERT_MINIMUM_CSI
        and isinstance(skill, (int, float))
        and skill >= ALERT_MINIMUM_SKILL
    )
    if not has_enough_samples:
        status = "collecting"
    elif not has_enough_events:
        status = "awaiting-rain"
    elif meets_quality_gate:
        status = "verified"
    else:
        status = "degraded"
    return {
        "targetLeadMinutes": target_lead_minutes,
        "windowStartMinutes": window_start_minutes,
        "windowEndMinutes": window_end_minutes,
        "status": status,
        "meetsQualityGate": meets_quality_gate,
        "eventPixelCount": event_pixel_count,
        "falseAlarmRate": _ratio(summary["falseAlarms"], summary["hits"] + summary["falseAlarms"]),
        "missRate": _ratio(summary["misses"], summary["hits"] + summary["misses"]),
        **summary,
    }


def _observatory_summary(
    history: list[dict[str, Any]], threshold_dbz: int = SIGNIFICANT_ECHO_DBZ
) -> dict[str, Any]:
    horizons = [
        _observatory_horizon(history, target, start, end, threshold_dbz)
        for target, start, end in OBSERVATORY_HORIZON_WINDOWS
    ]
    statuses = {horizon["status"] for horizon in horizons}
    if "degraded" in statuses:
        overall_status = "degraded"
    elif "collecting" in statuses:
        overall_status = "collecting"
    elif "awaiting-rain" in statuses:
        overall_status = "awaiting-rain"
    else:
        overall_status = "verified"
    return {
        "schemaVersion": 1,
        "thresholdDbz": threshold_dbz,
        "overallStatus": overall_status,
        "targetHorizonMinutes": [target for target, _start, _end in OBSERVATORY_HORIZON_WINDOWS],
        "qualityGate": {
            "minimumSamples": ALERT_MINIMUM_VALIDATION_SAMPLES,
            "minimumEventPixels": OBSERVATORY_MINIMUM_EVENT_PIXELS,
            "minimumCriticalSuccessIndex": ALERT_MINIMUM_CSI,
            "minimumSkillOverPersistence": ALERT_MINIMUM_SKILL,
        },
        "verifiedHorizonCount": sum(horizon["status"] == "verified" for horizon in horizons),
        "horizons": horizons,
    }


def _report(history: list[dict[str, Any]], recent_limit: int | None = None) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    cohorts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in history:
        cohorts[_algorithm_version(entry)].append(entry)

    active_version = _algorithm_version(history[-1]) if history else ALGORITHM_VERSION
    active_history = cohorts.get(active_version, [])
    active_summary = _cohort_summary(active_history)
    result_slice = history[-recent_limit:] if recent_limit is not None else history
    return {
        "schemaVersion": 5,
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
        "observatory": _observatory_summary(active_history),
        "observatoryByThresholdDbz": [
            _observatory_summary(active_history, threshold) for threshold in (5, 10, 15, 20)
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
    report["generatedAt"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    active_version = full_history.get("algorithmVersion", ALGORITHM_VERSION)
    active_results = [
        entry
        for entry in full_history.get("results", [])
        if _algorithm_version(entry) == active_version
    ]
    report["results"] = [
        {key: value for key, value in entry.items() if key != "shadowCandidateScores"}
        for entry in active_results[-recent_results:]
    ]
    report["returnedResultCount"] = len(report["results"])
    return report


def quality_by_lead(
    history: dict[str, Any] | None,
    threshold_dbz: int = SIGNIFICANT_ECHO_DBZ,
) -> dict[int, dict[str, Any]]:
    if not history or history.get("algorithmVersion") != ALGORITHM_VERSION:
        return {}
    profiles: dict[int, dict[str, Any]] = {}
    for entry in history.get("byLeadMinutes", []):
        profile = dict(entry)
        methods = {method["forecastMethod"]: method for method in entry.get("byForecastMethod", [])}
        optical = methods.get("optical-flow")
        persistence = methods.get("persistence")
        if optical:
            profile["opticalFlowSampleCount"] = optical["sampleCount"]
            profile["opticalFlowCriticalSuccessIndex"] = optical["criticalSuccessIndex"]
            profile["opticalFlowMeanCriticalSuccessIndexSkill"] = optical[
                "meanCriticalSuccessIndexSkill"
            ]
        if persistence:
            profile["persistenceSampleCount"] = persistence["sampleCount"]
            profile["persistenceCriticalSuccessIndex"] = persistence["criticalSuccessIndex"]
        profiles[int(entry["leadMinutes"])] = profile
    observatory = next(
        (
            entry
            for entry in history.get("observatoryByThresholdDbz", [])
            if int(entry.get("thresholdDbz", -999)) == threshold_dbz
        ),
        history.get("observatory", {}),
    )
    for horizon in observatory.get("horizons", []):
        for lead_minutes in range(
            int(horizon["windowStartMinutes"]),
            int(horizon["windowEndMinutes"]) + 1,
            5,
        ):
            profile = profiles.setdefault(lead_minutes, {})
            profile["operationalSampleCount"] = horizon["sampleCount"]
            profile["operationalCriticalSuccessIndex"] = horizon["criticalSuccessIndex"]
            profile["operationalMeanCriticalSuccessIndexSkill"] = horizon[
                "meanCriticalSuccessIndexSkill"
            ]
            profile["operationalStatus"] = horizon["status"]
    for candidate in history.get("shadowCandidates", []):
        for lead_quality in candidate.get("byLeadMinutes", []):
            lead_minutes = int(lead_quality["leadMinutes"])
            profile = profiles.setdefault(lead_minutes, {})
            profile.setdefault("shadowCandidates", []).append(
                {
                    "candidateId": candidate["candidateId"],
                    "forecastMethod": candidate["forecastMethod"],
                    **lead_quality,
                }
            )
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


def verification_forecast_changed(
    previous_state: dict[str, Any] | None,
    forecast: dict[str, Any],
) -> bool:
    """Detect a new source time or a verification contract rollout."""

    def contract(entry: dict[str, Any]) -> tuple[Any, ...]:
        candidates = tuple(
            sorted(
                (
                    candidate.get("candidateId"),
                    candidate.get("cubeKey"),
                    candidate.get("baselineCubeKey"),
                    candidate.get("minimumLeadMinutes"),
                    tuple(
                        int(frame.get("leadMinutes", 0))
                        for frame in candidate.get("frames", [])
                    ),
                )
                for candidate in entry.get("shadowCandidates", [])
            )
        )
        return (
            entry.get("schemaVersion", 1),
            entry.get("algorithmVersion"),
            candidates,
        )

    matching = [
        entry
        for entry in (previous_state or {}).get("forecasts", [])
        if entry.get("basedOnObservedAt") == forecast.get("basedOnObservedAt")
    ]
    return not matching or any(contract(entry) != contract(forecast) for entry in matching)
