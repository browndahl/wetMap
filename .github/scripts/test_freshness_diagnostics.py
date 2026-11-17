import argparse
import contextlib
import io
import json
import unittest
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import check_freshness as freshness


NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
STATUS = {"ok": False, "code": "source-delayed", "observedAt": "2026-11-17T11:10:00Z"}


def monitor(now=NOW):
    return {
        "monitoringActive": True,
        "scheduler": {"checkedAt": now.isoformat()},
        "probe": {"receivedAt": now.isoformat()},
        "radar": {"observedAt": STATUS["observedAt"]},
        "activeIncident": {
            "signature": "radar:source-delayed,performance:radar-unavailable"
        },
    }


class FreshnessDiagnosticsTests(unittest.TestCase):
    def invoke(self, response=None, error=None, status=STATUS):
        arguments = argparse.Namespace(
            manifest=Path("unused-test-manifest.json"),
            limit_minutes=25,
            managed_status_url="https://test.invalid/?token=never-log-this",
        )
        with (
            patch.object(
                freshness.argparse.ArgumentParser, "parse_args", return_value=arguments
            ),
            patch.object(Path, "read_text", return_value="{}"),
            patch.object(freshness, "radar_status", return_value=status),
            patch.object(
                freshness.urllib.request,
                "urlopen",
                return_value=response,
                side_effect=error,
            ),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            code = freshness.main()
        self.assertNotIn("never-log-this", output.getvalue())
        return code, output.getvalue()

    def test_static_reasons_preserve_exact_handoff_policy(self):
        valid = monitor()
        cases = [
            ({}, "monitor-inactive"),
            (
                {**valid, "scheduler": {"checkedAt": "2026-11-17T11:49:59Z"}},
                "scheduler-not-fresh",
            ),
            (
                {**valid, "probe": {"receivedAt": "2026-11-17T11:24:59Z"}},
                "probe-not-fresh",
            ),
            (
                {**valid, "radar": {"observedAt": "2026-11-17T11:05:00Z"}},
                "observation-mismatch",
            ),
            ({**valid, "activeIncident": None}, "incident-not-owned"),
            (
                {
                    **valid,
                    "activeIncident": {"signature": "private-token=never-log-this"},
                },
                "incident-not-owned",
            ),
        ]
        self.assertEqual(
            freshness.source_delay_handoff_reason(STATUS, valid, NOW), "owned"
        )
        for value, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(
                    freshness.source_delay_handoff_reason(STATUS, value, NOW), expected
                )
                self.assertFalse(freshness.managed_source_delay(STATUS, value, NOW))
        self.assertEqual(
            freshness.source_delay_handoff_reason(
                {**STATUS, "code": "ingestion-stalled"}, valid, NOW
            ),
            "not-source-delay",
        )

    def test_future_and_malformed_contracts_never_own_an_incident(self):
        for field, value in [
            ("scheduler", {"checkedAt": "2026-11-17T12:02:01Z"}),
            ("probe", {"receivedAt": "2026-11-17T12:02:01Z"}),
            ("scheduler", {"checkedAt": "bad"}),
            ("probe", None),
        ]:
            with self.subTest(field=field, value=value):
                self.assertNotEqual(
                    freshness.source_delay_handoff_reason(
                        STATUS, {**monitor(), field: value}, NOW
                    ),
                    "owned",
                )
        for malformed in [None, [], "private-token=never-log-this"]:
            self.assertEqual(
                freshness.source_delay_handoff_reason(STATUS, malformed, NOW),
                "monitor-invalid-contract",
            )

    def test_503_active_owner_still_hands_off_without_claiming_recovery(self):
        body = json.dumps(monitor(datetime.now(timezone.utc))).encode()
        error = urllib.error.HTTPError(
            "https://test.invalid", 503, "unhealthy", {}, io.BytesIO(body)
        )
        code, output = self.invoke(error=error)
        self.assertEqual(code, 0)
        self.assertIn('"reason": "owned"', output)
        self.assertIn("service status remains HTTP 503", output)

    def test_monitor_http_failure_is_static_and_still_fails_job(self):
        error = urllib.error.HTTPError(
            "https://test.invalid/?token=never-log-this",
            429,
            "never-log-this",
            {},
            None,
        )
        code, output = self.invoke(error=error)
        self.assertEqual(code, 1)
        self.assertIn('"reason": "monitor-unavailable"', output)

    def test_healthy_ingestion_does_not_fetch_monitor(self):
        code, output = self.invoke(
            error=AssertionError("must not fetch"),
            status={**STATUS, "ok": True, "code": "ok"},
        )
        self.assertEqual(code, 0)
        self.assertNotIn("source-delay-handoff", output)

    def test_stalled_ingestion_still_fails_without_handoff(self):
        code, output = self.invoke(
            error=AssertionError("must not fetch"),
            status={**STATUS, "code": "ingestion-stalled"},
        )
        self.assertEqual(code, 1)
        self.assertNotIn("source-delay-handoff", output)

    def test_response_body_is_bounded_and_invalid_json_does_not_leak(self):
        for payload, reason in [
            (b" " * 65_537, "monitor-too-large"),
            (b"never-log-this", "monitor-invalid-json"),
            (b"null", "monitor-invalid-contract"),
        ]:
            with self.subTest(reason=reason):
                response = io.BytesIO(payload)
                with patch.object(response, "read", wraps=response.read) as reader:
                    code, output = self.invoke(response=response)
                reader.assert_called_once_with(65_537)
                self.assertEqual(code, 1)
                self.assertIn(f'"reason": "{reason}"', output)


if __name__ == "__main__":
    unittest.main()
