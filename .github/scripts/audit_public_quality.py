from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable


ALIGNMENT_TOLERANCE_SECONDS = 180
ROUNDING_TOLERANCE = 0.00055
HORIZON_WINDOWS = {
    15: (10, 20),
    30: (25, 35),
    45: (40, 50),
    60: (55, 60),
}


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _primary_score(entry: dict[str, Any]) -> dict[str, Any]:
    if "hits" in entry:
        return entry
    scores = entry.get("scores") or entry.get("thresholdScores") or []
    selected = next(
        (score for score in scores if int(score.get("thresholdDbz", -1)) == 20),
        scores[0] if scores else {},
    )
    return {**entry, **selected}


def _difference(left: float | None, right: Any) -> float | None:
    if left is None or not isinstance(right, (int, float)):
        return None
    return abs(left - float(right))


def _mean(values: Iterable[float]) -> float | None:
    values = list(values)
    return sum(values) / len(values) if values else None


def _horizon_for_lead(lead: int) -> int | None:
    return next(
        (
            target
            for target, (window_start, window_end) in HORIZON_WINDOWS.items()
            if window_start <= lead <= window_end
        ),
        None,
    )


def audit_report(report: dict[str, Any], *, minimum_pairs: int = 50) -> dict[str, Any]:
    results = list(report.get("results") or [])
    metric_mismatches: list[dict[str, Any]] = []
    alignment_mismatches: list[dict[str, Any]] = []
    horizon_mismatches: list[dict[str, Any]] = []
    horizon_skips: list[dict[str, Any]] = []
    horizon_entries: dict[int, list[dict[str, Any]]] = defaultdict(list)
    persistence_comparisons = 0

    for entry in results:
        score = _primary_score(entry)
        hits = int(score.get("hits", 0) or 0)
        misses = int(score.get("misses", 0) or 0)
        false_alarms = int(score.get("falseAlarms", 0) or 0)
        recalculated = {
            "precision": _ratio(hits, hits + false_alarms),
            "recall": _ratio(hits, hits + misses),
            "criticalSuccessIndex": _ratio(hits, hits + misses + false_alarms),
            "falseAlarmRate": _ratio(false_alarms, hits + false_alarms),
            "missRate": _ratio(misses, hits + misses),
        }
        for name in ("precision", "recall", "criticalSuccessIndex"):
            difference = _difference(recalculated[name], score.get(name))
            if difference is not None and difference > ROUNDING_TOLERANCE:
                metric_mismatches.append(
                    {
                        "predictedAt": entry.get("predictedAt"),
                        "leadMinutes": entry.get("leadMinutes"),
                        "metric": name,
                        "reported": score.get(name),
                        "recalculated": round(float(recalculated[name]), 8),
                    }
                )

        try:
            predicted_at = _parse_time(str(entry["predictedAt"]))
            observed_at = _parse_time(str(entry["observedAt"]))
            based_on = _parse_time(str(entry["basedOnObservedAt"]))
            lead = int(entry["leadMinutes"])
            observed_delta = abs((predicted_at - observed_at).total_seconds())
            lead_delta = abs((predicted_at - (based_on + timedelta(minutes=lead))).total_seconds())
            if observed_delta > ALIGNMENT_TOLERANCE_SECONDS or lead_delta > 1:
                alignment_mismatches.append(
                    {
                        "predictedAt": entry.get("predictedAt"),
                        "observedAt": entry.get("observedAt"),
                        "leadMinutes": lead,
                        "predictionObservationDeltaSeconds": observed_delta,
                        "declaredLeadDeltaSeconds": lead_delta,
                    }
                )
        except (KeyError, TypeError, ValueError):
            alignment_mismatches.append(
                {
                    "predictedAt": entry.get("predictedAt"),
                    "leadMinutes": entry.get("leadMinutes"),
                    "error": "invalid-or-missing-timestamp",
                }
            )

        if isinstance(score.get("persistenceCriticalSuccessIndex"), (int, float)):
            persistence_comparisons += 1
        horizon = _horizon_for_lead(int(entry.get("leadMinutes", -1)))
        if horizon is not None:
            horizon_entries[horizon].append(score)

    horizons: dict[str, dict[str, Any]] = {}
    for target, entries in sorted(horizon_entries.items()):
        hits = sum(int(entry.get("hits", 0) or 0) for entry in entries)
        misses = sum(int(entry.get("misses", 0) or 0) for entry in entries)
        false_alarms = sum(int(entry.get("falseAlarms", 0) or 0) for entry in entries)
        pooled_csi = _ratio(hits, hits + misses + false_alarms)
        pair_skills = [
            float(entry["criticalSuccessIndexSkill"])
            for entry in entries
            if isinstance(entry.get("criticalSuccessIndexSkill"), (int, float))
        ]
        persistence_csi = [
            float(entry["persistenceCriticalSuccessIndex"])
            for entry in entries
            if isinstance(entry.get("persistenceCriticalSuccessIndex"), (int, float))
        ]
        mean_pair_skill = _mean(pair_skills)
        mean_persistence_csi = _mean(persistence_csi)
        pooled_proxy_skill = (
            pooled_csi - mean_persistence_csi
            if pooled_csi is not None and mean_persistence_csi is not None
            else None
        )
        direction_differs = bool(
            mean_pair_skill is not None
            and pooled_proxy_skill is not None
            and (
                (mean_pair_skill < 0 <= pooled_proxy_skill)
                or (pooled_proxy_skill < 0 <= mean_pair_skill)
            )
        )
        horizons[str(target)] = {
            "sampleCount": len(entries),
            "eventPixelCount": hits + misses + false_alarms,
            "precision": _ratio(hits, hits + false_alarms),
            "recall": _ratio(hits, hits + misses),
            "falseAlarmRate": _ratio(false_alarms, hits + false_alarms),
            "missRate": _ratio(misses, hits + misses),
            "pooledCriticalSuccessIndex": round(pooled_csi, 6) if pooled_csi is not None else None,
            "meanPairSkillOverPersistence": (
                round(mean_pair_skill, 6) if mean_pair_skill is not None else None
            ),
            "meanPairPersistenceCriticalSuccessIndex": (
                round(mean_persistence_csi, 6) if mean_persistence_csi is not None else None
            ),
            "pooledCsiMinusMeanPairPersistenceCsi": (
                round(pooled_proxy_skill, 6) if pooled_proxy_skill is not None else None
            ),
            "aggregationDirectionDiffers": direction_differs,
        }

    for reported in (report.get("observatory") or {}).get("horizons", []):
        target = str(reported.get("targetLeadMinutes"))
        recalculated = horizons.get(target)
        if recalculated is None:
            horizon_skips.append({"targetLeadMinutes": target, "reason": "no-public-pairs"})
            continue
        if int(reported.get("sampleCount", -1)) != int(recalculated["sampleCount"]):
            horizon_skips.append(
                {
                    "targetLeadMinutes": target,
                    "reason": "public-detail-is-a-bounded-subset",
                    "reportedSampleCount": reported.get("sampleCount"),
                    "publicPairCount": recalculated["sampleCount"],
                }
            )
            continue
        for metric, recalculated_name in (
            ("precision", "precision"),
            ("recall", "recall"),
            ("criticalSuccessIndex", "pooledCriticalSuccessIndex"),
            ("falseAlarmRate", "falseAlarmRate"),
            ("missRate", "missRate"),
        ):
            value = recalculated[recalculated_name]
            difference = _difference(value, reported.get(metric))
            if difference is not None and difference > ROUNDING_TOLERANCE:
                horizon_mismatches.append(
                    {
                        "targetLeadMinutes": target,
                        "metric": metric,
                        "reported": reported.get(metric),
                        "recalculated": round(float(value), 8),
                    }
                )

    failures: list[str] = []
    if len(results) < minimum_pairs:
        failures.append("minimum-pairs")
    if metric_mismatches:
        failures.append("metric-recalculation")
    if alignment_mismatches:
        failures.append("timestamp-alignment")
    if horizon_mismatches:
        failures.append("horizon-recalculation")
    if persistence_comparisons != len(results):
        failures.append("persistence-evidence")

    return {
        "status": "pass" if not failures else "fail",
        "pairCount": len(results),
        "requiredPairCount": minimum_pairs,
        "failures": failures,
        "alignment": {
            "toleranceSeconds": ALIGNMENT_TOLERANCE_SECONDS,
            "outsideToleranceCount": len(alignment_mismatches),
            "mismatches": alignment_mismatches[:20],
        },
        "metricRecalculation": {
            "roundingTolerance": ROUNDING_TOLERANCE,
            "mismatchCount": len(metric_mismatches),
            "mismatches": metric_mismatches[:20],
        },
        "horizonRecalculation": {
            "mismatchCount": len(horizon_mismatches),
            "mismatches": horizon_mismatches[:20],
            "skipped": horizon_skips,
        },
        "persistence": {
            "comparisonCount": persistence_comparisons,
            "missingCount": len(results) - persistence_comparisons,
        },
        "horizons": horizons,
        "limitations": [
            "Public counts can independently prove precision, recall and CSI.",
            "Raw-grid MAE and probabilistic Brier scores require the private verification cubes.",
            "Persistence counts are not public, so persistence CSI can be "
            "presence-checked but not independently reconstructed.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Independently audit WetMap public quality evidence"
    )
    parser.add_argument("report", type=Path)
    parser.add_argument("--minimum-pairs", type=int, default=50)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    audit = audit_report(
        json.loads(arguments.report.read_text(encoding="utf-8")),
        minimum_pairs=arguments.minimum_pairs,
    )
    rendered = json.dumps(audit, indent=2, sort_keys=True)
    if arguments.output:
        arguments.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0 if audit["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
