# Operations sprint — 30 October 2026

Owner-approved monitoring reliability and incident notifications, not a forecast
or UI release. [ADR 0009](adr/0009-operations-heartbeat-and-incidents.md).

## Baseline incident

Eight radar jobs on 29 October completed ingestion with zero new frames but failed
freshness. Observation age rose from 31.4 to 93.4 minutes. The 12:35 UTC synthetic
correctly failed at 45.5 minutes. The 13:31 UTC recovery job added 13 frames and
passed at 17.6 minutes. Non-advancing source results are established; a provider-wide
outage is not. Synthetic ran only five times that day despite a 15-minute schedule;
radar had 147 watchdog-dispatched jobs and four schedule-triggered jobs.

[Last failed job](https://github.com/browndahl/wetMap/actions/runs/40881349899),
[synthetic failure](https://github.com/browndahl/wetMap/actions/runs/40874512691),
[recovery](https://github.com/browndahl/wetMap/actions/runs/40882728583).

## Implementation and interpretation

- Reuse minute Cloudflare cron, with independent radar, push and monitor tasks.
  Persist a five-minute scheduler heartbeat; request a synthetic run after 15
  minutes without a completed probe. Claim a 15-minute dispatch slot with R2 ETag
  compare-and-swap, including on failed dispatches. GitHub schedule remains fallback.
- Probe every surface: web shell, API, 25-minute radar freshness, complete existing
  quality contract, existing cache-performance test and scheduler heartbeat.
  The old synthetic check allowed 30 minutes; it now follows the existing stricter
  25-minute ingestion SLO. No freshness limit was relaxed.
- Canonical health is `GET /api/v1/operations/status`, not an Actions execution's
  colour. HTTP 503 means stale radar, failed checks, disabled monitoring, missing
  scheduler heartbeat (>10 minutes), missing external probe (>35 minutes), or
  unavailable monitoring state. Observation age is recomputed on status reads.
- A private token-authenticated report opens/updates/recovers an incident. First or
  changed failing signatures fail Actions for notification. Repeats retain explicit
  DEGRADED summaries/warnings and public 503, but do not emit another failure for
  a successful execution of the same diagnostic. Upload/auth/storage failures
  still fail loudly. A recovered monitoring gap is reported by the next probe.
- Radar freshness stays strict by default. Only the exact source-delay incident
  already owned by a fresh monitor may hand off duplicate email ownership. Missing
  monitoring, different observations, invalid data and stalled ingestion still fail.
  Forecast and notification eligibility are untouched.

## Verification

Regression checks cover first/repeated/changed/recovered faults, CAS races,
idempotency and superseded reports, auth/body bounds, heartbeat expiry, unchanged
age limits, task isolation, running all checks after a failure and strict handoff
fallback. No fake failure is injected into production.

Local verification: `pnpm check` passed (75 TypeScript tests, lint, type checks and
builds); `.venv/bin/ruff check .github/scripts apps/worker` passed; script unittest
suite passed 20/20; worker pytest passed 35/35. Direct edge dry-run with a writable
temporary Wrangler log path also passed. The pre-existing MapLibre chunk-size
warning remains outside this sprint; no complete performance acceptance is claimed.

A predeployment read-only probe passed web/API/radar/quality/performance and
correctly failed the not-yet-present scheduler endpoint. After deployment verify
an authenticated real Actions report, public status and automatic follow-up.

## Free-only budget

Read-only account-wide R2 GraphQL measurement: 1 October 00:00 through 30 October
15:00 UTC, 287,892 operations across all action types. This is not a billing-class
total; even conservatively treating all as Class A leaves headroom below included
1M Class A / 10M Class B limits for the small increment.

Additional account analytics: recent maximum R2 payload was 8,207,238,416 bytes
(about 8.21 GB), plus 1,889,656 metadata bytes. The preview bucket was empty.
Workers recorded 1,450 requests and zero errors on 29 October. The two monitoring
objects add only kilobytes, but existing storage is already much closer to 10 GB
than the original budget estimate. Audit retention/storage separately before any
data expansion; no history is deleted by this sprint.

Two fixed small objects, no archive/lifecycle change. Normal new writes: about
288 scheduler + up to 96 watchdog-triggered reports/day (~11,520/month), plus
fallback/manual reports. New scheduled reads: ~2,880/day plus status reads. One
dispatch per 15-minute slot; the independent GitHub schedule may also run. No paid
plan, runner, dependency or personal-data storage added. This measured baseline
and bounded increment are not a billing cap or a promise about future traffic.

Both clocks/providers can fail. GitHub cannot mail about its own total outage;
there is no new independent third-party pager or SLA. Notification claims are
best-effort: a job cancelled after recording an incident but before completion may
not deliver an email. Canonical degraded status is retained regardless.

## Deferred

Dependabot #21 lint migration, V6 event acquisition/backtests, actual iPhone push
delivery and full performance acceptance are separate work. No forecast metric or
gate was changed by this sprint.
