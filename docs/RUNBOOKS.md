# Operations runbooks

## 0. Local Compose startup

Start Docker Desktop and wait until its engine reports ready before running `docker compose up --build`. If Compose reports that `~/.docker/run/docker.sock` is missing, Docker Desktop is installed but its daemon is not running; launch Docker Desktop and confirm with `docker info` before retrying. On a healthy first start, `worker` exits with status 0 after producing the radar manifest, while `api`, `web`, and `otel-collector` remain running. Open `http://localhost:8080` and use `docker compose down` when finished.

## 1. Radar stale (>25 minutes)

Check the latest worker workflow, DMI status, 429/retry logs, R2 manifest `generatedAt`, then frame object HEAD. Keep serving the last good manifest with a stale banner. Rerun one workflow only; do not fan out retries against DMI. Roll back worker if schema validation began failing after a deploy.

## 2. DMI unavailable or rate-limiting

Confirm dependency status and `Retry-After`. Stop manual polling, allow circuit breaker/backoff, and keep cached forecast/radar. If outage exceeds an hour, post status copy in the UI; never synthesize observations.

## 3. Map unavailable

Verify OpenFreeMap status/network/CSP. Radar controls and forecast should remain usable, but geographic context is degraded. At a sustained incident, switch a reviewed style URL or self-host vector tiles; preserve OSM attribution.

## 4. API error/latency spike

Separate cached R2 reads from DMI forecast misses using traces. Validate Workers daily usage/CPU errors. Increase cache efficiency first. Roll back the latest Worker version; if free quota is exhausted, static Pages shell and cached frames remain the fallback.

## 5. Corrupt/misaligned frame

Disable the bad manifest entry (do not overwrite its immutable object), compare SHA-256, run `wetmap-worker --inspect file.h5`, and confirm projection/corners. Republish a new manifest pointing at the last good frames. Add the case to the synthetic fixture.

## Rollback and recovery

Pages/Worker: redeploy the prior Git SHA. Worker: revert and dispatch once; idempotency skips existing objects. R2: restore `frames.json` from the previous workflow log/staging copy. Target RTO/RPO are in `SLO.md`. No v1 database exists; if Phase 2 adds one, automated daily backups plus a quarterly isolated restore test become a release gate.

## Local and Grafana telemetry

Compose uses `infra/observability/otel-collector.yaml`, which emits received telemetry to the collector debug exporter and requires no cloud credentials. For Grafana Cloud, mount `otel-collector.grafana.yaml` instead and provide `GRAFANA_OTLP_ENDPOINT` plus the complete `GRAFANA_OTLP_AUTH` authorization value through the deployment secret store.
