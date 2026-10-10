from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

ATTRIBUTION = "Baseret på data fra DMI og efterfølgende bearbejdet"


@dataclass(frozen=True)
class RadarItem:
    id: str
    observed_at: str
    download_url: str


@dataclass(frozen=True)
class Frame:
    id: str
    observedAt: str
    fetchedAt: str
    url: str
    bounds: list[float]
    product: str
    unit: str
    sha256: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def manifest(frames: list[Frame]) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "attribution": ATTRIBUTION,
        "frames": [frame.as_dict() for frame in sorted(frames, key=lambda item: item.observedAt)],
    }
