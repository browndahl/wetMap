"""Prevent accidental direct app logging outside the approved projection boundary."""

import re
import unittest
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[2] / "infra/edge/src"


class PrivateLoggingPolicyTests(unittest.TestCase):
    def test_production_source_inventory_is_not_empty(self):
        for name in (
            "index.ts",
            "push.ts",
            "radarScheduler.ts",
            "operations.ts",
            "logging.ts",
        ):
            self.assertTrue((SOURCE / name).is_file(), name)

    def test_only_the_projection_boundary_writes_direct_console_logs(self):
        for path in SOURCE.rglob("*.ts"):
            if path.name.endswith(".test.ts") or path.name == "logging.ts":
                continue
            with self.subTest(source=path.name):
                self.assertIsNone(re.search(r"\bconsole\s*(?:\.|\[)", path.read_text()))


if __name__ == "__main__":
    unittest.main()
