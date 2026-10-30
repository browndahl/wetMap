import unittest
from datetime import datetime, timezone

from check_freshness import managed_source_delay, radar_status


NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)


class FreshnessTests(unittest.TestCase):
    def test_observation_age_is_not_replaced_by_publication_time(self):
        status = radar_status(
            {
                "generatedAt": NOW.isoformat(),
                "frames": [{"observedAt": "2026-10-30T11:10:00Z"}],
            },
            now=NOW,
        )
        self.assertFalse(status["ok"])
        self.assertEqual(status["ageMinutes"], 50)
        self.assertEqual(status["code"], "source-delayed")

    def test_stalled_invalid_future_and_boundary_cases(self):
        self.assertTrue(
            radar_status({"frames": [{"observedAt": "2026-10-30T11:35:00Z"}]}, now=NOW)[
                "ok"
            ]
        )
        self.assertEqual(
            radar_status({"frames": [{"observedAt": "2026-10-30T11:34:59Z"}]}, now=NOW)[
                "code"
            ],
            "ingestion-stalled",
        )
        for manifest in [
            {},
            {"frames": []},
            {"frames": [{"observedAt": "bad"}]},
            {"frames": [{"observedAt": "2026-10-30T12:05:00Z"}]},
        ]:
            self.assertEqual(
                radar_status(manifest, now=NOW)["code"], "invalid-manifest"
            )

    def test_source_delay_handoff_requires_live_monitor_and_exact_active_incident(self):
        status = {"code": "source-delayed", "observedAt": "2026-10-30T11:10:00Z"}
        monitoring = {
            "monitoringActive": True,
            "scheduler": {"checkedAt": NOW.isoformat()},
            "probe": {"receivedAt": NOW.isoformat()},
            "radar": {"observedAt": status["observedAt"]},
            "activeIncident": {"signature": "radar:source-delayed"},
        }
        self.assertTrue(managed_source_delay(status, monitoring, NOW))
        for key, replacement in [
            ("monitoringActive", False),
            ("scheduler", {"checkedAt": "2026-10-30T11:40:00Z"}),
            ("probe", {"receivedAt": "2026-10-30T11:00:00Z"}),
            ("activeIncident", None),
            ("radar", {"observedAt": "2026-10-30T11:05:00Z"}),
        ]:
            self.assertFalse(
                managed_source_delay(status, {**monitoring, key: replacement}, NOW)
            )
        self.assertFalse(
            managed_source_delay(
                {**status, "code": "ingestion-stalled"}, monitoring, NOW
            )
        )


if __name__ == "__main__":
    unittest.main()
