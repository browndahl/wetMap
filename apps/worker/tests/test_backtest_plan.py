from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from wetmap_worker.backtest import BacktestPlan, load_backtest_plan


def _write_plan(path: Path, *, splits: list[dict[str, object]] | None = None) -> None:
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "datasetId": "dmi-composite-2026-v1",
                "source": {
                    "collection": "composite",
                    "product": "500_max",
                    "cadenceMinutes": 5,
                },
                "leadMinutes": list(range(5, 61, 5)),
                "splits": splits
                or [
                    {
                        "name": "train",
                        "startAt": "2026-04-25T00:00:00Z",
                        "endAt": "2026-08-01T00:00:00Z",
                        "mayTune": True,
                    },
                    {
                        "name": "validation",
                        "startAt": "2026-08-01T00:00:00Z",
                        "endAt": "2026-09-16T00:00:00Z",
                        "mayTune": True,
                    },
                    {
                        "name": "test",
                        "startAt": "2026-09-16T00:00:00Z",
                        "endAt": "2026-10-22T00:00:00Z",
                        "mayTune": False,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


def test_loads_fixed_plan_and_assigns_boundaries(tmp_path: Path) -> None:
    path = tmp_path / "split.json"
    _write_plan(path)

    plan = load_backtest_plan(path)

    assert plan.dataset_id == "dmi-composite-2026-v1"
    assert plan.lead_minutes == tuple(range(5, 61, 5))
    assert plan.split_for(datetime(2026, 7, 31, 23, 59, tzinfo=timezone.utc)).name == "train"
    assert plan.split_for(datetime(2026, 8, 1, tzinfo=timezone.utc)).name == "validation"
    assert plan.split_for(datetime(2026, 9, 16, tzinfo=timezone.utc)).name == "test"
    assert plan.split_for(datetime(2026, 10, 22, tzinfo=timezone.utc)) is None
    assert len(plan.sha256) == 64


def test_rejects_test_split_that_allows_tuning(tmp_path: Path) -> None:
    path = tmp_path / "split.json"
    _write_plan(
        path,
        splits=[
            {
                "name": "train",
                "startAt": "2026-04-25T00:00:00Z",
                "endAt": "2026-08-01T00:00:00Z",
                "mayTune": True,
            },
            {
                "name": "validation",
                "startAt": "2026-08-01T00:00:00Z",
                "endAt": "2026-09-16T00:00:00Z",
                "mayTune": True,
            },
            {
                "name": "test",
                "startAt": "2026-09-16T00:00:00Z",
                "endAt": "2026-10-22T00:00:00Z",
                "mayTune": True,
            },
        ],
    )

    with pytest.raises(ValueError, match="test split must never allow tuning"):
        load_backtest_plan(path)


@pytest.mark.parametrize(
    ("splits", "message"),
    [
        (
            [
                {
                    "name": "train",
                    "startAt": "2026-04-25T00:00:00Z",
                    "endAt": "2026-08-02T00:00:00Z",
                    "mayTune": True,
                },
                {
                    "name": "validation",
                    "startAt": "2026-08-01T00:00:00Z",
                    "endAt": "2026-09-16T00:00:00Z",
                    "mayTune": True,
                },
                {
                    "name": "test",
                    "startAt": "2026-09-16T00:00:00Z",
                    "endAt": "2026-10-22T00:00:00Z",
                    "mayTune": False,
                },
            ],
            "overlap",
        ),
        (
            [
                {
                    "name": "train",
                    "startAt": "2026-04-25T00:00:00",
                    "endAt": "2026-08-01T00:00:00Z",
                    "mayTune": True,
                },
                {
                    "name": "validation",
                    "startAt": "2026-08-01T00:00:00Z",
                    "endAt": "2026-09-16T00:00:00Z",
                    "mayTune": True,
                },
                {
                    "name": "test",
                    "startAt": "2026-09-16T00:00:00Z",
                    "endAt": "2026-10-22T00:00:00Z",
                    "mayTune": False,
                },
            ],
            "UTC",
        ),
    ],
)
def test_rejects_unsafe_split_boundaries(
    tmp_path: Path, splits: list[dict[str, object]], message: str
) -> None:
    path = tmp_path / "split.json"
    _write_plan(path, splits=splits)

    with pytest.raises(ValueError, match=message):
        load_backtest_plan(path)


def test_plan_requires_all_leads_from_five_to_sixty(tmp_path: Path) -> None:
    path = tmp_path / "split.json"
    _write_plan(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["leadMinutes"] = [15, 30, 45, 60]
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="5 through 60"):
        load_backtest_plan(path)


def test_checked_in_plan_is_valid_and_test_is_frozen() -> None:
    path = Path(__file__).parents[1] / "backtest" / "split-v1.json"

    plan: BacktestPlan = load_backtest_plan(path)

    assert [split.name for split in plan.splits] == ["train", "validation", "test"]
    assert plan.splits[-1].may_tune is False
