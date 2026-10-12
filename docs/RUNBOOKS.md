# Operations runbooks

## 0. Local Compose startup

Start Docker Desktop and wait until its engine reports ready before running `docker compose up --build`. If Compose reports that `~/.docker/run/docker.sock` is missing, Docker Desktop is installed but its daemon is not running; launch Docker Desktop and confirm with `docker info` before retrying. On a healthy first start, `worker` exits with status 0 after producing the radar manifest, while `api`, `web`, and `otel-collector` remain running. Open `http://localhost:8080` and use `docker compose down` when finished.

## 1. Radar stale (>25 minutes)

Check the Cloudflare `wetmap-api` cron logs first, then the latest worker workflow, DMI status, 429/retry logs, R2 manifest `generatedAt`, and frame object HEAD. The Cloudflare cron checks every five minutes and dispatches `radar.yml` when the newest observation is over 20 minutes old; verify the `GITHUB_DISPATCH_TOKEN` Worker secret if no dispatch appears. The synthetic workflow also calls the reusable radar workflow as a recovery path. Keep serving the last good manifest with a stale banner. Rerun one workflow only; do not fan out retries against DMI. Roll back worker if schema validation began failing after a deploy.

## 2. DMI unavailable or rate-limiting

Confirm dependency status and `Retry-After`. Stop manual polling, allow circuit breaker/backoff, and keep cached forecast/radar. If outage exceeds an hour, post status copy in the UI; never synthesize observations.

## 3. Map unavailable

Verify OpenFreeMap status/network/CSP. Radar controls and forecast should remain usable, but geographic context is degraded. At a sustained incident, switch a reviewed style URL or self-host vector tiles; preserve OSM attribution.

## 4. API error/latency spike

Separate cached R2 reads from DMI forecast misses using traces. Validate Workers daily usage/CPU errors. Increase cache efficiency first. Roll back the latest Worker version; if free quota is exhausted, static Pages shell and cached frames remain the fallback.

## 5. Corrupt/misaligned frame

Disable the bad manifest entry (do not overwrite its immutable object), compare SHA-256, run `wetmap-worker --inspect file.h5`, and confirm projection/corners. Republish a new manifest pointing at the last good frames. Add the case to the synthetic fixture.

## 6. Nowcast precision degradation

Open `/api/v1/radar/nowcast/quality` and first confirm `algorithmVersion`; never combine cohorts from `byAlgorithmVersion`. Separate the affected lead time and dBZ threshold before tuning. Do not infer +60-minute quality from +10-minute results. Compare `criticalSuccessIndex` with `meanPersistenceCriticalSuccessIndex` and inspect `byForecastMethod`; a negative optical-flow skill of at most −0.02 with 12 or more optical-flow samples should select persistence on the next generated forecast. Future push frames must remain ineligible until they have at least 12 validations, CSI ≥ 0.20, non-negative persistence skill and confidence ≥ 0.55. If no horizons beyond +10 appear after 65 minutes, inspect `verification-state.json`, the 16 ring-buffer cube objects, checksum failures and workflow logs. Treat `groundGauge` separately and compare its 5/10/15/20 dBZ threshold and 1/3/5-pixel spatial profiles within a single `comparisonVersion`; DMI MetObs is raw and sparse, so disagreement is evidence to investigate—not proof that the entire radar field is wrong. Roll back if the public report schema, point forecast and map frame no longer agree.

## Rollback and recovery

Pages/Worker: redeploy the prior Git SHA. Worker: revert and dispatch once; idempotency skips existing objects. R2: restore `frames.json` from the previous workflow log/staging copy. Target RTO/RPO are in `SLO.md`. No v1 database exists; if Phase 2 adds one, automated daily backups plus a quarterly isolated restore test become a release gate.

## Local and Grafana telemetry

Compose uses `infra/observability/otel-collector.yaml`, which emits received telemetry to the collector debug exporter and requires no cloud credentials. For Grafana Cloud, mount `otel-collector.grafana.yaml` instead and provide `GRAFANA_OTLP_ENDPOINT` plus the complete `GRAFANA_OTLP_AUTH` authorization value through the deployment secret store.
