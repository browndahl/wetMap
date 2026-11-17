"""Fail-closed, commit-specific deployment gate. No external Python packages."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.request


class GateError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def evaluate_runs(runs: list[dict], sha: str, repository: str) -> str:
    states = []
    for name in ("CI", "Security"):
        candidates = [
            run
            for run in runs
            if run.get("name") == name
            and run.get("head_sha") == sha
            and run.get("head_branch") == "main"
            and run.get("event") == "push"
            and (run.get("head_repository") or {}).get("full_name") == repository
        ]
        latest = max(candidates, key=lambda run: int(run["id"])) if candidates else None
        states.append(
            "pending"
            if not latest or latest.get("status") != "completed"
            else "ready"
            if latest.get("conclusion") == "success"
            else "failed"
        )
    return (
        "failed"
        if "failed" in states
        else "ready"
        if states == ["ready", "ready"]
        else "pending"
    )


def wait_for_checks(
    fetch_runs, sha, repository, *, clock=time.monotonic, sleep=time.sleep
):
    deadline = clock() + 360
    while clock() < deadline:
        decision = evaluate_runs(fetch_runs(), sha, repository)
        print(json.dumps({"event": "release.gate", "decision": decision}), flush=True)
        if decision == "ready":
            return
        if decision == "failed":
            raise GateError("required-checks-failed")
        sleep(10)
    raise TimeoutError("Required commit checks exceeded the gate deadline")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-current", action="store_true")
    parser.add_argument("--skip-superseded", action="store_true")
    parser.add_argument("--sha")
    arguments = parser.parse_args()
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    sha = (
        arguments.sha if arguments.sha is not None else os.environ.get("GITHUB_SHA", "")
    )
    token = os.environ.get("GH_TOKEN", "")
    output_path = os.environ.get("GITHUB_OUTPUT", "")
    if (
        not re.fullmatch(r"[\w.-]+/[\w.-]+", repository)
        or not re.fullmatch(r"[a-f0-9]{40}", sha)
        or os.environ.get("GITHUB_REF") != "refs/heads/main"
        or not token
        or (arguments.skip_superseded and not output_path)
    ):
        print("::error::release.gate.invalid-configuration")
        return 1

    def get(path):
        request = urllib.request.Request(
            f"https://api.github.com/repos/{repository}/{path}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "wetmap-release-gate/1.0",
            },
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise ValueError("Gate response exceeds its byte budget")
        return json.loads(body)

    def check_current():
        reference = get("git/ref/heads/main")
        object_ref = reference.get("object") if isinstance(reference, dict) else None
        current_sha = object_ref.get("sha") if isinstance(object_ref, dict) else None
        if not isinstance(current_sha, str) or not re.fullmatch(
            r"[a-f0-9]{40}", current_sha
        ):
            raise GateError("invalid-current-ref")
        if current_sha != sha:
            raise GateError("release-superseded")

    decision = "ready"
    try:
        try:
            check_current()
            if not arguments.check_current:
                wait_for_checks(
                    lambda: get(f"actions/runs?head_sha={sha}&event=push&per_page=100")[
                        "workflow_runs"
                    ],
                    sha,
                    repository,
                )
                check_current()
        except GateError as error:
            if not arguments.skip_superseded or error.code != "release-superseded":
                raise
            decision = "superseded"
        if arguments.skip_superseded:
            with open(output_path, "a", encoding="utf-8") as output:
                output.write(f"eligible={'true' if decision == 'ready' else 'false'}\n")
    except Exception as error:
        # Never expose headers/token, raw response bodies or arbitrary exception text.
        print(
            json.dumps(
                {
                    "event": "release.gate.failed",
                    "exceptionType": type(error).__name__,
                    "code": error.code
                    if isinstance(error, GateError)
                    else "release-gate-timeout"
                    if isinstance(error, TimeoutError)
                    else "release-gate-unavailable",
                }
            )
        )
        return 1
    if decision == "superseded":
        print(json.dumps({"event": "release.gate", "decision": "superseded"}))
        return 0
    print(
        "release.gate.ready" if not arguments.check_current else "release.gate.current"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
