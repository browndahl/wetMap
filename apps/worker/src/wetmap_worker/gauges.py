from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import requests
from PIL import Image

from .nowcast import POINT_GRID_HEIGHT, POINT_GRID_WIDTH, _parse_time, _reflectivity_grid

DMI_METOBS_URL = (
    "https://opendataapi.dmi.dk/v2/metObs/collections/observation/items"
)
GAUGE_PARAMETER = "precip_past10min"
GAUGE_WET_THRESHOLD_MM = 0.1
RADAR_WET_THRESHOLD_DBZ = 20
RADAR_THRESHOLDS_DBZ = (5, 10, 15, 20)
SPATIAL_RADII_PIXELS = (1, 3, 5)
PRIMARY_SPATIAL_RADIUS_PIXELS = 3
GAUGE_ACCUMULATION_MINUTES = 10
GAUGE_COMPARISON_VERSION = "10m-window-3px-v1"
LEGACY_GAUGE_COMPARISON_VERSION = "legacy-instant-1px"
MAXIMUM_TIME_OFFSET_MINUTES = 6


def fetch_recent_gauge_observations(
    base_url: str = DMI_METOBS_URL,
) -> list[dict[str, Any]]:
    """Fetch DMI's raw 10-minute gauge observations for the Danish radar bounds."""
    response = requests.get(
        base_url,
        params={
            "period": "latest-hour",
            "parameterId": GAUGE_PARAMETER,
            "bbox": "7,54,16,58",
            "limit": 1000,
        },
        timeout=(5, 20),
        headers={"User-Agent": "wetmap-ground-verification/1.0"},
    )
    response.raise_for_status()
    payload = response.json()
    observations: list[dict[str, Any]] = []
    for feature in payload.get("features", []):
        properties = feature.get("properties", {})
        coordinates = feature.get("geometry", {}).get("coordinates", [])
        if (
            len(coordinates) < 2
            or properties.get("parameterId") != GAUGE_PARAMETER
            or not properties.get("stationId")
            or not properties.get("observed")
        ):
            continue
        try:
            observations.append(
                {
                    "stationId": str(properties["stationId"]),
                    "observedAt": str(properties["observed"]),
                    "createdAt": str(properties.get("created", properties["observed"])),
                    "precipitationMm": float(properties["value"]),
                    "longitude": float(coordinates[0]),
                    "latitude": float(coordinates[1]),
                }
            )
        except (TypeError, ValueError):
            continue
    return observations


def _mercator_y(latitude: float) -> float:
    limited = max(-85.051129, min(85.051129, latitude))
    radians = math.radians(limited)
    return math.log(math.tan(math.pi / 4 + radians / 2))


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _empty_counts() -> dict[str, int]:
    return {"hits": 0, "misses": 0, "falseAlarms": 0, "correctNegatives": 0}


def _add_outcome(counts: dict[str, int], radar_wet: bool, gauge_wet: bool) -> None:
    if radar_wet and gauge_wet:
        counts["hits"] += 1
    elif gauge_wet:
        counts["misses"] += 1
    elif radar_wet:
        counts["falseAlarms"] += 1
    else:
        counts["correctNegatives"] += 1


def _score_counts(counts: dict[str, int]) -> dict[str, Any]:
    hits = counts["hits"]
    misses = counts["misses"]
    false_alarms = counts["falseAlarms"]
    return {
        **counts,
        "precision": _ratio(hits, hits + false_alarms),
        "recall": _ratio(hits, hits + misses),
        "criticalSuccessIndex": _ratio(hits, hits + misses + false_alarms),
    }


def compare_radar_to_gauges(
    observations: list[dict[str, Any]],
    observed_frame_path: Path,
    observed_at: str,
    bounds: list[float],
    radar_frames: list[tuple[Path, str]] | None = None,
) -> dict[str, Any]:
    """Compare 10-minute gauges with time-windowed nearby radar echoes."""
    radar_time = _parse_time(observed_at)
    nearest_by_station: dict[str, tuple[float, datetime, dict[str, Any]]] = {}
    for observation in observations:
        offset_minutes = abs(
            (_parse_time(observation["observedAt"]) - radar_time).total_seconds()
        ) / 60
        if offset_minutes > MAXIMUM_TIME_OFFSET_MINUTES:
            continue
        station = observation["stationId"]
        created_at = _parse_time(observation.get("createdAt", observation["observedAt"]))
        current = nearest_by_station.get(station)
        if current is None or (offset_minutes, -created_at.timestamp()) < (
            current[0],
            -current[1].timestamp(),
        ):
            nearest_by_station[station] = (offset_minutes, created_at, observation)

    input_frames = radar_frames or [(observed_frame_path, observed_at)]
    grids = [
        (
            _parse_time(frame_time),
            _reflectivity_grid(
                np.asarray(Image.open(frame_path).convert("RGBA"))[..., 3]
            ),
        )
        for frame_path, frame_time in input_frames
    ]
    west, south, east, north = bounds
    north_y = _mercator_y(north)
    south_y = _mercator_y(south)
    threshold_counts = {
        threshold: _empty_counts() for threshold in RADAR_THRESHOLDS_DBZ
    }
    spatial_counts = {
        radius: _empty_counts() for radius in SPATIAL_RADII_PIXELS
    }
    compared = 0
    trace_gauges = 0
    offsets: list[float] = []
    for offset_minutes, _created_at, observation in nearest_by_station.values():
        longitude = observation["longitude"]
        latitude = observation["latitude"]
        if not (west <= longitude <= east and south <= latitude <= north):
            continue
        x = min(
            POINT_GRID_WIDTH - 1,
            max(0, int(((longitude - west) / (east - west)) * POINT_GRID_WIDTH)),
        )
        y = min(
            POINT_GRID_HEIGHT - 1,
            max(
                0,
                int(
                    ((north_y - _mercator_y(latitude)) / (north_y - south_y))
                    * POINT_GRID_HEIGHT
                ),
            ),
        )
        gauge_time = _parse_time(observation["observedAt"])
        window_start = gauge_time - timedelta(minutes=GAUGE_ACCUMULATION_MINUTES)
        aligned_grids = [
            grid for frame_time, grid in grids if window_start <= frame_time <= gauge_time
        ]
        if not aligned_grids:
            continue
        precipitation = observation["precipitationMm"]
        gauge_wet = precipitation >= GAUGE_WET_THRESHOLD_MM
        dbz_by_radius: dict[int, int] = {}
        for radius in SPATIAL_RADII_PIXELS:
            covered_values: list[np.ndarray] = []
            for grid in aligned_grids:
                neighborhood = grid[
                    max(0, y - radius) : min(POINT_GRID_HEIGHT, y + radius + 1),
                    max(0, x - radius) : min(POINT_GRID_WIDTH, x + radius + 1),
                ]
                covered = neighborhood[neighborhood > 0]
                if covered.size:
                    covered_values.append(covered)
            if covered_values:
                dbz_by_radius[radius] = int(
                    max(int(np.max(values)) for values in covered_values)
                ) - 32
        if PRIMARY_SPATIAL_RADIUS_PIXELS not in dbz_by_radius:
            continue
        primary_dbz = dbz_by_radius[PRIMARY_SPATIAL_RADIUS_PIXELS]
        for threshold, counts in threshold_counts.items():
            _add_outcome(counts, primary_dbz >= threshold, gauge_wet)
        for radius, counts in spatial_counts.items():
            if radius in dbz_by_radius:
                _add_outcome(
                    counts,
                    dbz_by_radius[radius] >= RADAR_WET_THRESHOLD_DBZ,
                    gauge_wet,
                )
        trace_gauges += int(-0.1 <= precipitation < 0)
        compared += 1
        offsets.append(offset_minutes)

    primary = _score_counts(threshold_counts[RADAR_WET_THRESHOLD_DBZ])

    return {
        "verifiedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "radarObservedAt": observed_at,
        "source": "dmi-metobs-raw",
        "comparisonVersion": GAUGE_COMPARISON_VERSION,
        "parameterId": GAUGE_PARAMETER,
        "radarThresholdDbz": RADAR_WET_THRESHOLD_DBZ,
        "gaugeThresholdMm10m": GAUGE_WET_THRESHOLD_MM,
        "temporalWindowMinutes": GAUGE_ACCUMULATION_MINUTES,
        "spatialRadiusPixels": PRIMARY_SPATIAL_RADIUS_PIXELS,
        "stationCount": compared,
        "traceStationCount": trace_gauges,
        "meanTimeOffsetMinutes": (
            round(sum(offsets) / len(offsets), 2) if offsets else None
        ),
        **primary,
        "byRadarThresholdDbz": [
            {"thresholdDbz": threshold, **_score_counts(counts)}
            for threshold, counts in threshold_counts.items()
        ],
        "bySpatialRadiusPixels": [
            {"radiusPixels": radius, **_score_counts(counts)}
            for radius, counts in spatial_counts.items()
        ],
    }


def _aggregate_profiles(
    history: list[dict[str, Any]], key: str, identity: str
) -> list[dict[str, Any]]:
    grouped: dict[int, dict[str, int]] = {}
    for entry in history:
        for profile in entry.get(key, []):
            value = int(profile[identity])
            counts = grouped.setdefault(value, _empty_counts())
            for count_key in counts:
                counts[count_key] += int(profile.get(count_key, 0))
    return [
        {identity: value, **_score_counts(counts)}
        for value, counts in sorted(grouped.items())
    ]


def append_gauge_history(
    history_path: Path,
    result: dict[str, Any],
    maximum_entries: int = 432,
) -> dict[str, Any]:
    history: list[dict[str, Any]] = []
    if history_path.exists():
        try:
            history = json.loads(history_path.read_text(encoding="utf-8")).get("results", [])
        except (json.JSONDecodeError, AttributeError):
            history = []
    history = [
        entry
        for entry in history
        if entry.get("radarObservedAt") != result["radarObservedAt"]
    ]
    history.append(result)
    history.sort(key=lambda entry: entry["radarObservedAt"])
    history = history[-maximum_entries:]
    def version_for(entry: dict[str, Any]) -> str:
        return str(
            entry.get("comparisonVersion", LEGACY_GAUGE_COMPARISON_VERSION)
        )
    active_version = version_for(history[-1])
    active_history = [entry for entry in history if version_for(entry) == active_version]

    def summarize(entries: list[dict[str, Any]]) -> dict[str, Any]:
        hits = sum(entry["hits"] for entry in entries)
        misses = sum(entry["misses"] for entry in entries)
        false_alarms = sum(entry["falseAlarms"] for entry in entries)
        correct_negatives = sum(entry["correctNegatives"] for entry in entries)
        return {
            "observationCount": len(entries),
            "stationComparisonCount": hits
            + misses
            + false_alarms
            + correct_negatives,
            "hits": hits,
            "misses": misses,
            "falseAlarms": false_alarms,
            "correctNegatives": correct_negatives,
            "precision": _ratio(hits, hits + false_alarms),
            "recall": _ratio(hits, hits + misses),
            "criticalSuccessIndex": _ratio(hits, hits + misses + false_alarms),
        }

    active_summary = summarize(active_history)
    versions = sorted({str(version_for(entry)) for entry in history})
    return {
        "schemaVersion": 2,
        "generatedAt": result["verifiedAt"],
        "source": "dmi-metobs-raw",
        "comparisonVersion": active_version,
        "parameterId": GAUGE_PARAMETER,
        "radarThresholdDbz": RADAR_WET_THRESHOLD_DBZ,
        "gaugeThresholdMm10m": GAUGE_WET_THRESHOLD_MM,
        "temporalWindowMinutes": GAUGE_ACCUMULATION_MINUTES,
        "spatialRadiusPixels": PRIMARY_SPATIAL_RADIUS_PIXELS,
        "totalObservationCount": len(history),
        **active_summary,
        "byRadarThresholdDbz": _aggregate_profiles(
            active_history, "byRadarThresholdDbz", "thresholdDbz"
        ),
        "bySpatialRadiusPixels": _aggregate_profiles(
            active_history, "bySpatialRadiusPixels", "radiusPixels"
        ),
        "byComparisonVersion": [
            {
                "comparisonVersion": version,
                **summarize(
                    [entry for entry in history if version_for(entry) == version]
                ),
            }
            for version in versions
        ],
        "note": "DMI MetObs is raw station data; stations validate radar only at their locations.",
        "results": history,
    }


def public_gauge_report(history: dict[str, Any], recent_results: int = 24) -> dict[str, Any]:
    report = dict(history)
    active_version = history.get("comparisonVersion", GAUGE_COMPARISON_VERSION)
    active_results = [
        entry
        for entry in history.get("results", [])
        if entry.get("comparisonVersion", LEGACY_GAUGE_COMPARISON_VERSION)
        == active_version
    ]
    report["results"] = active_results[-recent_results:]
    report["returnedResultCount"] = len(report["results"])
    return report
