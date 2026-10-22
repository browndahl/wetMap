from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

BACKTEST_LEAD_MINUTES = tuple(range(5, 61, 5))
REQUIRED_SPLITS = ("train", "validation", "test")


def _utc_timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{field} must be an explicit UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise ValueError(f"{field} must be a valid UTC timestamp") from error
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError(f"{field} must be UTC")
    return parsed


@dataclass(frozen=True)
class DatasetSplit:
    name: str
    start_at: datetime
    end_at: datetime
    may_tune: bool

    def contains(self, timestamp: datetime) -> bool:
        if timestamp.utcoffset() is None:
            raise ValueError("backtest timestamps must be timezone-aware UTC")
        return self.start_at <= timestamp < self.end_at


@dataclass(frozen=True)
class BacktestPlan:
    schema_version: int
    dataset_id: str
    source: dict[str, Any]
    lead_minutes: tuple[int, ...]
    splits: tuple[DatasetSplit, ...]
    sha256: str

    def split_for(self, timestamp: datetime) -> DatasetSplit | None:
        return next((split for split in self.splits if split.contains(timestamp)), None)


def load_backtest_plan(path: Path) -> BacktestPlan:
    raw = path.read_bytes()
    payload = json.loads(raw)
    if payload.get("schemaVersion") != 1:
        raise ValueError("unsupported backtest split schemaVersion")
    dataset_id = payload.get("datasetId")
    if not isinstance(dataset_id, str) or not dataset_id.strip():
        raise ValueError("datasetId must be a non-empty string")
    source = payload.get("source")
    if not isinstance(source, dict):
        raise ValueError("source must be an object")
    lead_minutes = tuple(payload.get("leadMinutes", []))
    if lead_minutes != BACKTEST_LEAD_MINUTES:
        raise ValueError("leadMinutes must contain every 5-minute lead from 5 through 60")

    rows = payload.get("splits")
    if not isinstance(rows, list) or [row.get("name") for row in rows] != list(REQUIRED_SPLITS):
        raise ValueError("splits must be ordered train, validation, test")
    splits: list[DatasetSplit] = []
    for row in rows:
        name = str(row["name"])
        start_at = _utc_timestamp(row.get("startAt"), f"{name}.startAt")
        end_at = _utc_timestamp(row.get("endAt"), f"{name}.endAt")
        may_tune = row.get("mayTune")
        if not isinstance(may_tune, bool):
            raise ValueError(f"{name}.mayTune must be boolean")
        if start_at >= end_at:
            raise ValueError(f"{name} split must have a positive duration")
        splits.append(DatasetSplit(name, start_at, end_at, may_tune))

    for previous, current in zip(splits, splits[1:]):
        if current.start_at < previous.end_at:
            raise ValueError(f"split overlap between {previous.name} and {current.name}")
    if splits[-1].may_tune:
        raise ValueError("test split must never allow tuning")

    return BacktestPlan(
        schema_version=1,
        dataset_id=dataset_id,
        source=source,
        lead_minutes=lead_minutes,
        splits=tuple(splits),
        sha256=hashlib.sha256(raw).hexdigest(),
    )
