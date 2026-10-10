import json
import sys
from datetime import datetime, timezone
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
limit_minutes = int(sys.argv[2])
if not manifest["frames"]:
    raise SystemExit("No radar frames")
latest = datetime.fromisoformat(manifest["frames"][-1]["observedAt"].replace("Z", "+00:00"))
age = (datetime.now(timezone.utc) - latest).total_seconds() / 60
print(f"Latest radar frame is {age:.1f} minutes old")
if age > limit_minutes:
    raise SystemExit(f"Radar data is stale (>{limit_minutes} minutes)")
