from __future__ import annotations

import logging
import random
import time
from pathlib import Path

import requests

from .model import RadarItem

LOG = logging.getLogger(__name__)


class DmiClient:
    """The only DMI client in the system; browsers consume processed output."""

    def __init__(self, base_url: str, timeout_seconds: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "wetmap-worker/0.1 (+https://github.com/wetmap)"})

    def _get(self, url: str, *, stream: bool = False) -> requests.Response:
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                response = self.session.get(url, timeout=self.timeout, stream=stream)
                if response.status_code == 429:
                    retry_after = min(float(response.headers.get("Retry-After", "2")), 30)
                    time.sleep(retry_after)
                    continue
                response.raise_for_status()
                return response
            except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as error:
                last_error = error
                if attempt == 3:
                    break
                delay = min(2**attempt + random.uniform(0, 0.5), 8)
                LOG.warning("DMI request failed; retrying", extra={"attempt": attempt + 1, "delay": delay})
                time.sleep(delay)
        raise RuntimeError(f"DMI request failed after four attempts: {url}") from last_error

    def newest_composites(self, limit: int = 13) -> list[RadarItem]:
        url = (
            f"{self.base_url}/v1/radardata/collections/composite/items"
            f"?limit={max(1, min(limit, 24))}&sortorder=datetime,DESC"
        )
        features = self._get(url).json().get("features", [])
        return [
            RadarItem(
                id=feature["id"].removesuffix(".h5"),
                observed_at=feature["properties"]["datetime"],
                download_url=feature["asset"]["data"]["href"],
            )
            for feature in features
        ]

    def download(self, item: RadarItem, target: Path) -> str:
        import hashlib

        response = self._get(item.download_url, stream=True)
        digest = hashlib.sha256()
        temporary = target.with_suffix(".part")
        with temporary.open("wb") as output:
            for block in response.iter_content(1024 * 128):
                if block:
                    digest.update(block)
                    output.write(block)
        temporary.replace(target)
        return digest.hexdigest()
