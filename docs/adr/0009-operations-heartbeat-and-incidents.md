# ADR 0009: Operations heartbeat and incident-based notifications

Status: accepted for implementation, 2026-10-30, owner-approved operations sprint.

## Plan and acceptance

Change `infra/edge/src/operations.ts`, the edge router/scheduled handler,
`.github/workflows/synthetic.yml`, the freshness/probe scripts, tests and API/runbooks.
Do not modify forecasts, verification metrics, promotion gates or subscriptions.

- Use the existing minute Cloudflare cron to recover missed synthetic runs. Target
  a completed external probe every 15 minutes, with a 15-minute dispatch cooldown.
- Persist a separate five-minute scheduler heartbeat and the last external probe.
  A heartbeat older than 10 minutes or a probe older than 35 minutes is unhealthy.
- Keep public operational status HTTP 503 during an unresolved fault. Report radar
  observation age using the unchanged 25-minute ingestion SLO; source delay is not
  healthy data. A recent completed source fetch plus an old observation indicates
  `source-delayed`, not a proven provider-wide outage. Old/missing publication is
  classified separately as stalled/invalid ingestion.
- An authenticated probe report atomically opens, updates or recovers an incident.
  Fail the Actions notification job for the first occurrence or a changed failure
  signature. Repeated failures remain prominent in job summaries and public 503
  status, but do not generate a new failure mail on every successful execution of
  the same diagnostic. Execution success is not equivalent to service health.
- The radar workflow may hand off repeated source-delay notifications only after
  the active monitor has recorded that exact source-delay incident. Otherwise its
  existing strict freshness failure remains. Program, invalid-data and stalled
  ingestion failures are not suppressed.
- Prove authentication, timeout/cooldown, CAS races, report replay/idempotency,
  stale-heartbeat detection, first/repeated/changed/recovered faults, strict
  freshness fallback and independent scheduled-task failure isolation with tests.

## Cost, security and failure boundaries

No paid service, runner, archive or personal-data change. Reuse the public repo,
existing Worker cron and R2. Two fixed small objects (scheduler and latest report),
not an accumulating event archive. Additional scheduled state writes are bounded
at roughly 288 scheduler + 96 probe writes/day in steady state; reads are about
2,880/day plus status/probe traffic. This is a bounded increment, not proof of
account-wide free-tier headroom or a billing cap. No paid upgrade is enabled.

Use a new random `MONITOR_REPORT_TOKEN` in Cloudflare and Actions Secrets, never in
the browser, source, artifacts or logs. Limit report size and fields, use R2
conditional writes for concurrent transitions, and accept no arbitrary URLs to
probe. Status endpoints use `no-store`. Rollback flag `OPERATIONS_MONITOR_ENABLED`
disables dispatch/report handoff; original strict checks remain the fallback.

The two clocks are independent, not an availability SLA. GitHub can still queue or
drop jobs; Cloudflare can also fail. If both providers fail, GitHub cannot deliver
a mail about its own outage. A recovered heartbeat gap is visible on the next
probe. Report-upload failures fail loudly rather than silently losing monitoring.

Keep original synthetic checks, including quality-contract and cache-performance
checks. Check every surface even if one fails. Do not mark the overall forecast or
performance programme complete when this operations sprint is delivered.
