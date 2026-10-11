import json
from pathlib import Path

import numpy as np
from PIL import Image

from wetmap_worker.nowcast import POINT_GRID_HEIGHT, POINT_GRID_WIDTH
from wetmap_worker.verification import append_verification_history, verify_previous_nowcast


def test_scores_previous_nowcast_against_new_observation(tmp_path: Path) -> None:
    observed = np.zeros((64, 96, 4), dtype=np.uint8)
    observed[..., 3] = 1
    observed[20:40, 30:55, 3] = 198  # Approximately 20 dBZ.
    observed_path = tmp_path / "observed.webp"
    Image.fromarray(observed).save(observed_path, "WEBP", lossless=True)

    frame_count = 2
    cube = np.full((POINT_GRID_HEIGHT, POINT_GRID_WIDTH, frame_count), 14, dtype=np.uint8)
    actual_echo = (
        np.asarray(
            Image.open(observed_path).convert("RGBA").resize((POINT_GRID_WIDTH, POINT_GRID_HEIGHT))
        )[..., 3]
        >= 190
    )
    cube[..., 1][actual_echo] = 52
    cube_path = tmp_path / "point-risk.bin"
    cube_path.write_bytes(cube.tobytes())
    metadata_path = tmp_path / "point-risk.json"
    metadata_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "basedOnObservedAt": "2026-10-11T11:55:00Z",
                "bounds": [7, 54, 13, 58],
                "width": POINT_GRID_WIDTH,
                "height": POINT_GRID_HEIGHT,
                "frameCount": frame_count,
                "encoding": "pixel-major-uint8-dbz-plus-32",
                "frames": [
                    {
                        "leadMinutes": 0,
                        "predictedAt": "2026-10-11T11:55:00Z",
                        "confidence": 1,
                    },
                    {
                        "leadMinutes": 5,
                        "predictedAt": "2026-10-11T12:00:00Z",
                        "confidence": 0.94,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    result = verify_previous_nowcast(
        metadata_path,
        cube_path,
        observed_path,
        "2026-10-11T12:00:00Z",
    )

    assert result is not None
    assert result["leadMinutes"] == 5
    assert result["hits"] > 0
    assert result["criticalSuccessIndex"] > 0.9
    assert result["persistenceCriticalSuccessIndex"] is not None
    assert result["criticalSuccessIndexSkill"] is not None
    history = append_verification_history(tmp_path / "history.json", result)
    assert history["sampleCount"] == 1
    assert history["meanCriticalSuccessIndex"] > 0.9
    assert history["meanCriticalSuccessIndexSkill"] is not None
