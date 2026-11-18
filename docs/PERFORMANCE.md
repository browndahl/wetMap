# Master performance evidence — 17 November 2026

No full performance acceptance is claimed. Correctness/stability and free-only
constraints take priority. Historical end-user measurements remain in
NOVEMBER_RELIABILITY.md; they are not silently compared with new warm samples.

## Measured bounded push-risk work

Motivation: seven-day provider analytics show cron CPU p99 41.854–52.469 ms,
above the documented Free 10 ms allowance. Actual subscription/plan could not be
confirmed by the existing token (read-only subscriptions request returned 403).
Do not infer a paid plan, upgrade it, or claim CPU compliance from this test.

Reproduction and comparison: same local Node/Vitest, 64×43 synthetic risk grid,
13 dry eligible frames, 40 locations per scan, twelve newly allocated manifest
batches. Mocked/no network, no encryption or provider delivery. Encodings are
constructed outside the measured lookup interval. Each batch has new frame
objects, so the improved version still pays its first-decode cost per scan.

| Metric | Before | After, isolated same test command |
| --- | ---: | ---: |
| Native base64 decodes per 40-location scan | 520 | 13 |
| Decodes of wholly ineligible frames | 13 | 0 |
| Lookup-only p50 per scan | 38.084 ms | 1.034 ms |
| Lookup-only p95 (largest of 12) | 39.006 ms | 1.274 ms |

The measured change removes repeated decoding of identical weather grids within
a scan. A weakly owned, weather-only scratch cache holds at most 13 entries and
128 KiB per manifest, checks changed encoded contents, and holds no coordinates,
subscriptions or personal history. Large frames aren't retained. No extra cloud
requests/storage, algorithm/gate/expiry change or lower subscription scan cap.

Timing is diagnostic, **not a flaky CI speed assertion**, Cloudflare CPU result,
full scan/encryption latency, real subscription load or a field p95. Unit assertions
enforce exact work counts, invalidation and cache budgets. Must observe actual
post-release cron CPU before claiming platform-budget improvement.

Command: `pnpm --filter @wetmap/edge exec vitest run src/pushCpu.test.ts --reporter=dot`.
Initial deterministic work-count tests failed; the original implementation made
520 decodes instead of 13 and decoded ineligible frames. A test-source octal escape
was corrected before the actual baseline run; that compilation failure is not
counted as a product defect or performance evidence.

## First post-release provider CPU sample — not compliance

Read-only account analytics for `wetmap-api`, 22:38–22:44 UTC, after #45's
22:37:01 deployment. Six successful cron invocations: CPU p50 **12.293 ms**,
p95/p99 **17.977 ms**; seven successful fetches: p50 **3.437 ms**, p95/p99
**28.708 ms**, zero reported errors. These are aggregate provider CPU, not local
lookup timings. Workload/sample differs from seven complete historical days;
don't subtract percentiles or claim causally matched before/after field improvement.

Importantly, this small sample still exceeds the documented Free 10 ms allowance.
It does not resolve plan/CPU compliance or validate real push delivery. The
bounded decoder removes proven work; other CPU contributors remain to profile.

## Read-only point microprobes

- 21:51 UTC: MISS 630 ms / HIT 77 ms, six operations checks passed.
- 22:11 UTC after version-bound reader: MISS 490 ms / HIT 76 ms, six passed.

These are separate two-request normal diagnostic sequences, not a load test,
matched cold-cache experiment or p95 proof of an improvement. No API threshold
was relaxed. Conditional range reads add no request to the point lookup path.

## UI/clock inspection, not device performance acceptance

Six UI states: 1440×900, 390×844 and 320×568, Danish and English, installed system
Chrome headless. Normal production reads only: **24 API requests, 86 total**;
budget 80/700, no mutations/GPS/push permission. Temperature visible, one map
canvas, zero page exceptions, no horizontal document overflow. Phone screenshot
visually inspected. Dark-only UI; a light-theme matrix is not implemented.

Bundled Playwright's expected browser executable was absent. Reused installed
Chrome instead; no dependency/browser download. No claim about WebKit/Firefox,
physical iPhone, screen readers, throttled CWV, INP, 50 fps or 30-minute memory.

One extra normal clock diagnostic at 22:19 UTC found browser/server drift **100 ms**.
This does not pass the acceptance test for a deliberately wrong device clock ±10 min.
Screenshots remain local temporary public-weather/default-Aarhus captures, not
the owner's location. No private audit cubes/inputs were used for UI captures.

## 18 November follow-up — CPU costs isolated locally

Matched Node 22 runs, eight warm-up and 40 measured batches per case. Times are
process CPU (user + system), **not** latency, full cron/fetch CPU or Cloudflare
quota evidence. The point-grid mock is an in-memory R2 response substitute;
the separate native-runtime smoke test below checks semantics, not performance.

| Synthetic batch | Before p50 / p95 | After p50 / p95 |
| --- | ---: | ---: |
| 40 dry push-grid lookups, 13 frames | 1.018 / 1.832 ms | 0.121 / 0.837 ms |
| 40 push payloads, half observations and half forecasts | 0.879 / 0.955 ms | 0.048 / 0.050 ms |
| 20 point-grid lookups, three ranges each | 0.940 / 3.606 ms | 0.212 / 1.223 ms |

The decoder copies the same bytes without allocating the per-character iterable
used by `Uint8Array.from`. Push formats forecasts only, reusing at most two
locale formatters and no subscriber data. Point sampling reads the R2 body's
native `arrayBuffer()` instead of wrapping it in a synthetic `Response`. Width,
ETag and exact byte-length guards remain. The benchmark checks unchanged row
count and byte totals. No cloud request, polling, dependency or storage change.

Reproduce with `WETMAP_CPU_BENCH=1 pnpm --filter @wetmap/edge exec vitest run src/edgeCpu.test.ts --reporter=dot`.
This opt-in diagnostic has no CI speed assertion. Regression tests verify native
reader use, range truncation, no formatter for observation alerts, unchanged
expiry and the repeated Copenhagen DST hour in Danish and English. The reader
and observation-work tests fail on the old implementation and pass after it.

The dry-run bundle also passed three local Miniflare route checks using an
ephemeral R2 emulator and mocked DMI. An exact ETag and complete data returned
radar-based rain intervals; a stale ETag or short range returned labelled model
data instead. No Cloudflare deployment, private data or external requests.

Not yet verified: field p95/p99, Free CPU compliance and actual push delivery.
Repeat Cloudflare analytics only after an approved deployment, using comparable
time windows and sample counts; aggregate CPU still cannot prove route causality.
