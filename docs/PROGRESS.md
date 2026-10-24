# WetMap programme progress

This log follows the phase order in the WetMap best-in-class build brief. Evidence is
linked where it is stored in the repository.

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

## Earlier completed work relevant to this programme

- `004e129`: delayed/expired rain notification protections.
- `4f4eab2`: V5 recall-calibrated challenger in shadow mode.
- `4d6b894`: V4 probability-gated challenger in shadow mode.
- `1ceec18`: V3 regime-adaptive ensemble and paired verification.
- `9087880`: map/point geographic consistency verification.

These commits are inputs to the baseline, not evidence that later build phases or the
release acceptance suite are complete.
