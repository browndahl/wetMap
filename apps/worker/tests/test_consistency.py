from pathlib import Path

import numpy as np
from PIL import Image

from wetmap_worker.consistency import geographic_consistency_report


def test_marks_map_point_rain_disagreement_as_degraded(tmp_path: Path) -> None:
    map_path = tmp_path / "map.webp"
    Image.fromarray(np.zeros((20, 20, 4), dtype=np.uint8)).save(
        map_path,
        "WEBP",
        lossless=True,
    )
    point_cube = np.full((20, 20, 1), 52, dtype=np.uint8)

    report = geographic_consistency_report(
        [map_path],
        point_cube,
        [{"leadMinutes": 0}],
        [7, 54, 15.5, 58],
        rain_threshold_dbz=15,
        radius_pixels=1,
        based_on_observed_at="2026-10-13T12:00:00Z",
    )

    assert report["status"] == "degraded"
    assert report["locationCount"] == 20
    assert report["comparisonCount"] == 20
    assert report["valueMismatchCount"] == 20
    assert report["rainClassificationMismatchCount"] == 20
    assert len(report["mismatchExamples"]) == 10
