from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from wetmap_worker import cli, dmi
from wetmap_worker.model import Frame, manifest
from wetmap_worker.storage import write_json_atomic

NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)


class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW


def catalogue(observed_at):
    return {
        "features": [
            {
                "id": "dk.com.202611171200.500_max.h5",
                "properties": {"datetime": observed_at},
                "asset": {"data": {"href": "https://dmi.test/frame.h5"}},
            }
        ]
    }


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(dmi, "datetime", FrozenDatetime)
    return dmi.DmiClient("https://dmi.test")


@pytest.mark.parametrize("timestamp", ["2026-11-17T12:02:00.001Z", "2026-11-18T12:00:00Z"])
def test_future_source_is_rejected_before_processing(client, monkeypatch, timestamp):
    monkeypatch.setattr(client, "_get", lambda *_args: Mock(json=lambda: catalogue(timestamp)))
    with pytest.raises(ValueError, match="Invalid DMI observation catalogue"):
        client.newest_composites()


@pytest.mark.parametrize("timestamp", ["2026-11-17T12:00:00Z", "2026-11-17T12:02:00Z"])
def test_existing_two_minute_clock_tolerance_is_preserved(client, monkeypatch, timestamp):
    monkeypatch.setattr(client, "_get", lambda *_args: Mock(json=lambda: catalogue(timestamp)))
    assert client.newest_composites()[0].observed_at == timestamp


def test_future_catalogue_leaves_last_good_manifest_and_remote_state_untouched(
    client, tmp_path, monkeypatch
):
    old = Frame(
        "old",
        "2026-11-17T11:50:00Z",
        "2026-11-17T11:51:00Z",
        "/frames/old.webp",
        [7, 54, 13, 58],
        "DBZH",
        "dBZ",
        "old-sha",
    )
    path = tmp_path / "frames.json"
    write_json_atomic(path, manifest([old]))
    original = path.read_bytes()
    monkeypatch.setattr(
        client, "_get", lambda *_args: Mock(json=lambda: catalogue("2026-11-18T12:00:00Z"))
    )
    download = Mock(side_effect=AssertionError("must reject before download"))
    monkeypatch.setattr(client, "download", download)
    monkeypatch.setattr(cli, "DmiClient", lambda *_args: client)
    upload = Mock()
    monkeypatch.setattr(cli, "upload_r2", upload)
    with pytest.raises(ValueError, match="Invalid DMI observation catalogue"):
        cli.run(tmp_path, limit=13, upload=True)
    assert path.read_bytes() == original
    download.assert_not_called()
    upload.assert_not_called()
