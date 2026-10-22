from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from PIL import Image

from wetmap_worker.backtest import load_backtest_plan

TOOL_PATH = Path(__file__).parents[1] / "tools" / "backtest_nowcast.py"
SPEC = importlib.util.spec_from_file_location("backtest_nowcast", TOOL_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
backtest = MODULE.backtest


def _moving_echo_frames(directory: Path) -> None:
    start = datetime(2026, 10, 21, 16, 45, tzinfo=timezone.utc)
    for index in range(13):
        rgba = np.zeros((43, 64, 4), dtype=np.uint8)
        rgba[..., 3] = 1
        x = 8 + index
        rgba[16:24, x : x + 8, 1] = 180
        rgba[16:24, x : x + 8, 3] = 120
        observed_at = start + timedelta(minutes=index * 5)
        name = f"dk.com.{observed_at:%Y%m%d%H%M}.500_max.webp"
        Image.fromarray(rgba).save(directory / name, "WEBP", lossless=True, method=6)


def test_small_ci_replay_emits_auditable_all_lead_report(tmp_path: Path) -> None:
    _moving_echo_frames(tmp_path)
    split_path = Path(__file__).parents[1] / "backtest" / "split-v1.json"
    plan = load_backtest_plan(split_path)

    report = backtest(tmp_path, plan)

    assert report["dataset"]["id"] == "dmi-composite-2026-v1"
    assert report["dataset"]["splitConfigSha256"] == plan.sha256
    assert report["inputs"]["frameCount"] == 13
    assert report["inputs"]["evaluatedBaseTimes"] == {"test": 6}
    assert list(report["results"]["test"]) == [str(value) for value in range(5, 61, 5)]
    assert report["results"]["test"]["5"]["optical-flow"]["sampleCount"] == 5
    assert report["results"]["test"]["50"]["persistence"]["sampleCount"] == 1
    assert report["results"]["test"]["55"]["persistence"]["sampleCount"] == 0
    assert report["calibration"]["test"]["60"] == 0.25
    json.dumps(report)
