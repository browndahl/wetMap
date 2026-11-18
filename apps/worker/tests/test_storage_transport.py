from pathlib import Path
from unittest.mock import Mock

import pytest

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


def test_streaming_download_attempts_do_not_stack_a_second_retry_loop() -> None:
    # Botocore's API retry budget does not govern successful-HTTP body failures.
    assert storage._transfer_config().num_download_attempts == 1


@pytest.mark.parametrize("kind", ["manifest", "frame", "ledger", "cube"])
def test_real_transfer_manager_stops_after_one_broken_stream_and_keeps_last_good(
    tmp_path: Path, monkeypatch, kind: str
) -> None:
    import io

    import boto3
    from boto3.exceptions import RetriesExceededError
    from botocore.exceptions import ReadTimeoutError
    from botocore.response import StreamingBody
    from botocore.stub import Stubber

    reads = []

    class BrokenBody(StreamingBody):
        def read(self, amt=None):
            reads.append(1)
            raise ReadTimeoutError(endpoint_url="https://r2.test.invalid")

    client = boto3.client(
        "s3",
        endpoint_url="https://r2.test.invalid",
        aws_access_key_id="synthetic",
        aws_secret_access_key="synthetic",
        region_name="auto",
    )
    stubber = Stubber(client)
    stubber.add_response("head_object", {"ContentLength": 10})
    # Queue five responses to measure the SDK's old hidden retry loop exactly;
    # new config must leave four unused. No sockets, sleeps or production reads.
    for _ in range(5):
        stubber.add_response(
            "get_object",
            {"Body": BrokenBody(io.BytesIO(b""), 10), "ContentLength": 10},
        )
    monkeypatch.setattr(storage, "_r2_client", lambda: client)
    monkeypatch.setenv("R2_BUCKET", "synthetic-bucket")
    targets = {
        "manifest": "frames.json",
        "frame": "new.webp",
        "ledger": "verification-state.json",
        "cube": "cube-00.npz",
    }
    target = tmp_path / targets[kind]
    sentinel = tmp_path / "unchanged.webp"
    sentinel.write_bytes(b"immutable-observation")
    if kind != "frame":
        target.write_bytes(b"last-good")
    with stubber, pytest.raises(RetriesExceededError):
        if kind == "manifest":
            storage.download_manifest_r2(target)
        elif kind == "frame":
            storage.download_frames_r2(tmp_path, [target.name])
        elif kind == "ledger":
            storage.download_verification_r2(tmp_path)
        else:
            storage.download_verification_cube_r2(
                tmp_path, "nowcast/verification-cubes/cube-00.npz"
            )
    assert len(reads) == 1
    assert sentinel.read_bytes() == b"immutable-observation"
    if kind == "frame":
        assert not target.exists()
    else:
        assert target.read_bytes() == b"last-good"


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

    from botocore.exceptions import ClientError

    def put(**kwargs):
        uploads[kwargs["Key"]] = kwargs["Body"].read()
        return {"ETag": '"' + "a" * 32 + '"'}

    client = Mock(upload_file=upload, put_object=put)
    client.get_object.side_effect = ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
    monkeypatch.setattr(storage, "_r2_client", lambda: client)
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
