import copy
import json

import numpy as np
import pytest

from wetmap_worker.comparison import compare_shared_coverage, shared_coverage_summary


def grid(*values):
    return np.array([values], dtype=np.uint8)


def test_shared_mask_removes_different_denominators_and_reports_lost_coverage():
    comparison = compare_shared_coverage(grid(60, 0), grid(60, 14), grid(60, 60))
    assert comparison["mode"] == "shadow-only"
    assert comparison["comparisonVersion"] == "shared-coverage-v2"
    assert (
        comparison["forecastScore"]["validPixels"]
        == comparison["persistenceScore"]["validPixels"]
        == 1
    )
    assert comparison["skillOverPersistence"] == 0
    assert comparison["coverage"]["commonFractionOfObserved"] == 0.5


def test_empty_coverage_and_dry_rain_scores_do_not_claim_perfect_skill():
    empty = compare_shared_coverage(grid(0), grid(14), grid(60))
    assert empty["forecastScore"]["criticalSuccessIndex"] is None
    assert empty["skillOverPersistence"] is None
    dry = compare_shared_coverage(grid(14), grid(14), grid(14))
    assert dry["forecastScore"]["falseAlarmRatio"] is None
    assert dry["forecastScore"]["criticalSuccessIndex"] is None


def test_candidate_uses_exact_archived_incumbent_and_same_mask_for_brier():
    candidate = {
        "candidateId": "example",
        "leadMinutes": 40,
        "predicted": grid(60, 60, 0),
        "incumbent": grid(60, 14, 60),
        "probability": grid(80, 20, 100),
        "probabilityThresholdDbz": 20,
    }
    before = copy.deepcopy(candidate)
    result = compare_shared_coverage(
        grid(60, 14, 60), grid(14, 60, 60), grid(60, 14, 60), [candidate]
    )
    scored = result["candidates"][0]
    assert scored["forecastScore"]["criticalSuccessIndex"] == 0.5
    assert scored["incumbentScore"]["criticalSuccessIndex"] == 1
    assert scored["improvementOverIncumbent"] == -0.5
    assert (
        scored["forecastScore"]["validPixels"]
        == scored["incumbentScore"]["validPixels"]
        == scored["probability"]["validPixels"]
        == 2
    )
    assert scored["probability"]["brierScore"] == pytest.approx(0.04)
    assert scored["probability"]["persistenceBrierScore"] == 1
    assert scored["probability"]["brierSkillScore"] == pytest.approx(0.96)
    for name in ("predicted", "incumbent", "probability"):
        np.testing.assert_array_equal(candidate[name], before[name])


def test_probability_of_a_different_dbz_event_is_not_labelled_as_twenty_dbz():
    candidate = {
        "candidateId": "example",
        "leadMinutes": 40,
        "predicted": grid(60),
        "incumbent": grid(60),
        "probability": grid(80),
        "probabilityThresholdDbz": 15,
    }
    row = compare_shared_coverage(grid(60), grid(60), grid(60), [candidate])["candidates"][0]
    assert row["probability"]["status"] == "threshold-mismatch"
    assert "brierScore" not in row["probability"]


def test_invalid_shapes_probabilities_and_duplicate_candidates_fail_closed():
    with pytest.raises(ValueError):
        compare_shared_coverage(grid(60), grid(60, 60), grid(60))
    candidate = {
        "candidateId": "example",
        "leadMinutes": 40,
        "predicted": grid(60),
        "incumbent": grid(60),
        "probability": grid(101),
        "probabilityThresholdDbz": 20,
    }
    with pytest.raises(ValueError):
        compare_shared_coverage(grid(60), grid(60), grid(60), [candidate])
    candidate["probability"] = grid(80)
    with pytest.raises(ValueError):
        compare_shared_coverage(grid(60), grid(60), grid(60), [candidate, candidate])


def test_summary_is_cohort_separated_additive_and_never_promotes():
    comparison = compare_shared_coverage(grid(60), grid(14), grid(60))
    history = [
        {"algorithmVersion": version, "leadMinutes": 10, "sharedCoverageComparison": comparison}
        for version in ("old", "new")
    ]
    history.append({"algorithmVersion": "new", "leadMinutes": 10, "hits": 100000})
    summary = shared_coverage_summary(history)
    assert summary["sampleCount"] == 2
    assert summary["canAffectForecasts"] is False
    assert summary["promotionEnabled"] is False
    assert [cohort["algorithmVersion"] for cohort in summary["cohorts"]] == ["new", "old"]
    assert all(cohort["sampleCount"] == 1 for cohort in summary["cohorts"])
    assert "safeToPromote" not in str(summary)


def test_probability_skill_is_undefined_when_persistence_is_perfect():
    candidate = {
        "candidateId": "example",
        "leadMinutes": 40,
        "predicted": grid(14),
        "incumbent": grid(14),
        "probability": grid(0),
        "probabilityThresholdDbz": 20,
    }
    row = compare_shared_coverage(grid(14), grid(14), grid(14), [candidate])["candidates"][0]
    assert row["probability"]["brierScore"] == 0
    assert row["probability"]["brierSkillScore"] is None


def test_parallel_evidence_cannot_change_operational_quality_or_leak_raw_detail(tmp_path):
    from wetmap_worker.nowcast import ALGORITHM_VERSION
    from wetmap_worker.verification import (
        append_verification_history,
        public_verification_report,
        quality_by_lead,
    )

    legacy = {
        "verifiedAt": "2026-11-12T10:10:00Z",
        "basedOnObservedAt": "2026-11-12T10:00:00Z",
        "predictedAt": "2026-11-12T10:10:00Z",
        "observedAt": "2026-11-12T10:10:00Z",
        "leadMinutes": 10,
        "algorithmVersion": ALGORITHM_VERSION,
        "hits": 1,
        "misses": 9,
        "falseAlarms": 1,
        "validPixels": 100,
        "criticalSuccessIndex": 0.0909,
        "criticalSuccessIndexSkill": -0.1,
        "persistenceCriticalSuccessIndex": 0.1909,
        "thresholdScores": [],
    }
    original = append_verification_history(tmp_path / "old.json", legacy)
    enhanced = append_verification_history(
        tmp_path / "new.json",
        {
            **legacy,
            "sharedCoverageComparison": compare_shared_coverage(grid(60), grid(14), grid(60)),
        },
    )
    assert quality_by_lead(original) == quality_by_lead(enhanced)
    assert original["shadowCandidates"] == enhanced["shadowCandidates"]
    public = public_verification_report(enhanced)
    assert public["comparisonAudit"]["sampleCount"] == 1
    assert "sharedCoverageComparison" not in public["results"][0]


def test_secondary_record_size_stays_bounded_without_image_or_probability_arrays():
    values = np.full((171, 256), 60, dtype=np.uint8)
    candidates = [
        {
            "candidateId": f"candidate-{index}",
            "leadMinutes": 40,
            "predicted": values,
            "incumbent": values,
            "probability": np.full_like(values, 80),
            "probabilityThresholdDbz": 20,
        }
        for index in range(5)
    ]
    record = compare_shared_coverage(values, values, values, candidates)
    assert len(json.dumps(record, allow_nan=False).encode()) < 12000
