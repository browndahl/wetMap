# Verification completeness rollout — 12 November 2026

Owner approved continuing after PR #26's precision audit. This is the first stage
of [ADR 0012](adr/0012-verification-completeness-shared-coverage.md): repair sampling,
then introduce shared-coverage-v2 as an additive parallel comparison. No Redis,
paid service, raw archive expansion, metric redefinition or gate relaxation here.

## Implementation

The planner examines all observations in the retained manifest (up to the existing
24-frame CLI limit) against the bounded archived forecasts, not only source_frames[-1].
It includes cached observations, so a rerun can recover missing pairs even when
there are no new downloads from DMI. Identity includes algorithm version, source,
predicted/observed valid time and lead; UTC spellings are normalised for identity
without changing stored fields. Duplicate inputs cannot inflate samples.

Execution uses at most 192 pairs / a 45-second verification budget, checked between
I/O/scoring operations. One already-started network operation can finish after the
deadline; existing bounded R2 timeouts remain. Reuse each cube and observation once
per run, reuse already-local source images, verify observation hashes and bounds,
and isolate failures. Pending/error pairs remain eligible for retry. Fresh observed
radar publication and the eight-minute workflow budget are unchanged.

History appends are first-wins: a retry does not overwrite a historical score or
unknown fields. Different algorithm/lead/valid time remains a distinct pair. The
existing 5,200-entry rolling bound remains; there is no reset, bulk rescore or
relabeling of stored evidence. Better completeness can legitimately change future
model-selection outcomes through the existing gates; no gate is bypassed.

The additive verificationBatch field reports retained-window eligibility,
already-verified/planned/completed/error/deferred counts, duration and coverage.
It is not a claim about all historical storms. Quality/observatory API projections
preserve it. The monitor checks accounting and the **existing 95% SLO**, rather than
presenting partial/budget-exhausted work as 100% complete. Legacy reports remain valid
during rollout. Empty windows have null coverage, not a fake perfect score.

## Deterministic and real-input evidence

Added 11 batch/history regression tests, plus API projection and monitoring tests.
Fixed the older observatory test fixture to use six distinct source/valid times
instead of six copies of the same pair; unchanged sample/quality assertions remain.
Worker suite: **73 passed**; script suite: **25 passed**. Full CI/security required
before merge.

A local read-only replay used the earlier checksum-verified raw snapshot: seven
cubes/thirteen observations, 6,047,259 input bytes. Of 42 eligible pairs, 21 were
already in the public snapshot. All **21 missing intermediate pairs** were scored:
+5: 6; +15: 5; +25: 4; +35: 3; +45: 2; +55: 1. No errors or deferrals, 100% retained
window coverage, **668 ms** (not including network). Six cube/six image loads were
needed. Retry: zero new scores/downloads, 1 ms. New serialised results: 43,191 bytes.

This replay is plumbing evidence, not an improvement in forecast accuracy or a
50-pair independent public acceptance pass. Aggregate replay evidence is versioned
alongside this document; raw private inputs stay local.

## Following stage

Shared-coverage-v2 will compare forecast/persistence and each candidate/exact archived
incumbent on common valid pixels, with Brier on the same comparison mask and explicit
lost-coverage reporting. It stays separately versioned and shadow-only; it cannot
enter calibration, alerts or promotion in this release. Legacy gates remain unchanged.
Production ingestion, retained-window accounting, byte sizes and independent raw
reconstruction will be checked after rollout. Do not label an unavailable 50-pair
sample as passed.
