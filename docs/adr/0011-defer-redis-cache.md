# ADR 0011: Keep edge/R2 caching; defer Redis pending measured need

Date: 2026-11-12. Decision for this audit sprint: **do not add Redis**.

## Evidence and scope

The owner asked whether Redis makes sense while approving a precision audit. The
owner's free-only requirement remains. Today's 36-request diagnostic after release
890d7a6 had point-cache HIT p95 83 ms and MISS p95 699 ms. The deliberately repeated
coordinates are not a production traffic-weighted cache-hit ratio or field p95.
No Redis account, database, credential, paid plan or additional cloud archive is
created by this decision.

## Existing design

- TanStack Query and the service worker cache browser responses/assets.
- The Worker Cache API stores short-lived point/model responses at each serving
  data centre. Contents are **not** automatically replicated across data centres;
  cache.put is not compatible with tiered caching. [Cloudflare Cache API](https://developers.cloudflare.com/workers/runtime-apis/cache/), checked 12 November 2026.
- Cold model operations coalesce within an isolate, not across all regions or
  isolates. This is not proof of the 500-concurrent-global-cold-request acceptance.
- R2 provides shared last-known-good model responses and authoritative radar assets.
  Different data centres can restore useful persisted model responses without a
  new DMI request, while fresh point-cache entries avoid repeated radar byte reads.

## Why defer

Redis would introduce another network round trip on paths that use it, another
timeout/failure mode, access management, invalidation rules and a quota to monitor.
It does not improve forecast physics, make DMI publish earlier,
fix verification sampling, or remove the browser's map-library/tile download cost.
It is not yet demonstrated that the new layer would improve total latency or
upstream request counts versus the current edge/R2 architecture.

Redis could later be an L2 for small model results or coordination, **not** a new
store for radar image binaries. Keep L1 edge hits independent of it and fail open
to current safe paths when the cache is unavailable. Serving older cached radar
for longer to manufacture more hits is not an acceptable optimisation.

Free Redis exists, but is bounded: Upstash currently advertises 250 MB, 500,000
commands/month and 10 GB monthly bandwidth; adding a card upgrades to pay-as-you-go
according to its FAQ. [Official pricing](https://upstash.com/pricing/redis), checked
12 November 2026. No such upgrade or registration is authorised here.

## Revisit only after

1. Real traffic shows repeated expensive hot-key misses/duplicate DMI calls across
   isolates/data centres, not simply many legitimate unique map clicks.
2. Compare total response latency, upstream calls, R2 operations and failure behaviour
   for edge/R2 versus edge/Redis/R2 on a bounded representative trace. Include cold
   regions and Redis failure; do not compare an edge miss with a prewarmed Redis hit.
3. Meter the complete command/bandwidth budget, including GET/SET/TTL/coordination,
   maintenance and monitoring, with free-tier headroom and no automatic paid upgrade.
4. Record the measured trade-off in a new ADR before enabling any service.

Meanwhile prioritise verification integrity and the slow first map load. No new
cache technology is required to run the local precision audit.
