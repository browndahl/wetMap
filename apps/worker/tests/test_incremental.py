from pathlib import Path
from types import SimpleNamespace

import pytest

from wetmap_worker import cli
from wetmap_worker.model import Frame, manifest
from wetmap_worker.storage import write_json_atomic


def test_promotes_calibration_only_after_matching_nowcast_quality_is_verified() -> None:
    gauge_history = {
        "calibration": {
            "safeToPromote": True,
            "recommendedThresholdDbz": 15,
            "recommendedSpatialRadiusPixels": 5,
        }
    }
    verification_history = {
        "observatoryByThresholdDbz": [{"thresholdDbz": 15, "overallStatus": "awaiting-rain"}]
    }

    assert cli.operational_radar_calibration(gauge_history, verification_history) == (
        20,
        1,
    )
    assert gauge_history["calibration"]["forecastQualityStatus"] == "awaiting-rain"

    verification_history["observatoryByThresholdDbz"][0]["overallStatus"] = "verified"
    assert cli.operational_radar_calibration(gauge_history, verification_history) == (
        15,
        5,
    )
    assert gauge_history["calibration"]["appliedThresholdDbz"] == 15


@pytest.mark.parametrize("failure_stage", ["none", "derived", "publication"])
def test_upload_run_only_processes_new_frames_and_publishes_before_derivation(
    tmp_path: Path, monkeypatch, failure_stage: str
) -> None:
    old_frame = Frame(
        "old",
        "2026-10-10T20:00:00Z",
        "2026-10-10T20:01:00Z",
        "/frames/old.webp",
        [7, 54, 13, 58],
        "DBZH",
        "dBZ",
        "old-sha",
    )
    write_json_atomic(tmp_path / "frames.json", manifest([old_frame]))

    class FakeClient:
        def __init__(self, _base_url: str) -> None:
            pass

        def newest_composites(self, _limit: int):
            return [
                SimpleNamespace(id="new", observed_at="2026-10-10T20:05:00Z"),
                SimpleNamespace(id="old", observed_at="2026-10-10T20:00:00Z"),
            ]

        def download(self, item, destination: Path) -> None:
            destination.write_bytes(item.id.encode())

    def fake_process(_source: Path, target: Path):
        target.write_bytes(b"webp")
        return SimpleNamespace(bounds=[7, 54, 13, 58], product="DBZH", unit="dBZ", sha256="new-sha")

    uploaded: list[Path] = []
    derived_called = False

    def fake_upload(_output: Path, paths: list[Path]):
        if failure_stage == "publication":
            raise OSError("Cannot publish observations")
        uploaded.extend(paths)

    def fake_download_frames(output: Path, names: list[str]):
        nonlocal derived_called
        derived_called = True
        assert [path.name for path in uploaded] == ["new.webp"]
        if failure_stage == "derived":
            raise TimeoutError("Derived computation cannot delay published radar")
        paths = []
        for name in names:
            path = output / name
            path.write_bytes(b"webp")
            paths.append(path)
        return paths

    monkeypatch.setattr(cli, "DmiClient", FakeClient)
    monkeypatch.setattr(cli, "process_hdf5", fake_process)
    monkeypatch.setattr(cli, "download_frames_r2", fake_download_frames)
    monkeypatch.setattr(cli, "download_verification_r2", lambda _directory: False)
    monkeypatch.setattr(cli, "fetch_recent_gauge_observations", lambda *_args: [])
    monkeypatch.setattr(
        cli,
        "compare_radar_to_gauges",
        lambda *_args: {
            "verifiedAt": "2026-10-10T20:06:00Z",
            "radarObservedAt": "2026-10-10T20:05:00Z",
            "hits": 0,
            "misses": 0,
            "falseAlarms": 0,
            "correctNegatives": 0,
        },
    )
    monkeypatch.setattr(cli, "generate_nowcast", lambda *_args, **_kwargs: ({}, {}, []))
    monkeypatch.setattr(cli, "upload_r2", fake_upload)

    if failure_stage == "publication":
        with pytest.raises(OSError, match="Cannot publish observations"):
            cli.run(tmp_path, limit=2, upload=True)
        assert uploaded == []
        assert not derived_called
        return
    cli.run(tmp_path, limit=2, upload=True)

    assert derived_called
    assert [path.name for path in uploaded] == ["new.webp"]
    assert not (tmp_path / "old.webp").exists()
