import unittest
import contextlib
import io
import subprocess
from datetime import datetime, timezone
from unittest.mock import patch

from operations_probe import collect_checks, report_exit_code


class OperationsProbeTests(unittest.TestCase):
    @patch("operations_probe.check_live_performance")
    @patch("operations_probe.get_document")
    def test_quality_validator_rejections_have_safe_specific_codes(
        self, document, performance
    ):
        document.side_effect = None

        def response(url):
            if url.endswith("health/live"):
                return {"status": "ok"}
            if url.endswith("radar/frames"):
                return {"frames": [{"observedAt": "2026-10-30T11:50:00Z"}]}
            if url.endswith("operations/status"):
                return {
                    "monitoringEnabled": True,
                    "scheduler": {"checkedAt": "2026-10-30T12:00:00Z"},
                }
            return '<div id="root"></div>' if url.endswith("/") else {}

        document.side_effect = response
        cases = [
            ("Nowcast verification is stale (50.0 minutes)", "quality-stale"),
            (
                "ValueError: Invalid shared-coverage metric",
                "quality-shared-coverage-invalid",
            ),
            (
                "ValueError: Inconsistent verification accounting",
                "quality-verification-invalid",
            ),
            ("Shadow candidate promoted below the CSI floor", "quality-promotion-csi"),
            ("KeyError: 'untrusted-secret-field'", "quality-contract-invalid"),
            ("UNEXPECTED private-token=must-not-be-logged", "quality-validator-failed"),
        ]
        for stderr, expected in cases:
            with (
                self.subTest(expected=expected),
                patch(
                    "operations_probe.subprocess.run",
                    side_effect=subprocess.CalledProcessError(
                        1, ["validator"], stderr=stderr
                    ),
                ),
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                checks = collect_checks(
                    "https://web.test",
                    "https://api.test",
                    now=datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc),
                )
                self.assertEqual(checks[3]["code"], expected)
                self.assertFalse(checks[3]["ok"])
                self.assertEqual(len(checks), 6)
                self.assertTrue(checks[-1]["ok"])
                self.assertNotIn("must-not-be-logged", output.getvalue())
                self.assertNotIn("untrusted-secret-field", output.getvalue())

    @patch("operations_probe.check_live_performance")
    @patch("operations_probe.get_document")
    def test_validator_timeout_is_not_relabelled_as_an_opaque_failure(
        self, document, performance
    ):
        document.side_effect = [
            '<div id="root"></div>',
            {"status": "ok"},
            {"frames": [{"observedAt": "2026-10-30T11:50:00Z"}]},
            {},
            {
                "monitoringEnabled": True,
                "scheduler": {"checkedAt": "2026-10-30T12:00:00Z"},
            },
        ]
        with patch(
            "operations_probe.subprocess.run",
            side_effect=subprocess.TimeoutExpired(["validator"], 15),
        ):
            checks = collect_checks(
                "https://web.test",
                "https://api.test",
                now=datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc),
            )
        self.assertEqual(checks[3]["code"], "quality-validator-timeout")
        self.assertFalse(checks[3]["ok"])

    @patch(
        "operations_probe.check_live_performance",
        side_effect=SystemExit(
            "Live precipitation probe did not use the radar-nowcast path"
        ),
    )
    @patch("operations_probe.validate_quality", return_value=None)
    @patch("operations_probe.get_document")
    def test_performance_failure_has_a_specific_cause_without_weakening_health(
        self, document, quality, performance
    ):
        document.side_effect = [
            '<div id="root"></div>',
            {"status": "ok"},
            {"frames": [{"observedAt": "2026-10-30T11:50:00Z"}]},
            {},
            {
                "monitoringEnabled": True,
                "scheduler": {"checkedAt": "2026-10-30T12:00:00Z"},
            },
        ]
        checks = collect_checks(
            "https://web.test",
            "https://api.test",
            now=datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc),
        )
        self.assertFalse(checks[4]["ok"])
        self.assertEqual(checks[4]["code"], "radar-unavailable")

    @patch("operations_probe.check_live_performance")
    @patch("operations_probe.validate_quality")
    @patch("operations_probe.get_document")
    def test_runs_remaining_checks_after_one_surface_fails(
        self, document, quality, performance
    ):
        quality.return_value = None

        def response(url):
            if url == "https://web.test/":
                raise OSError("offline")
            if url.endswith("health/live"):
                return {"status": "ok"}
            if url.endswith("radar/frames"):
                return {
                    "generatedAt": "2026-10-30T12:00:00Z",
                    "frames": [{"observedAt": "2026-10-30T11:50:00Z"}],
                }
            if url.endswith("operations/status"):
                return {
                    "monitoringEnabled": True,
                    "scheduler": {"checkedAt": "2026-10-30T12:00:00Z"},
                }
            return {"quality": True}

        document.side_effect = response
        checks = collect_checks(
            "https://web.test",
            "https://api.test",
            now=datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(len(checks), 6)
        self.assertFalse(checks[0]["ok"])
        self.assertTrue(all(check["ok"] for check in checks[1:]))
        quality.assert_called_once()
        performance.assert_called_once()

    @patch("operations_probe.check_live_performance")
    @patch("operations_probe.validate_quality")
    @patch("operations_probe.get_document")
    def test_stale_radar_is_reported_not_relabelled_healthy(
        self, document, quality, performance
    ):
        quality.return_value = None
        document.side_effect = [
            '<div id="root"></div>',
            {"status": "ok"},
            {
                "generatedAt": "2026-10-30T12:00:00Z",
                "frames": [{"observedAt": "2026-10-30T10:00:00Z"}],
            },
            {},
            {
                "monitoringEnabled": True,
                "scheduler": {"checkedAt": "2026-10-30T11:00:00Z"},
            },
        ]
        checks = collect_checks(
            "https://web.test",
            "https://api.test",
            now=datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(checks[2]["code"], "source-delayed")
        self.assertFalse(checks[2]["ok"])
        self.assertEqual(checks[-1]["code"], "scheduler-missed")

    def test_first_fault_fails_notification_job_but_repeats_do_not_clear_health(self):
        checks = [
            {"name": "radar", "ok": False, "code": "source-delayed", "durationMs": 0}
        ]
        self.assertEqual(
            report_exit_code(
                checks, {"accepted": True, "shouldFail": True, "transition": "opened"}
            ),
            1,
        )
        self.assertEqual(
            report_exit_code(
                checks, {"accepted": True, "shouldFail": False, "transition": "ongoing"}
            ),
            0,
        )
        self.assertFalse(checks[0]["ok"])

    def test_malformed_acknowledgement_does_not_silently_succeed(self):
        for result in [
            {},
            {"accepted": True},
            {"shouldFail": False},
            {"accepted": False, "shouldFail": False, "transition": "unknown"},
        ]:
            with self.assertRaises(ValueError):
                report_exit_code([], result)

    @patch("operations_probe.check_live_performance")
    @patch("operations_probe.validate_quality")
    @patch("operations_probe.get_document")
    def test_a_resumed_monitor_reports_the_missed_probe_gap(
        self, document, quality, performance
    ):
        quality.return_value = None
        document.side_effect = [
            '<div id="root"></div>',
            {"status": "ok"},
            {"frames": [{"observedAt": "2026-10-30T11:50:00Z"}]},
            {},
            {
                "monitoringEnabled": True,
                "scheduler": {"checkedAt": "2026-10-30T12:00:00Z"},
                "probe": {"receivedAt": "2026-10-30T11:00:00Z"},
            },
        ]
        checks = collect_checks(
            "https://web.test",
            "https://api.test",
            now=datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(checks[-1]["code"], "probe-missed")


if __name__ == "__main__":
    unittest.main()
