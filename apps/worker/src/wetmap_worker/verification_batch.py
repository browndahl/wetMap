"""Bounded, resumable scoring of every retained valid observation, not just latest."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from .model import Frame
from .nowcast import _parse_time
from .storage import download_frames_r2, download_verification_cube_r2
from .verification import (
    FORECAST_MATCH_TOLERANCE_SECONDS,
    FORECAST_RETENTION_MINUTES,
    verification_identity,
    verify_previous_nowcast,
)

MAX_PAIRS = 192
TIME_BUDGET_SECONDS = 45


@dataclass(frozen=True)
class VerificationTask:
    forecast: dict
    observation: Frame
    frame: dict

    def identity(self):
        return verification_identity(
            {
                **self.forecast,
                **self.frame,
                "observedAt": self.observation.observedAt,
            }
        )


def plan_verifications(state, observations, history, *, rejections=None):
    forecasts = state.get("forecasts", [])
    if len(forecasts) > 16 or len(observations) > 24:
        raise ValueError("Verification inputs exceed retained-state budget")
    seen = {verification_identity(entry) for entry in (history or {}).get("results", [])}
    tasks = []
    for forecast in forecasts:
        try:
            base = _parse_time(forecast["basedOnObservedAt"])
            frames = [
                frame
                for frame in forecast["frames"]
                if int(frame["leadMinutes"]) in range(5, 61, 5)
            ]
            if len(frames) > 12 or len({frame["leadMinutes"] for frame in frames}) != len(frames):
                raise ValueError("Duplicate/invalid forecast leads")
            for frame in frames:
                if _parse_time(frame["predictedAt"]) != base + timedelta(
                    minutes=int(frame["leadMinutes"])
                ):
                    raise ValueError("Invalid forecast valid time")
            for observation in sorted(observations, key=lambda value: value.observedAt):
                valid_at = _parse_time(observation.observedAt)
                age = (valid_at - base).total_seconds() / 60
                if not frames or age <= 0 or age > FORECAST_RETENTION_MINUTES:
                    continue
                selected = min(
                    frames,
                    key=lambda frame: abs(
                        (_parse_time(frame["predictedAt"]) - valid_at).total_seconds()
                    ),
                )
                if (
                    abs((_parse_time(selected["predictedAt"]) - valid_at).total_seconds())
                    > FORECAST_MATCH_TOLERANCE_SECONDS
                ):
                    continue
                task = VerificationTask(forecast, observation, selected)
                key = task.identity()
                if key not in seen:
                    tasks.append(task)
                    seen.add(key)
        except (KeyError, TypeError, ValueError):
            if rejections is not None:
                rejections.append(forecast.get("basedOnObservedAt"))
            logging.exception("nowcast.verification.plan-rejected")
    return tasks


def run_verifications(
    state,
    observations,
    history,
    directory: Path,
    *,
    max_pairs=MAX_PAIRS,
    time_budget=TIME_BUDGET_SECONDS,
    clock=time.monotonic,
    load_cube=download_verification_cube_r2,
    load_frames=download_frames_r2,
    verify=verify_previous_nowcast,
):
    started = clock()
    rejections = []
    tasks = plan_verifications(state, observations, history, rejections=rejections)
    eligible = len(plan_verifications(state, observations, None))
    already_verified = eligible - len(tasks)
    cubes, images, results = {}, {}, []
    errors, attempted = 0, 0
    for task in tasks:
        if attempted >= max_pairs or clock() - started >= time_budget:
            break
        attempted += 1
        try:
            key = task.forecast["dataKey"]
            if key not in cubes:
                try:
                    cubes[key] = load_cube(directory, key)
                except Exception as error:
                    cubes[key] = error
            if isinstance(cubes[key], Exception):
                raise RuntimeError("Cube unavailable in this run") from cubes[key]
            if clock() - started >= time_budget:
                attempted -= 1
                break
            frame = task.observation
            if frame.url not in images:
                try:
                    if (
                        frame.url != f"/frames/{frame.id}.webp"
                        or "/" in frame.id
                        or ".." in frame.id
                    ):
                        raise ValueError("Invalid observation image key")
                    image = load_frames(directory, [f"{frame.id}.webp"])[0]
                    if hashlib.sha256(image.read_bytes()).hexdigest() != frame.sha256:
                        raise ValueError("Observation checksum mismatch")
                    images[frame.url] = image
                except Exception as error:
                    images[frame.url] = error
            if isinstance(images[frame.url], Exception):
                raise RuntimeError("Observation unavailable in this run") from images[frame.url]
            if task.forecast.get("bounds") != frame.bounds:
                raise ValueError("Forecast/observation bounds mismatch")
            if clock() - started >= time_budget:
                attempted -= 1
                break
            result = verify(task.forecast, cubes[key], images[frame.url], frame.observedAt)
            if result is None or verification_identity(result) != task.identity():
                raise ValueError("Verifier returned a different/unmatched pair")
            results.append(result)
        except Exception:
            errors += 1
            logging.exception("nowcast.verification.pair-failed")
    report = {
        "event": "nowcast.verification.batch",
        "scope": "retained-valid-time-pairs",
        "eligiblePairs": eligible,
        "alreadyVerified": already_verified,
        "planned": len(tasks),
        "attempted": attempted,
        "completed": len(results),
        "errors": errors,
        "deferred": len(tasks) - attempted,
        "rejectedForecasts": len(rejections),
        "budgetExhausted": len(tasks) > attempted,
        "cubeDownloads": len(cubes),
        "observationDownloads": len(images),
        "durationMs": round((clock() - started) * 1000),
        "coverageFraction": (already_verified + len(results)) / eligible if eligible else None,
        "complete": not errors and attempted == len(tasks) and not rejections,
    }
    logging.info(json.dumps(report))
    return results, report
