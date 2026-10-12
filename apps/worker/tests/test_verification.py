import json
from pathlib import Path

import numpy as np
from PIL import Image

from wetmap_worker.nowcast import ALGORITHM_VERSION, POINT_GRID_HEIGHT, POINT_GRID_WIDTH
from wetmap_worker.verification import (
    append_verification_history,
    public_verification_report,
    quality_by_lead,
    update_verification_state,
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
