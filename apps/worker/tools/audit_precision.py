"""Local, read-only reconstruction from checksum-verified raw verification inputs.

Does not import production scoring code, update ledgers, select challengers or
change gates. The common-mask result is an additive counterfactual diagnostic,
NOT a replacement for published metrics or evidence of better forecasts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

MAX_BYTES = 64 * 1024 * 1024
CUBE_KEY = re.compile(r"nowcast/verification-cubes/(cube-\d{2}\.npz)")
FRAME_KEY = re.compile(r"/frames/(dk\.com\.\d{12}\.500_max\.webp)")


def ratio(a, b):
    return float(a / b) if b else None


def score_grid(predicted, actual, threshold=20, *, mask=None):
    if predicted.shape != actual.shape or predicted.ndim != 2:
        raise ValueError("Grid shape mismatch")
    if predicted.dtype != np.uint8 or actual.dtype != np.uint8:
        raise ValueError("Expected encoded uint8 grids")
    available = (predicted != 0) & (actual != 0)
    if mask is None:
        mask = available
    elif mask.shape != actual.shape or mask.dtype != bool or np.any(mask & ~available):
        raise ValueError("Invalid coverage mask")
    forecast = predicted[mask] >= threshold + 32
    observed = actual[mask] >= threshold + 32
    # Independent confusion-matrix implementation: truth*2 + forecast.
    tn, fa, miss, hit = map(int, np.bincount(observed * 2 + forecast, minlength=4))
    echo = forecast | observed
    errors = np.abs(predicted[mask].astype(float) - actual[mask].astype(float))
    return {
        "validPixels": int(mask.sum()),
        "hits": hit,
        "misses": miss,
        "falseAlarms": fa,
        "correctNegatives": tn,
        "precision": ratio(hit, hit + fa),
        "recall": ratio(hit, hit + miss),
        "criticalSuccessIndex": ratio(hit, hit + miss + fa),
        "falseAlarmRatio": ratio(fa, hit + fa),
        "dbzMeanAbsoluteError": (
            float(errors[echo].mean()) if echo.any() else (0.0 if mask.any() else None)
        ),
    }


def skill(forecast, baseline):
    a, b = forecast["criticalSuccessIndex"], baseline["criticalSuccessIndex"]
    return a - b if a is not None and b is not None else None


def compare_masks(predicted, persistence, actual):
    forecast_mask = (predicted != 0) & (actual != 0)
    baseline_mask = (persistence != 0) & (actual != 0)
    common = forecast_mask & baseline_mask
    return {
        "forecastValidPixels": int(forecast_mask.sum()),
        "persistenceValidPixels": int(baseline_mask.sum()),
        "commonValidPixels": int(common.sum()),
        "maskDifferencePixels": int((forecast_mask ^ baseline_mask).sum()),
        "commonCoverageFractionOfObserved": ratio(int(common.sum()), int((actual != 0).sum())),
        "independentMaskSkill": skill(
            score_grid(predicted, actual), score_grid(persistence, actual)
        ),
        "commonMaskSkill": skill(
            score_grid(predicted, actual, mask=common),
            score_grid(persistence, actual, mask=common),
        ),
    }


def utc(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.utcoffset() != timedelta(0):
        raise ValueError("Explicit UTC timestamp required")
    return result


def verified_file(directory, filename, checksum):
    path = directory / filename
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("Input exceeds byte budget")
    if hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
        raise ValueError("Input checksum mismatch")
    return path


def observation_grid(path, width, height):
    # Reimplement the documented alpha -> dBZ+32 encoding. INTER_AREA is part of
    # the sampling contract; no production verification/scoring helper is called.
    with Image.open(path) as image:
        alpha = np.asarray(image.convert("RGBA"))[..., 3]
    reduced = cv2.resize(alpha, (width, height), interpolation=cv2.INTER_AREA)
    dbz = np.rint((reduced.astype(np.float32) - 45) * (60 / 175) - 10)
    encoded = np.where(reduced >= 44, np.clip(dbz + 32, 1, 95), np.where(reduced > 0, 14, 0))
    return encoded.astype(np.uint8)


def pair_key(entry):
    return (
        entry.get("algorithmVersion", "unversioned"),
        utc(entry["basedOnObservedAt"]),
        utc(entry["predictedAt"]),
        utc(entry["observedAt"]),
        int(entry["leadMinutes"]),
    )


def mean(values):
    values = [value for value in values if value is not None]
    return sum(values) / len(values) if values else None


def audit(state, manifest, public, directory, *, minimum_pairs=50, include_pair_ids=False):
    observations, inventory, bounds = {}, set(), {}
    for frame in manifest["frames"]:
        match = FRAME_KEY.fullmatch(frame["url"])
        if not match:
            raise ValueError("Unexpected observation key")
        path = verified_file(directory, match[1], frame["sha256"])
        timestamp = utc(frame["observedAt"])
        named_time = datetime.strptime(match[1], "dk.com.%Y%m%d%H%M.500_max.webp").replace(
            tzinfo=timezone.utc
        )
        if named_time != timestamp:
            raise ValueError("Observation filename/valid timestamp mismatch")
        if timestamp in observations:
            raise ValueError("Duplicate observation timestamp")
        observations[timestamp] = path
        bounds[timestamp] = frame.get("bounds")
        inventory.add(path)
    published = {}
    for entry in public["results"]:
        key = pair_key(entry)
        if key in published:
            raise ValueError("Duplicate published pair")
        published[key] = entry
    pairs, mismatches, decoded = [], [], {}
    forecast_generations = set()
    identity = {"checked": 0, "missing": 0, "mismatched": 0}
    skipped, comparisons = defaultdict(int), 0

    def actual_at(timestamp, width, height):
        if not metadata.get("bounds") or bounds[timestamp] != metadata["bounds"]:
            raise ValueError("Forecast/observation geographic bounds mismatch")
        key = (timestamp, width, height)
        if key not in decoded:
            decoded[key] = observation_grid(observations[timestamp], width, height)
        return decoded[key]

    for metadata in state["forecasts"]:
        match = CUBE_KEY.fullmatch(metadata["dataKey"])
        if not match:
            raise ValueError("Unexpected cube key")
        path = verified_file(directory, match[1], metadata["sha256"])
        inventory.add(path)
        if sum(item.stat().st_size for item in inventory) > MAX_BYTES:
            raise ValueError("Input inventory exceeds byte budget")
        with zipfile.ZipFile(path) as archive:
            if sum(entry.file_size for entry in archive.infolist()) > MAX_BYTES:
                raise ValueError("Expanded cube exceeds byte budget")
        width, height, count = (int(metadata[name]) for name in ("width", "height", "frameCount"))
        if not (0 < width <= 512 and 0 < height <= 512 and 0 < count <= 13):
            raise ValueError("Unsupported cube dimensions")
        with np.load(path, allow_pickle=False) as archive:
            cube = archive["cube"]
        if cube.shape != (height, width, count) or cube.dtype != np.uint8:
            raise ValueError("Cube shape/type mismatch")
        frames = metadata["frames"]
        if len(frames) != count or frames[0]["leadMinutes"] != 0:
            raise ValueError("Invalid persistence frame index")
        base = utc(metadata["basedOnObservedAt"])
        generation = (metadata.get("algorithmVersion", "unversioned"), base)
        if generation in forecast_generations:
            raise ValueError("Duplicate forecast generation")
        forecast_generations.add(generation)
        if len({frame["leadMinutes"] for frame in frames}) != count:
            raise ValueError("Duplicate forecast lead")
        if utc(frames[0]["predictedAt"]) != base:
            raise ValueError("Persistence timestamp mismatch")
        if base in observations:
            identity["checked"] += 1
            identity["mismatched"] += int(
                not np.array_equal(cube[..., 0], actual_at(base, width, height))
            )
        else:
            identity["missing"] += 1
        for index, frame in enumerate(frames[1:], 1):
            lead, target = int(frame["leadMinutes"]), utc(frame["predictedAt"])
            if lead not in range(5, 61, 5) or target != base + timedelta(minutes=lead):
                raise ValueError("Forecast valid-time/lead mismatch")
            if target not in observations:
                skipped["missing-observation"] += 1
                continue
            cohort = metadata.get("algorithmVersion", "unversioned")
            entry = published.get((cohort, base, target, target, lead))
            actual = actual_at(target, width, height)
            predicted, persistence = cube[..., index], cube[..., 0]
            pairs.append(
                {
                    "algorithmVersion": cohort,
                    "leadMinutes": lead,
                    "observedAt": target.isoformat(),
                    "basedOnObservedAt": base.isoformat(),
                    "published": entry is not None,
                    **compare_masks(predicted, persistence, actual),
                }
            )
            if entry is None:
                skipped["missing-public-pair"] += 1
                continue
            rows = list(entry.get("thresholdScores") or [])
            if entry.get("thresholdDbz") == 20:
                rows.append(entry)
            if not rows:
                raise ValueError("Missing explicit threshold scores")
            for row in rows:
                threshold = int(row["thresholdDbz"])
                calculated = score_grid(predicted, actual, threshold)
                baseline = score_grid(persistence, actual, threshold)
                calculated["persistenceCriticalSuccessIndex"] = baseline["criticalSuccessIndex"]
                calculated["criticalSuccessIndexSkill"] = skill(calculated, baseline)
                for name, expected in calculated.items():
                    if name == "falseAlarmRatio":
                        continue  # Public per-pair contract does not expose FAR.
                    value = row.get(name)
                    if name == "dbzMeanAbsoluteError":
                        tolerance = 0.0051
                    elif name == "criticalSuccessIndexSkill":
                        tolerance = 0.00015  # Difference of two rounded CSIs.
                    else:
                        tolerance = 0.000055
                    matches = (
                        value is None
                        if expected is None
                        else (
                            isinstance(value, (int, float))
                            and not isinstance(value, bool)
                            and math.isfinite(value)
                            and abs(value - expected) <= tolerance
                        )
                    )
                    if not matches:
                        mismatches.append(
                            {
                                "metric": name,
                                "algorithmVersion": cohort,
                                "basedOnObservedAt": base.isoformat(),
                                "predictedAt": target.isoformat(),
                                "leadMinutes": lead,
                                "thresholdDbz": threshold,
                                "expected": expected,
                                "reported": value
                                if isinstance(value, (int, float)) and math.isfinite(value)
                                else None,
                            }
                        )
                comparisons += 1
    cohorts = {}
    for cohort in sorted({pair["algorithmVersion"] for pair in pairs}):
        cohorts[cohort] = {}
        for lead in sorted(
            {pair["leadMinutes"] for pair in pairs if pair["algorithmVersion"] == cohort}
        ):
            entries = [
                pair
                for pair in pairs
                if pair["algorithmVersion"] == cohort and pair["leadMinutes"] == lead
            ]
            cohorts[cohort][str(lead)] = {
                "pairCount": len(entries),
                "publishedPairCount": sum(pair["published"] for pair in entries),
                "differentMaskPairs": sum(pair["maskDifferencePixels"] > 0 for pair in entries),
                "meanIndependentMaskSkill": mean(pair["independentMaskSkill"] for pair in entries),
                "meanCommonMaskSkill": mean(pair["commonMaskSkill"] for pair in entries),
                "meanCommonCoverageFractionOfObserved": mean(
                    pair["commonCoverageFractionOfObserved"] for pair in entries
                ),
            }
    published_pairs = [pair for pair in pairs if pair["published"]]
    blocked = [] if len(published_pairs) >= minimum_pairs else ["minimum-pairs"]
    if identity["missing"]:
        blocked.append("missing-persistence-source")
    report = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "publicReportGeneratedAt": public.get("generatedAt"),
        "stateGeneratedAt": state.get("generatedAt"),
        "reproductionStatus": "fail"
        if mismatches or identity["mismatched"]
        else ("blocked" if blocked else "pass"),
        "minimumPairs": minimum_pairs,
        "pairCount": len(published_pairs),
        "availablePairCount": len(pairs),
        "scoreComparisons": comparisons,
        "uniqueObservedTimes": len({pair["observedAt"] for pair in pairs}),
        "publishedUniqueObservedTimes": len({pair["observedAt"] for pair in published_pairs}),
        "uniqueForecastOrigins": len({pair["basedOnObservedAt"] for pair in pairs}),
        "blockedReasons": blocked,
        "mismatchCount": len(mismatches),
        "mismatches": mismatches[:20],
        "persistenceIdentity": identity,
        "skipped": dict(skipped),
        "coverageComparison": {
            "differentMaskPairs": sum(pair["maskDifferencePixels"] > 0 for pair in pairs),
            "maximumMaskDifferencePixels": max(
                (pair["maskDifferencePixels"] for pair in pairs), default=0
            ),
            "diagnosticOnly": True,
        },
        "cohorts": cohorts,
        "inputInventory": {
            "fileCount": len(inventory),
            "bytes": sum(path.stat().st_size for path in inventory),
        },
        "limitations": [
            "Overlapping forecast pairs/pixels are not independent weather events; no IID confidence intervals.",
            "Common-mask skill is an additive diagnostic, not a new production metric or a promotion decision.",
            "This sample cannot establish seasonal/regional skill or independent published Brier agreement.",
            "Projected WebP bounds/encoding are checked; ODIM georeprojection is not independently reconstructed.",
            "No model tuning, archive write, gate change or Redis service is performed.",
        ],
    }
    if include_pair_ids:
        report["verifiedPairIds"] = [
            [
                pair["algorithmVersion"],
                pair["basedOnObservedAt"],
                pair["observedAt"],
                pair["leadMinutes"],
            ]
            for pair in published_pairs
        ]
    return report


def combine_audits(reports, *, minimum_pairs=50):
    """Apply the same evidence floor to a deduplicated union, never summed counts."""
    identities = {tuple(identity) for report in reports for identity in report["verifiedPairIds"]}
    blocked = sorted(
        {
            reason
            for report in reports
            for reason in report["blockedReasons"]
            if reason != "minimum-pairs"
        }
    )
    if len(identities) < minimum_pairs:
        blocked.append("minimum-pairs")
    mismatches = sum(report["mismatchCount"] for report in reports)
    failed = mismatches or any(report["reproductionStatus"] == "fail" for report in reports)
    return {
        "schemaVersion": 2,
        "scope": "deduplicated-multi-snapshot-raw-reconstruction",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "minimumPairs": minimum_pairs,
        "pairCount": len(identities),
        "snapshotCount": len(reports),
        "overlappingPairCount": sum(report["pairCount"] for report in reports) - len(identities),
        "uniqueObservedTimes": len({identity[2] for identity in identities}),
        "uniqueForecastOrigins": len({identity[1] for identity in identities}),
        "verifiedPairIdsSha256": hashlib.sha256(
            json.dumps(sorted(identities)).encode()
        ).hexdigest(),
        "reproductionStatus": "fail" if failed else ("blocked" if blocked else "pass"),
        "mismatchCount": mismatches,
        "blockedReasons": blocked,
        "snapshots": [
            {key: value for key, value in report.items() if key != "verifiedPairIds"}
            for report in reports
        ],
        "limitations": [
            "The 50-pair floor is applied to the deduplicated union, not lowered for any snapshot.",
            "Overlapping pairs/pixels are not independent weather events; no IID confidence intervals.",
            "Covered metrics: counts, precision/recall/CSI, dBZ MAE and persistence skill; not full published Brier acceptance.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, nargs="+")
    parser.add_argument("--minimum-pairs", type=int, default=50)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.minimum_pairs < 1:
        parser.error("minimum-pairs must be positive")
    source_names = ("verification-state.json", "frames.json", "public-quality.json")
    reports = []
    for directory in args.directory:
        documents = [json.loads((directory / name).read_text()) for name in source_names]
        report = audit(
            *documents, directory, minimum_pairs=args.minimum_pairs, include_pair_ids=True
        )
        report["sourceDocuments"] = {
            name: {"sha256": hashlib.sha256((directory / name).read_bytes()).hexdigest()}
            for name in source_names
        }
        reports.append(report)
    report = (
        combine_audits(reports, minimum_pairs=args.minimum_pairs)
        if len(reports) > 1
        else reports[0]
    )
    report.pop("verifiedPairIds", None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "reproductionStatus",
                    "pairCount",
                    "mismatchCount",
                    "coverageComparison",
                )
                if key in report
            }
        )
    )
    return 0 if report["reproductionStatus"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
