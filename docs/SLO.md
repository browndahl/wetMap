# Reliability and observability

Initial SLOs over a rolling 28 days:

- Public shell availability: 99.9% successful navigation responses.
- Dynamic API availability: 99.5% non-5xx, excluding invalid input.
- Cached API p95 latency: <300 ms; uncached forecast p95: <2 s.
- Radar freshness: 99% of time latest observation is <15 minutes old.
- Worker success: 99% of scheduled runs; alert after 3 consecutive failures.

SLIs are emitted as request duration/status, DMI dependency duration/status, manifest newest-observation age, and worker completion/failure counters. Send OTLP to Grafana Cloud Free or keep the local debug exporter. Configure Sentry only after confirming the current dashboard quota. A GitHub scheduled synthetic check calls Pages, `/health/live`, and validates manifest freshness every 15 minutes.

RTO: 30 minutes for frontend/API rollback; 60 minutes for worker recovery. RPO: one radar cycle (5 minutes); there is no user database. R2 objects and source-controlled IaC are the recovery source. Restore testing is a manifest re-upload to staging and a frame hash verification each quarter.
