from __future__ import annotations

import logging
import random
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

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
        document = self._get(url).json()
        features = document.get("features") if isinstance(document, dict) else None
        if not isinstance(features, list) or not features:
            raise ValueError("DMI catalogue contains no usable observations")
        items: list[RadarItem] = []
        identifiers: set[str] = set()
        for feature in features:
            try:
                identifier = feature["id"]
                observed_at = feature["properties"]["datetime"]
                download_url = feature["asset"]["data"]["href"]
                if not isinstance(identifier, str) or not re.fullmatch(
                    r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}\.h5", identifier
                ):
                    raise ValueError("Invalid observation identifier")
                if identifier in identifiers:
                    raise ValueError("Duplicate observation identifier")
                if not isinstance(observed_at, str):
                    raise ValueError("Invalid observation timestamp")
                timestamp = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
                if timestamp.utcoffset() != timedelta(0):
                    raise ValueError("Observation timestamp must be explicit UTC")
                if not isinstance(download_url, str):
                    raise ValueError("Invalid observation asset URL")
                asset = urlsplit(download_url)
                if asset.scheme != "https" or not asset.hostname or asset.username or asset.password:
                    raise ValueError("Observation asset must be unauthenticated HTTPS")
                identifiers.add(identifier)
                items.append(RadarItem(identifier.removesuffix(".h5"), observed_at, download_url))
            except (KeyError, TypeError, ValueError, AttributeError):
                # Do not echo upstream fields/URLs into logs. Reject the whole batch
                # before any frame path or manifest can be constructed from it.
                raise ValueError("Invalid DMI observation catalogue") from None
        return items

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
