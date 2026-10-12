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
