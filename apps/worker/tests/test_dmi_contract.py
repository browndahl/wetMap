from unittest.mock import Mock

import pytest

from wetmap_worker import cli
from wetmap_worker.dmi import DmiClient
from wetmap_worker.model import Frame, manifest
from wetmap_worker.storage import write_json_atomic


def item():
    return {
        "id": "dk.com.202611170725.500_max.h5",
        "properties": {"datetime": "2026-11-17T07:25:00Z"},
        "asset": {"data": {"href": "https://dmigw.govcloud.dk/radar/frame.h5"}},
    }


@pytest.mark.parametrize("document", [{}, {"features": []}, {"features": None}, {"features": {}}])
def test_unusable_catalogues_are_not_silently_accepted(monkeypatch, document):
    client = DmiClient("https://dmi.test")
    monkeypatch.setattr(client, "_get", lambda *_args: Mock(json=lambda: document))
    with pytest.raises(ValueError):
        client.newest_composites()


def test_empty_catalogue_cannot_replace_or_publish_last_good_manifest(tmp_path, monkeypatch):
    old = Frame(
        "old",
        "2026-11-17T07:25:00Z",
        "2026-11-17T07:26:00Z",
        "/frames/old.webp",
        [7, 54, 13, 58],
        "DBZH",
        "dBZ",
        "old-sha",
    )
    path = tmp_path / "frames.json"
    write_json_atomic(path, manifest([old]))
    original = path.read_bytes()
    client = Mock(newest_composites=Mock(return_value=[]))
    monkeypatch.setattr(cli, "DmiClient", lambda *_args: client)
    upload = Mock()
    monkeypatch.setattr(cli, "upload_r2", upload)
    with pytest.raises(ValueError):
        cli.run(tmp_path, limit=13, upload=True)
    assert path.read_bytes() == original
    upload.assert_not_called()


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "../escape.h5"),
        ("id", ""),
        ("time", "not-a-date"),
        ("time", "2026-11-17T07:25:00"),
        ("url", "file:///etc/passwd"),
        ("url", "https://user:password@dmi.test/frame.h5"),
    ],
)
def test_invalid_source_metadata_is_rejected_before_processing(monkeypatch, field, value):
    feature = item()
    if field == "id":
        feature["id"] = value
    elif field == "time":
        feature["properties"]["datetime"] = value
    else:
        feature["asset"]["data"]["href"] = value
    client = DmiClient("https://dmi.test")
    monkeypatch.setattr(client, "_get", lambda *_args: Mock(json=lambda: {"features": [feature]}))
    with pytest.raises(ValueError):
        client.newest_composites()


def test_duplicate_ids_are_rejected_instead_of_overwriting_outputs(monkeypatch):
    client = DmiClient("https://dmi.test")
    monkeypatch.setattr(
        client, "_get", lambda *_args: Mock(json=lambda: {"features": [item(), item()]})
    )
    with pytest.raises(ValueError):
        client.newest_composites()


def test_valid_catalogue_remains_compatible(monkeypatch):
    client = DmiClient("https://dmi.test")
    monkeypatch.setattr(client, "_get", lambda *_args: Mock(json=lambda: {"features": [item()]}))
    result = client.newest_composites()
    assert result[0].id == "dk.com.202611170725.500_max"
    assert result[0].observed_at == "2026-11-17T07:25:00Z"
