"""Read-only local v2 replay versus the independent raw-grid scoring oracle.

Requires checksum-verified snapshots in audit_precision's format. This checks
locally generated diagnostic rows, not a published v2 ledger or weather skill.
Run with the worker package installed; only aggregate JSON is printed.
"""

import argparse
import json
import math
from pathlib import Path

import numpy as np

from audit_precision import audit, observation_grid, score_grid, utc
from wetmap_worker.verification import verify_previous_nowcast


def equal(value, expected, tolerance):
    if not (
        (value is None and expected is None)
        or (
            value is not None
            and expected is not None
            and math.isfinite(value)
            and abs(value - expected) <= tolerance
        )
    ):
        raise ValueError(f"Oracle mismatch: {value} != {expected}")


def replay(directories):
    seen = set()
    counts = dict.fromkeys(
        (
            "rawPairs",
            "scoreChecks",
            "candidateComparisons",
            "brierChecks",
            "mismatches",
            "secondaryBytes",
            "maximumSecondaryBytes",
        ),
        0,
    )

    def check_score(value, predicted, actual, mask):
        expected = score_grid(predicted, actual, mask=mask)
        for name, target in expected.items():
            equal(value[name], target, 0.0051 if name == "dbzMeanAbsoluteError" else 0.000055)
        counts["scoreChecks"] += 1

    for directory in directories:
        state, manifest, public = [
            json.loads((directory / name).read_text())
            for name in ("verification-state.json", "frames.json", "public-quality.json")
        ]
        validated = audit(state, manifest, public, directory)
        if validated["mismatchCount"] or validated["persistenceIdentity"]["mismatched"]:
            raise ValueError("Raw snapshot does not reconstruct legacy evidence")
        observations = {
            utc(row["observedAt"]): directory / Path(row["url"]).name for row in manifest["frames"]
        }
        for meta in state["forecasts"]:
            cube_path = directory / Path(meta["dataKey"]).name
            with np.load(cube_path, allow_pickle=False) as archive:
                arrays = {name: archive[name] for name in archive.files}
            cube, persistence = arrays["cube"], arrays["cube"][..., 0]
            for index, frame in enumerate(meta["frames"][1:], 1):
                target = utc(frame["predictedAt"])
                identity = (
                    meta["algorithmVersion"],
                    utc(meta["basedOnObservedAt"]),
                    target,
                    frame["leadMinutes"],
                )
                if target not in observations or identity in seen:
                    continue
                seen.add(identity)
                actual = observation_grid(observations[target], meta["width"], meta["height"])
                result = verify_previous_nowcast(
                    meta, cube_path, observations[target], frame["predictedAt"]
                )
                value = result["sharedCoverageComparison"]
                mask = (actual > 0) & (persistence > 0) & (cube[..., index] > 0)
                check_score(value["forecastScore"], cube[..., index], actual, mask)
                check_score(value["persistenceScore"], persistence, actual, mask)
                observed_count = int(np.count_nonzero(actual))
                equal(
                    value["coverage"]["commonFractionOfObserved"],
                    float(mask.sum() / observed_count) if observed_count else None,
                    0.00000051,
                )
                for candidate in value["candidates"]:
                    metadata = next(
                        row
                        for row in meta["shadowCandidates"]
                        if row["candidateId"] == candidate["candidateId"]
                    )
                    candidate_grid = arrays[metadata["cubeKey"]][..., index]
                    incumbent = cube[..., index]
                    common = mask & (candidate_grid > 0)
                    check_score(candidate["forecastScore"], candidate_grid, actual, common)
                    check_score(candidate["incumbentScore"], incumbent, actual, common)
                    check_score(candidate["persistenceScore"], persistence, actual, common)
                    counts["candidateComparisons"] += 1
                    if candidate.get("probability", {}).get("status") == "available":
                        observed = (actual[common] >= 52).astype(float)
                        probability = (
                            arrays[metadata["probabilityCubeKey"]][..., index][common].astype(float)
                            / 100
                        )
                        persistent = (persistence[common] >= 52).astype(float)
                        brier = float(np.average(np.square(probability - observed)))
                        baseline = float(np.average(np.square(persistent - observed)))
                        equal(candidate["probability"]["brierScore"], brier, 0.00000051)
                        equal(
                            candidate["probability"]["persistenceBrierScore"],
                            baseline,
                            0.00000051,
                        )
                        equal(
                            candidate["probability"]["brierSkillScore"],
                            1 - brier / baseline if baseline else None,
                            0.000055,
                        )
                        counts["brierChecks"] += 1
                counts["rawPairs"] += 1
                size = len(json.dumps(value).encode())
                counts["secondaryBytes"] += size
                counts["maximumSecondaryBytes"] = max(counts["maximumSecondaryBytes"], size)
    return {
        "mode": "local-verifier-vs-independent-oracle",
        "comparisonVersion": "shared-coverage-v2",
        **counts,
        "publishedV2LedgerChecked": False,
        "promotionEnabled": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", type=Path, nargs="+")
    print(json.dumps(replay(parser.parse_args().directories), allow_nan=False))
