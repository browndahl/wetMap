import io
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError

from wetmap_worker import storage


def setup(tmp_path, monkeypatch, active="nowcast/point-risk-1.bin"):
    monkeypatch.setenv("R2_BUCKET", "test")
    for name in ("nowcast.json", "risk.json", "consistency.json"):
        (tmp_path / name).write_text("{}")
    (tmp_path / "point-risk.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "dataKey": "nowcast/point-risk-1.bin",
                "sha256": "unchanged",
            }
        )
    )
    (tmp_path / "point-risk.bin").write_bytes(b"new-grid")
    uploads = {}

    def upload(filename, _bucket, key, **_kwargs):
        uploads[key] = Path(filename).read_bytes()

    def put(**kwargs):
        assert kwargs["Key"] != active
        uploads[kwargs["Key"]] = kwargs["Body"].read()
        return {"ETag": '"' + "a" * 32 + '"'}

    client = Mock(
        upload_file=upload,
        put_object=Mock(side_effect=put),
        get_object=Mock(
            return_value={"Body": io.BytesIO(json.dumps({"dataKey": active}).encode())}
        ),
    )
    monkeypatch.setattr(storage, "_r2_client", lambda: client)
    return client, uploads


@pytest.mark.parametrize(
    "active,expected",
    [
        ("nowcast/point-risk-1.bin", "nowcast/point-risk-0.bin"),
        ("nowcast/point-risk-0.bin", "nowcast/point-risk-1.bin"),
        ("nowcast/point-risk.bin", "nowcast/point-risk-0.bin"),
    ],
)
def test_actual_active_slot_not_observation_parity_selects_inactive_slot(
    tmp_path, monkeypatch, active, expected
):
    _client, uploads = setup(tmp_path, monkeypatch, active)
    storage.upload_nowcast_r2(tmp_path, [], upload_verification=False)
    meta = json.loads(uploads["nowcast/point-risk.json"])
    assert meta["dataKey"] == expected
    assert meta["dataEtag"] == "a" * 32
    assert meta["schemaVersion"] == 2
    assert meta["sha256"] == "unchanged"
    assert uploads[expected] == b"new-grid"
    assert list(uploads).index(expected) < list(uploads).index("nowcast/point-risk.json")


def test_missing_previous_metadata_can_bootstrap_without_more_slots(tmp_path, monkeypatch):
    client, uploads = setup(tmp_path, monkeypatch, None)
    client.get_object.side_effect = ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
    storage.upload_nowcast_r2(tmp_path, [], upload_verification=False)
    assert json.loads(uploads["nowcast/point-risk.json"])["dataKey"] == "nowcast/point-risk-1.bin"


def test_failed_active_metadata_read_does_not_mutate_remote_assets(tmp_path, monkeypatch):
    client, uploads = setup(tmp_path, monkeypatch)
    client.get_object.side_effect = TimeoutError("read unavailable")
    with pytest.raises(TimeoutError):
        storage.upload_nowcast_r2(tmp_path, [], upload_verification=False)
    assert uploads == {}


@pytest.mark.parametrize("result", [{}, {"ETag": ""}])
def test_binary_without_an_etag_never_gets_a_published_pointer(tmp_path, monkeypatch, result):
    client, uploads = setup(tmp_path, monkeypatch)
    client.put_object.return_value = result
    client.put_object.side_effect = None
    with pytest.raises(ValueError):
        storage.upload_nowcast_r2(tmp_path, [], upload_verification=False)
    assert "nowcast/point-risk.json" not in uploads
    assert "nowcast/nowcast.json" not in uploads


def test_failed_binary_write_never_gets_a_published_pointer(tmp_path, monkeypatch):
    client, uploads = setup(tmp_path, monkeypatch)
    client.put_object.side_effect = TimeoutError("write unavailable")
    with pytest.raises(TimeoutError):
        storage.upload_nowcast_r2(tmp_path, [], upload_verification=False)
    assert "nowcast/point-risk.json" not in uploads
    assert "nowcast/nowcast.json" not in uploads
