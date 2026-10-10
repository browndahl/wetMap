from wetmap_worker.model import ATTRIBUTION, Frame, manifest


def test_manifest_is_ordered_and_attributed() -> None:
    newer = Frame("b", "2026-01-01T00:05:00Z", "now", "/b.webp", [1, 2, 3, 4], "DBZH", "dBZ", "b")
    older = Frame("a", "2026-01-01T00:00:00Z", "now", "/a.webp", [1, 2, 3, 4], "DBZH", "dBZ", "a")
    result = manifest([newer, older])
    assert result["attribution"] == ATTRIBUTION
    assert [item["id"] for item in result["frames"]] == ["a", "b"]
