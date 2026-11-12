"""Sanity checks for additive comparison evidence, never operational promotion."""

import math


def _fraction(value, expected):
    if expected is None:
        return value is None
    return (
        type(value) in (int, float)
        and math.isfinite(value)
        and abs(value - expected) <= 0.000055
    )


def _lead(row):
    common = row["coverage"]["commonValidPixels"]
    observed = row["coverage"]["observedValidPixels"]
    if (
        type(common) is not int
        or type(observed) is not int
        or not 0 <= common <= observed
    ):
        raise ValueError("Invalid shared coverage counts")
    if not _fraction(
        row["coverage"]["commonFractionOfObserved"],
        common / observed if observed else None,
    ):
        raise ValueError("Invalid shared coverage fraction")
    for name in ("forecast", "persistence", "incumbent"):
        score = row.get(name)
        if score is None:
            continue
        counts = [
            score.get(key)
            for key in ("hits", "misses", "falseAlarms", "correctNegatives")
        ]
        if (
            any(type(value) is not int or value < 0 for value in counts)
            or sum(counts) != common
            or score["validPixels"] != common
        ):
            raise ValueError("Comparison members do not use the same coverage")
        hit, miss, false, _tn = counts
        for metric, denominator in (
            ("precision", hit + false),
            ("recall", hit + miss),
            ("criticalSuccessIndex", hit + miss + false),
        ):
            if not _fraction(
                score.get(metric), hit / denominator if denominator else None
            ):
                raise ValueError("Invalid shared-coverage metric")


def validate_shared_coverage(report):
    audit = report.get("comparisonAudit")
    if audit is None:
        return
    if (
        audit.get("comparisonVersion") != "shared-coverage-v2"
        or audit.get("mode") != "shadow-only"
        or audit.get("canAffectForecasts") is not False
        or audit.get("promotionEnabled") is not False
        or audit.get("thresholdDbz") != 20
    ):
        raise ValueError(
            "Shared-coverage evidence must remain versioned and shadow-only"
        )
    if audit.get("failedPairCount") != 0:
        raise ValueError("Shared-coverage comparison has failed pairs")
    cohorts = audit.get("cohorts", [])
    if len({cohort["algorithmVersion"] for cohort in cohorts}) != len(cohorts):
        raise ValueError("Duplicate comparison cohort")
    if sum(cohort["sampleCount"] for cohort in cohorts) != audit.get("sampleCount"):
        raise ValueError("Invalid comparison sample accounting")
    for cohort in cohorts:
        if (
            sum(row["sampleCount"] for row in cohort["byLeadMinutes"])
            != cohort["sampleCount"]
        ):
            raise ValueError("Invalid per-lead comparison accounting")
        for row in cohort["byLeadMinutes"]:
            _lead(row)
        for candidate in cohort["candidates"]:
            for row in candidate["byLeadMinutes"]:
                if "incumbent" not in row:
                    raise ValueError("Comparison is missing the actual incumbent")
                _lead(row)
