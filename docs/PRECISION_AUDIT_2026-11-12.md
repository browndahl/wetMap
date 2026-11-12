# Precision audit checkpoint — 12 November 2026

Scope approved by owner: inspect precision before selecting a model improvement;
evaluate Redis without introducing paid services. This is implementation/audit work,
not the independent release acceptance run. Forecast pixels, scoring definitions,
quality/promotion thresholds and stored histories are unchanged.

## Written plan and acceptance

1. Inspect current cache, verification, ingestion and locked backtest contracts.
2. Reconstruct raw forecast/observation scores independently, with exact valid times,
   input checksums and persistence identity. Separate published evidence from merely
   available pairs. Never reduce the existing 50-pair evidence requirement.
3. Measure common-versus-independent coverage masks as an additive diagnostic only.
4. Document limitations, a ranked next sprint, tests and the Redis decision.

Files: a local audit CLI and unit tests under apps/worker; aggregate evidence and
ADRs/docs. Raw private cubes/metadata remain on local temporary disk, not in Git or
Actions artifacts. No production model, API contract, live history or gate edits.

## Findings

### 1. Verification sampling omits intermediate observations

In apps/worker/src/wetmap_worker/cli.py, restored forecasts are verified against
source_frames[-1] / source_paths[-1] only. If ingestion obtains multiple observations,
the intermediate observations are not verified by that run. This differs from
the intended every-valid-observation verification contract.

The public snapshot generated **20:26:43 UTC** contains 288 detailed pairs, but only
11 are for +5/+15/+25/+35/+45/+55 combined; 277 are for ten-minute multiples. Exact
+15 has two pairs, last valid 15:15 UTC; +10 has 46, last valid 20:15 UTC. This is a
bounded recent subset, not the full ledger or proof of seasonal skill. The code path
is consistent with the skew; ingestion cadence and publication gaps also matter.

The raw snapshot has **42 usable forecast/observation matches**, but only **21**
match the public detailed subset. Missing public detail alone does not prove a
record never existed in the private history. The latest-only code path is the
direct, reproducible completeness problem. Verification completeness should be
fixed before interpreting more accumulated samples as balanced horizon evidence.

### 2. Forecast/persistence masks differ

Production _categorical_scores uses (prediction > 0) & (observation > 0).
Persistence is scored separately with its own valid mask. Advection can move the
coverage boundary, so subtracting their CSIs need not compare identical pixels.
The offline candidate harness has the same independent-mask issue.

**27 of 42 available raw pairs** have different masks, up to 1,009 pixels. A synthetic
test demonstrates apparent +0.50 skill disappearing to zero on common coverage.
That is a counterexample, not a measured 50-percentage-point production error.
Actual effects in this small real sample vary in both directions:

| Lead | Raw pairs | Published pairs | Mean current-style skill | Mean common-mask diagnostic |
| --- | ---: | ---: | ---: | ---: |
| +10 | 6 | 6 | +0.2974 | +0.2948 |
| +20 | 5 | 5 | +0.2676 | +0.2607 |
| +30 | 4 | 4 | +0.2211 | +0.2177 |
| +40 | 3 | 3 | +0.2453 | +0.2490 |
| +50 | 2 | 2 | +0.1472 | +0.1572 |
| +60 | 1 | 1 | +0.0412 | +0.0557 |

Common coverage falls to about 91.1% of observed coverage in the single +60 pair.
Common-mask scores alone can also hide lost coverage; report coverage explicitly.
Do not call this diagnostic a better model, silently replace published metrics,
or use it to promote any horizon. A live comparison-policy change requires an
approved ADR and a new comparison cohort, keeping historical evidence intact.

### 3. Raw reconstruction is internally consistent but below the evidence floor

Added apps/worker/tools/audit_precision.py. It does not import production scoring
helpers. It independently builds a confusion matrix and reproduces precision,
recall, CSI, dBZ MAE, persistence CSI and skill across five dBZ thresholds, plus the
primary row. Uses the existing INTER_AREA/alpha encoding contract, checksum-checked
WebPs/cubes, exact UTC leads and matching geographic bounds.

- 7 archived cubes + 13 observations: **6,047,259 bytes**; bounded local inputs.
- 7/7 persistence-source grids match their originating observations exactly.
- 21 published pairs / 126 score-row comparisons: **zero mismatches**.
- 42 available pairs represent 12 observation times and 6 forecast origins; these
  overlap and are not 42 independent weather events.
- Published comparisons cover six observation times. **21 < 50**, so the CLI returns
  nonzero with reproductionStatus=blocked, not PASS. The report is intentionally
  not wired into recurring production monitoring as a false healthy/failed job.

[Aggregate machine-readable evidence](evidence/precision-audit-2026-11-12/raw-reconstruction.json)
includes source-document checksums, per-cohort/per-lead results and limitations,
but no raw private cubes, metadata or subscription data.

Not established: independent published Brier agreement, regional/regime/seasonal
accuracy, confidence intervals from independent storm events, full ODIM georeferencing,
or full C1 acceptance. A short real sample cannot establish a challenger advantage.

## Redis

Do not add Redis now. Existing point-cache HIT p95 was 83 ms in today's controlled
sample. Real traffic hit ratios/global stampedes are not measured by repeated
benchmark coordinates. Redis does not fix either finding above or radar physics.
[ADR 0011](adr/0011-defer-redis-cache.md) records current architecture, official free
quotas, costs/latency risks and concrete conditions for revisiting the decision.

## Recommended next sprint and approval boundary

1. Test and repair ingestion verification completeness: select every available
   unverified valid-time pair, deduplicate using version/source/valid-time/lead, reuse
   each cube download, cap work and profile against the existing ingestion budget.
   Start with deterministic missing-intermediate-observation fixtures and dry-run
   planning; do not duplicate history or assume a scheduler runs every five minutes.
2. Propose a versioned shared-coverage comparison policy for incumbent, persistence,
   challengers and Brier, including explicit lost-coverage reporting. **Ask the owner
   before changing metric definitions or production comparison cohorts.** No threshold
   relaxation, retrospective rewriting or cross-policy pooling.
3. Collect at least 50 checksum-verified raw published pairs over multiple weather
   situations. Keep the fixed train/validation/test split; do not tune on test data.
4. Only then rank motion/decay/blending challengers using bounded local event replay
   and unchanged live-shadow gates. Regional/regime evidence needs actual grids and
   curated events, not labels inferred from aggregate national counts.

## Verification of this audit tooling

15 new tests cover independent counts, no-coverage/dry semantics, a mask-bias
counterexample, malformed shapes/masks, raw reconstruction, metric tampering/NaN,
the unchanged 50-pair floor, unpublished evidence separation, checksums/path safety,
timestamp alignment, geographic bounds, duplicate-evidence rejection and cohort
separation. Full worker suite: **62 passed**; Ruff
passed. Existing monitoring-script tests: **21 passed**. Full CI/security is required
before merging; this checkpoint is not a model promotion or full programme completion.
