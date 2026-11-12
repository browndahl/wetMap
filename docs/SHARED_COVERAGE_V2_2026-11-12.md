# Shared-coverage-v2 — 12 November 2026

Second stage of [ADR 0012](adr/0012-verification-completeness-shared-coverage.md).
This is additive **shadow-only measurement**, not an accuracy improvement, new
model, historical rescore or promotion-policy change. Redis remains deferred; no
new service, paid tier or raw archive is introduced.

## Comparison contract

At the existing 20 dBZ significant-echo threshold, forecast and persistence are
scored on their common observed footprint. Each candidate is compared with the
**actual archived operational incumbent**, not its upstream ablation/control,
and persistence, on the intersection of all four valid masks. Probability Brier,
persistence Brier and Brier skill use that exact same comparison footprint.
Probabilities for another threshold are explicitly unavailable for this comparison.

Observed/common pixel counts and coverage fraction accompany scores; discarding
coverage cannot silently look like better skill. Empty common coverage has null
skill. Dry comparisons have undefined rain CSI, not a perfect forecast score.
Perfect persistence has undefined relative Brier skill, not division by zero.

New private results carry `sharedCoverageComparison`. The public `comparisonAudit`
contains bounded per-lead aggregates, separated by algorithm version. It explicitly
sets `canAffectForecasts: false` and `promotionEnabled: false`. Individual raw
diagnostic rows are omitted from the public projection. Existing legacy scores,
calibration, alert restrictions and all numeric promotion gates are unchanged.
The existing 5,200-entry rolling history bound remains. First-wins identity means
old results are not replaced simply to add v2 fields.

A diagnostic exception preserves otherwise valid legacy scoring and fresh radar
publication, but records an error. Monitoring rejects failed comparisons,
inconsistent sample accounting, mismatched denominators or enabled promotion.

## Independent and performance evidence

The completeness stage is already live in PR #27, merge `ab01317`.
[Ingestion 43309672443](https://github.com/browndahl/wetMap/actions/runs/43309672443)
finished in 97 seconds. Its retained window had 63 eligible pairs: 26 already
verified and all 37 missing pairs completed, zero errors/deferrals, 100% coverage.
Verification took 11,354 ms including eight cube/seven observation downloads,
inside the unchanged eight-minute workflow budget.

Two checksum-verified raw snapshots independently reconstruct **64 unique published
legacy pairs**, zero mismatches in checked counts, CSI, MAE and persistence skill.
The unchanged 50-pair implementation-audit floor is therefore passed for those
metrics. Duplicate snapshots cannot satisfy that floor; overlapping identities
are deduplicated. Per-snapshot results retain their original status. These pairs
are not 64 independent storms, nor a full C1/seasonal/regional acceptance pass.

A separate local replay compared the verifier's new v2 rows against an independent
NumPy histogram/counting oracle: **85 raw pairs, 350 member-score checks, 60
candidate comparisons and 36 same-mask Brier/Brier-skill checks; zero mismatches**.
This is local reconstruction, **not** independent checking of a published v2 ledger.
The two snapshots reuse inputs; counts are deduplicated within each stated audit,
not added together to inflate acceptance evidence.

Additional serialised v2 rows totalled 135,664 bytes across 85 pairs; maximum
6,543 bytes per pair with candidates. No additional archive objects are created.
This bounded sample is not a long-term storage or free-tier guarantee. Raw private
cubes/images stay in local temporary directories, never Git/GitHub artifacts.
Only aggregate reports/checksums are committed under `docs/evidence`.

Reproduce with the worker installed and the two local snapshot directories:

```sh
.venv/bin/python apps/worker/tools/audit_precision.py SNAPSHOT_1 SNAPSHOT_2 --output /tmp/reconstruction.json
.venv/bin/python apps/worker/tools/audit_shared_coverage.py SNAPSHOT_1 SNAPSHOT_2
```

The latter imports the independent histogram-based scorer, not the production
comparison scorer, as its oracle; mismatches fail instead of printing success.

Regression coverage includes common-mask counts and Brier, empty/dry grids,
threshold mismatch, malformed inputs, no mutation, exact incumbent alignment,
cohort isolation, operational quality invariance, bounded record size, diagnostic
failure isolation and multi-snapshot audit deduplication. Full CI/security and a
post-release ingestion remain required before describing this release as live.

## Activation boundary

V2 starts collecting only on newly verified pairs. It does not retrospectively
replace the historical ledger or borrow legacy sample counts. It remains outside
forecast selection, calibration and push-alert gates until separately reviewed
independent validation and representative weather evidence justify a transition.
No numerical gate may be relaxed to make the new evidence pass. More observations
improve confidence in measurement; they do not automatically improve forecasts.
