import json
import sys
from datetime import datetime, timezone
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if report.get("sampleCount", 0) < 1:
    raise SystemExit("Nowcast quality has no verification samples")

generated = datetime.fromisoformat(report["generatedAt"].replace("Z", "+00:00"))
age_minutes = (datetime.now(timezone.utc) - generated).total_seconds() / 60
if age_minutes > 45:
    raise SystemExit(f"Nowcast verification is stale ({age_minutes:.1f} minutes)")

leads = {
    int(summary["leadMinutes"])
    for summary in report.get("byLeadMinutes", [])
    if summary.get("sampleCount", 0) > 0
}
print(
    f"Nowcast verification has {report['sampleCount']} samples across leads "
    f"{sorted(leads)}; generated {age_minutes:.1f} minutes ago"
)

# Allow one warm-up hour after deployment of the multi-horizon ledger.
if report.get("schemaVersion", 1) >= 2 and report["sampleCount"] >= 150:
    required = {15, 30, 45, 60}
    if not required.issubset(leads):
        raise SystemExit(
            f"Multi-horizon verification is incomplete; missing {sorted(required - leads)}"
        )

if report.get("schemaVersion", 1) >= 4:
    observatory = report.get("observatory") or {}
    targets = {
        int(horizon["targetLeadMinutes"]) for horizon in observatory.get("horizons", [])
    }
    required_targets = {15, 30, 45, 60}
    if targets != required_targets:
        raise SystemExit(
            "Precision Observatory is incomplete; expected horizons "
            f"{sorted(required_targets)}, got {sorted(targets)}"
        )
    print(
        "Precision Observatory status "
        f"{observatory.get('overallStatus', 'unknown')} with "
        f"{observatory.get('verifiedHorizonCount', 0)}/4 verified horizons"
    )

ground_gauge = report.get("groundGauge") or {}
if ground_gauge.get("schemaVersion", 0) >= 3:
    calibration = ground_gauge.get("calibration") or {}
    candidates = calibration.get("candidates") or []
    combinations = {
        (int(candidate["thresholdDbz"]), int(candidate["spatialRadiusPixels"]))
        for candidate in candidates
    }
    required_combinations = {
        (threshold, radius) for threshold in (5, 10, 15, 20) for radius in (1, 3, 5)
    }
    if combinations != required_combinations:
        raise SystemExit(
            "Radar threshold calibration grid is incomplete; expected 12 candidates"
        )
    print(
        "Radar calibration status "
        f"{calibration.get('status', 'unknown')} with applied threshold "
        f"{calibration.get('appliedThresholdDbz', 'unknown')} dBZ"
    )

consistency = report.get("geographicConsistency") or {}
if consistency:
    if consistency.get("status") != "verified":
        raise SystemExit(
            "Map/point geographic consistency is degraded: "
            f"{consistency.get('rainClassificationMismatchCount', 'unknown')} rain mismatches"
        )
    if int(consistency.get("locationCount", 0)) < 18:
        raise SystemExit("Geographic consistency covers too few Danish test locations")
    if int(consistency.get("frameCount", 0)) != 13:
        raise SystemExit("Geographic consistency does not cover observation plus 60-minute nowcast")
    expected_comparisons = int(consistency["locationCount"]) * int(
        consistency["frameCount"]
    )
    if int(consistency.get("comparisonCount", 0)) != expected_comparisons:
        raise SystemExit("Geographic consistency comparison count is incomplete")
    if int(consistency.get("valueMismatchCount", 0)) != 0:
        raise SystemExit("Map and point dBZ values disagree")
    print(
        "Geographic consistency verified across "
        f"{consistency['locationCount']} locations and "
        f"{consistency['frameCount']} frames"
    )

for candidate in report.get("shadowCandidates", []):
    candidate_id = candidate.get("candidateId")
    if candidate_id not in {
        "trajectory-recency-flow-v1",
        "trajectory-speed-bias-v2",
        "regime-adaptive-ensemble-v3",
        "probability-gated-ensemble-v4",
    }:
        raise SystemExit(f"Unknown shadow nowcast candidate {candidate.get('candidateId')}")
    lead_entries = candidate.get("byLeadMinutes", [])
    candidate_leads = {int(entry["leadMinutes"]) for entry in lead_entries}
    if not candidate_leads.issubset({40, 50, 60}):
        raise SystemExit(f"Shadow candidate has invalid leads {sorted(candidate_leads)}")
    for entry in lead_entries:
        if entry.get("status") not in {
            "collecting",
            "awaiting-rain",
            "promotable",
            "held-back",
        }:
            raise SystemExit("Shadow candidate has an invalid promotion status")
        if not entry.get("safeToPromote"):
            continue
        if int(entry.get("sampleCount", 0)) < 48:
            raise SystemExit("Shadow candidate promoted without 48 paired samples")
        if int(entry.get("eventPixelCount", 0)) < 1000:
            raise SystemExit("Shadow candidate promoted without enough rain evidence")
        if float(entry.get("criticalSuccessIndex", -1)) < 0.2:
            raise SystemExit("Shadow candidate promoted below the CSI floor")
        if float(entry.get("criticalSuccessIndexImprovement", -1)) < 0.02:
            raise SystemExit("Shadow candidate promoted without enough CSI improvement")
        if float(entry.get("meanCriticalSuccessIndexSkill", -1)) < 0:
            raise SystemExit("Shadow candidate promoted below persistence skill")
        if float(entry.get("falseAlarmRateIncrease", 1)) > 0.02:
            raise SystemExit("Shadow candidate promoted with too many additional false alarms")
        if (
            candidate_id
            in {"regime-adaptive-ensemble-v3", "probability-gated-ensemble-v4"}
            and float(entry.get("meanBrierSkillScore", -1)) < 0
        ):
            raise SystemExit("Adaptive ensemble promoted below persistence Brier skill")
    print(
        f"Shadow nowcast candidate {candidate_id} measured at leads "
        f"{sorted(candidate_leads)}; promoted "
        f"{candidate.get('safeToPromoteLeadMinutes', [])}"
    )
