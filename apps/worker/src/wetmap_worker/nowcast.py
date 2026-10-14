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

from .consistency import geographic_consistency_report
from .model import ATTRIBUTION, Frame

METHOD = "adaptive-optical-flow-persistence"
ALGORITHM_VERSION = "adaptive-optical-flow-persistence-v1"
SHADOW_CANDIDATE_ID = "trajectory-recency-flow-v1"
SHADOW_CANDIDATE_METHOD = "trajectory-optical-flow"
SHADOW_CANDIDATE_CUBE_KEY = "trajectoryRecency"
SHADOW_BASELINE_CUBE_KEY = "baselineOpticalFlow"
SPEED_CANDIDATE_ID = "trajectory-speed-bias-v2"
SPEED_CANDIDATE_METHOD = "trajectory-speed-corrected"
SPEED_CANDIDATE_CUBE_KEY = "trajectorySpeedCorrected"
SPEED_BASELINE_CUBE_KEY = "speedCorrectedBaseline"
SPEED_CORRECTION_FACTOR = 1.1
SHADOW_MINIMUM_LEAD_MINUTES = 40
SHADOW_VERIFICATION_LEAD_MINUTES = (40, 50, 60)
LEAD_MINUTES = tuple(range(5, 61, 5))
RISK_WIDTH = 128
RISK_HEIGHT = 96
POINT_GRID_WIDTH = 768
POINT_GRID_HEIGHT = 512
VERIFICATION_GRID_WIDTH = 256
VERIFICATION_GRID_HEIGHT = 171
VERIFICATION_RING_SLOTS = 16
ALERT_MINIMUM_VALIDATION_SAMPLES = 12
ALERT_MINIMUM_CSI = 0.2
ALERT_MINIMUM_SKILL = 0.0
ALERT_MINIMUM_CONFIDENCE = 0.55
SHADOW_PROMOTION_MINIMUM_SAMPLES = 48
SHADOW_PROMOTION_MINIMUM_EVENT_PIXELS = 1_000
SHADOW_PROMOTION_MINIMUM_CSI_IMPROVEMENT = 0.02
SHADOW_PROMOTION_MAX_FALSE_ALARM_RATE_INCREASE = 0.02


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _radar_signal(rgba: np.ndarray) -> np.ndarray:
    """Return the monotonic reflectivity signal encoded in frame alpha."""
    return cv2.GaussianBlur(rgba[..., 3], (5, 5), 0)


def _dense_motion(
    images: list[np.ndarray],
    intervals_minutes: list[float],
    *,
    recency_weighted: bool = False,
) -> np.ndarray:
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
    if recency_weighted:
        weights = np.arange(1, len(flows_per_minute) + 1, dtype=np.float32)
        flow = np.average(np.stack(flows_per_minute), axis=0, weights=weights)
    else:
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


def _advect_trajectory(rgba: np.ndarray, flow: np.ndarray, steps: float) -> np.ndarray:
    """Backtrace through a spatially varying flow field with a midpoint step."""
    height, width = rgba.shape[:2]
    x, y = np.meshgrid(
        np.arange(width, dtype=np.float32),
        np.arange(height, dtype=np.float32),
    )
    midpoint_x = x - flow[..., 0] * steps * 0.5
    midpoint_y = y - flow[..., 1] * steps * 0.5
    midpoint_flow_x = cv2.remap(
        flow[..., 0],
        midpoint_x,
        midpoint_y,
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )
    midpoint_flow_y = cv2.remap(
        flow[..., 1],
        midpoint_x,
        midpoint_y,
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return cv2.remap(
        rgba,
        x - midpoint_flow_x * steps,
        y - midpoint_flow_y * steps,
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )


def _shadow_candidate_quality(
    quality: dict[str, Any], candidate_id: str
) -> dict[str, Any]:
    return next(
        (
            candidate
            for candidate in quality.get("shadowCandidates", [])
            if candidate.get("candidateId") == candidate_id
        ),
        {},
    )


def _shadow_candidate_evidence(
    quality_by_lead: dict[int, dict[str, Any]],
    lead_minutes: int,
    candidate_id: str,
    forecast_method: str,
) -> dict[str, Any]:
    """Return direct or conservatively interpolated promotion evidence.

    Danish radar observations arrive on ten-minute anchors. Five-minute display
    frames between those anchors may only use the candidate when both adjacent
    anchors have independently passed the promotion gate.
    """
    if lead_minutes < SHADOW_MINIMUM_LEAD_MINUTES:
        return {}
    direct = _shadow_candidate_quality(
        quality_by_lead.get(lead_minutes, {}), candidate_id
    )
    if direct.get("safeToPromote") is True:
        return {**direct, "promotionEvidenceLeadMinutes": [lead_minutes]}
    lower_leads = [lead for lead in SHADOW_VERIFICATION_LEAD_MINUTES if lead < lead_minutes]
    upper_leads = [lead for lead in SHADOW_VERIFICATION_LEAD_MINUTES if lead > lead_minutes]
    if not lower_leads or not upper_leads:
        return direct
    lower_lead = max(lower_leads)
    upper_lead = min(upper_leads)
    lower = _shadow_candidate_quality(
        quality_by_lead.get(lower_lead, {}), candidate_id
    )
    upper = _shadow_candidate_quality(
        quality_by_lead.get(upper_lead, {}), candidate_id
    )
    if not (
        lower.get("safeToPromote") is True
        and upper.get("safeToPromote") is True
    ):
        return direct
    return {
        "candidateId": candidate_id,
        "forecastMethod": forecast_method,
        "safeToPromote": True,
        "sampleCount": min(
            int(lower.get("sampleCount", 0) or 0),
            int(upper.get("sampleCount", 0) or 0),
        ),
        "criticalSuccessIndex": min(
            float(lower.get("criticalSuccessIndex", 0) or 0),
            float(upper.get("criticalSuccessIndex", 0) or 0),
        ),
        "meanCriticalSuccessIndexSkill": min(
            float(lower.get("meanCriticalSuccessIndexSkill", 0) or 0),
            float(upper.get("meanCriticalSuccessIndexSkill", 0) or 0),
        ),
        "promotionEvidenceLeadMinutes": [lower_lead, upper_lead],
    }


def _risk_bucket(alpha: np.ndarray, rain_threshold_dbz: int = 20) -> str:
    reduced = cv2.resize(alpha, (RISK_WIDTH, RISK_HEIGHT), interpolation=cv2.INTER_AREA)
    categories = np.zeros(reduced.shape, dtype=np.uint8)
    intermediate_threshold_dbz = min(10, max(1, rain_threshold_dbz - 5))
    intermediate_threshold_alpha = round(
        45 + (intermediate_threshold_dbz + 10) * (175 / 60)
    )
    rain_threshold_alpha = round(45 + (rain_threshold_dbz + 10) * (175 / 60))
    # Processor alpha is monotonic in dBZ. Bucket 3 is the calibrated rain boundary.
    categories[reduced >= 74] = 1
    categories[reduced >= intermediate_threshold_alpha] = 2
    categories[reduced >= rain_threshold_alpha] = 3
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
    rain_threshold_dbz: int = 20,
    rain_radius_pixels: int = 1,
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
    trajectory_flow = _dense_motion(images, intervals_minutes, recency_weighted=True)
    generated_at = datetime.now(latest_time.tzinfo).isoformat().replace("+00:00", "Z")
    output_directory.mkdir(parents=True, exist_ok=True)

    frame_entries: list[dict[str, Any]] = []
    latest_prediction_time = latest_time.isoformat().replace("+00:00", "Z")
    risk_entries: list[dict[str, Any]] = [
        {
            "leadMinutes": 0,
            "predictedAt": latest_prediction_time,
            "intensity": _risk_bucket(latest[..., 3], rain_threshold_dbz),
            "confidence": 1.0,
            "validationSamples": None,
            "verificationCsi": None,
            "skillOverPersistence": None,
            "alertEligible": True,
        }
    ]
    point_frames = [_reflectivity_grid(latest[..., 3])]
    verification_frames = [
        _reflectivity_grid(latest[..., 3], VERIFICATION_GRID_WIDTH, VERIFICATION_GRID_HEIGHT)
    ]
    trajectory_verification_frames = [verification_frames[0]]
    baseline_verification_frames = [verification_frames[0]]
    speed_candidate_verification_frames = [verification_frames[0]]
    speed_baseline_verification_frames = [verification_frames[0]]
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
        trajectory_prediction = (
            _advect_trajectory(latest, trajectory_flow, lead_minutes)
            if lead_minutes >= SHADOW_MINIMUM_LEAD_MINUTES
            else optical_flow_prediction
        )
        speed_candidate_prediction = (
            _advect_trajectory(
                latest,
                trajectory_flow * SPEED_CORRECTION_FACTOR,
                lead_minutes,
            )
            if lead_minutes >= SHADOW_MINIMUM_LEAD_MINUTES
            else optical_flow_prediction
        )
        quality = (quality_by_lead or {}).get(lead_minutes, {})
        trajectory_quality = _shadow_candidate_evidence(
            quality_by_lead or {},
            lead_minutes,
            SHADOW_CANDIDATE_ID,
            SHADOW_CANDIDATE_METHOD,
        )
        speed_candidate_quality = _shadow_candidate_evidence(
            quality_by_lead or {},
            lead_minutes,
            SPEED_CANDIDATE_ID,
            SPEED_CANDIDATE_METHOD,
        )
        use_trajectory_candidate = trajectory_quality.get("safeToPromote") is True
        use_speed_candidate = speed_candidate_quality.get("safeToPromote") is True
        operational_status = quality.get("operationalStatus")
        raw_validation_samples = int(
            quality.get("opticalFlowSampleCount", quality.get("sampleCount", 0)) or 0
        )
        validation_samples = int(quality.get("operationalSampleCount", raw_validation_samples) or 0)
        raw_skill = quality.get(
            "opticalFlowMeanCriticalSuccessIndexSkill",
            quality.get("meanCriticalSuccessIndexSkill"),
        )
        skill = quality.get("operationalMeanCriticalSuccessIndexSkill", raw_skill)
        use_persistence = (
            raw_validation_samples >= 12
            and isinstance(raw_skill, (int, float))
            and raw_skill <= -0.02
        )
        if use_trajectory_candidate:
            incumbent_prediction = trajectory_prediction
            incumbent_method = SHADOW_CANDIDATE_METHOD
            incumbent_quality = trajectory_quality
        elif use_persistence:
            incumbent_prediction = latest.copy()
            incumbent_method = "persistence"
            incumbent_quality = None
        else:
            incumbent_prediction = optical_flow_prediction
            incumbent_method = "optical-flow"
            incumbent_quality = None
        speed_baseline_prediction = incumbent_prediction
        if use_speed_candidate:
            raw_prediction = speed_candidate_prediction
            forecast_method = SPEED_CANDIDATE_METHOD
            active_candidate_quality = speed_candidate_quality
        else:
            raw_prediction = incumbent_prediction
            forecast_method = incumbent_method
            active_candidate_quality = incumbent_quality
        if active_candidate_quality is not None:
            validation_samples = int(active_candidate_quality.get("sampleCount", 0) or 0)
            skill = active_candidate_quality.get("meanCriticalSuccessIndexSkill")
        heuristic_confidence = max(0.25, math.exp(-lead_minutes / 75))
        if active_candidate_quality is not None:
            verified_csi = active_candidate_quality.get("criticalSuccessIndex")
        elif use_persistence:
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
        if active_candidate_quality is None:
            verified_csi = quality.get("operationalCriticalSuccessIndex", verified_csi)
        effective_operational_status = (
            "verified" if active_candidate_quality is not None else operational_status
        )
        evidence_ready = effective_operational_status in (None, "verified", "degraded")
        if evidence_ready and validation_samples >= 6 and isinstance(verified_csi, (int, float)):
            empirical_confidence = min(0.95, max(0.2, 0.2 + 0.75 * verified_csi))
            empirical_weight = min(0.8, validation_samples / 60)
            confidence = (
                heuristic_confidence * (1 - empirical_weight)
                + empirical_confidence * empirical_weight
            )
        else:
            confidence = heuristic_confidence
        confidence = round(min(0.95, max(0.2, confidence)), 2)
        alert_eligible = (
            effective_operational_status in (None, "verified")
            and validation_samples >= ALERT_MINIMUM_VALIDATION_SAMPLES
            and isinstance(verified_csi, (int, float))
            and verified_csi >= ALERT_MINIMUM_CSI
            and isinstance(skill, (int, float))
            and skill >= ALERT_MINIMUM_SKILL
            and confidence >= ALERT_MINIMUM_CONFIDENCE
        )
        risk_entries.append(
            {
                "leadMinutes": lead_minutes,
                "predictedAt": (latest_time + timedelta(minutes=lead_minutes))
                .isoformat()
                .replace("+00:00", "Z"),
                "intensity": _risk_bucket(raw_prediction[..., 3], rain_threshold_dbz),
                "confidence": confidence,
                "validationSamples": validation_samples,
                "verificationCsi": verified_csi,
                "skillOverPersistence": skill,
                "alertEligible": alert_eligible,
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
        baseline_verification_frames.append(
            _reflectivity_grid(
                optical_flow_prediction[..., 3],
                VERIFICATION_GRID_WIDTH,
                VERIFICATION_GRID_HEIGHT,
            )
        )
        trajectory_verification_frames.append(
            _reflectivity_grid(
                trajectory_prediction[..., 3],
                VERIFICATION_GRID_WIDTH,
                VERIFICATION_GRID_HEIGHT,
            )
        )
        speed_candidate_verification_frames.append(
            _reflectivity_grid(
                speed_candidate_prediction[..., 3],
                VERIFICATION_GRID_WIDTH,
                VERIFICATION_GRID_HEIGHT,
            )
        )
        speed_baseline_verification_frames.append(
            _reflectivity_grid(
                speed_baseline_prediction[..., 3],
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
        "algorithmVersion": ALGORITHM_VERSION,
        "rainThresholdDbz": rain_threshold_dbz,
        "rainRadiusPixels": rain_radius_pixels,
        "basedOnObservedAt": latest_frame.observedAt,
        "sourceFrameCount": len(source_frames),
        "frames": frame_entries,
    }
    risk = {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "basedOnObservedAt": latest_frame.observedAt,
        "method": METHOD,
        "algorithmVersion": ALGORITHM_VERSION,
        "bounds": latest_frame.bounds,
        "width": RISK_WIDTH,
        "height": RISK_HEIGHT,
        "encoding": "uint8-base64",
        "thresholdsDbz": [
            0,
            min(10, max(1, rain_threshold_dbz - 5)),
            rain_threshold_dbz,
        ],
        "alertPolicy": {
            "minimumIntensityBucket": 3,
            "minimumReflectivityDbz": rain_threshold_dbz,
            "minimumValidationSamples": ALERT_MINIMUM_VALIDATION_SAMPLES,
            "minimumCriticalSuccessIndex": ALERT_MINIMUM_CSI,
            "minimumSkillOverPersistence": ALERT_MINIMUM_SKILL,
            "minimumConfidence": ALERT_MINIMUM_CONFIDENCE,
        },
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
        "algorithmVersion": ALGORITHM_VERSION,
        "bounds": latest_frame.bounds,
        "width": POINT_GRID_WIDTH,
        "height": POINT_GRID_HEIGHT,
        "frameCount": len(point_frame_entries),
        "encoding": "pixel-major-uint8-dbz-plus-32",
        "dataKey": f"nowcast/point-risk-{int(latest_time.timestamp() // 300) % 2}.bin",
        "neighborhoodRadiusPixels": rain_radius_pixels,
        "rainThresholdDbz": rain_threshold_dbz,
        "frames": point_frame_entries,
        "sha256": hashlib.sha256(point_grid_path.read_bytes()).hexdigest(),
    }
    (output_directory / "point-risk.json").write_text(
        json.dumps(point_grid, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    consistency = geographic_consistency_report(
        [source_paths[-1], *output_paths],
        point_cube,
        point_frame_entries,
        latest_frame.bounds,
        rain_threshold_dbz,
        rain_radius_pixels,
        latest_frame.observedAt,
    )
    (output_directory / "consistency.json").write_text(
        json.dumps(consistency, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    verification_cube_path = output_directory / "verification-cube.npz"
    np.savez_compressed(
        verification_cube_path,
        cube=np.stack(verification_frames, axis=-1),
        **{
            SHADOW_BASELINE_CUBE_KEY: np.stack(
                baseline_verification_frames, axis=-1
            ),
            SHADOW_CANDIDATE_CUBE_KEY: np.stack(
                trajectory_verification_frames, axis=-1
            ),
            SPEED_CANDIDATE_CUBE_KEY: np.stack(
                speed_candidate_verification_frames, axis=-1
            ),
            SPEED_BASELINE_CUBE_KEY: np.stack(
                speed_baseline_verification_frames, axis=-1
            ),
        },
    )
    verification_slot = int(latest_time.timestamp() // 300) % VERIFICATION_RING_SLOTS
    verification_forecast = {
        "schemaVersion": 2,
        "generatedAt": generated_at,
        "basedOnObservedAt": latest_frame.observedAt,
        "method": METHOD,
        "algorithmVersion": ALGORITHM_VERSION,
        "bounds": latest_frame.bounds,
        "width": VERIFICATION_GRID_WIDTH,
        "height": VERIFICATION_GRID_HEIGHT,
        "frameCount": len(point_frame_entries),
        "encoding": "npz-pixel-major-uint8-dbz-plus-32",
        "dataKey": f"nowcast/verification-cubes/cube-{verification_slot:02d}.npz",
        "frames": point_frame_entries,
        "shadowCandidates": [
            {
                "candidateId": SHADOW_CANDIDATE_ID,
                "forecastMethod": SHADOW_CANDIDATE_METHOD,
                "cubeKey": SHADOW_CANDIDATE_CUBE_KEY,
                "baselineCubeKey": SHADOW_BASELINE_CUBE_KEY,
                "minimumLeadMinutes": SHADOW_MINIMUM_LEAD_MINUTES,
                "frames": [
                    {**frame, "cubeFrameIndex": index}
                    for index, frame in enumerate(point_frame_entries)
                    if int(frame["leadMinutes"]) in SHADOW_VERIFICATION_LEAD_MINUTES
                ],
            },
            {
                "candidateId": SPEED_CANDIDATE_ID,
                "forecastMethod": SPEED_CANDIDATE_METHOD,
                "cubeKey": SPEED_CANDIDATE_CUBE_KEY,
                "baselineCubeKey": SPEED_BASELINE_CUBE_KEY,
                "minimumLeadMinutes": SHADOW_MINIMUM_LEAD_MINUTES,
                "frames": [
                    {**frame, "cubeFrameIndex": index}
                    for index, frame in enumerate(point_frame_entries)
                    if int(frame["leadMinutes"]) in SHADOW_VERIFICATION_LEAD_MINUTES
                ],
            },
        ],
        "sha256": hashlib.sha256(verification_cube_path.read_bytes()).hexdigest(),
    }
    (output_directory / "verification-forecast.json").write_text(
        json.dumps(verification_forecast, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    return manifest, risk, output_paths
