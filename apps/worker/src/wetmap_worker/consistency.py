from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image


# Stable reference locations cover the populated Danish regions and major islands.
# They are coordinates, not forecast truth; the check compares two delivery paths
# for the exact same radar field at each location.
REFERENCE_LOCATIONS = (
    ("Skagen", 57.7209, 10.5839),
    ("Frederikshavn", 57.4407, 10.5366),
    ("Aalborg", 57.0488, 9.9217),
    ("Thisted", 56.9550, 8.6949),
    ("Viborg", 56.4520, 9.3963),
    ("Aarhus", 56.1629, 10.2039),
    ("Herning", 56.1386, 8.9738),
    ("Horsens", 55.8607, 9.8503),
    ("Vejle", 55.7113, 9.5364),
    ("Esbjerg", 55.4765, 8.4594),
    ("Kolding", 55.4904, 9.4722),
    ("Sonderborg", 54.9093, 9.7922),
    ("Odense", 55.4038, 10.4024),
    ("Kalundborg", 55.6810, 11.0884),
    ("Roskilde", 55.6419, 12.0878),
    ("Hilleroed", 55.9279, 12.3008),
    ("Copenhagen", 55.6761, 12.5683),
    ("Naestved", 55.2299, 11.7609),
    ("Nykoebing Falster", 54.7654, 11.8755),
    ("Roenne", 55.1009, 14.7066),
)


def _mercator_y(latitude: float) -> float:
    limited = max(-85.051129, min(85.051129, latitude))
    radians = np.deg2rad(limited)
    return float(np.log(np.tan(np.pi / 4 + radians / 2)))


def _grid_position(
    latitude: float,
    longitude: float,
    bounds: list[float],
    width: int,
    height: int,
) -> tuple[int, int]:
    west, south, east, north = bounds
    x = min(width - 1, max(0, int(((longitude - west) / (east - west)) * width)))
    north_y = _mercator_y(north)
    south_y = _mercator_y(south)
    y = min(
        height - 1,
        max(
            0,
            int((north_y - _mercator_y(latitude)) / (north_y - south_y) * height),
        ),
    )
    return x, y


def _encoded_reflectivity(alpha: np.ndarray, width: int, height: int) -> np.ndarray:
    reduced = cv2.resize(alpha, (width, height), interpolation=cv2.INTER_AREA)
    dbz = np.rint((reduced.astype(np.float32) - 45) * (60 / 175) - 10)
    detected = reduced >= 44
    return np.where(
        detected,
        np.clip(dbz + 32, 1, 95),
        np.where(reduced > 0, 14, 0),
    ).astype(np.uint8)


def _neighborhood_peak(grid: np.ndarray, x: int, y: int, radius: int) -> int:
    return int(
        np.max(
            grid[
                max(0, y - radius) : min(grid.shape[0], y + radius + 1),
                max(0, x - radius) : min(grid.shape[1], x + radius + 1),
            ]
        )
    )


def geographic_consistency_report(
    map_frame_paths: list[Path],
    point_cube: np.ndarray,
    frame_metadata: list[dict[str, Any]],
    bounds: list[float],
    rain_threshold_dbz: int,
    radius_pixels: int,
    based_on_observed_at: str,
) -> dict[str, Any]:
    if point_cube.ndim != 3:
        raise ValueError("Point cube must have height, width and frame dimensions")
    if len(map_frame_paths) != point_cube.shape[-1] or len(frame_metadata) != point_cube.shape[-1]:
        raise ValueError("Map frames, point cube and frame metadata must align")

    west, south, east, north = bounds
    locations = [
        (name, latitude, longitude)
        for name, latitude, longitude in REFERENCE_LOCATIONS
        if west <= longitude <= east and south <= latitude <= north
    ]
    if not locations:
        raise ValueError("Radar bounds do not contain any geographic consistency locations")

    height, width, _frame_count = point_cube.shape
    threshold_encoded = rain_threshold_dbz + 32
    value_mismatches = 0
    rain_classification_mismatches = 0
    maximum_encoded_difference = 0
    mismatch_examples: list[dict[str, Any]] = []

    for frame_index, map_path in enumerate(map_frame_paths):
        alpha = np.asarray(Image.open(map_path).convert("RGBA"))[..., 3]
        map_grid = _encoded_reflectivity(alpha, width, height)
        point_grid = point_cube[..., frame_index]
        for name, latitude, longitude in locations:
            x, y = _grid_position(latitude, longitude, bounds, width, height)
            map_peak = _neighborhood_peak(map_grid, x, y, radius_pixels)
            point_peak = _neighborhood_peak(point_grid, x, y, radius_pixels)
            difference = abs(map_peak - point_peak)
            maximum_encoded_difference = max(maximum_encoded_difference, difference)
            map_wet = map_peak >= threshold_encoded
            point_wet = point_peak >= threshold_encoded
            if difference:
                value_mismatches += 1
            if map_wet != point_wet:
                rain_classification_mismatches += 1
            if (difference or map_wet != point_wet) and len(mismatch_examples) < 10:
                mismatch_examples.append(
                    {
                        "location": name,
                        "latitude": latitude,
                        "longitude": longitude,
                        "leadMinutes": int(frame_metadata[frame_index]["leadMinutes"]),
                        "mapReflectivityDbz": None if map_peak == 0 else map_peak - 32,
                        "pointReflectivityDbz": None if point_peak == 0 else point_peak - 32,
                    }
                )

    comparison_count = len(locations) * len(map_frame_paths)
    status = (
        "verified"
        if value_mismatches == 0 and rain_classification_mismatches == 0
        else "degraded"
    )
    return {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "basedOnObservedAt": based_on_observed_at,
        "status": status,
        "rainThresholdDbz": rain_threshold_dbz,
        "spatialRadiusPixels": radius_pixels,
        "locationCount": len(locations),
        "frameCount": len(map_frame_paths),
        "comparisonCount": comparison_count,
        "valueMismatchCount": value_mismatches,
        "rainClassificationMismatchCount": rain_classification_mismatches,
        "maximumReflectivityDifferenceDbz": maximum_encoded_difference,
        "locations": [name for name, _latitude, _longitude in locations],
        "mismatchExamples": mismatch_examples,
    }
