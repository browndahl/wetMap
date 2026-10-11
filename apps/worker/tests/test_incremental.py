from pathlib import Path
from types import SimpleNamespace

from wetmap_worker import cli
from wetmap_worker.model import Frame, manifest
from wetmap_worker.storage import write_json_atomic


def test_upload_run_only_processes_new_frames(tmp_path: Path, monkeypatch) -> None:
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

    def fake_download_frames(output: Path, names: list[str]):
        paths = []
        for name in names:
            path = output / name
            path.write_bytes(b"webp")
            paths.append(path)
        return paths

    monkeypatch.setattr(cli, "DmiClient", FakeClient)
    monkeypatch.setattr(cli, "process_hdf5", fake_process)
    monkeypatch.setattr(cli, "download_frames_r2", fake_download_frames)
    monkeypatch.setattr(cli, "generate_nowcast", lambda *_args: ({}, {}, []))
    monkeypatch.setattr(cli, "upload_r2", lambda _output, paths: uploaded.extend(paths))

    cli.run(tmp_path, limit=2, upload=True)

    assert [path.name for path in uploaded] == ["new.webp"]
    assert not (tmp_path / "old.webp").exists()
