# ADR 0016 — Trusted, exact-commit GitHub Release candidates

Date: 18 November 2026 (Copenhagen). Status: accepted for scoped implementation.

## Context

Final inspection of 91 runs since 21:45 UTC found Release 44186050603 failing at
22:02:58 UTC: GitHub rejected `refs/notes/semantic-release-v1.22.4` with Internal
Server Error. Tag v1.22.4 exists at `fda019b`, but the GitHub Release API returns 404. No evidence this was a radar/runtime failure or that serialization fixes
GitHub's remote 500. Blindly replaying the whole publisher is unsafe after partial
tag creation. Repair of the old Release post is separately awaiting approval.

Independently, release.yml accepted a successful CI run by branch name only,
checked out floating main, did not wait for Security and lacked serialization.
This is distinct from the already corrected deployment gate. GitHub documents
the privilege boundary for
[workflow_run](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run).

## Decision

- Only successful own-repository **push** CI on main can nominate a release.
- Checkout that exact nominated SHA. Pass it through a normal `RELEASE_SHA` env
  and validated `--sha` CLI argument, not an override of reserved GITHUB_* values.
- Reuse the bounded CI+Security gate; both latest same-SHA own push runs must
  succeed. Serialize `wetmap-release`, do not cancel a running publisher.
- Recheck current main immediately before publication. An obsolete **candidate**
  may explicitly output `eligible=false`; publisher is skipped, not reported as
  successfully released. A new current commit has its own workflow candidate.
- The optional skip handles only the static `release-superseded` condition. Missing
  output path, failed/unknown checks, timeout, network or output I/O still fail.
  Default deployment-gate behavior remains strict/failing for superseded commits.
- Keep existing semantic-release version/plugin policy. No side-effect retry,
  tag/history rewrite, old Release repair or dependency major upgrade in this fix.

## Evidence / consequences

The old workflow fails eleven source-policy assertions. Three additional tests
exercise the new opt-in interface; unsupported CLI errors on old code are not
historical production failures. All thirteen release-gate methods /54 script
methods pass after implementation, including old strict default and static
secret-sentinel non-leakage. Normal live gate ordering will be observed after merge.

Uses existing standard public runner/token plus Actions read. Same bounded GET
polling as deploy; no cloud runtime/storage or service. Rollback: revert this
workflow/optional-gate change. It doesn't eliminate provider 5xx, impose branch
protection or prove installer dependency security. The historical publisher log
also reports 14 high /1 critical npm advisories in its action installation tree;
exact packages/reachability need separate verification, not an invented exploit
or evidence that repository Trivy covers the action's runtime installation.
