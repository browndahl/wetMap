# Operations runbooks

Master safety boundary (17 November 2026): procedures are not blanket authority
to mutate production. Account/cost/privacy/retention changes and any radar or
verification-history rewrite/deletion require explicit owner approval. Prefer
read-only diagnosis and reviewed code reverts; never inject faults into production.

## 0. Local Compose startup

Start Docker Desktop and wait until its engine reports ready before running `docker compose up --build`. If Compose reports that `~/.docker/run/docker.sock` is missing, Docker Desktop is installed but its daemon is not running; launch Docker Desktop and confirm with `docker info` before retrying. On a healthy first start, `worker` exits with status 0 after producing the radar manifest, while `api`, `web`, and `otel-collector` remain running. Open `http://localhost:8080` and use `docker compose down` when finished.

## 1. Radar stale (>25 minutes)

Check the Cloudflare `wetmap-api` cron logs first, then the latest worker workflow, DMI status, 429/retry logs, R2 manifest `generatedAt`, and frame object HEAD. The Cloudflare cron scans alerts every minute. Radar recovery starts after six minutes without a publication (legacy manifests without `generatedAt` use the 20-minute observation threshold), before the unchanged 25-minute observation freshness gate. A recent publication with old observations is a source delay, not a reason to dispatch every minute.

`/api/v1/operations/status` exposes `radarRecovery`: the last bounded decision, check time, dispatched time, active run ID or dispatch error. When recovery is due, the scheduler atomically claims an R2 ETag before inspecting the latest 20 workflow runs on the configured branch. Recent queued/pending/requested/waiting runs suppress duplicates for five minutes; in-progress runs for ten minutes from **creation**, not actual runner start. Older records cannot block recovery indefinitely. Queue inspections/failures have a two-minute cooldown and successful dispatches a five-minute cooldown; each GitHub request has a ten-second deadline. Nothing cancels an active writer; the workflow's serial concurrency lock remains. Inspect actual job `startedAt` separately from run `createdAt` when measuring runner queue delay.

Verify the `GITHUB_DISPATCH_TOKEN` Worker secret (Actions read/write for inspection/dispatch) if no dispatch appears. Radar Python setup has no Actions dependency-cache restore/save, and setup, pip installation, processing and validation have explicit step deadlines inside the eight-minute job cap. Fresh immutable radar images and their manifest publish **before** derived nowcast/verification work; publication failure still fails the job. The synthetic workflow checks independently and does not rerun ingestion. Keep serving the last good manifest with a stale banner. Rerun one workflow only; do not fan out retries against DMI. Roll back worker if schema validation began failing after a deploy. GitHub runner outages and DMI publication delays remain external dependencies, not an application-controlled availability guarantee.

## 1a. Monitoring heartbeat and grouped incidents

Start with `/api/v1/operations/status`: `scheduler.checkedAt` must be within 10
minutes, `probe.receivedAt` within 35, and radar observation age within 25. Public
503 means unhealthy, even if a repeated diagnostic's Actions execution is green.
Check `checks`, `activeIncident`, `radar` and scheduler `dispatchError`. The
Cloudflare watchdog requests a synthetic run after 15 minutes without a completed
probe, capped at one dispatch per 15 minutes. The independent GitHub schedule is
fallback, not the sole clock. Dispatch manually at most once after checking queues.

`source-delayed` means recent publication still contains old observations, not a
proven provider-wide outage. `ingestion-stalled` means publication is also old.
Only the exact active source-delay incident may own duplicate radar-job emails;
missing/stale monitoring restores strict workflow failure. First/changed incidents
fail the notification job; repeats warn and retain DEGRADED in the summary.

Missing or mismatched `MONITOR_REPORT_TOKEN` in Cloudflare/Actions fails loudly.
Rotate the same random secret in both stores without printing it. Never inject
fake health reports into production. Synthetic probes do not rerun radar ingestion.

Rollback: disable `OPERATIONS_MONITOR_ENABLED`, restore the previous strict
synthetic workflow and deploy; keep radar recovery/push enabled. Two bounded
`monitoring/*.json` metadata objects are separate from radar/verification history.

## 2. DMI unavailable or rate-limiting

Source admission now rejects empty/malformed catalogues, invalid required fields
and timestamps >2 minutes in the future **before** download/publication. Preserve
the last-good state, inspect the static rejection, and compare source UTC with
the ingestion host's clock. Do not bypass the guard or fabricate/retimestamp a
frame. Static source-delay ownership reasons appear as
`radar.source-delay-handoff`; `owned` is notification ownership, not recovery.

For R2 timeouts, distinguish transport from source freshness: history bytes must
not be truncated to meet a workflow deadline. Transport uses bounded retries and
at most two multipart threads; ordinary ledgers use a single PUT. Synthetic
`radar-unavailable`, `cache-no-hit`, `cache-slow`, `telemetry-invalid` codes identify
performance causes; a radar-dependent failure stays unhealthy even when grouped
into the same incident signature.

Confirm dependency status and `Retry-After`. Stop manual polling, allow circuit breaker/backoff, and keep cached forecast/radar. If outage exceeds an hour, post status copy in the UI; never synthesize observations.

## 3. Map unavailable

Verify OpenFreeMap status/network/CSP. Radar controls and forecast should remain usable, but geographic context is degraded. At a sustained incident, review a free alternative style; self-hosting or new capacity needs explicit cost/operational approval. Preserve OSM attribution.

## 4. API error/latency spike

Separate cached R2 reads from DMI forecast misses using traces. Validate Workers daily usage/CPU errors. Increase cache efficiency first. Roll back the latest Worker version; if free quota is exhausted, static Pages shell and cached frames remain the fallback.

## 5. Corrupt/misaligned frame

Compare SHA-256, inspect the local file and projection/corners, and reproduce in a synthetic fixture. Do not overwrite immutable objects or silently remove history. Propose a specific manifest repair to the owner before a production data change; reviewed code reverts remain the normal deployment rollback.

## 6. Nowcast precision degradation

Open `/api/v1/radar/nowcast/quality` and first confirm `algorithmVersion`; never combine cohorts from `byAlgorithmVersion`. Separate the affected lead time and dBZ threshold before tuning. Do not infer +60-minute quality from +10-minute results. Compare `criticalSuccessIndex` with `meanPersistenceCriticalSuccessIndex` and inspect `byForecastMethod`; a negative optical-flow skill of at most −0.02 with 12 or more optical-flow samples should select persistence on the next generated forecast. Future push frames must remain ineligible until they have at least 12 validations, CSI ≥ 0.20, non-negative persistence skill and confidence ≥ 0.55. If no horizons beyond +10 appear after 65 minutes, inspect `verification-state.json`, the 16 ring-buffer cube objects, checksum failures and workflow logs. Treat `groundGauge` separately and compare its 5/10/15/20 dBZ threshold and 1/3/5-pixel spatial profiles within a single `comparisonVersion`; DMI MetObs is raw and sparse, so disagreement is evidence to investigate—not proof that the entire radar field is wrong. Roll back if the public report schema, point forecast and map frame no longer agree.

Inspect `verificationBatch` for retained-window completeness: errors/deferred work
are not successful coverage. Retry failed pairs without resetting or replacing
history. Downloads and verification are bounded; fresh radar must still publish.
For `comparisonAudit`, require `shared-coverage-v2`, shadow-only mode, zero failed
pairs, and both forecast/promotion flags false. Compare within algorithm and lead,
inspect common/observed coverage, and never substitute this cohort for legacy
promotion or alert evidence. A small/empty v2 cohort is normal during rollout;
do not backfill by replacing historical scores. See ADR 0012 and the dated v2 report.

## 7. Quota exhaustion or CPU/storage budget risk

Start with [FREE_TIER.md](FREE_TIER.md), dated provider analytics and official
allowances, not the old storage estimate. Read account aggregates only; don't
download subscriptions or issue bursts against a failing upstream. Distinguish:

- **Workers requests/day:** Free cap resets 00:00 UTC. If reached, public API and
  cron/push may be unavailable until reset; static Pages or a cached view isn't
  proof of live weather. Keep stale/offline copy honest. Don't automatically
  upgrade, fan out requests across accounts or disable safeguards.
- **Workers CPU:** inspect actual event type/outcome and plan before inferring
  compliance. A successful call can still exceed the documented 10 ms Free
  allowance through burst flexibility. The first post-optimization sample is
  still above it. Profile local synthetic work and compare real matched windows;
  no arbitrary retry/timeout or gate relaxation as a “CPU fix”.
- **R2:** storage/operations above included amounts can cost money; there is no
  hard spending cap. Daily peak bytes aren't GB-month billing. An allowance
  warning requires owner review of nonessential writes/capacity, not a paid
  upgrade. Existing derived-WebP cleanup is narrowly approved; no blanket
  history/cube/subscription deletion or lifecycle change.
- **Actions:** confirm public repository and standard runner. Distinguish failed
  work, runner queue and upstream stale data. No recursive redispatch/retry storm;
  use the existing bounded recovery guard. Artifact/cache billing isn't unlimited
  merely because execution is free.

Escalate missing telemetry/plan permission explicitly. Current account-plan API
403 is unresolved, not permission to broaden scopes/copy credentials. No live
quota-exhaustion drill is safe on shared staging/prod account. Disabling cron,
new retention or changing account/security/billing policy needs owner direction.

## 8. Point binary/pointer race or storage mismatch

Writer uses the actual inactive one of two slots and publishes schema-v2 metadata
only after a successful version-returning binary PUT. Reader binds every range
to `dataEtag` and rejects a different/missing version. A rejected read uses the
existing labelled model fallback; it must not become “dry radar”. Inspect static
read-failure logs and normal next publication, not private point data in public
logs. Test partial reads/publication failures locally with the regression fixtures.

For rollout/rollback keep writer-first order (ADR 0014). Never remove reader
version checks to hide a mismatch. Independent map/model caches still have their
own lifetimes; don't claim a transaction across all weather assets. Revert a
specific reviewed commit through the exact-SHA CI/security deploy gate (ADR 0015),
not an untested force-push or raw object rewrite.

## Rollback and recovery

Retired nowcast WebPs: run **Retired nowcast image cleanup** with apply=false;
inspect/download the retention-report artifact before setting apply=true and an
explicit max_delete. Only exact derived-image keys with both upload and valid times
older than 48h are eligible; active manifest is refreshed before every batch.
NOWCAST_RETENTION_ENABLED=true enables once-per-day cleanup after good ingestion.
Set it false to stop future cleanup. No broad R2 nowcast/ lifecycle is safe: that
prefix also contains private history. Deletion is permanent; rollback does not
restore the retired derived images. Radar observations and verification history
are not targets. See [November evidence](NOVEMBER_RELIABILITY.md).

Pages/Worker: reviewed revert of the specific commit through the exact-SHA CI/security gate. Worker ingestion: check active runs before at most one manual recovery; idempotency skips existing observations. Any R2 pointer/manifest restore must be explicitly scoped and owner-approved; never overwrite verification/radar history as a generic rollback. Target RTO/RPO are in `SLO.md`. There is no user database; any future database/backup adoption requires architecture, privacy and cost review.

## Local and Grafana telemetry

Compose uses `infra/observability/otel-collector.yaml`, which emits received telemetry to the collector debug exporter and requires no cloud credentials. For Grafana Cloud, mount `otel-collector.grafana.yaml` instead and provide `GRAFANA_OTLP_ENDPOINT` plus the complete `GRAFANA_OTLP_AUTH` authorization value through the deployment secret store.

That is an optional configuration reference, not evidence of an active hosted
dashboard. No new Grafana/Sentry/service is authorised here; verify free/no-card
terms and privacy/budget before any adoption. Existing Worker logs, analytics,
public status and Actions summaries remain the current operational tools.
