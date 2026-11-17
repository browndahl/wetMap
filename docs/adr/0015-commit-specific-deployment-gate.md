# ADR 0015: require exact-commit CI and Security before deployment

17 November 2026. Owner requested correctness/stability work under the master prompt.
No repository protection/account setting, paid runner or provider plan is changed.

## Problem and decision

Deploy previously started independently on main push. Staging reran pnpm checks,
but .NET, containers or security could fail while production was already published.
PR checks were observed manually, not enforced by this workflow. Main protection
and production-environment approval remain separate owner/configuration decisions.

Add a validate job before staging. It waits at most six minutes for successful
CI and Security **push runs on the exact SHA, main branch and own repository**.
Skipped/cancelled/neutral/failure/timeouts do not authorize publication; a newer
pending/failed run cannot reuse an older successful run for the same workflow.
Missing permissions, malformed responses and unavailable GitHub fail closed.

All checkout steps pin the original github.sha. Recheck main's current SHA just
before production publication; reject a superseded release. Serialize deploy
workflows without cancel-in-progress so a partial Cloudflare publication isn't
interrupted by another commit. Manual dispatch is subject to the same main gate.

## Bounds and evidence

One read-only GitHub API query per ten-second poll, max six minutes (at most 36
polls plus two reference reads in a normal deadline window), 10s HTTP timeout,
2 MB response ceiling, eight-minute job cap. This is bounded control-plane waiting,
not retrying a side-effecting deploy. Uses the existing public standard runner.
Token stays in GH_TOKEN/Authorization and never appears in diagnostic text.

Deterministic local tests cover exact SHA/repo/branch/event, both workflows,
missing checks, failed/skipped/cancelled/timeout outcomes, newer failed reruns,
deadline, workflow dependencies, superseded release and redacted errors. They
do not contact GitHub. The workflow dependency test fails on the old config.

Production verification must observe the first real gate waiting until both
actual workflows succeed before staging starts. No forced failing production
release is injected. Rollback is a reviewed workflow revert, not bypassing the
gate to ship an unverified commit. This does not establish isolated staging or
replace branch protection, independent acceptance or artifact provenance checks.
