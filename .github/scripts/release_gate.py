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
    arguments = parser.parse_args()
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    sha = os.environ.get("GITHUB_SHA", "")
    token = os.environ.get("GH_TOKEN", "")
    if (
        not re.fullmatch(r"[\w.-]+/[\w.-]+", repository)
        or not re.fullmatch(r"[a-f0-9]{40}", sha)
        or os.environ.get("GITHUB_REF") != "refs/heads/main"
        or not token
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
        if get("git/ref/heads/main").get("object", {}).get("sha") != sha:
            raise GateError("release-superseded")

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
    print(
        "release.gate.ready" if not arguments.check_current else "release.gate.current"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
