from __future__ import annotations

import json
import math
from datetime import datetime, timezone
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


def compare_radar_to_gauges(
    observations: list[dict[str, Any]],
    observed_frame_path: Path,
    observed_at: str,
    bounds: list[float],
) -> dict[str, Any]:
    """Compare radar echo with nearby-in-time DMI rain gauges at station locations."""
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

    rgba = np.asarray(Image.open(observed_frame_path).convert("RGBA"))
    grid = _reflectivity_grid(rgba[..., 3])
    west, south, east, north = bounds
    north_y = _mercator_y(north)
    south_y = _mercator_y(south)
    hits = misses = false_alarms = correct_negatives = 0
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
        neighborhood = grid[
            max(0, y - 1) : min(POINT_GRID_HEIGHT, y + 2),
            max(0, x - 1) : min(POINT_GRID_WIDTH, x + 2),
        ]
        covered = neighborhood[neighborhood > 0]
        if covered.size == 0:
            continue
        radar_dbz = int(np.max(covered)) - 32
        precipitation = observation["precipitationMm"]
        gauge_wet = precipitation >= GAUGE_WET_THRESHOLD_MM
        radar_wet = radar_dbz >= RADAR_WET_THRESHOLD_DBZ
        trace_gauges += int(-0.1 <= precipitation < GAUGE_WET_THRESHOLD_MM)
        hits += int(radar_wet and gauge_wet)
        misses += int(not radar_wet and gauge_wet)
        false_alarms += int(radar_wet and not gauge_wet)
        correct_negatives += int(not radar_wet and not gauge_wet)
        compared += 1
        offsets.append(offset_minutes)

    return {
        "verifiedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "radarObservedAt": observed_at,
        "source": "dmi-metobs-raw",
        "parameterId": GAUGE_PARAMETER,
        "radarThresholdDbz": RADAR_WET_THRESHOLD_DBZ,
        "gaugeThresholdMm10m": GAUGE_WET_THRESHOLD_MM,
        "stationCount": compared,
        "traceStationCount": trace_gauges,
        "meanTimeOffsetMinutes": (
            round(sum(offsets) / len(offsets), 2) if offsets else None
        ),
        "hits": hits,
        "misses": misses,
        "falseAlarms": false_alarms,
        "correctNegatives": correct_negatives,
        "precision": _ratio(hits, hits + false_alarms),
        "recall": _ratio(hits, hits + misses),
        "criticalSuccessIndex": _ratio(hits, hits + misses + false_alarms),
    }


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
    hits = sum(entry["hits"] for entry in history)
    misses = sum(entry["misses"] for entry in history)
    false_alarms = sum(entry["falseAlarms"] for entry in history)
    correct_negatives = sum(entry["correctNegatives"] for entry in history)
    return {
        "schemaVersion": 1,
        "generatedAt": result["verifiedAt"],
        "source": "dmi-metobs-raw",
        "parameterId": GAUGE_PARAMETER,
        "radarThresholdDbz": RADAR_WET_THRESHOLD_DBZ,
        "gaugeThresholdMm10m": GAUGE_WET_THRESHOLD_MM,
        "observationCount": len(history),
        "stationComparisonCount": hits + misses + false_alarms + correct_negatives,
        "hits": hits,
        "misses": misses,
        "falseAlarms": false_alarms,
        "correctNegatives": correct_negatives,
        "precision": _ratio(hits, hits + false_alarms),
        "recall": _ratio(hits, hits + misses),
        "criticalSuccessIndex": _ratio(hits, hits + misses + false_alarms),
        "note": "DMI MetObs is raw station data; stations validate radar only at their locations.",
        "results": history,
    }


def public_gauge_report(history: dict[str, Any], recent_results: int = 24) -> dict[str, Any]:
    report = dict(history)
    report["results"] = history.get("results", [])[-recent_results:]
    report["returnedResultCount"] = len(report["results"])
    return report
