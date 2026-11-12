from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

SPEC = importlib.util.spec_from_file_location(
    "audit_precision", Path(__file__).parents[1] / "tools" / "audit_precision.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_independent_confusion_matrix_separates_no_coverage_from_dry():
    result = MODULE.score_grid(
        np.array([[60, 60, 14, 14, 0]], dtype=np.uint8),
        np.array([[60, 14, 60, 14, 60]], dtype=np.uint8),
    )
    assert [result[key] for key in ("hits", "falseAlarms", "misses", "correctNegatives")] == [
        1,
        1,
        1,
        1,
    ]
    assert result["validPixels"] == 4
    assert result["criticalSuccessIndex"] == pytest.approx(1 / 3)
    assert result["falseAlarmRatio"] == 0.5


def test_dry_empty_and_missing_coverage_never_become_perfect_rain_scores():
    dry = np.array([[14]], dtype=np.uint8)
    assert MODULE.score_grid(dry, dry)["criticalSuccessIndex"] is None
    assert MODULE.score_grid(dry, dry)["falseAlarmRatio"] is None
    empty = MODULE.score_grid(np.zeros_like(dry), dry)
    assert empty["validPixels"] == 0
    assert empty["dbzMeanAbsoluteError"] is None


def test_independent_masks_can_manufacture_positive_skill():
    comparison = MODULE.compare_masks(
        np.array([[60, 0]], dtype=np.uint8),
        np.array([[60, 14]], dtype=np.uint8),
        np.array([[60, 60]], dtype=np.uint8),
    )
    assert comparison["maskDifferencePixels"] == 1
    assert comparison["independentMaskSkill"] == 0.5
    assert comparison["commonMaskSkill"] == 0
    assert comparison["commonCoverageFractionOfObserved"] == 0.5


def test_masks_cannot_include_invalid_pixels_or_mismatched_shapes():
    values = np.array([[0, 60]], dtype=np.uint8)
    with pytest.raises(ValueError, match="mask"):
        MODULE.score_grid(values, values, mask=np.ones_like(values, dtype=bool))
    with pytest.raises(ValueError, match="shape"):
        MODULE.score_grid(values, values.T)


def fixture(directory: Path):
    source = np.array([[52, 14], [14, 52]], dtype=np.uint8)
    cube = np.stack([source, source, source], axis=-1)
    cube_path = directory / "cube-00.npz"
    np.savez_compressed(cube_path, cube=cube)
    frames, results = [], []
    for minute in (0, 5, 10):
        stamp = f"2026-11-12T10:{minute:02}:00Z"
        filename = f"dk.com.2026111210{minute:02}.500_max.webp"
        rgba = np.zeros((2, 2, 4), dtype=np.uint8)
        rgba[..., 3] = np.where(source == 52, 132, 1)
        Image.fromarray(rgba).save(directory / filename, "WEBP", lossless=True)
        frames.append(
            {
                "observedAt": stamp,
                "url": "/frames/" + filename,
                "bounds": [7, 54, 13, 58],
                "sha256": hashlib.sha256((directory / filename).read_bytes()).hexdigest(),
            }
        )
        if minute:
            results.append(
                {
                    "algorithmVersion": "test-v1",
                    "basedOnObservedAt": "2026-11-12T10:00:00Z",
                    "predictedAt": stamp,
                    "observedAt": stamp,
                    "leadMinutes": minute,
                    "thresholdDbz": 20,
                    "validPixels": 4,
                    "hits": 2,
                    "misses": 0,
                    "falseAlarms": 0,
                    "correctNegatives": 2,
                    "precision": 1.0,
                    "recall": 1.0,
                    "criticalSuccessIndex": 1.0,
                    "dbzMeanAbsoluteError": 0.0,
                    "persistenceCriticalSuccessIndex": 1.0,
                    "criticalSuccessIndexSkill": 0.0,
                }
            )
    metadata = {
        "algorithmVersion": "test-v1",
        "basedOnObservedAt": "2026-11-12T10:00:00Z",
        "width": 2,
        "height": 2,
        "frameCount": 3,
        "bounds": [7, 54, 13, 58],
        "dataKey": "nowcast/verification-cubes/cube-00.npz",
        "sha256": hashlib.sha256(cube_path.read_bytes()).hexdigest(),
        "frames": [
            {"leadMinutes": minute, "predictedAt": f"2026-11-12T10:{minute:02}:00Z"}
            for minute in (0, 5, 10)
        ],
    }
    return {"forecasts": [metadata]}, {"frames": frames}, {"results": results}


def test_raw_pairs_reproduce_scores_and_identical_persistence_input(tmp_path):
    state, manifest, public = fixture(tmp_path)
    report = MODULE.audit(state, manifest, public, tmp_path, minimum_pairs=2)
    assert report["reproductionStatus"] == "pass"
    assert report["pairCount"] == 2
    assert report["mismatches"] == []
    assert report["persistenceIdentity"] == {"checked": 1, "missing": 0, "mismatched": 0}
    assert report["coverageComparison"]["differentMaskPairs"] == 0
    assert report["cohorts"]["test-v1"]["5"]["pairCount"] == 1
    json.dumps(report, allow_nan=False)


def test_fails_on_published_metric_tampering(tmp_path):
    state, manifest, public = fixture(tmp_path)
    public["results"][0]["precision"] = 0.2
    report = MODULE.audit(state, manifest, public, tmp_path, minimum_pairs=2)
    assert report["reproductionStatus"] == "fail"
    assert report["mismatches"][0]["metric"] == "precision"


def test_minimum_pairs_is_blocked_not_silently_reduced(tmp_path):
    state, manifest, public = fixture(tmp_path)
    report = MODULE.audit(state, manifest, public, tmp_path, minimum_pairs=50)
    assert report["reproductionStatus"] == "blocked"
    assert "minimum-pairs" in report["blockedReasons"]


def test_available_unpublished_pairs_remain_visible_not_counted_as_verified(tmp_path):
    state, manifest, public = fixture(tmp_path)
    public["results"].pop()
    report = MODULE.audit(state, manifest, public, tmp_path, minimum_pairs=2)
    assert report["availablePairCount"] == 2
    assert report["pairCount"] == 1
    assert report["reproductionStatus"] == "blocked"
    assert report["skipped"]["missing-public-pair"] == 1


def test_observation_filename_must_match_declared_valid_time(tmp_path):
    state, manifest, public = fixture(tmp_path)
    manifest["frames"][0]["observedAt"] = "2026-11-12T09:00:00Z"
    with pytest.raises(ValueError, match="timestamp"):
        MODULE.audit(state, manifest, public, tmp_path)


def test_comparison_refuses_misaligned_geographic_bounds(tmp_path):
    state, manifest, public = fixture(tmp_path)
    manifest["frames"][1]["bounds"] = [7, 54, 14, 58]
    with pytest.raises(ValueError, match="bounds"):
        MODULE.audit(state, manifest, public, tmp_path)


def test_invalid_cube_checksum_and_path_fail_closed(tmp_path):
    state, manifest, public = fixture(tmp_path)
    state["forecasts"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="checksum"):
        MODULE.audit(state, manifest, public, tmp_path)
    state["forecasts"][0]["dataKey"] = "../../private.npz"
    with pytest.raises(ValueError, match="key"):
        MODULE.audit(state, manifest, public, tmp_path)


def test_non_finite_metrics_are_not_accepted_as_matching(tmp_path):
    state, manifest, public = fixture(tmp_path)
    public["results"][0]["precision"] = float("nan")
    report = MODULE.audit(state, manifest, public, tmp_path, minimum_pairs=2)
    assert report["reproductionStatus"] == "fail"


def test_duplicate_forecast_origins_cannot_inflate_evidence_floor(tmp_path):
    state, manifest, public = fixture(tmp_path)
    state["forecasts"].append(state["forecasts"][0])
    with pytest.raises(ValueError, match="Duplicate forecast generation"):
        MODULE.audit(state, manifest, public, tmp_path)


def test_duplicate_leads_cannot_count_as_distinct_pairs(tmp_path):
    state, manifest, public = fixture(tmp_path)
    state["forecasts"][0]["frames"][2] = state["forecasts"][0]["frames"][1]
    with pytest.raises(ValueError, match="Duplicate forecast lead"):
        MODULE.audit(state, manifest, public, tmp_path)


def test_current_report_version_never_relabels_older_pair_cohorts(tmp_path):
    state, manifest, public = fixture(tmp_path)
    public["algorithmVersion"] = "different-latest-version"
    public["results"][0]["algorithmVersion"] = "other-cohort"
    report = MODULE.audit(state, manifest, public, tmp_path, minimum_pairs=2)
    assert report["pairCount"] == 1
    assert report["availablePairCount"] == 2
    assert list(report["cohorts"]) == ["test-v1"]
    assert report["reproductionStatus"] == "blocked"
