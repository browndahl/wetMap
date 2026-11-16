# Radar ingestion recovery — 16 November 2026

## Evidence and limits

The two failed synthetic runs, [43854193447](https://github.com/browndahl/wetMap/actions/runs/43854193447)
and [43892474884](https://github.com/browndahl/wetMap/actions/runs/43892474884),
reported only `radar:ingestion-stalled`. Web, API, quality, performance and
scheduler checks passed. Radar jobs 43853151430 and 43890914942 waited about 22
and 52 minutes between run creation and actual job start; processing once started
took around a minute. The logs do not establish the precise underlying cause of
those waits.

A separate [job 43898002577](https://github.com/browndahl/wetMap/actions/runs/43898002577)
installed Python, then reported `Failed to restore: Egress is over the account
limit` in setup-python's pip cache handling. It never reached processing and was
cancelled at the eight-minute deadline. This happened **after** the two alarms;
it is not evidence that cache caused the earlier queues. The error text does not
establish a billable spending limit.

GitHub documents that scheduled workflows can be delayed/dropped under load:
[schedule event](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
Our external cron dispatch mitigates missed scheduling but still needs GitHub's
runner pool. No software change can guarantee uninterrupted DMI/GitHub availability.

## Changes

- Remove Actions pip dependency-cache restore/save from radar, Python CI and
  manual retention. Radar installs directly with bounded pip retries/timeouts;
  no new service, storage or paid plan. Pin the radar runner to Ubuntu 24.04.
- Add per-step deadlines without increasing the eight-minute radar job cap.
  Setup cannot consume the full job budget. No `continue-on-error` bypass.
- Publish immutable observation images, then their manifest, before downloading
  verification state or generating forecasts. Derived failure cannot hold fresh
  processed observations back. A publication error still aborts the run; the old
  manifest stays until images have uploaded successfully.
- Recover after six minutes without a manifest publication. This is a private
  ingestion heartbeat, **not** an artificial change to observation timestamps.
  A healthy ingestion that finds delayed DMI data does not trigger a job storm.
- Atomically claim the recovery attempt using R2 conditional PUT. Inspect the
  latest 20 radar runs on the configured branch, avoid duplicating recent active
  work and retry past old queued records. Preserve the single-writer concurrency
  group and never cancel a running writer. Two-minute inspection/failure and
  five-minute successful-dispatch cooldowns bound retries across cron isolates.
- Bound both GitHub calls at ten seconds, retain redacted error state, and expose
  `radarRecovery` diagnostics in the public operations endpoint. A failed recovery
  task remains independent of push scanning and monitoring scheduling.

Observation age ≤25 minutes, public degraded/503 behavior, historical incidents,
nowcast quality gates, rain thresholds, ledger contents, approved 48-hour cleanup
scope and push eligibility remain unchanged. Genuine upstream failures must still
raise an incident. This addresses known failure modes, not a 100% availability SLA.

## Verification

Regression tests cover early dispatch, the six-minute boundary, source delay,
legacy/invalid/future manifests, queued/pending/waiting/requested/running jobs,
52-minute-old queue records, concurrent ETag claims, cooldown expiry, API errors,
ambiguous network failure and corrupt state. Additional tests guard cache-free
workflow setup, step deadlines, serial writing, strict freshness, early observation
publication and operations diagnostics without hiding an unhealthy radar.

Local verification: 117 TypeScript tests (77 edge, 38 web, 2 shared), 86 worker
tests and 32 monitoring/workflow tests passed, with lint, strict types and build.
Release verification results are recorded in the pull request. A successful local
test or one green production probe does not prove the absence of future outages.
