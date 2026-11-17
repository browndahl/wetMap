import unittest
import contextlib
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from release_gate import evaluate_runs, wait_for_checks, main


SHA = "a" * 40
REPO = "browndahl/wetMap"


def run(name, **changes):
    return {
        "id": 1,
        "name": name,
        "head_sha": SHA,
        "head_branch": "main",
        "head_repository": {"full_name": REPO},
        "event": "push",
        "status": "completed",
        "conclusion": "success",
        **changes,
    }


class ReleaseGateTests(unittest.TestCase):
    def test_release_workflow_uses_trusted_exact_push_and_both_checks(self):
        workflow = (
            Path(__file__).resolve().parents[1] / "workflows/release.yml"
        ).read_text()
        for required in (
            "github.event.workflow_run.event == 'push'",
            "github.event.workflow_run.head_repository.full_name == github.repository",
            'ref: "${{ github.event.workflow_run.head_sha }}"',
            'RELEASE_SHA: "${{ github.event.workflow_run.head_sha }}"',
            "actions: read",
            "group: wetmap-release",
            "cancel-in-progress: false",
            "release_gate.py --skip-superseded",
            "release_gate.py --check-current --skip-superseded",
            "steps.current.outputs.eligible == 'true'",
        ):
            with self.subTest(required=required):
                self.assertIn(required, workflow)
        self.assertNotIn("continue-on-error", workflow)
        self.assertNotIn("ref: main", workflow)

    def invoke_optional_gate(self, output_path, documents, *, check_current=False):
        environment = {
            "GITHUB_REPOSITORY": REPO,
            "GITHUB_SHA": "b" * 40,
            "GITHUB_REF": "refs/heads/main",
            "GH_TOKEN": "synthetic-sensitive-value",
            "GITHUB_OUTPUT": str(output_path) if output_path else "",
        }
        responses = []
        for document in documents:
            if isinstance(document, Exception):
                responses.append(document)
                continue
            response = Mock()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            response.read.return_value = json.dumps(document).encode()
            responses.append(response)
        arguments = ["gate", "--skip-superseded", "--sha", SHA]
        if check_current:
            arguments.append("--check-current")
        with (
            patch.dict("os.environ", environment),
            patch("sys.argv", arguments),
            patch("release_gate.urllib.request.urlopen", side_effect=responses),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            result = main()
        self.assertNotIn("synthetic-sensitive-value", output.getvalue())
        return result, output.getvalue()

    def test_optional_superseded_candidate_is_explicitly_not_publishable(self):
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "output"
            result, message = self.invoke_optional_gate(
                output_path, [{"object": {"sha": "b" * 40}}]
            )
            self.assertEqual(result, 0)
            self.assertEqual(output_path.read_text(), "eligible=false\n")
            self.assertIn('"decision": "superseded"', message)

    def test_optional_gate_only_enables_current_successfully_checked_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "output"
            current = {"object": {"sha": SHA}}
            result, _ = self.invoke_optional_gate(
                output_path,
                [
                    current,
                    {"workflow_runs": [run("CI"), run("Security")]},
                    current,
                ],
            )
            self.assertEqual(result, 0)
            self.assertEqual(output_path.read_text(), "eligible=true\n")
            output_path.unlink()
            result, _ = self.invoke_optional_gate(
                output_path, [current], check_current=True
            )
            self.assertEqual(result, 0)
            self.assertEqual(output_path.read_text(), "eligible=true\n")

    def test_optional_gate_never_masks_failure_or_missing_output(self):
        current = {"object": {"sha": SHA}}
        for documents in [
            [OSError("synthetic-sensitive-value")],
            [{}],
            [{"object": {"sha": "malformed"}}],
            [
                current,
                {"workflow_runs": [run("CI", conclusion="failure"), run("Security")]},
            ],
        ]:
            with (
                self.subTest(documents=documents),
                tempfile.TemporaryDirectory() as directory,
            ):
                output_path = Path(directory) / "output"
                result, _ = self.invoke_optional_gate(output_path, documents)
                self.assertEqual(result, 1)
                self.assertFalse(output_path.exists())
        self.assertEqual(self.invoke_optional_gate(None, [current])[0], 1)

    def test_cli_checks_current_commit_and_never_logs_auth_or_raw_errors(self):
        environment = {
            "GITHUB_REPOSITORY": REPO,
            "GITHUB_SHA": SHA,
            "GITHUB_REF": "refs/heads/main",
            "GH_TOKEN": "synthetic-sensitive-value",
        }
        with (
            patch.dict("os.environ", environment),
            patch("sys.argv", ["gate", "--check-current"]),
            patch(
                "release_gate.urllib.request.urlopen",
                side_effect=OSError("synthetic-sensitive-value"),
            ),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(main(), 1)
            self.assertNotIn("synthetic-sensitive-value", output.getvalue())
            self.assertIn("release-gate-unavailable", output.getvalue())

    def test_cli_rejects_superseded_commit_before_publication(self):
        environment = {
            "GITHUB_REPOSITORY": REPO,
            "GITHUB_SHA": SHA,
            "GITHUB_REF": "refs/heads/main",
            "GH_TOKEN": "test-only",
        }
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps({"object": {"sha": "b" * 40}}).encode()
        with (
            patch.dict("os.environ", environment),
            patch("sys.argv", ["gate", "--check-current"]),
            patch("release_gate.urllib.request.urlopen", return_value=response),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(main(), 1)
            self.assertIn("release-superseded", output.getvalue())

    def test_deploy_workflow_requires_the_gate_and_pins_the_checked_commit(self):
        workflow = (
            Path(__file__).resolve().parents[1] / "workflows/deploy.yml"
        ).read_text()
        self.assertIn("needs: validate", workflow)
        self.assertIn("actions: read", workflow)
        self.assertIn("release_gate.py --check-current", workflow)
        self.assertGreaterEqual(workflow.count('ref: "${{ github.sha }}"'), 3)
        self.assertNotIn("continue-on-error", workflow)

    def test_requires_both_exact_commit_workflows_to_succeed(self):
        self.assertEqual(
            evaluate_runs([run("CI"), run("Security")], SHA, REPO), "ready"
        )
        for workflows in ([], [run("CI")], [run("Security")]):
            self.assertEqual(evaluate_runs(workflows, SHA, REPO), "pending")

    def test_failure_cancel_skip_and_timeout_are_not_release_success(self):
        for conclusion in ("failure", "cancelled", "skipped", "timed_out", "neutral"):
            with self.subTest(conclusion=conclusion):
                self.assertEqual(
                    evaluate_runs(
                        [run("CI"), run("Security", conclusion=conclusion)], SHA, REPO
                    ),
                    "failed",
                )

    def test_wrong_commit_branch_fork_or_event_cannot_authorize_a_deploy(self):
        for changes in (
            {"head_sha": "b" * 40},
            {"head_branch": "feature"},
            {"head_repository": {"full_name": "untrusted/fork"}},
            {"event": "pull_request"},
        ):
            self.assertEqual(
                evaluate_runs([run("CI"), run("Security", **changes)], SHA, REPO),
                "pending",
            )

    def test_in_progress_or_new_failed_rerun_cannot_reuse_old_success(self):
        runs = [
            run("CI"),
            run("Security"),
            run("Security", id=2, status="in_progress", conclusion=None),
        ]
        self.assertEqual(evaluate_runs(runs, SHA, REPO), "pending")
        runs[-1]["status"] = "completed"
        runs[-1]["conclusion"] = "failure"
        self.assertEqual(evaluate_runs(runs, SHA, REPO), "failed")

    def test_bounded_wait_with_no_network_or_real_sleep(self):
        ticks = iter([0, 0, 20, 40])
        states = iter([[], [run("CI")], [run("CI"), run("Security")]])
        waits = []
        wait_for_checks(
            lambda: next(states),
            SHA,
            REPO,
            clock=lambda: next(ticks),
            sleep=waits.append,
        )
        self.assertEqual(waits, [10, 10])

    def test_timeout_and_failed_checks_abort_without_publishing(self):
        with self.assertRaises(TimeoutError):
            ticks = iter([0, 400])
            wait_for_checks(
                lambda: [], SHA, REPO, clock=lambda: next(ticks), sleep=lambda _: None
            )
        with self.assertRaises(ValueError):
            wait_for_checks(
                lambda: [run("CI", conclusion="failure"), run("Security")],
                SHA,
                REPO,
                clock=lambda: 0,
                sleep=lambda _: None,
            )


if __name__ == "__main__":
    unittest.main()
