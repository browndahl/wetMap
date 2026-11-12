# Reliability and performance — 12 November 2026

Scope: investigate every failed Actions run since the 30 October release, repair
reproducible causes, measure the web/API paths, and apply only the owner's approved
48-hour retention for retired derived nowcast WebPs. No paid upgrade, forecast
threshold change or verification-history deletion.

## Incident findings

| Failure | Evidence | Change |
| --- | --- | --- |
| Dependency CI | Runs 42328667324 / 41159342285: updated React hooks lint rejects synchronous effect state cascades in LocationSearch | Key the editor by selected location; derive active query and debounce only valid input. Incorporate PR #24 minor updates with frozen lockfile. |
| R2 upload timeout | Runs 41914396595 / 41928047181: multipart parts of verification-history.json time out; retries consume the eight-minute ingestion budget | Preserve ledger bytes and keys; ordinary ledgers use a single PUT, large transfers at most two threads, bounded connection/read retries; atomic history downloads. |
| Real source delay | Run 41448505058; synthetic 41449301509 also reports radar dependency failure | Keep strict age limits/public 503. Give the dependent performance failure a specific code and group it with the existing radar incident, not a second incident. |
| Opaque performance failures | Runs 41502204897 / 41104162109; November 11 stalled ingestion in 43098390979 | Preserve cache-hit/latency thresholds, expose stable failure causes; remove cache-write latency, hedge slow DMI after 400 ms, coalesce identical cold model requests within an isolate. |
| External runner failure | Runs 43095346498 / 42673045523 have no executed diagnostic steps/logs | Not an application exception. Existing independent Cloudflare heartbeat/recovery remains necessary; no promise that GitHub itself cannot fail. |

The latest main before this work was 71c80ab. Read-only checks found ingestion and
all six operational checks recovered before deploying changes. A green probe does
not retrospectively erase incidents or prove permanent availability.

## Implementation and verification

- Map image sources now reuse two buffers and switch only on loaded image content,
  keeping the old frame visible while a replacement downloads. Opacity changes do
  not expose the pending buffer. Playback waits for image readiness before its
  700 ms dwell timer; removed speculative downloads that accumulated while a
  throttled connection could not keep up. Unrelated renders do not restart loading.
  `wetmap:map-ready` and `wetmap:radar-ready` marks
  distinguish actual readiness from canvas creation.
- `/design` loads lazily; service-worker registration waits for window load, keeping
  precaching off the first-load critical path. Offline caches and push handlers remain.
- Additive gzip budgets enforce entry ≤110,000 bytes, lazy map ≤320,000, map worker
  ≤170,000. Vite's existing >500 KB map chunk warning remains visible and unresolved;
  this is not a claim that the original full build acceptance is complete.
- Local checks: 81 TypeScript tests (28 web, 51 edge, 2 shared), 47 worker tests,
  21 monitoring-script tests; lint, strict types and build passed. GitHub additionally
  verifies .NET, all three containers and security scans before release.

## Measurements

Before: 36 bounded production point requests, six cities × two points × three
repeats, 200 ms between calls. Twelve point-cache MISS: p50 1129 ms / p95 2181 ms;
24 HIT: p50 34 ms / p95 153 ms. Underlying model MISS, provider timing and R2 writes
matter; a later warmer cache is not evidence of an equivalent cold-path speedup.

Three cold Chrome mobile contexts (390×844, 1.6 Mbps down, 150 ms latency, 4× CPU):
status shell 1060–1580 ms, LCP 1044–1568 ms, CLS 0.013–0.023; desktop shell 189–336 ms.
The original shell selector also matches loading/error copy, so it is **not** proof
of a completed weather answer. The revised measurement separately waits for a
populated rain summary and the radar-ready mark. Staging exposed an unbounded
prefetch backlog: map-ready took 20.7 s on a throttled mobile run and radar never
became ready within the 45 s deadline; that finding prompted the playback fix.
These are small diagnostic samples, not field p95, Lighthouse or physical iPhone
acceptance. Cross-origin ResourceTiming sizes can be absent without TAO.

Post-release measurements and workflow evidence are recorded after deployment.

## Storage and owner-approved retention

Read-only account-wide R2 analytics, Nov 1–12 19:00 UTC: 14,138 ListObjects,
62,483 PutObject, 1,695 CompleteMultipart, 1,704 CreateMultipart, 11,889 UploadPart,
142,316 GetObject and 20,616 HeadObject operations. Recent maximum payload
10,416,575,003 bytes, 56,951 objects (preview empty). Workers Nov 11: 2,049 requests,
one error. An instantaneous 10.42 GB snapshot is not GB-month billing or a spend cap.

Owner explicitly approved **only derived nowcast images older than 48 hours**.
Cleanup is dry-run by default, exact WebP filename allowlist, valid lead/timestamp,
both upload and forecast-valid time older than 48h, active manifest protected and
re-read per 500-object batch, explicit deletion budget and confirmed-delete report.
Missing manifest, provider errors and ambiguous deletion responses fail closed.
Nothing under frames/, histories, verification cubes, model/binary/push data or
active manifests is eligible. No broad nowcast/ lifecycle is installed.

After reviewed initial dry-run/application, NOWCAST_RETENTION_ENABLED enables a
once-daily sweep following successful ingestion, tracked by one maintenance object.
To stop future cleanup set the variable false. Deleted derived images cannot be
restored by reverting code; history and radar observations are never cleanup targets.

## Remaining limits

Free GitHub schedules/runner availability, DMI publication latency and external map
services have no application-controlled SLA. Forecast V6, physical iPhone/Safari,
real push timing and the independent full acceptance programme are not completed
by this reliability sprint. Quality gates and public data-age warnings remain honest.
