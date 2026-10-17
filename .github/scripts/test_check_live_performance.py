import unittest
import urllib.error
from datetime import datetime, timezone

from check_live_performance import (
    ProbeResult,
    check_live_performance,
    probe_url,
)


def result(
    cache_status: str,
    *,
    seconds: float = 0.1,
    source: str = "dmi-radar-nowcast-harmonie",
    edge: str = "CPH",
) -> ProbeResult:
    timing = (
        "point_cache;dur=0.5, total;dur=1.0"
        if cache_status == "HIT"
        else "radar;dur=30.0, combined_total;dur=100.0"
    )
    return ProbeResult(
        seconds=seconds,
        headers={
            "x-wetmap-point-cache": cache_status,
            "server-timing": timing,
            "cf-ray": f"abc123-{edge}",
        },
        payload={
            "source": source,
            "basedOnObservedAt": "2026-10-17T08:00:00Z",
        },
    )


class LivePerformanceCheckTests(unittest.TestCase):
    def test_retries_until_the_async_edge_cache_is_ready(self) -> None:
        responses = iter([result("MISS"), result("MISS"), result("HIT")])
        delays: list[float] = []

        checked = check_live_performance(
            "https://api.test",
            probe=lambda _: next(responses),
            sleep=delays.append,
            retry_delays=(0.5, 1.0, 2.0),
        )

        self.assertEqual([item.cache_status for item in checked], ["MISS", "MISS", "HIT"])
        self.assertEqual(delays, [0.5, 1.0])

    def test_retries_a_transient_network_error(self) -> None:
        responses = iter(
            [
                urllib.error.URLError("temporary"),
                result("MISS"),
                result("HIT"),
            ]
        )

        def probe(_: str) -> ProbeResult:
            response = next(responses)
            if isinstance(response, Exception):
                raise response
            return response

        checked = check_live_performance(
            "https://api.test",
            probe=probe,
            sleep=lambda _: None,
            retry_delays=(0.1, 0.2),
        )

        self.assertEqual([item.cache_status for item in checked], ["MISS", "HIT"])

    def test_fails_when_the_cache_never_hits(self) -> None:
        with self.assertRaisesRegex(SystemExit, "did not produce a HIT after 3 attempts"):
            check_live_performance(
                "https://api.test",
                probe=lambda _: result("MISS"),
                sleep=lambda _: None,
                retry_delays=(0.1, 0.2),
            )

    def test_fails_when_cached_response_is_slow(self) -> None:
        with self.assertRaisesRegex(SystemExit, "Cached point forecast is too slow"):
            check_live_performance(
                "https://api.test",
                probe=lambda _: result("HIT", seconds=5.1),
                sleep=lambda _: None,
                retry_delays=(),
            )

    def test_fails_when_radar_nowcast_is_not_used(self) -> None:
        with self.assertRaisesRegex(SystemExit, "did not use the radar-nowcast path"):
            check_live_performance(
                "https://api.test",
                probe=lambda _: result("MISS", source="open-meteo-dmi"),
                sleep=lambda _: None,
                retry_delays=(),
            )

    def test_probe_coordinate_is_stable_inside_a_quarter_hour(self) -> None:
        first = probe_url(
            "https://api.test/",
            datetime(2026, 10, 17, 8, 1, tzinfo=timezone.utc),
        )
        second = probe_url(
            "https://api.test",
            datetime(2026, 10, 17, 8, 14, tzinfo=timezone.utc),
        )

        self.assertEqual(first, second)
        self.assertIn("/api/v1/weather/precipitation?", first)


if __name__ == "__main__":
    unittest.main()
