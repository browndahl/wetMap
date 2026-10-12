# Reliability and observability

Initial SLOs over a rolling 28 days:

- Public shell availability: 99.9% successful navigation responses.
- Dynamic API availability: 99.5% non-5xx, excluding invalid input.
- Cached API p95 latency: <300 ms; uncached forecast p95: <2 s.
- Radar freshness: 99% of time latest observation is <25 minutes old; DMI normally publishes the composite 10–20 minutes after observation.
- Worker success: 99% of scheduled runs; alert after 3 consecutive failures.
- Verification completeness: after the 65-minute warm-up, at least 95% of eligible +5 to +60 minute forecast/observation pairs are scored.
- Adaptive safety: never select persistence for a lead time with fewer than 12 optical-flow samples, and only select it when mean optical-flow CSI skill is at most −0.02 versus persistence.

SLIs are emitted as request duration/status, DMI dependency duration/status, manifest newest-observation age, and worker completion/failure counters. Forecast and precipitation responses expose `Server-Timing` entries for edge cache, R2, DMI, Open-Meteo and total duration, plus `X-WetMap-Provider` and `X-WetMap-Fallback` provenance headers. `/api/v1/radar/nowcast/quality` additionally reports precision, recall, CSI, dBZ MAE and skill over persistence by lead time and 10/20/35 dBZ threshold. Its separate `groundGauge` section compares radar against time-aligned raw DMI rain gauges; station sparsity and raw-data quality must remain visible when interpreting it. Send OTLP to Grafana Cloud Free or keep the local debug exporter. Configure Sentry only after confirming the current dashboard quota. A GitHub scheduled synthetic check calls Pages, `/health/live`, and validates manifest freshness every 15 minutes.

RTO: 30 minutes for frontend/API rollback; 60 minutes for worker recovery. RPO: one radar cycle (5 minutes); there is no user database. R2 objects and source-controlled IaC are the recovery source. Restore testing is a manifest re-upload to staging and a frame hash verification each quarter.
