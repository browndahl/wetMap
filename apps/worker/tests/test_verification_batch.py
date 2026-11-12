from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from dataclasses import replace
from pathlib import Path

from wetmap_worker.model import Frame
from wetmap_worker.verification_batch import plan_verifications, run_verifications
from wetmap_worker.verification import append_verification_history


def fixture():
    base = datetime(2026, 11, 12, 10, tzinfo=timezone.utc)
    times = [
        (base + timedelta(minutes=lead)).isoformat().replace("+00:00", "Z")
        for lead in (0, 5, 10, 15)
    ]
    forecast = {
        "algorithmVersion": "test-v1",
        "basedOnObservedAt": times[0],
        "dataKey": "nowcast/verification-cubes/cube-00.npz",
        "bounds": [7, 54, 13, 58],
        "frames": [
            {"leadMinutes": lead, "predictedAt": stamp}
            for lead, stamp in zip((0, 5, 10, 15), times)
        ],
    }
    frames = [
        Frame(
            f"frame-{lead}",
            stamp,
            stamp,
            f"/frames/frame-{lead}.webp",
            [7, 54, 13, 58],
            "DBZH",
            "dBZ",
            hashlib.sha256(b"image").hexdigest(),
        )
        for lead, stamp in zip((5, 10, 15), times[1:])
    ]
    return {"forecasts": [forecast]}, frames


def result(task):
    return {
        "algorithmVersion": task.forecast["algorithmVersion"],
        "basedOnObservedAt": task.forecast["basedOnObservedAt"],
        "observedAt": task.observation.observedAt,
        "predictedAt": task.frame["predictedAt"],
        "leadMinutes": task.frame["leadMinutes"],
    }


def test_plans_intermediate_and_cached_observations_not_only_latest():
    state, frames = fixture()
    tasks = plan_verifications(state, frames, None)
    assert [task.frame["leadMinutes"] for task in tasks] == [5, 10, 15]
    assert plan_verifications(state, frames, {"results": [result(task) for task in tasks]}) == []


def test_identity_includes_algorithm_and_declared_lead_not_only_source_and_observation():
    state, frames = fixture()
    old = result(plan_verifications(state, frames, None)[0])
    old["algorithmVersion"] = "old-version"
    assert len(plan_verifications(state, frames, {"results": [old]})) == 3
    old["algorithmVersion"] = "test-v1"
    old["leadMinutes"] = 15
    assert len(plan_verifications(state, frames, {"results": [old]})) == 3


def test_duplicate_metadata_and_observations_do_not_duplicate_planned_pairs():
    state, frames = fixture()
    state["forecasts"] *= 2
    assert len(plan_verifications(state, frames * 2, None)) == 3


def test_batch_downloads_each_cube_and_observation_once(tmp_path: Path):
    state, frames = fixture()
    second = {**state["forecasts"][0], "algorithmVersion": "other-version"}
    state["forecasts"].append(second)
    cube_calls, frame_calls = [], []

    def cube(directory, key):
        cube_calls.append(key)
        return directory / "cube-00.npz"

    def images(directory, names):
        frame_calls.extend(names)
        paths = [directory / name for name in names]
        for path in paths:
            path.write_bytes(b"image")
        return paths

    results, report = run_verifications(
        state,
        frames,
        None,
        tmp_path,
        load_cube=cube,
        load_frames=images,
        verify=lambda meta, _cube, _image, observed: {
            "algorithmVersion": meta["algorithmVersion"],
            "observedAt": observed,
            "basedOnObservedAt": meta["basedOnObservedAt"],
            "predictedAt": observed,
            "leadMinutes": int(
                (
                    datetime.fromisoformat(observed.replace("Z", "+00:00"))
                    - datetime.fromisoformat(meta["basedOnObservedAt"].replace("Z", "+00:00"))
                ).total_seconds()
                / 60
            ),
        },
    )
    assert len(results) == 6
    assert len(cube_calls) == 1
    assert len(frame_calls) == 3
    assert report["completed"] == 6 and report["errors"] == 0


def test_failed_cube_is_not_retried_per_observation_and_other_work_continues(tmp_path):
    state, frames = fixture()
    calls = []

    def fail(_directory, key):
        calls.append(key)
        raise TimeoutError("unavailable")

    results, report = run_verifications(state, frames, None, tmp_path, load_cube=fail)
    assert results == []
    assert len(calls) == 1
    assert report["errors"] == 3


def test_pair_and_time_budgets_report_deferred_work_without_claiming_completeness(tmp_path):
    state, frames = fixture()
    ticks = iter([0.0, 46.0, 46.0])
    results, report = run_verifications(state, frames, None, tmp_path, clock=lambda: next(ticks))
    assert results == []
    assert report["planned"] == 3 and report["deferred"] == 3
    assert report["budgetExhausted"] is True
    results, report = run_verifications(state, frames, None, tmp_path, max_pairs=0)
    assert not results and report["deferred"] == 3


def test_failed_observation_checksum_cannot_enter_verification(tmp_path):
    state, frames = fixture()
    frames[0] = replace(frames[0], sha256="0" * 64)
    verified = []

    def images(directory, names):
        paths = [directory / name for name in names]
        for path in paths:
            path.write_bytes(b"image")
        return paths

    results, report = run_verifications(
        state,
        frames,
        None,
        tmp_path,
        max_pairs=1,
        load_cube=lambda directory, _key: directory / "cube.npz",
        load_frames=images,
        verify=lambda *args: verified.append(args),
    )
    assert results == [] and verified == []
    assert report["errors"] == 1


def test_existing_record_is_never_rewritten_and_incoming_duplicates_count_once(tmp_path):
    state, frames = fixture()
    original = {
        **result(plan_verifications(state, frames, None)[0]),
        "verifiedAt": frames[0].observedAt,
        "hits": 1,
        "misses": 0,
        "falseAlarms": 0,
        "criticalSuccessIndex": 1.0,
        "unknownOldField": "preserve",
    }
    path = tmp_path / "history.json"
    path.write_text(json.dumps({"results": [original]}))
    attempted_rewrite = {**original, "hits": 999, "verifiedAt": frames[-1].observedAt}
    report = append_verification_history(path, [attempted_rewrite, attempted_rewrite])
    assert report["results"] == [original]
    other_version = {**original, "algorithmVersion": "other-version"}
    report = append_verification_history(path, [other_version, other_version])
    assert len(report["results"]) == 2


def test_one_failed_cube_does_not_block_another_forecast(tmp_path):
    state, frames = fixture()
    state["forecasts"].append(
        {
            **state["forecasts"][0],
            "algorithmVersion": "other-version",
            "dataKey": "nowcast/verification-cubes/cube-01.npz",
        }
    )
    calls = []

    def cube(directory, key):
        calls.append(key)
        if "00" in key:
            raise TimeoutError("unavailable")
        return directory / "good.npz"

    def images(directory, names):
        path = directory / names[0]
        path.write_bytes(b"image")
        return [path]

    def verify(meta, _cube, _image, observed):
        task = next(
            task
            for task in plan_verifications({"forecasts": [meta]}, frames, None)
            if task.observation.observedAt == observed
        )
        return result(task)

    results, report = run_verifications(
        state, frames, None, tmp_path, load_cube=cube, load_frames=images, verify=verify
    )
    assert len(results) == 3 and report["errors"] == 3
    assert len(calls) == 2
    assert report["coverageFraction"] == 0.5 and not report["complete"]


def test_existing_pairs_count_toward_completeness_without_repeat_downloads(tmp_path):
    state, frames = fixture()
    history = {"results": [result(task) for task in plan_verifications(state, frames, None)]}
    results, report = run_verifications(state, frames, history, tmp_path)
    assert results == [] and report["alreadyVerified"] == 3
    assert report["coverageFraction"] == 1.0 and report["complete"]
    assert report["cubeDownloads"] == 0 and report["observationDownloads"] == 0


def test_equivalent_utc_spellings_do_not_duplicate_a_pair():
    state, frames = fixture()
    records = [result(task) for task in plan_verifications(state, frames, None)]
    for entry in records:
        for key in ("basedOnObservedAt", "predictedAt", "observedAt"):
            entry[key] = entry[key].replace("Z", "+00:00")
    assert plan_verifications(state, frames, {"results": records}) == []
