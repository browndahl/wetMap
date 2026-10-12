from pathlib import Path

import numpy as np
from PIL import Image

from wetmap_worker.gauges import (
    append_gauge_history,
    compare_radar_to_gauges,
    public_gauge_report,
)


def test_compares_radar_echo_with_time_aligned_ground_gauges(tmp_path: Path) -> None:
    radar = np.zeros((64, 96, 4), dtype=np.uint8)
    radar[..., 3] = 133  # approximately 20 dBZ across the synthetic coverage
    radar_path = tmp_path / "radar.webp"
    Image.fromarray(radar).save(radar_path, "WEBP", lossless=True)
    observations = [
        {
            "stationId": "wet",
            "observedAt": "2026-10-12T08:10:00Z",
            "precipitationMm": 0.2,
            "longitude": 10.0,
            "latitude": 56.0,
        },
        {
            "stationId": "dry",
            "observedAt": "2026-10-12T08:10:00Z",
            "precipitationMm": 0.0,
            "longitude": 11.0,
            "latitude": 56.0,
        },
        {
            "stationId": "too-old",
            "observedAt": "2026-10-12T07:50:00Z",
            "precipitationMm": 1.0,
            "longitude": 10.0,
            "latitude": 56.0,
        },
    ]

    result = compare_radar_to_gauges(
        observations,
        radar_path,
        "2026-10-12T08:10:00Z",
        [7, 54, 13, 58],
    )

    assert result["stationCount"] == 2
    assert result["hits"] == 1
    assert result["falseAlarms"] == 1
    history = append_gauge_history(tmp_path / "history.json", result)
    assert history["stationComparisonCount"] == 2
    assert history["precision"] == 0.5
    assert public_gauge_report(history, 1)["returnedResultCount"] == 1
