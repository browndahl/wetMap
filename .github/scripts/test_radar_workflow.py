"""Guard the live-data path against reintroducing a blocking Actions pip cache."""

import re
import unittest
from pathlib import Path


WORKFLOWS = Path(__file__).resolve().parents[1] / "workflows"


class RadarWorkflowTests(unittest.TestCase):
    def test_python_workflows_do_not_depend_on_actions_dependency_cache(self):
        for name in ("radar.yml", "ci.yml", "retention.yml"):
            with self.subTest(workflow=name):
                workflow = (WORKFLOWS / name).read_text()
                self.assertNotRegex(workflow, r"cache:\s*pip\b")
                self.assertNotIn("actions/cache@", workflow)

    def test_live_setup_install_and_processing_have_explicit_deadlines(self):
        workflow = (WORKFLOWS / "radar.yml").read_text()
        steps = re.split(r"^      - ", workflow, flags=re.MULTILINE)[1:]
        self.assertEqual(len(steps), 6)
        for step in steps:
            with self.subTest(step=step.splitlines()[0]):
                self.assertRegex(step, r"timeout-minutes: [124]\b")
        self.assertIn("--no-cache-dir --retries 2 --timeout 20", workflow)

    def test_strict_freshness_and_serial_writer_remain_enabled(self):
        workflow = (WORKFLOWS / "radar.yml").read_text()
        self.assertIn("group: radar-ingestion", workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("timeout-minutes: 8", workflow)
        self.assertIn("frames.json 25 --managed-status-url", workflow)
        self.assertNotIn("continue-on-error", workflow)
        self.assertIn('cron: "2-59/5 * * * *"', workflow)


if __name__ == "__main__":
    unittest.main()
