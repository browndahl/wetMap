# WetMap programme progress

## Governing master checkpoint — 17 November 2026

Owner adopted [`WETMAP_MASTER_PROMPT.md`](WETMAP_MASTER_PROMPT.md), copied exactly
from the supplied document (SHA-256
`9bb74ea151b2f14f8dc866cb71e0737a67f8c6d6623ded8b87921e50ffa977e5`).
It supersedes the earlier build/review/acceptance inputs and phase numbering:
**correctness → stability → forecast accuracy → location/UX → performance**.
Older sections below are historical, not the current order or acceptance verdict.
The owner explicitly requested uninterrupted work, waiving routine phase pauses,
not the stop-and-ask boundaries for costs, history, gates or stored personal data.

Phase: **partial master baseline plus confirmed-defect implementation**.
No full Phase 0/independent acceptance or all-phase completion is claimed.

### Changed / evidence

- [#39](https://github.com/browndahl/wetMap/pull/39): empty/malformed radar catalogue
  rejected before replacing last-good manifest; 12 initial failing cases, 13 pass.
- [#40](https://github.com/browndahl/wetMap/pull/40): static quality-validator
  failure causes and public-report hash; no raw stderr. Historical cause unknown.
- [#41](https://github.com/browndahl/wetMap/pull/41) and
  [#42](https://github.com/browndahl/wetMap/pull/42): actual inactive point binary
  slot, publish ETag after successful binary upload, conditional/version-checked
  reads. Writer-first normal publication proved before strict reader rollout.
- [#43](https://github.com/browndahl/wetMap/pull/43): exact-main-commit CI+Security
  prerequisite, serialized/pinned deploy and superseded-release guard. First
  normal release proves checks completed before staging/production.
- [#44](https://github.com/browndahl/wetMap/pull/44): actual 8 KiB push body limit,
  JSON object/runtime field types. No real push mutation in tests.
- [#45](https://github.com/browndahl/wetMap/pull/45): bounded weather-only decoded
  scratch cache, 520→13 decodes per synthetic 40-point scan; local lookup-only
  p50 38.084→1.034 ms. Not field latency, real delivery or CPU compliance.
- [#46](https://github.com/browndahl/wetMap/pull/46): safe source-delay ownership
  reasons, same gates/503 health, bounded existing 64 KiB status read.
- [#47](https://github.com/browndahl/wetMap/pull/47): missing/blank required
  coordinates no longer become zero; 10 failing baseline cases, 20 now pass.
- [#48](https://github.com/browndahl/wetMap/pull/48): apply the existing +2-minute future tolerance
  before publication, not only after; three failing baseline cases, five now pass.
  Its PR/normal rollout is tracked in TEST_EVIDENCE.md.
- Fresh deterministic suite: 124 edge + 38 web + 2 shared + 112 worker + 50 script
  tests = **326**, not an end-to-end coverage/acceptance percentage. CI also runs
  portable .NET and container builds plus security. Gzip budgets unchanged/pass;
  existing map chunk warning remains.

### Raw-data and quota findings

Owner separately approved **one** private local snapshot ≤34 reads / 64 MB,
without subscriptions/persondata or raw upload. Actual 22 reads / 10,761,702 bytes,
stable state. Reconstructs **31 published / 43 available pairs, 186 score checks,
zero mismatches, persistence identity 6/6**. C1 remains **BLOCKED** at unchanged
minimum 50, with no independent published-v2/Brier full acceptance. Local v2
oracle is diagnostic only. No second snapshot is implicitly authorised.

Seven-day Cloudflare aggregate usage measured against current official limits.
Peak Worker requests 3,192/day, R2 A/B 7,870/15,194/day. Storage daily peak
10.443 GB on 12/11, 1.497 GB on 16/11 after previously approved cleanup, not
a monthly invoice. Historical cron CPU p99 41.854–52.469 ms; first six post-release
cron calls p50 12.293 / p95 17.977 ms still exceed documented Free 10 ms. Samples
aren't matched; actual plan request 403. **Free-tier compliance unresolved**, no
upgrade/new paid service/hard cost guarantee. No new Redis/KV/monitoring vendor.

### Not done / risks / next step

- Full correctness/quality evidence, held-out V6 and independent acceptance remain.
- Remote load/chaos blocked: staging shares production API/account. No production
  destructive scenario or new quota-consuming archive.
- Main/rulesets/environment protection absent despite workflow release gate.
  Existing app logs contain location fields/raw errors; a scoped future-log
  minimisation change awaits explicit owner approval. No existing logs deleted.
- Physical-device push, WebKit/Firefox, screen readers, wrong-clock/offline/SW
  update, CWV/FPS/long-memory aren't accepted by six Chrome screenshots.
- Historical source delay and original quality rejection not retrospectively
  explained. New diagnostics improve future evidence, not historical certainty.

Quota impact: no new service/request path for validation/decoder fixes; point
writer adds at most one small R2 read/ingestion (~8,640/month at 5 min). Same two
point slots, existing retention/history preserved. Existing public standard CI
runners and bounded release polling; total account artifact/monthly accounting
still not established. Detailed evidence and next safe steps: BASELINE.md,
FINDINGS.md, RCA.md, TEST_EVIDENCE.md, PERFORMANCE.md, FREE_TIER.md, RISKS.md,
MASTER_WORK_PLAN.md and ADRs 0014/0015. Next: close correctness/CPU evidence and
approval/isolation gaps before new product features or forecast promotion.

Normal rollout follow-through: all ten code PRs #39–#48 merged after CI/security.
Last code deploy 44194026781 and radar 44194543306 passed on `72b34d8`.
Documentation PR #49 records this checkpoint and updates quota/input/race runbooks;
historical budget/test-result pages now point to the dated master evidence. No
private handoff/raw snapshot is published and no new approval boundary is waived.

---

The following log records the earlier build-brief programme. Evidence is linked
where it is stored in the repository; historical phase labels aren't master status.

## Phase 0 — Baseline and audit

Status: **approved by owner on 2026-10-22**

### Changed

- Added the two governing inputs to the repository as
  [`WETMAP_BUILD_PROMPT.md`](WETMAP_BUILD_PROMPT.md) and
  [`WETMAP_ACCEPTANCE_TEST.md`](WETMAP_ACCEPTANCE_TEST.md), preserving their order and
  separation of implementation from independent release testing.
- Added the missing canonical system overview in [`SYSTEM_CONTEXT.md`](SYSTEM_CONTEXT.md).
- Added a read-only independent public-quality audit in
  [`.github/scripts/audit_public_quality.py`](../.github/scripts/audit_public_quality.py).
- Added four audit regression tests in
  [`.github/scripts/test_audit_public_quality.py`](../.github/scripts/test_audit_public_quality.py).
- Captured the ranked baseline and explicit evidence limitations in
  [`BASELINE.md`](BASELINE.md).
- Captured production UI evidence under [`evidence/phase-0`](evidence/phase-0).

### Evidence

- Independent audit: 288 public pairs; zero timestamp-alignment errors; zero
  precision/recall/CSI recomputation mismatches at the 0.5 percentage-point criterion.
- Audit tests: `python3 -m unittest discover -s .github/scripts -p 'test_*.py'` —
  12/12 passed, including 5 new independent-audit tests.
- Worker: Ruff passed and pytest passed 28/28.
- TypeScript workspace: `pnpm check` passed lint, strict type checks, 52 tests and all
  builds. Vite's existing >500 KB chunk warning remains an explicit baseline failure.
- Audited release `004e129`: GitHub CI run
  [39670315002](https://github.com/browndahl/wetMap/actions/runs/39670315002) and security
  run [39670314893](https://github.com/browndahl/wetMap/actions/runs/39670314893) passed.
- Production radar/API timing and five Lighthouse mobile runs are recorded in
  `BASELINE.md` with sample sizes and limitations.
- Browser audit covered desktop/mobile and Danish/English. The product has no light
  theme, which is recorded as a gap rather than represented by a fake screenshot.

### Open risks

- Independent MAE, Brier and persistence reconstruction is blocked by the public
  evidence contract; raw/private verification grids were not accessible in this
  session.
- Forecast and persistence categorical metrics do not currently use one shared valid
  coverage mask, so their CSI skill can be based on slightly different edge pixels.
- Pooled CSI and mean per-pair persistence skill use different weighting. The gate is
  mathematically reproducible but the UI juxtaposition is easy to misread.
- Production lacks measurements for exact R2-visible-to-first-client-visible latency,
  alert scan duration and provider-side cache/operation totals.

### Decision gate

No Phase 1/V6 forecast implementation or acceptance run has started. The build brief
requires explicit owner approval of the Phase 0 findings first.

## Phase 1 — Forecast engine V6

Status: **in progress — offline backtest foundation**

### Fixed evaluation protocol

- Added the validated split loader in
  [`apps/worker/src/wetmap_worker/backtest.py`](../apps/worker/src/wetmap_worker/backtest.py)
  and its locked configuration in
  [`apps/worker/backtest/split-v1.json`](../apps/worker/backtest/split-v1.json).
- Recorded the decision in
  [`ADR 0004`](adr/0004-fixed-v6-backtest-split.md): train 25 April–31 July,
  validation 1 August–15 September, immutable test 16 September–21 October 2026.
- The split covers every five-minute lead from +5 through +60 and its loader rejects
  overlap, non-UTC boundaries, missing leads, or a tunable test split.
- Extended `apps/worker/tools/backtest_nowcast.py` from three shadow anchors to all 12
  lead times. It now rejects cross-split source/target pairs, freezes learned gates at
  split boundaries, excludes the test split from calibration, and emits auditable JSON
  containing the split SHA-256, input inventory, skipped-pair reasons and metrics versus
  both persistence and the incumbent.
- Added a small moving-echo replay to the normal worker pytest suite so the full report
  path runs in CI without downloading external data.

### Source inventory and retention finding

- The official DMI composite API was sampled on 22 October 2026. It returned frames
  for every boundary day and historical data beginning 25 April 2026; no composites
  were returned for 24 April or earlier in the sampled 2026 range.
- No processed historical radar frames exist in the local repository. Production R2
  currently expires `frames/` after 48 hours.
- Thirteen public production WebPs totalled 5,832,680 bytes (448,668-byte mean). At
  288 frames/day, unchanged one-year retention projects to about 43.92 GiB. Because
  that can exceed the free storage allowance, no retention change has been made.
- A local lossless resize of the same frames to the harness grid measured 13,560 bytes
  per WebP on average, or about 1.33 GiB/year. Compressed NPZ measured 1.56 GiB/year.
  [`ADR 0005`](adr/0005-compact-backtest-archive.md) records the measurement. Following
  the owner's free-only instruction on 22 October, its cloud-retention proposal is
  deferred. Bounded local event downloads are the next implementation step.

### Open Phase 1 work

- Extend the runner to emit auditable JSON per split, lead, event regime and region.
- Curate and review the event catalogue; snow/sleet remains seasonally unavailable.
- Build bounded local event acquisition and replay within the owner's free-only
  constraint. Additional R2 archival and the 400-day lifecycle remain disabled.
- Measure account-wide R2 usage before considering any future cloud archive. A storage
  projection is not a billing cap, and no new billing cap has been configured.
- This is implementation work, not the independent acceptance run.

### Current evidence

- Worker Ruff: passed.
- Worker pytest: 35/35 passed, including six split-safety tests and the all-lead CI
  replay.
- Repository Python audit/synthetic tests: 12/12 passed.
- A 13-frame real production smoke replay completed successfully and emitted the
  expected split hash, frame inventory and non-empty +5 through +50 test metrics. This
  smoke sample is plumbing evidence only, not forecast-quality evidence.

## Phone sprint 1 — owner-directed layout and performance work

Status: **implemented; automated and Chrome viewport checks passed** (2026-10-23).

The owner approved starting phone work while Phase 1 forecast work continues. Added
the responsive bottom weather dock, exclusive detail expansion, 44 px main controls,
safe-area/dynamic-height layout and landscape arrangement. Added device-aware 2D
defaults with a remembered override and fixed style-load building visibility and
manual scrubbing. No additional service or paid dependency was introduced.

[ADR 0006](adr/0006-mobile-weather-dock.md) records scope and rollback.
[Mobile sprint evidence](MOBILE_SPRINT_1.md) records tests, six viewport sizes and
screenshots. Physical-device, installation, push delivery and performance measurements
remain open; the forecast accuracy programme and independent acceptance run are not
marked complete by this sprint.

## Mobile simplification — owner feedback

2026-10-24: refined the layout after the owner found the first phone layout too cluttered. Replaced simultaneous
forecast/timeline panels with one compact rain overview and three navigation choices:
Rain, Radar and More. Combined search and data-age information; moved map settings,
language and quality controls under More. Source, confidence and displayed frame time
remain visible. [ADR 0007](adr/0007-mobile-progressive-disclosure.md) and
[verification/screenshots](MOBILE_SIMPLIFIED.md) record the refinement.

## iPhone installation and resume

2026-10-24: following the owner's iPhone selection, added compatible home-screen
icons/metadata, unobtrusive installation instructions and an install-first alert
action for ordinary iPhone browsers. Radar/nowcast revalidate on focus; the clock
updates on resume and active weather queries refresh on bfcache/network restoration.
Fixed inherited panel stacking over the phone's sticky navigation. No new service,
paid dependency, forecast logic or quality-gate change.

`pnpm check` passed with 62 TypeScript tests. Chrome iPhone-user-agent checks passed
at three viewport sizes plus simulated installed mode; built icons/manifest and
precache were validated. [ADR 0008](adr/0008-iphone-installation-and-resume.md) and
[iPhone checks](IPHONE_CHECKS.md) record evidence and the still-open physical iPhone,
Safari, home-screen installation and real background-push delivery checks.

## Operations reliability — 30 October 2026

Owner-approved response to the 29 October stale-radar incident and sparse GitHub
scheduled checks. Added an independent scheduler heartbeat, bounded synthetic
dispatch recovery, authenticated reports, incident deduplication and public HTTP
503 while unhealthy. Successful execution of a repeated diagnostic is explicitly
not service recovery. Radar's 25-minute SLO remains strict unless a fresh monitor
already owns that exact source-delay notification; invalid/stalled ingestion and
missing monitoring continue to fail.

[ADR 0009](adr/0009-operations-heartbeat-and-incidents.md) records the decision;
[operations evidence](OPERATIONS_SPRINT.md) records the incident, test scope,
account-wide R2 measurement and limitations. No forecast, gate, subscription-data
or archive-retention change. Dependency migration and V6 remain separate work.

## Earlier completed work relevant to this programme

13 November UI/UX refinement: rain-first desktop overview, readable intervals,
explicit observed/latest/predicted navigation, tap/keyboard data-age help and
bounded small-screen panels. No backend, model, gate or paid-service change.
[Scope, tests and screenshots](UI_UX_REFINEMENT_2026-11-13.md), [ADR 0013](adr/0013-rain-first-interface.md).
Owner follow-up places the hourly temperature prominently above rain on both
layouts, and reveals the phone overview on location selection. Previous-city
placeholder temperatures are suppressed; valid time remains explicit. Six added
regression cases, no extra weather requests or backend changes.

13 November release follow-up: PRs #27/#28 deployed, 159 successful GitHub runs
since merge at inspection, 1,115 v2 pairs with no calculation errors, latest retained
window 53/53 covered. All six public probes passed. Direct DMI raw files confirm
changing source footprints; both checked files cover all 20 reference cities.
+45/+60 legacy quality remains degraded; v2 is still diagnostic only.
[Post-release evidence and remaining work](SHARED_COVERAGE_RELEASE_2026-11-13.md).

12 November shared-coverage-v2: added an explicitly shadow-only, algorithm-separated
comparison against persistence and the exact archived operational incumbent, with
same-mask probability evidence and visible coverage loss. Legacy gates and scores
are unchanged. Two raw snapshots now reconstruct 64 unique published legacy pairs
without checked metric mismatches; the original 21-pair checkpoint below remains
historically blocked. A separate 85-pair local v2 oracle replay has zero mismatches,
but is not a published-v2 or full independent acceptance pass.
[Contract and evidence](SHARED_COVERAGE_V2_2026-11-12.md).

12 November verification completeness: owner approved proceeding after the audit.
Implemented bounded all-retained-observation planning/execution, canonical pair
identity, first-wins history preservation and public retained-window accounting.
Local real-input replay scored all 21 missing intermediate pairs in 668 ms, with
100% window coverage and zero repeat scores/downloads. [Rollout evidence](VERIFICATION_COMPLETENESS_2026-11-12.md),
[ADR 0012](adr/0012-verification-completeness-shared-coverage.md). Shared-mask comparison
is the following shadow-only stage; no numerical gate or scoring definition changed
in the completeness stage.

12 November precision audit / Redis decision: added independent raw-grid scoring
reconstruction and mask-comparison diagnostics. 7 cubes / 13 observations gave 42
available pairs, 21 public matches, zero score mismatches, and identical persistence
inputs in 7/7 cubes. The unchanged 50-pair criterion is **BLOCKED**, not passed.
Found latest-observation-only verification and unequal comparison masks; no model,
history, scoring definition or gate was changed. Redis deferred, no service created.
[Audit checkpoint](PRECISION_AUDIT_2026-11-12.md), [ADR 0011](adr/0011-defer-redis-cache.md).

12 November reliability/performance: repaired dependency lint, bounded R2 transport,
nonblocking cache persistence, isolate-local cold-request coalescing and map buffer
reuse; added stable monitoring failure causes and bundle regression budgets.
Owner separately approved only derived nowcast images older than 48h, with active
protection and a reviewed dry-run. [Evidence and limitations](NOVEMBER_RELIABILITY.md),
[ADR 0010](adr/0010-november-reliability-performance.md). This does not complete V6,
physical-device or independent full acceptance testing.

- `004e129`: delayed/expired rain notification protections.
- `4f4eab2`: V5 recall-calibrated challenger in shadow mode.
- `4d6b894`: V4 probability-gated challenger in shadow mode.
- `1ceec18`: V3 regime-adaptive ensemble and paired verification.
- `9087880`: map/point geographic consistency verification.

These commits are inputs to the baseline, not evidence that later build phases or the
release acceptance suite are complete.
