"""Additive shared-coverage diagnostics. Never consumed by operational gates."""

from __future__ import annotations

from collections import defaultdict

import numpy as np

COMPARISON_VERSION = "shared-coverage-v2"
THRESHOLD_DBZ = 20


def _ratio(a, b, digits=4):
    return round(a / b, digits) if b else None


def _difference(left, right):
    return round(left - right, 4) if left is not None and right is not None else None


def _mean(values):
    values = [value for value in values if value is not None]
    return round(sum(values) / len(values), 6) if values else None


def _score(predicted, actual, valid):
    forecast_echo = (predicted >= THRESHOLD_DBZ + 32) & valid
    observed_echo = (actual >= THRESHOLD_DBZ + 32) & valid
    hits = int(np.count_nonzero(forecast_echo & observed_echo))
    misses = int(np.count_nonzero(~forecast_echo & observed_echo & valid))
    false_alarms = int(np.count_nonzero(forecast_echo & ~observed_echo & valid))
    negatives = int(np.count_nonzero(~forecast_echo & ~observed_echo & valid))
    echo = forecast_echo | observed_echo
    return {
        "validPixels": int(np.count_nonzero(valid)),
        "hits": hits,
        "misses": misses,
        "falseAlarms": false_alarms,
        "correctNegatives": negatives,
        "precision": _ratio(hits, hits + false_alarms),
        "recall": _ratio(hits, hits + misses),
        "criticalSuccessIndex": _ratio(hits, hits + misses + false_alarms),
        "falseAlarmRatio": _ratio(false_alarms, hits + false_alarms),
        "dbzMeanAbsoluteError": (
            round(
                float(np.mean(np.abs(predicted[echo].astype(float) - actual[echo].astype(float)))),
                2,
            )
            if np.any(echo)
            else (0.0 if np.any(valid) else None)
        ),
    }


def _pair(predicted, persistence, actual, incumbent=None):
    grids = [predicted, persistence, actual] + ([] if incumbent is None else [incumbent])
    if any(
        grid.shape != actual.shape or grid.ndim != 2 or grid.dtype != np.uint8 for grid in grids
    ):
        raise ValueError("Shared-coverage grid shape/type mismatch")
    common = np.logical_and.reduce([grid > 0 for grid in grids])
    observed_count = int(np.count_nonzero(actual))
    common_count = int(np.count_nonzero(common))
    forecast_score, persistence_score = (
        _score(predicted, actual, common),
        _score(persistence, actual, common),
    )
    result = {
        "coverage": {
            "observedValidPixels": observed_count,
            "forecastValidPixels": int(np.count_nonzero((predicted > 0) & (actual > 0))),
            "persistenceValidPixels": int(np.count_nonzero((persistence > 0) & (actual > 0))),
            "commonValidPixels": common_count,
            "commonFractionOfObserved": _ratio(common_count, observed_count, 6),
        },
        "forecastScore": forecast_score,
        "persistenceScore": persistence_score,
        "skillOverPersistence": _difference(
            forecast_score["criticalSuccessIndex"], persistence_score["criticalSuccessIndex"]
        ),
    }
    if incumbent is not None:
        incumbent_score = _score(incumbent, actual, common)
        result["incumbentScore"] = incumbent_score
        result["coverage"]["incumbentValidPixels"] = int(
            np.count_nonzero((incumbent > 0) & (actual > 0))
        )
        result["improvementOverIncumbent"] = _difference(
            forecast_score["criticalSuccessIndex"], incumbent_score["criticalSuccessIndex"]
        )
    return result, common


def compare_shared_coverage(predicted, persistence, actual, candidates=()):
    if len(candidates) > 5:
        raise ValueError("Too many shared-coverage candidates")
    primary, _mask = _pair(predicted, persistence, actual)
    scored, seen = [], set()
    for candidate in candidates:
        identity = (candidate["candidateId"], candidate["leadMinutes"])
        if identity in seen:
            raise ValueError("Duplicate shared-coverage candidate")
        seen.add(identity)
        # The actual archived operational grid is mandatory; do not fall back to
        # the candidate's upstream ablation/control cube.
        row, mask = _pair(candidate["predicted"], persistence, actual, candidate["incumbent"])
        row.update({"candidateId": identity[0], "leadMinutes": identity[1]})
        probability = candidate.get("probability")
        if probability is not None:
            if (
                probability.shape != actual.shape
                or probability.dtype != np.uint8
                or np.any(probability > 100)
            ):
                raise ValueError("Invalid archived probability grid")
            if candidate.get("probabilityThresholdDbz") != THRESHOLD_DBZ:
                row["probability"] = {"status": "threshold-mismatch"}
            elif not np.any(mask):
                row["probability"] = {"status": "no-common-coverage"}
            else:
                observed = (actual[mask] >= THRESHOLD_DBZ + 32).astype(float)
                persistent = (persistence[mask] >= THRESHOLD_DBZ + 32).astype(float)
                brier = float(np.mean((probability[mask].astype(float) / 100 - observed) ** 2))
                baseline = float(np.mean((persistent - observed) ** 2))
                row["probability"] = {
                    "status": "available",
                    "validPixels": int(np.count_nonzero(mask)),
                    "brierScore": round(brier, 6),
                    "persistenceBrierScore": round(baseline, 6),
                    "brierSkillScore": round(1 - brier / baseline, 4) if baseline > 0 else None,
                }
        scored.append(row)
    return {
        "comparisonVersion": COMPARISON_VERSION,
        "mode": "shadow-only",
        "thresholdDbz": THRESHOLD_DBZ,
        **primary,
        "candidates": scored,
    }


def _aggregate(rows):
    counts = {
        name: sum(row[name] for row in rows)
        for name in ("validPixels", "hits", "misses", "falseAlarms", "correctNegatives")
    }
    hit, miss, false = (counts[name] for name in ("hits", "misses", "falseAlarms"))
    return {
        **counts,
        "precision": _ratio(hit, hit + false),
        "recall": _ratio(hit, hit + miss),
        "criticalSuccessIndex": _ratio(hit, hit + miss + false),
        "falseAlarmRatio": _ratio(false, hit + false),
        "meanPairDbzMAE": _mean(row["dbzMeanAbsoluteError"] for row in rows),
    }


def _lead_summary(rows):
    grouped = defaultdict(list)
    for lead, row in rows:
        grouped[lead].append(row)
    summaries = []
    for lead, entries in sorted(grouped.items()):
        observed = sum(row["coverage"]["observedValidPixels"] for row in entries)
        common = sum(row["coverage"]["commonValidPixels"] for row in entries)
        fractions = [
            row["coverage"]["commonFractionOfObserved"]
            for row in entries
            if row["coverage"]["commonFractionOfObserved"] is not None
        ]
        summary = {
            "leadMinutes": lead,
            "sampleCount": len(entries),
            "forecast": _aggregate([row["forecastScore"] for row in entries]),
            "persistence": _aggregate([row["persistenceScore"] for row in entries]),
            "meanPairSkillOverPersistence": _mean(row["skillOverPersistence"] for row in entries),
            "coverage": {
                "observedValidPixels": observed,
                "commonValidPixels": common,
                "commonFractionOfObserved": _ratio(common, observed, 6),
                "minimumPairFraction": min(fractions) if fractions else None,
            },
        }
        if all("incumbentScore" in row for row in entries):
            probabilities = [
                row["probability"]
                for row in entries
                if row.get("probability", {}).get("status") == "available"
            ]
            summary.update(
                {
                    "incumbent": _aggregate([row["incumbentScore"] for row in entries]),
                    "meanPairImprovementOverIncumbent": _mean(
                        row["improvementOverIncumbent"] for row in entries
                    ),
                    "probability": {
                        "sampleCount": len(probabilities),
                        "meanBrierScore": _mean(row["brierScore"] for row in probabilities),
                        "meanPersistenceBrierScore": _mean(
                            row["persistenceBrierScore"] for row in probabilities
                        ),
                        "meanBrierSkillScore": _mean(
                            row["brierSkillScore"] for row in probabilities
                        ),
                        "thresholdMismatchCount": sum(
                            row.get("probability", {}).get("status") == "threshold-mismatch"
                            for row in entries
                        ),
                    },
                }
            )
        summaries.append(summary)
    return summaries


def shared_coverage_summary(history):
    grouped = defaultdict(list)
    failed = 0
    for entry in history:
        row = entry.get("sharedCoverageComparison", {})
        if (
            row.get("comparisonVersion") == COMPARISON_VERSION
            and row.get("mode") == "shadow-only"
            and row.get("thresholdDbz") == THRESHOLD_DBZ
        ):
            grouped[entry.get("algorithmVersion") or "legacy-unversioned"].append((entry, row))
        if entry.get("comparisonAuditError", {}).get("comparisonVersion") == COMPARISON_VERSION:
            failed += 1
    cohorts = []
    for version, entries in sorted(grouped.items()):
        candidates = defaultdict(list)
        for _entry, row in entries:
            for candidate in row["candidates"]:
                candidates[candidate["candidateId"]].append((candidate["leadMinutes"], candidate))
        cohorts.append(
            {
                "algorithmVersion": version,
                "sampleCount": len(entries),
                "byLeadMinutes": _lead_summary(
                    [(entry["leadMinutes"], row) for entry, row in entries]
                ),
                "candidates": [
                    {"candidateId": name, "byLeadMinutes": _lead_summary(rows)}
                    for name, rows in sorted(candidates.items())
                ],
            }
        )
    return {
        "comparisonVersion": COMPARISON_VERSION,
        "mode": "shadow-only",
        "thresholdDbz": THRESHOLD_DBZ,
        "canAffectForecasts": False,
        "promotionEnabled": False,
        "sampleCount": sum(len(entries) for entries in grouped.values()),
        "failedPairCount": failed,
        "cohorts": cohorts,
    }
