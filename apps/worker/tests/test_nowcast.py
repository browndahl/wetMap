import base64
import json
from pathlib import Path

import numpy as np
from PIL import Image

from wetmap_worker.model import Frame
from wetmap_worker.nowcast import (
    ALGORITHM_VERSION,
    LEAD_MINUTES,
    POINT_GRID_HEIGHT,
    POINT_GRID_WIDTH,
    RISK_HEIGHT,
    RISK_WIDTH,
    generate_nowcast,
)


def _frame(path: Path, x: int) -> None:
    rgba = np.zeros((72, 96, 4), dtype=np.uint8)
    rgba[25:45, x : x + 20, :3] = [52, 120, 229]
    rgba[25:45, x : x + 20, 3] = 133
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

    assert manifest["method"] == "adaptive-optical-flow-persistence"
    assert manifest["algorithmVersion"] == ALGORITHM_VERSION
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
    assert risk["frames"][0]["leadMinutes"] == 0
    assert risk["frames"][0]["alertEligible"] is True
    assert risk["frames"][1]["alertEligible"] is False
    point_metadata = json.loads((tmp_path / "nowcast/point-risk.json").read_text())
    point_grid = (tmp_path / "nowcast/point-risk.bin").read_bytes()
    assert point_metadata["frameCount"] == len(LEAD_MINUTES) + 1
    assert point_metadata["frames"][0]["leadMinutes"] == 0
    assert point_metadata["dataKey"].startswith("nowcast/point-risk-")
    assert len(point_grid) == POINT_GRID_WIDTH * POINT_GRID_HEIGHT * (len(LEAD_MINUTES) + 1)
    verification_metadata = json.loads(
        (tmp_path / "nowcast/verification-forecast.json").read_text()
    )
    assert verification_metadata["dataKey"].startswith(
        "nowcast/verification-cubes/cube-"
    )
    with np.load(tmp_path / "nowcast/verification-cube.npz") as archive:
        assert archive["cube"].shape[-1] == len(LEAD_MINUTES) + 1


def test_uses_verified_persistence_without_attenuating_reflectivity(tmp_path: Path) -> None:
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

    manifest, _, outputs = generate_nowcast(
        paths,
        frames,
        tmp_path / "adaptive",
        {
            5: {
                "sampleCount": 20,
                "criticalSuccessIndex": 0.3,
                "meanCriticalSuccessIndexSkill": -0.08,
            },
            10: {
                "sampleCount": 20,
                "criticalSuccessIndex": 0.6,
                "meanCriticalSuccessIndexSkill": 0.12,
            },
        },
    )

    assert manifest["frames"][0]["forecastMethod"] == "persistence"
    assert manifest["frames"][1]["forecastMethod"] == "optical-flow"
    assert manifest["frames"][0]["skillOverPersistence"] == -0.08
    assert manifest["frames"][0]["confidence"] >= 0.55
    with np.load(tmp_path / "adaptive/verification-cube.npz") as archive:
        cube = archive["cube"]
        assert np.array_equal(cube[..., 0], cube[..., 1])
        assert not np.array_equal(cube[..., 0], cube[..., 2])
    # Confidence remains metadata and no longer weakens the forecast's dBZ signal.
    first_alpha = np.asarray(Image.open(outputs[0]).convert("RGBA"))[..., 3]
    assert int(first_alpha.max()) == 133
