"""Closed, argument-free timings for the derived radar pipeline."""

from __future__ import annotations

import json
import logging
from time import perf_counter


STAGES = frozenset(
    {
        "observation-publish",
        "nowcast-source-load",
        "verification-state-load",
        "verification-history-load",
        "verification-score",
        "verification-history-append",
        "gauge-fetch",
        "gauge-score",
        "nowcast-generate",
        "nowcast-publish",
    }
)


def run_stage(stage: str, operation, /, *args, **kwargs):
    if not isinstance(stage, str) or stage not in STAGES:
        raise ValueError("unsupported-worker-stage")
    started = perf_counter()
    logging.info(json.dumps({"event": "worker.stage.started", "stage": stage}))
    outcome = "failed"
    try:
        result = operation(*args, **kwargs)
        outcome = "completed"
        return result
    finally:
        # No args, return values, identifiers or raw exception text/traceback.
        # Preserve the exact result/exception and existing pipeline failure policy.
        logging.info(
            json.dumps(
                {
                    "event": f"worker.stage.{outcome}",
                    "stage": stage,
                    "durationMs": max(0, round((perf_counter() - started) * 1000)),
                }
            )
        )
