import base64
import json
from pathlib import Path

import numpy as np
from PIL import Image

from wetmap_worker.model import Frame
from wetmap_worker.nowcast import (
    ALGORITHM_VERSION,
    CALIBRATED_GATE_BASELINE_CUBE_KEY,
    CALIBRATED_GATE_CANDIDATE_CUBE_KEY,
    CALIBRATED_GATE_CANDIDATE_ID,
    CALIBRATED_GATE_CANDIDATE_METHOD,
    CALIBRATION_POLICY_VERSION,
    LEAD_MINUTES,
    POINT_GRID_HEIGHT,
    POINT_GRID_WIDTH,
    PROBABILITY_GATE_BASELINE_CUBE_KEY,
    PROBABILITY_GATE_CANDIDATE_CUBE_KEY,
    PROBABILITY_GATE_CANDIDATE_ID,
    PROBABILITY_GATE_CANDIDATE_METHOD,
    REGIME_BASELINE_CUBE_KEY,
    REGIME_CANDIDATE_CUBE_KEY,
    REGIME_CANDIDATE_ID,
    REGIME_CANDIDATE_METHOD,
    REGIME_PROBABILITY_CUBE_KEY,
    RISK_HEIGHT,
    RISK_WIDTH,
    SHADOW_BASELINE_CUBE_KEY,
    SHADOW_CANDIDATE_CUBE_KEY,
    SHADOW_CANDIDATE_ID,
    SHADOW_CANDIDATE_METHOD,
    SPEED_BASELINE_CUBE_KEY,
    SPEED_CANDIDATE_CUBE_KEY,
    SPEED_CANDIDATE_ID,
    SPEED_CANDIDATE_METHOD,
    _probability_gated_prediction,
    _calibrated_probability_gate_for_lead,
    _regime_selector,
    generate_nowcast,
)


def _frame(path: Path, x: int) -> None:
    rgba = np.zeros((72, 96, 4), dtype=np.uint8)
    rgba[25:45, x : x + 20, :3] = [52, 120, 229]
    rgba[25:45, x : x + 20, 3] = 133
    Image.fromarray(rgba).save(path, "WEBP", lossless=True)


def _radar_array(x: int) -> np.ndarray:
    rgba = np.ones((72, 96, 4), dtype=np.uint8)
    rgba[25:45, x : x + 20, 3] = 180
    return rgba


def test_regime_selector_uses_only_recent_hindcast_skill() -> None:
    selector = _regime_selector(
        [_radar_array(20), _radar_array(24), _radar_array(28)],
        [5.0, 5.0],
        20,
    )

    assert selector["selectedMember"] in {
        "optical-flow",
        "trajectory",
        "speed-corrected",
    }
    assert selector["scores"][selector["selectedMember"]] > selector["scores"]["persistence"]
    assert selector["eventPixelCount"] >= 25
    assert abs(sum(selector["weights"].values()) - 1) < 0.00001


def test_regime_selector_fails_closed_to_persistence_without_motion_gain() -> None:
    static = _radar_array(24)
    selector = _regime_selector([static, static.copy(), static.copy()], [5.0, 5.0], 20)

    assert selector["selectedMember"] == "persistence"
    assert selector["scores"]["persistence"] == 1.0


def test_probability_gate_removes_only_low_agreement_rain() -> None:
    prediction = _radar_array(24)
    probability = np.zeros(prediction.shape[:2], dtype=np.uint8)
    probability[25:45, 24:34] = 80
    probability[25:45, 34:44] = 40

    gated = _probability_gated_prediction(prediction, probability, 0.6, 20)

    assert np.all(gated[25:45, 24:34, 3] == 180)
    assert np.all(gated[25:45, 34:44, 3] == 1)
    assert np.all(gated[25:45, 34:44, :3] == 0)
    assert np.all(prediction[25:45, 34:44, 3] == 180)


def test_calibrated_gate_uses_only_completed_prior_calibration() -> None:
    cold = _calibrated_probability_gate_for_lead({}, 40)
    calibrated_quality = {
        40: {
            "shadowCandidates": [
                {
                    "candidateId": CALIBRATED_GATE_CANDIDATE_ID,
                    "probabilityCalibration": {
                        "status": "calibrated",
                        "sampleCount": 64,
                        "selectedMinimumRainProbability": 0.2,
                    },
                }
            ]
        },
        50: {
            "shadowCandidates": [
                {
                    "candidateId": CALIBRATED_GATE_CANDIDATE_ID,
                    "probabilityCalibration": {
                        "status": "calibrated",
                        "sampleCount": 60,
                        "selectedMinimumRainProbability": 0.3,
                    },
                }
            ]
        },
    }

    assert cold == (0.25, "cold-start", 0)
    assert _calibrated_probability_gate_for_lead(calibrated_quality, 40) == (
        0.2,
        "rolling-calibration",
        64,
    )
    assert _calibrated_probability_gate_for_lead(calibrated_quality, 45) == (
        0.25,
        "rolling-calibration",
        60,
    )


def test_generates_hour_of_optical_flow_frames_and_compact_risk_grid(tmp_path: Path) -> None:
    paths = [tmp_path / f"source-{index}.webp" for index in range(3)]
    for path, x in zip(paths, [24, 28, 32], strict=True):
        _frame(path, x)
    frames = [
        Frame(
            id=f"frame-{index}",
            observedAt=f"2026-10-11T12:{index * 5:02d}:00Z",
            fetchedAt="2026-10-11T12:11:00Z",
            url=f"/frames/{path.name}",
            bounds=[7, 54, 13, 58],
            product="DBZH",
            unit="dBZ",
            sha256=str(index),
        )
        for index, path in enumerate(paths)
    ]

    manifest, risk, outputs = generate_nowcast(
        paths,
        frames,
        tmp_path / "nowcast",
        rain_threshold_dbz=15,
        rain_radius_pixels=5,
    )

    assert manifest["method"] == "adaptive-optical-flow-persistence"
    assert manifest["algorithmVersion"] == ALGORITHM_VERSION
    assert manifest["basedOnObservedAt"] == frames[-1].observedAt
    assert manifest["rainThresholdDbz"] == 15
    assert manifest["rainRadiusPixels"] == 5
    assert [frame["leadMinutes"] for frame in manifest["frames"]] == list(LEAD_MINUTES)
    assert len(outputs) == len(LEAD_MINUTES)
    assert all(path.exists() for path in outputs)
    assert manifest["frames"][0]["confidence"] > manifest["frames"][-1]["confidence"]
    assert risk["width"] == RISK_WIDTH
    assert risk["height"] == RISK_HEIGHT
    assert risk["thresholdsDbz"] == [0, 10, 15]
    assert risk["alertPolicy"]["minimumReflectivityDbz"] == 15
    decoded = base64.b64decode(risk["frames"][0]["intensity"])
    assert len(decoded) == RISK_WIDTH * RISK_HEIGHT
    assert max(decoded) >= 2
    assert risk["frames"][0]["leadMinutes"] == 0
    assert risk["frames"][0]["alertEligible"] is True
    assert risk["frames"][1]["alertEligible"] is False
    point_metadata = json.loads((tmp_path / "nowcast/point-risk.json").read_text())
    point_grid = (tmp_path / "nowcast/point-risk.bin").read_bytes()
    assert point_metadata["frameCount"] == len(LEAD_MINUTES) + 1
    assert point_metadata["frames"][0]["leadMinutes"] == 0
    assert point_metadata["dataKey"].startswith("nowcast/point-risk-")
    assert point_metadata["rainThresholdDbz"] == 15
    assert point_metadata["neighborhoodRadiusPixels"] == 5
    assert len(point_grid) == POINT_GRID_WIDTH * POINT_GRID_HEIGHT * (len(LEAD_MINUTES) + 1)
    consistency = json.loads((tmp_path / "nowcast/consistency.json").read_text())
    assert consistency["status"] == "verified"
    assert consistency["locationCount"] >= 18
    assert consistency["frameCount"] == len(LEAD_MINUTES) + 1
    assert consistency["comparisonCount"] == consistency["locationCount"] * (len(LEAD_MINUTES) + 1)
    assert consistency["valueMismatchCount"] == 0
    assert consistency["rainClassificationMismatchCount"] == 0
    assert consistency["rainThresholdDbz"] == 15
    assert consistency["spatialRadiusPixels"] == 5
    verification_metadata = json.loads(
        (tmp_path / "nowcast/verification-forecast.json").read_text()
    )
    assert verification_metadata["schemaVersion"] == 2
    assert verification_metadata["dataKey"].startswith("nowcast/verification-cubes/cube-")
    trajectory, speed, regime, probability_gate, calibrated_gate = verification_metadata[
        "shadowCandidates"
    ]
    assert trajectory["candidateId"] == SHADOW_CANDIDATE_ID
    assert trajectory["forecastMethod"] == SHADOW_CANDIDATE_METHOD
    assert trajectory["baselineCubeKey"] == SHADOW_BASELINE_CUBE_KEY
    assert [frame["leadMinutes"] for frame in trajectory["frames"]] == [40, 50, 60]
    assert speed["candidateId"] == SPEED_CANDIDATE_ID
    assert speed["forecastMethod"] == SPEED_CANDIDATE_METHOD
    assert speed["baselineCubeKey"] == SPEED_BASELINE_CUBE_KEY
    assert [frame["leadMinutes"] for frame in speed["frames"]] == [40, 50, 60]
    assert regime["candidateId"] == REGIME_CANDIDATE_ID
    assert regime["forecastMethod"] == REGIME_CANDIDATE_METHOD
    assert regime["baselineCubeKey"] == REGIME_BASELINE_CUBE_KEY
    assert regime["probabilityCubeKey"] == REGIME_PROBABILITY_CUBE_KEY
    assert regime["probabilityThresholdDbz"] == 15
    assert regime["selector"]["selectedMember"] in {
        "persistence",
        "optical-flow",
        "trajectory",
        "speed-corrected",
    }
    assert abs(sum(regime["selector"]["weights"].values()) - 1) < 0.00001
    assert [frame["leadMinutes"] for frame in regime["frames"]] == [40, 50, 60]
    assert probability_gate["candidateId"] == PROBABILITY_GATE_CANDIDATE_ID
    assert probability_gate["forecastMethod"] == PROBABILITY_GATE_CANDIDATE_METHOD
    assert probability_gate["baselineCubeKey"] == PROBABILITY_GATE_BASELINE_CUBE_KEY
    assert probability_gate["probabilityCubeKey"] == REGIME_PROBABILITY_CUBE_KEY
    assert probability_gate["probabilityGateByLeadMinutes"] == {
        "40": 0.5,
        "50": 0.6,
        "60": 0.65,
    }
    assert [frame["minimumRainProbability"] for frame in probability_gate["frames"]] == [
        0.5,
        0.6,
        0.65,
    ]
    assert calibrated_gate["candidateId"] == CALIBRATED_GATE_CANDIDATE_ID
    assert calibrated_gate["forecastMethod"] == CALIBRATED_GATE_CANDIDATE_METHOD
    assert calibrated_gate["baselineCubeKey"] == CALIBRATED_GATE_BASELINE_CUBE_KEY
    assert calibrated_gate["calibrationBaseCubeKey"] == REGIME_CANDIDATE_CUBE_KEY
    assert calibrated_gate["probabilityCubeKey"] == REGIME_PROBABILITY_CUBE_KEY
    assert calibrated_gate["calibrationPolicyVersion"] == CALIBRATION_POLICY_VERSION
    assert calibrated_gate["probabilityCalibrationThresholds"][0] == 0
    assert [frame["minimumRainProbability"] for frame in calibrated_gate["frames"]] == [
        0.25,
        0.25,
        0.25,
    ]
    assert all(frame["calibrationSource"] == "cold-start" for frame in calibrated_gate["frames"])
    with np.load(tmp_path / "nowcast/verification-cube.npz") as archive:
        assert archive["cube"].shape[-1] == len(LEAD_MINUTES) + 1
        assert archive[SHADOW_CANDIDATE_CUBE_KEY].shape == archive["cube"].shape
        assert archive[SHADOW_BASELINE_CUBE_KEY].shape == archive["cube"].shape
        assert archive[SPEED_CANDIDATE_CUBE_KEY].shape == archive["cube"].shape
        assert archive[SPEED_BASELINE_CUBE_KEY].shape == archive["cube"].shape
        assert archive[REGIME_CANDIDATE_CUBE_KEY].shape == archive["cube"].shape
        assert archive[REGIME_BASELINE_CUBE_KEY].shape == archive["cube"].shape
        assert archive[REGIME_PROBABILITY_CUBE_KEY].shape == archive["cube"].shape
        assert int(archive[REGIME_PROBABILITY_CUBE_KEY].min()) >= 0
        assert int(archive[REGIME_PROBABILITY_CUBE_KEY].max()) <= 100
        assert archive[PROBABILITY_GATE_CANDIDATE_CUBE_KEY].shape == archive["cube"].shape
        assert archive[PROBABILITY_GATE_BASELINE_CUBE_KEY].shape == archive["cube"].shape
        assert archive[CALIBRATED_GATE_CANDIDATE_CUBE_KEY].shape == archive["cube"].shape
        assert archive[CALIBRATED_GATE_BASELINE_CUBE_KEY].shape == archive["cube"].shape


def test_uses_verified_persistence_without_attenuating_reflectivity(tmp_path: Path) -> None:
    paths = [tmp_path / f"source-{index}.webp" for index in range(3)]
    for path, x in zip(paths, [24, 28, 32], strict=True):
        _frame(path, x)
    frames = [
        Frame(
            id=f"frame-{index}",
            observedAt=f"2026-10-11T12:{index * 5:02d}:00Z",
            fetchedAt="2026-10-11T12:11:00Z",
            url=f"/frames/{path.name}",
            bounds=[7, 54, 13, 58],
            product="DBZH",
            unit="dBZ",
            sha256=str(index),
        )
        for index, path in enumerate(paths)
    ]

    manifest, risk, outputs = generate_nowcast(
        paths,
        frames,
        tmp_path / "adaptive",
        {
            5: {
                "sampleCount": 20,
                "criticalSuccessIndex": 0.3,
                "meanCriticalSuccessIndexSkill": -0.08,
            },
            10: {
                "sampleCount": 20,
                "criticalSuccessIndex": 0.6,
                "meanCriticalSuccessIndexSkill": 0.12,
                "operationalSampleCount": 20,
                "operationalCriticalSuccessIndex": 0.6,
                "operationalMeanCriticalSuccessIndexSkill": 0.12,
                "operationalStatus": "awaiting-rain",
            },
        },
    )

    assert manifest["frames"][0]["forecastMethod"] == "persistence"
    assert manifest["frames"][1]["forecastMethod"] == "optical-flow"
    assert manifest["frames"][0]["skillOverPersistence"] == -0.08
    assert manifest["frames"][0]["confidence"] >= 0.55
    assert risk["frames"][2]["alertEligible"] is False
    with np.load(tmp_path / "adaptive/verification-cube.npz") as archive:
        cube = archive["cube"]
        assert np.array_equal(cube[..., 0], cube[..., 1])
        assert not np.array_equal(cube[..., 0], cube[..., 2])
    # Confidence remains metadata and no longer weakens the forecast's dBZ signal.
    first_alpha = np.asarray(Image.open(outputs[0]).convert("RGBA"))[..., 3]
    assert int(first_alpha.max()) == 133


def test_promotes_verified_anchors_and_only_safe_intermediate_long_horizons(
    tmp_path: Path,
) -> None:
    paths = [tmp_path / f"source-{index}.webp" for index in range(3)]
    for path, x in zip(paths, [24, 28, 32], strict=True):
        _frame(path, x)
    frames = [
        Frame(
            id=f"frame-{index}",
            observedAt=f"2026-10-11T12:{index * 5:02d}:00Z",
            fetchedAt="2026-10-11T12:11:00Z",
            url=f"/frames/{path.name}",
            bounds=[7, 54, 13, 58],
            product="DBZH",
            unit="dBZ",
            sha256=str(index),
        )
        for index, path in enumerate(paths)
    ]
    candidate_quality = {
        "candidateId": SHADOW_CANDIDATE_ID,
        "forecastMethod": SHADOW_CANDIDATE_METHOD,
        "sampleCount": 48,
        "criticalSuccessIndex": 0.48,
        "meanCriticalSuccessIndexSkill": 0.11,
        "safeToPromote": True,
    }
    speed_candidate_quality = {
        **candidate_quality,
        "candidateId": SPEED_CANDIDATE_ID,
        "forecastMethod": SPEED_CANDIDATE_METHOD,
        "criticalSuccessIndex": 0.52,
        "meanCriticalSuccessIndexSkill": 0.14,
    }
    probability_gate_candidate_quality = {
        **candidate_quality,
        "candidateId": PROBABILITY_GATE_CANDIDATE_ID,
        "forecastMethod": PROBABILITY_GATE_CANDIDATE_METHOD,
        "criticalSuccessIndex": 0.56,
        "meanCriticalSuccessIndexSkill": 0.18,
    }
    calibrated_gate_candidate_quality = {
        **candidate_quality,
        "candidateId": CALIBRATED_GATE_CANDIDATE_ID,
        "forecastMethod": CALIBRATED_GATE_CANDIDATE_METHOD,
        "criticalSuccessIndex": 0.59,
        "meanCriticalSuccessIndexSkill": 0.2,
    }

    manifest, risk, _outputs = generate_nowcast(
        paths,
        frames,
        tmp_path / "promoted",
        {
            40: {
                "operationalStatus": "degraded",
                "operationalCriticalSuccessIndex": 0.3,
                "shadowCandidates": [
                    candidate_quality,
                    speed_candidate_quality,
                    probability_gate_candidate_quality,
                    calibrated_gate_candidate_quality,
                ],
            },
            50: {
                "shadowCandidates": [
                    {
                        **candidate_quality,
                        "sampleCount": 52,
                        "criticalSuccessIndex": 0.48,
                        "meanCriticalSuccessIndexSkill": 0.09,
                    },
                    {
                        **speed_candidate_quality,
                        "sampleCount": 52,
                        "criticalSuccessIndex": 0.51,
                        "meanCriticalSuccessIndexSkill": 0.12,
                    },
                    {
                        **probability_gate_candidate_quality,
                        "sampleCount": 52,
                        "criticalSuccessIndex": 0.55,
                        "meanCriticalSuccessIndexSkill": 0.16,
                    },
                    {
                        **calibrated_gate_candidate_quality,
                        "sampleCount": 52,
                        "criticalSuccessIndex": 0.58,
                        "meanCriticalSuccessIndexSkill": 0.19,
                    },
                ]
            },
        },
    )

    by_lead = {frame["leadMinutes"]: frame for frame in manifest["frames"]}
    assert by_lead[40]["forecastMethod"] == CALIBRATED_GATE_CANDIDATE_METHOD
    assert by_lead[45]["forecastMethod"] == CALIBRATED_GATE_CANDIDATE_METHOD
    assert by_lead[45]["verificationCsi"] == 0.58
    assert by_lead[45]["skillOverPersistence"] == 0.19
    assert by_lead[45]["validationSamples"] == 48
    assert by_lead[50]["forecastMethod"] == CALIBRATED_GATE_CANDIDATE_METHOD
    assert by_lead[55]["forecastMethod"] == "optical-flow"
    assert risk["frames"][9]["alertEligible"] is True
    with np.load(tmp_path / "promoted/verification-cube.npz") as archive:
        assert np.array_equal(
            archive[SPEED_BASELINE_CUBE_KEY][..., 10],
            archive[SHADOW_CANDIDATE_CUBE_KEY][..., 10],
        )
        assert not np.array_equal(
            archive["cube"][..., 10],
            archive[SPEED_BASELINE_CUBE_KEY][..., 10],
        )
        assert np.array_equal(
            archive[PROBABILITY_GATE_BASELINE_CUBE_KEY][..., 10],
            archive[SPEED_CANDIDATE_CUBE_KEY][..., 10],
        )
        assert np.array_equal(
            archive[CALIBRATED_GATE_BASELINE_CUBE_KEY][..., 10],
            archive[PROBABILITY_GATE_CANDIDATE_CUBE_KEY][..., 10],
        )
