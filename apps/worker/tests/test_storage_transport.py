from pathlib import Path
from unittest.mock import Mock

from wetmap_worker import storage


def test_r2_client_uses_bounded_network_attempts(monkeypatch) -> None:
    client = Mock()
    monkeypatch.setenv("R2_ACCOUNT_ID", "account")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "test")
    monkeypatch.setattr("boto3.client", client)
    storage._r2_client()
    config = client.call_args.kwargs["config"]
    assert config.connect_timeout == 5
    assert config.read_timeout == 20
    assert config.retries["total_max_attempts"] == 3


def test_metadata_transfer_avoids_small_multipart_and_unbounded_threads() -> None:
    config = storage._transfer_config()
    assert config.multipart_threshold == 128 * 1024 * 1024
    assert config.max_concurrency == 2
    assert config.preferred_transfer_client == "classic"


def test_upload_keeps_verification_bytes_and_keys_unchanged(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("R2_BUCKET", "test-bucket")
    history = b'{"results":[{"hits":23,"misses":4,"falseAlarms":2}],"sentinel":"unchanged"}'
    for name in [
        "nowcast.json",
        "risk.json",
        "consistency.json",
        "verification.json",
        "verification-state.json",
        "gauge-verification-history.json",
    ]:
        (tmp_path / name).write_bytes(b"{}")
    (tmp_path / "verification-history.json").write_bytes(history)
    (tmp_path / "point-risk.json").write_text('{"dataKey":"nowcast/point-risk-1.bin"}')
    (tmp_path / "point-risk.bin").write_bytes(b"grid")
    uploads = {}

    def upload(filename, bucket, key, **kwargs):
        assert kwargs["Config"].max_concurrency == 2
        uploads[key] = Path(filename).read_bytes()

    monkeypatch.setattr(storage, "_r2_client", lambda: Mock(upload_file=upload))
    storage.upload_nowcast_r2(tmp_path, [])
    assert uploads["nowcast/verification-history.json"] == history
    assert uploads["nowcast/point-risk-1.bin"] == b"grid"


def test_failed_ledger_download_does_not_replace_a_good_local_copy(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("R2_BUCKET", "test-bucket")
    target = tmp_path / "verification-history.json"
    target.write_bytes(b"original")

    def download(bucket, key, filename, **kwargs):
        Path(filename).write_bytes(b"partial")
        if key.endswith("verification-history.json"):
            raise TimeoutError("network timeout")

    monkeypatch.setattr(storage, "_r2_client", lambda: Mock(download_file=download))
    import pytest

    with pytest.raises(TimeoutError):
        storage.download_verification_r2(tmp_path)
    assert target.read_bytes() == b"original"
