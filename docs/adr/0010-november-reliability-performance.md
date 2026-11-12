# ADR 0010: November reliability and measured performance fixes

Status: implementation approved by owner on 12 November 2026.

Scope: resolve the recurring Dependabot lint failures without disabling rules;
bound R2 transport retries/concurrency after multipart history-upload timeouts;
remove cache-persistence latency from response paths and coalesce concurrent cold
requests; improve map source reuse/loading and build budgets. Keep all forecast
values, verification gates and data-age limits unchanged. Prefer direct DMI with a
bounded initial head start and labelled model fallback; late direct responses may
refresh the cache in the existing background path.

Baseline: current main is 71c80ab (30 October). Since then: two dependency CI
failures from synchronous setState effects, two radar timeouts uploading private
verification JSON, one source-delay radar failure, and six synthetic failures,
including two runs with no completed runner/logs. The latter are external execution
failures, not evidence of an application exception.

Before changes, 36 bounded API samples: 12 point-cache MISS p50 1129 ms / p95
2181 ms; 24 HIT p50 34 ms / p95 153 ms. Three cold Chrome mobile simulations
(390x844, 1.6 Mbps, 150 ms latency, 4x CPU) showed status shell 1060–1580 ms, LCP
1044–1568 ms, CLS 0.013–0.023. Canvas creation is not proof of a rendered map;
add local performance marks for meaningful map/radar readiness. These small samples
are diagnostic measurements, not a production field p95 or real-device acceptance.

Work in a dedicated branch/PR; tests first for changed behavior, full CI/security,
staging and read-only production checks. Retain evidence and before/after results
in docs. No paid service, broad production load test or history alteration.

Retention was explicitly approved by the owner: only derived nowcast WebPs older
than 48 hours. Measured R2 payload reached 10.42 GB. Use an exact-key allowlist,
both upload/valid-time age checks, a deletion budget and active-manifest protection
rechecked per batch. Review a dry-run before the first application, then enable
once-daily cleanup after a successful ingestion. Do not apply a broad nowcast/
lifecycle: it would include private histories and cannot protect active images
during an outage. Preserve observations, verification/gauge histories, binary
grids, manifests and subscription data. A storage snapshot is not GB-month billing
or a spend cap.

Rollback: revert the application/transport changes, preserve existing operational
state and histories; do not suppress failures or weaken thresholds to turn CI green.
