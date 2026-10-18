import json
from pathlib import Path

import numpy as np
from PIL import Image

from wetmap_worker.nowcast import (
    ALGORITHM_VERSION,
    PROBABILITY_GATE_CANDIDATE_ID,
    PROBABILITY_GATE_CANDIDATE_METHOD,
    REGIME_CANDIDATE_ID,
    REGIME_CANDIDATE_METHOD,
    POINT_GRID_HEIGHT,
    POINT_GRID_WIDTH,
    SHADOW_CANDIDATE_ID,
    SHADOW_CANDIDATE_METHOD,
    SPEED_CANDIDATE_ID,
    SPEED_CANDIDATE_METHOD,
)
from wetmap_worker.verification import (
    append_verification_history,
    public_verification_report,
    quality_by_lead,
    update_verification_state,
    verification_forecast_changed,
    verification_candidates,
    verify_previous_nowcast,
)


def test_scores_previous_nowcast_against_new_observation(tmp_path: Path) -> None:
    observed = np.zeros((64, 96, 4), dtype=np.uint8)
    observed[..., 3] = 1
    observed[20:40, 30:55, 3] = 198  # Approximately 20 dBZ.
    observed_path = tmp_path / "observed.webp"
    Image.fromarray(observed).save(observed_path, "WEBP", lossless=True)

    frame_count = 2
    cube = np.full((POINT_GRID_HEIGHT, POINT_GRID_WIDTH, frame_count), 14, dtype=np.uint8)
    actual_echo = (
        np.asarray(
            Image.open(observed_path).convert("RGBA").resize((POINT_GRID_WIDTH, POINT_GRID_HEIGHT))
        )[..., 3]
        >= 190
    )
    cube[..., 1][actual_echo] = 52
    cube_path = tmp_path / "point-risk.bin"
    cube_path.write_bytes(cube.tobytes())
    metadata_path = tmp_path / "point-risk.json"
    metadata_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "basedOnObservedAt": "2026-10-11T11:55:00Z",
                "bounds": [7, 54, 13, 58],
                "width": POINT_GRID_WIDTH,
                "height": POINT_GRID_HEIGHT,
                "frameCount": frame_count,
                "encoding": "pixel-major-uint8-dbz-plus-32",
                "frames": [
                    {
                        "leadMinutes": 0,
                        "predictedAt": "2026-10-11T11:55:00Z",
                        "confidence": 1,
                    },
                    {
                        "leadMinutes": 5,
                        "predictedAt": "2026-10-11T12:00:00Z",
                        "confidence": 0.94,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    result = verify_previous_nowcast(
        metadata_path,
        cube_path,
        observed_path,
        "2026-10-11T12:00:00Z",
    )

    assert result is not None
    assert result["leadMinutes"] == 5
    assert result["hits"] > 0
    assert result["criticalSuccessIndex"] > 0.9
    assert result["persistenceCriticalSuccessIndex"] is not None
    assert result["criticalSuccessIndexSkill"] is not None
    assert [score["thresholdDbz"] for score in result["thresholdScores"]] == [
        5,
        10,
        15,
        20,
        35,
    ]
    history = append_verification_history(tmp_path / "history.json", result)
    assert history["sampleCount"] == 1
    assert history["meanCriticalSuccessIndex"] > 0.9
    assert history["meanCriticalSuccessIndexSkill"] is not None


def test_groups_multiple_forecast_horizons_and_keeps_public_payload_bounded(
    tmp_path: Path,
) -> None:
    base = {
        "verifiedAt": "2026-10-11T12:31:00Z",
        "predictedAt": "2026-10-11T12:30:00Z",
        "observedAt": "2026-10-11T12:30:00Z",
        "thresholdDbz": 20,
        "validPixels": 100,
        "hits": 50,
        "misses": 10,
        "falseAlarms": 20,
        "correctNegatives": 20,
        "precision": 0.7143,
        "recall": 0.8333,
        "criticalSuccessIndex": 0.625,
        "dbzMeanAbsoluteError": 4.0,
        "persistenceCriticalSuccessIndex": 0.5,
        "criticalSuccessIndexSkill": 0.125,
        "forecastMethod": "optical-flow",
        "algorithmVersion": ALGORITHM_VERSION,
        "thresholdScores": [
            {
                "thresholdDbz": 15,
                "validPixels": 100,
                "hits": 55,
                "misses": 5,
                "falseAlarms": 15,
                "correctNegatives": 25,
                "precision": 0.7857,
                "recall": 0.9167,
                "criticalSuccessIndex": 0.7333,
                "dbzMeanAbsoluteError": 3.0,
                "persistenceCriticalSuccessIndex": 0.55,
                "criticalSuccessIndexSkill": 0.1833,
            }
        ],
    }
    results = [
        {**base, "basedOnObservedAt": "2026-10-11T12:15:00Z", "leadMinutes": 15},
        {**base, "basedOnObservedAt": "2026-10-11T12:00:00Z", "leadMinutes": 30},
    ]

    history = append_verification_history(tmp_path / "missing.json", results)
    assert history["sampleCount"] == 2
    assert [row["leadMinutes"] for row in history["byLeadMinutes"]] == [15, 30]
    public = public_verification_report(history, recent_results=1)
    assert public["sampleCount"] == 2
    assert public["returnedResultCount"] == 1
    assert public["schemaVersion"] == 5
    assert public["observatory"]["targetHorizonMinutes"] == [15, 30, 45, 60]
    assert public["observatory"]["horizons"][0]["sampleCount"] == 1
    profile = quality_by_lead(history)[15]
    assert profile["opticalFlowSampleCount"] == 1
    assert profile["opticalFlowMeanCriticalSuccessIndexSkill"] == 0.125
    assert profile["operationalSampleCount"] == 1
    assert profile["operationalStatus"] == "collecting"
    threshold_profile = quality_by_lead(history, 15)[15]
    assert threshold_profile["operationalSampleCount"] == 1
    assert threshold_profile["operationalCriticalSuccessIndex"] == 0.7333
    assert [entry["thresholdDbz"] for entry in history["observatoryByThresholdDbz"]] == [
        5,
        10,
        15,
        20,
    ]


def test_observatory_uses_horizon_windows_and_requires_rain_evidence(
    tmp_path: Path,
) -> None:
    base = {
        "verifiedAt": "2026-10-12T12:31:00Z",
        "basedOnObservedAt": "2026-10-12T12:00:00Z",
        "predictedAt": "2026-10-12T12:30:00Z",
        "observedAt": "2026-10-12T12:30:00Z",
        "thresholdDbz": 20,
        "validPixels": 1000,
        "hits": 0,
        "misses": 0,
        "falseAlarms": 0,
        "correctNegatives": 1000,
        "precision": None,
        "recall": None,
        "criticalSuccessIndex": None,
        "dbzMeanAbsoluteError": 0.0,
        "persistenceCriticalSuccessIndex": None,
        "criticalSuccessIndexSkill": None,
        "forecastMethod": "optical-flow",
        "algorithmVersion": ALGORITHM_VERSION,
        "thresholdScores": [],
    }
    dry_results = [
        {**base, "leadMinutes": lead}
        for lead in (10, 20, 25, 35, 40, 50, 55, 60)
        for _sample in range(6)
    ]

    dry_report = append_verification_history(tmp_path / "dry-history.json", dry_results)

    assert dry_report["observatory"]["overallStatus"] == "awaiting-rain"
    assert all(
        horizon["status"] == "awaiting-rain" for horizon in dry_report["observatory"]["horizons"]
    )
    assert dry_report["observatory"]["horizons"][0]["sampleCount"] == 12

    wet_base = {
        **base,
        "hits": 80,
        "misses": 10,
        "falseAlarms": 10,
        "correctNegatives": 900,
        "precision": 0.8889,
        "recall": 0.8889,
        "criticalSuccessIndex": 0.8,
        "persistenceCriticalSuccessIndex": 0.6,
        "criticalSuccessIndexSkill": 0.2,
        "dbzMeanAbsoluteError": 2.0,
    }
    wet_results = [
        {**wet_base, "leadMinutes": lead}
        for lead in (10, 20, 25, 35, 40, 50, 55, 60)
        for _sample in range(6)
    ]
    wet_report = append_verification_history(tmp_path / "wet-history.json", wet_results)

    assert wet_report["observatory"]["overallStatus"] == "verified"
    assert wet_report["observatory"]["verifiedHorizonCount"] == 4
    assert all(horizon["meetsQualityGate"] for horizon in wet_report["observatory"]["horizons"])
    assert wet_report["observatory"]["horizons"][0]["falseAlarmRate"] == 0.1111
    assert wet_report["observatory"]["horizons"][0]["missRate"] == 0.1111


def test_tracks_pending_forecasts_for_every_matching_horizon() -> None:
    forecasts = []
    for minute, lead in ((15, 15), (0, 30)):
        forecasts.append(
            {
                "generatedAt": f"2026-10-11T12:{minute:02d}:30Z",
                "basedOnObservedAt": f"2026-10-11T12:{minute:02d}:00Z",
                "dataKey": f"nowcast/verification-cubes/cube-{minute:02d}.npz",
                "frames": [
                    {
                        "leadMinutes": lead,
                        "predictedAt": "2026-10-11T12:30:00Z",
                    }
                ],
            }
        )
    state = {"forecasts": forecasts}

    candidates = verification_candidates(state, "2026-10-11T12:30:00Z")

    assert len(candidates) == 2
    updated = update_verification_state(
        state,
        {
            "generatedAt": "2026-10-11T12:30:30Z",
            "basedOnObservedAt": "2026-10-11T12:30:00Z",
            "frames": [],
        },
    )
    assert len(updated["forecasts"]) == 3


def test_republishes_a_new_verification_contract_for_the_same_observation() -> None:
    previous = {
        "forecasts": [
            {
                "schemaVersion": 1,
                "algorithmVersion": ALGORITHM_VERSION,
                "basedOnObservedAt": "2026-10-11T12:00:00Z",
            }
        ]
    }
    upgraded = {
        "schemaVersion": 2,
        "algorithmVersion": ALGORITHM_VERSION,
        "basedOnObservedAt": "2026-10-11T12:00:00Z",
        "shadowCandidates": [
            {
                "candidateId": SHADOW_CANDIDATE_ID,
                "cubeKey": "trajectoryRecency",
                "baselineCubeKey": "baselineOpticalFlow",
                "minimumLeadMinutes": 40,
                "frames": [{"leadMinutes": 40}, {"leadMinutes": 50}, {"leadMinutes": 60}],
            }
        ],
    }

    assert verification_forecast_changed(previous, upgraded) is True
    assert verification_forecast_changed({"forecasts": [upgraded]}, upgraded) is False
    changed_anchors = {
        **upgraded,
        "shadowCandidates": [
            {
                **upgraded["shadowCandidates"][0],
                "frames": [{"leadMinutes": 45}, {"leadMinutes": 55}],
            }
        ],
    }
    assert verification_forecast_changed({"forecasts": [upgraded]}, changed_anchors) is True
    gated = {
        **upgraded,
        "shadowCandidates": [
            {
                "candidateId": PROBABILITY_GATE_CANDIDATE_ID,
                "cubeKey": "probabilityGatedEnsemble",
                "baselineCubeKey": "probabilityGatedBaseline",
                "probabilityCubeKey": "regimeRainProbability",
                "minimumLeadMinutes": 40,
                "probabilityGateByLeadMinutes": {"40": 0.5, "50": 0.6, "60": 0.65},
                "frames": [
                    {"leadMinutes": 40, "minimumRainProbability": 0.5},
                    {"leadMinutes": 50, "minimumRainProbability": 0.6},
                    {"leadMinutes": 60, "minimumRainProbability": 0.65},
                ],
            }
        ],
    }
    changed_gate = {
        **gated,
        "shadowCandidates": [
            {
                **gated["shadowCandidates"][0],
                "probabilityGateByLeadMinutes": {"40": 0.55, "50": 0.6, "60": 0.65},
                "frames": [
                    {"leadMinutes": 40, "minimumRainProbability": 0.55},
                    {"leadMinutes": 50, "minimumRainProbability": 0.6},
                    {"leadMinutes": 60, "minimumRainProbability": 0.65},
                ],
            }
        ],
    }
    assert verification_forecast_changed({"forecasts": [gated]}, gated) is False
    assert verification_forecast_changed({"forecasts": [gated]}, changed_gate) is True


def test_keeps_algorithm_versions_in_separate_quality_cohorts(tmp_path: Path) -> None:
    base = {
        "verifiedAt": "2026-10-12T12:10:00Z",
        "basedOnObservedAt": "2026-10-12T12:00:00Z",
        "predictedAt": "2026-10-12T12:10:00Z",
        "observedAt": "2026-10-12T12:10:00Z",
        "leadMinutes": 10,
        "thresholdDbz": 20,
        "validPixels": 100,
        "hits": 8,
        "misses": 2,
        "falseAlarms": 2,
        "correctNegatives": 88,
        "precision": 0.8,
        "recall": 0.8,
        "criticalSuccessIndex": 0.6667,
        "dbzMeanAbsoluteError": 3.0,
        "persistenceCriticalSuccessIndex": 0.5,
        "criticalSuccessIndexSkill": 0.1667,
        "forecastMethod": "optical-flow",
        "thresholdScores": [],
    }
    history_path = tmp_path / "history.json"
    history_path.write_text(json.dumps({"results": [base]}), encoding="utf-8")
    current = {
        **base,
        "verifiedAt": "2026-10-12T12:15:00Z",
        "basedOnObservedAt": "2026-10-12T12:05:00Z",
        "predictedAt": "2026-10-12T12:15:00Z",
        "observedAt": "2026-10-12T12:15:00Z",
        "algorithmVersion": ALGORITHM_VERSION,
    }

    report = append_verification_history(history_path, current)
    public = public_verification_report(report)

    assert report["algorithmVersion"] == ALGORITHM_VERSION
    assert report["sampleCount"] == 1
    assert report["totalSampleCount"] == 2
    assert len(report["byAlgorithmVersion"]) == 2
    assert public["returnedResultCount"] == 1
    assert public["results"][0]["algorithmVersion"] == ALGORITHM_VERSION


def test_does_not_calibrate_current_forecasts_from_legacy_results(tmp_path: Path) -> None:
    legacy = {
        "verifiedAt": "2026-10-12T12:10:00Z",
        "basedOnObservedAt": "2026-10-12T12:00:00Z",
        "predictedAt": "2026-10-12T12:10:00Z",
        "observedAt": "2026-10-12T12:10:00Z",
        "leadMinutes": 10,
        "validPixels": 100,
        "hits": 8,
        "misses": 2,
        "falseAlarms": 2,
        "criticalSuccessIndex": 0.6667,
        "criticalSuccessIndexSkill": 0.1667,
        "forecastMethod": "optical-flow",
        "thresholdScores": [],
    }

    report = append_verification_history(tmp_path / "history.json", legacy)

    assert report["algorithmVersion"] == "legacy-unversioned"
    assert quality_by_lead(report) == {}


def test_scores_shadow_candidate_against_the_same_observation(tmp_path: Path) -> None:
    observed = np.zeros((6, 8, 4), dtype=np.uint8)
    observed[..., 3] = 1
    observed[2:4, 3:6, 3] = 198
    observed_path = tmp_path / "observed.webp"
    Image.fromarray(observed).save(observed_path, "WEBP", lossless=True)

    actual = np.full((6, 8), 14, dtype=np.uint8)
    actual[2:4, 3:6] = 52
    operational_cube = np.stack([np.full_like(actual, 14), actual], axis=-1)
    baseline_cube = np.stack(
        [np.full_like(actual, 14), np.full_like(actual, 14)], axis=-1
    )
    candidate_cube = np.stack([np.full_like(actual, 14), actual], axis=-1)
    cube_path = tmp_path / "verification-cube.npz"
    np.savez_compressed(
        cube_path,
        cube=operational_cube,
        baselineOpticalFlow=baseline_cube,
        trajectoryRecency=candidate_cube,
        speedCorrectedBaseline=baseline_cube,
        trajectorySpeedCorrected=candidate_cube,
        regimeAdaptiveBaseline=baseline_cube,
        regimeAdaptiveEnsemble=candidate_cube,
        regimeRainProbability=np.where(candidate_cube >= 52, 85, 10).astype(np.uint8),
        probabilityGatedBaseline=baseline_cube,
        probabilityGatedEnsemble=candidate_cube,
    )
    metadata = {
        "schemaVersion": 2,
        "basedOnObservedAt": "2026-10-11T11:15:00Z",
        "algorithmVersion": ALGORITHM_VERSION,
        "width": 8,
        "height": 6,
        "frameCount": 2,
        "encoding": "npz-pixel-major-uint8-dbz-plus-32",
        "frames": [
            {"leadMinutes": 0, "predictedAt": "2026-10-11T11:15:00Z"},
            {
                "leadMinutes": 45,
                "predictedAt": "2026-10-11T12:00:00Z",
                "forecastMethod": "optical-flow",
            },
        ],
        "shadowCandidates": [
            {
                "candidateId": SHADOW_CANDIDATE_ID,
                "forecastMethod": SHADOW_CANDIDATE_METHOD,
                "cubeKey": "trajectoryRecency",
                "baselineCubeKey": "baselineOpticalFlow",
                "frames": [
                    {
                        "leadMinutes": 45,
                        "predictedAt": "2026-10-11T12:00:00Z",
                        "cubeFrameIndex": 1,
                    }
                ],
            },
            {
                "candidateId": SPEED_CANDIDATE_ID,
                "forecastMethod": SPEED_CANDIDATE_METHOD,
                "cubeKey": "trajectorySpeedCorrected",
                "baselineCubeKey": "speedCorrectedBaseline",
                "frames": [
                    {
                        "leadMinutes": 45,
                        "predictedAt": "2026-10-11T12:00:00Z",
                        "cubeFrameIndex": 1,
                    }
                ],
            },
            {
                "candidateId": REGIME_CANDIDATE_ID,
                "forecastMethod": REGIME_CANDIDATE_METHOD,
                "cubeKey": "regimeAdaptiveEnsemble",
                "baselineCubeKey": "regimeAdaptiveBaseline",
                "probabilityCubeKey": "regimeRainProbability",
                "probabilityThresholdDbz": 20,
                "frames": [
                    {
                        "leadMinutes": 45,
                        "predictedAt": "2026-10-11T12:00:00Z",
                        "cubeFrameIndex": 1,
                    }
                ],
            },
            {
                "candidateId": PROBABILITY_GATE_CANDIDATE_ID,
                "forecastMethod": PROBABILITY_GATE_CANDIDATE_METHOD,
                "cubeKey": "probabilityGatedEnsemble",
                "baselineCubeKey": "probabilityGatedBaseline",
                "probabilityCubeKey": "regimeRainProbability",
                "probabilityThresholdDbz": 20,
                "frames": [
                    {
                        "leadMinutes": 45,
                        "predictedAt": "2026-10-11T12:00:00Z",
                        "cubeFrameIndex": 1,
                        "minimumRainProbability": 0.6,
                    }
                ],
            },
        ],
    }

    result = verify_previous_nowcast(
        metadata, cube_path, observed_path, "2026-10-11T12:00:00Z"
    )

    assert result is not None
    assert len(result["shadowCandidateScores"]) == 4
    candidate = result["shadowCandidateScores"][0]
    assert candidate["candidateId"] == SHADOW_CANDIDATE_ID
    assert candidate["criticalSuccessIndex"] == result["criticalSuccessIndex"]
    assert candidate["criticalSuccessIndexImprovement"] > 0
    assert candidate["baselineScore"]["criticalSuccessIndex"] < result["criticalSuccessIndex"]
    assert candidate["leadMinutes"] == 45
    speed_candidate = result["shadowCandidateScores"][1]
    assert speed_candidate["candidateId"] == SPEED_CANDIDATE_ID
    assert speed_candidate["forecastMethod"] == SPEED_CANDIDATE_METHOD
    assert speed_candidate["criticalSuccessIndexImprovement"] > 0
    regime_candidate = result["shadowCandidateScores"][2]
    assert regime_candidate["candidateId"] == REGIME_CANDIDATE_ID
    assert regime_candidate["forecastMethod"] == REGIME_CANDIDATE_METHOD
    assert regime_candidate["brierScore"] < regime_candidate["persistenceBrierScore"]
    assert regime_candidate["brierSkillScore"] > 0
    probability_gate_candidate = result["shadowCandidateScores"][3]
    assert probability_gate_candidate["candidateId"] == PROBABILITY_GATE_CANDIDATE_ID
    assert probability_gate_candidate["forecastMethod"] == PROBABILITY_GATE_CANDIDATE_METHOD
    assert probability_gate_candidate["criticalSuccessIndexImprovement"] > 0
    assert probability_gate_candidate["brierSkillScore"] > 0
    assert probability_gate_candidate["minimumRainProbability"] == 0.6


def test_promotes_shadow_candidate_only_after_paired_quality_gate(tmp_path: Path) -> None:
    operational = {
        "validPixels": 1000,
        "hits": 50,
        "misses": 30,
        "falseAlarms": 20,
        "correctNegatives": 900,
        "precision": 0.7143,
        "recall": 0.625,
        "criticalSuccessIndex": 0.5,
        "dbzMeanAbsoluteError": 4.0,
        "persistenceCriticalSuccessIndex": 0.4,
        "criticalSuccessIndexSkill": 0.1,
    }
    candidate = {
        "candidateId": SHADOW_CANDIDATE_ID,
        "forecastMethod": SHADOW_CANDIDATE_METHOD,
        "leadMinutes": 60,
        "validPixels": 1000,
        "hits": 70,
        "misses": 10,
        "falseAlarms": 10,
        "correctNegatives": 910,
        "precision": 0.875,
        "recall": 0.875,
        "criticalSuccessIndex": 0.7778,
        "dbzMeanAbsoluteError": 3.0,
        "persistenceCriticalSuccessIndex": 0.4,
        "criticalSuccessIndexSkill": 0.3778,
        "operationalCriticalSuccessIndex": 0.5,
        "criticalSuccessIndexImprovement": 0.2778,
        "thresholdDbz": 20,
        "thresholdScores": [],
    }
    speed_candidate = {
        **candidate,
        "candidateId": SPEED_CANDIDATE_ID,
        "forecastMethod": SPEED_CANDIDATE_METHOD,
    }
    results = [
        {
            "verifiedAt": "2026-10-12T13:01:00Z",
            "basedOnObservedAt": f"2026-10-12T{index // 12:02d}:{(index % 12) * 5:02d}:00Z",
            "predictedAt": "2026-10-12T13:00:00Z",
            "observedAt": f"2026-10-12T{(index // 12) + 1:02d}:{(index % 12) * 5:02d}:00Z",
            "leadMinutes": 60,
            "forecastMethod": "optical-flow",
            "algorithmVersion": ALGORITHM_VERSION,
            "thresholdDbz": 20,
            "thresholdScores": [],
            "shadowCandidateScores": [candidate, speed_candidate],
            **operational,
        }
        for index in range(48)
    ]

    report = append_verification_history(tmp_path / "shadow-history.json", results)

    assert len(report["shadowCandidates"]) == 2
    shadow = report["shadowCandidates"][0]
    lead = shadow["byLeadMinutes"][0]
    assert lead["sampleCount"] == 48
    assert lead["eventPixelCount"] >= 1000
    assert lead["criticalSuccessIndexImprovement"] > 0.02
    assert lead["falseAlarmRateIncrease"] < 0
    assert lead["status"] == "promotable"
    assert lead["safeToPromote"] is True
    assert shadow["safeToPromoteLeadMinutes"] == [60]
    speed_shadow = report["shadowCandidates"][1]
    assert speed_shadow["candidateId"] == SPEED_CANDIDATE_ID
    assert speed_shadow["safeToPromoteLeadMinutes"] == [60]
    profile_candidate = quality_by_lead(report)[60]["shadowCandidates"][0]
    assert profile_candidate["safeToPromote"] is True
    public = public_verification_report(report)
    assert public["shadowCandidates"][0]["safeToPromoteLeadMinutes"] == [60]
    assert "shadowCandidateScores" not in public["results"][0]

    noisy_candidate = {
        **candidate,
        "hits": 100,
        "misses": 0,
        "falseAlarms": 50,
        "correctNegatives": 850,
        "precision": 0.6667,
        "recall": 1.0,
        "criticalSuccessIndex": 0.6667,
        "criticalSuccessIndexSkill": 0.2667,
        "criticalSuccessIndexImprovement": 0.1667,
    }
    noisy_results = [
        {**entry, "shadowCandidateScores": [noisy_candidate]} for entry in results
    ]
    noisy_report = append_verification_history(tmp_path / "noisy-shadow.json", noisy_results)
    noisy_lead = noisy_report["shadowCandidates"][0]["byLeadMinutes"][0]
    assert noisy_lead["criticalSuccessIndexImprovement"] > 0.02
    assert noisy_lead["falseAlarmRateIncrease"] > 0.02
    assert noisy_lead["status"] == "held-back"
    assert noisy_lead["safeToPromote"] is False


def test_requires_non_negative_probability_skill_for_ensemble_promotion(
    tmp_path: Path,
) -> None:
    operational = {
        "validPixels": 1000,
        "hits": 50,
        "misses": 30,
        "falseAlarms": 20,
        "correctNegatives": 900,
        "precision": 0.7143,
        "recall": 0.625,
        "criticalSuccessIndex": 0.5,
        "dbzMeanAbsoluteError": 4.0,
        "persistenceCriticalSuccessIndex": 0.4,
        "criticalSuccessIndexSkill": 0.1,
    }
    candidate = {
        "candidateId": REGIME_CANDIDATE_ID,
        "forecastMethod": REGIME_CANDIDATE_METHOD,
        "leadMinutes": 60,
        "validPixels": 1000,
        "hits": 70,
        "misses": 10,
        "falseAlarms": 10,
        "correctNegatives": 910,
        "precision": 0.875,
        "recall": 0.875,
        "criticalSuccessIndex": 0.7778,
        "dbzMeanAbsoluteError": 3.0,
        "persistenceCriticalSuccessIndex": 0.4,
        "criticalSuccessIndexSkill": 0.3778,
        "criticalSuccessIndexImprovement": 0.2778,
        "thresholdDbz": 20,
        "thresholdScores": [],
        "brierScore": 0.22,
        "persistenceBrierScore": 0.2,
        "brierSkillScore": -0.1,
    }
    results = [
        {
            "verifiedAt": "2026-10-12T13:01:00Z",
            "basedOnObservedAt": f"2026-10-12T{index // 12:02d}:{(index % 12) * 5:02d}:00Z",
            "predictedAt": "2026-10-12T13:00:00Z",
            "observedAt": f"2026-10-12T{(index // 12) + 1:02d}:{(index % 12) * 5:02d}:00Z",
            "leadMinutes": 60,
            "forecastMethod": "optical-flow",
            "algorithmVersion": ALGORITHM_VERSION,
            "thresholdDbz": 20,
            "thresholdScores": [],
            "shadowCandidateScores": [candidate],
            **operational,
        }
        for index in range(48)
    ]

    degraded = append_verification_history(tmp_path / "ensemble-degraded.json", results)
    degraded_lead = degraded["shadowCandidates"][0]["byLeadMinutes"][0]
    assert degraded_lead["meanBrierSkillScore"] == -0.1
    assert degraded_lead["status"] == "held-back"
    assert degraded_lead["safeToPromote"] is False

    improved_results = [
        {
            **entry,
            "shadowCandidateScores": [
                {
                    **candidate,
                    "brierScore": 0.18,
                    "brierSkillScore": 0.1,
                }
            ],
        }
        for entry in results
    ]
    improved = append_verification_history(tmp_path / "ensemble-improved.json", improved_results)
    improved_candidate = improved["shadowCandidates"][0]
    improved_lead = improved_candidate["byLeadMinutes"][0]
    assert improved_candidate["promotionGate"]["minimumBrierSkillOverPersistence"] == 0
    assert improved_lead["meanBrierSkillScore"] == 0.1
    assert improved_lead["status"] == "promotable"
    assert improved_lead["safeToPromote"] is True
