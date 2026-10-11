import base64
from pathlib import Path

import numpy as np
from PIL import Image

from wetmap_worker.model import Frame
from wetmap_worker.nowcast import LEAD_MINUTES, RISK_HEIGHT, RISK_WIDTH, generate_nowcast


def _frame(path: Path, x: int) -> None:
    rgba = np.zeros((72, 96, 4), dtype=np.uint8)
    rgba[25:45, x : x + 20, :3] = [52, 120, 229]
    rgba[25:45, x : x + 20, 3] = 170
    Image.fromarray(rgba).save(path, "WEBP", lossless=True)


def test_generates_hour_of_optical_flow_frames_and_compact_risk_grid(tmp_path: Path) -> None:
    paths = [tmp_path / f"source-{index}.webp" for index in range(3)]
    for path, x in zip(paths, [24, 28, 32], strict=True):
        _frame(path, x)
    frames = [
        Frame(
            id=f"frame-{index}",
            observedAt=f"2026-10-11T12:{index * 5:02d}:00Z",
            fetchedAt="2026-10-11T12:11:00Z",
            url=f"/frames/{path.name}",
            bounds=[7, 54, 13, 58],
            product="DBZH",
            unit="dBZ",
            sha256=str(index),
        )
        for index, path in enumerate(paths)
    ]

    manifest, risk, outputs = generate_nowcast(paths, frames, tmp_path / "nowcast")

    assert manifest["method"] == "dense-optical-flow-extrapolation"
    assert manifest["basedOnObservedAt"] == frames[-1].observedAt
    assert [frame["leadMinutes"] for frame in manifest["frames"]] == list(LEAD_MINUTES)
    assert len(outputs) == len(LEAD_MINUTES)
    assert all(path.exists() for path in outputs)
    assert manifest["frames"][0]["confidence"] > manifest["frames"][-1]["confidence"]
    assert risk["width"] == RISK_WIDTH
    assert risk["height"] == RISK_HEIGHT
    decoded = base64.b64decode(risk["frames"][0]["intensity"])
    assert len(decoded) == RISK_WIDTH * RISK_HEIGHT
    assert max(decoded) >= 2
