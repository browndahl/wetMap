# ADR 0004: Fixed V6 backtest split and immutable test period

Status: accepted, 2026-10-22.

## Context

V6 challengers need a reproducible offline comparison without tuning on the same
observations used for the final claim. On 22 October 2026 the official DMI radar API
was verified to return five-minute composite observations from 25 April 2026 onward.
WetMap's own processed frame retention is only 48 hours.

## Decision

The first V6 dataset uses UTC, half-open, date-based periods recorded in
`apps/worker/backtest/split-v1.json`:

- train: 25 April through 31 July 2026;
- validation: 1 August through 15 September 2026;
- test: 16 September through 21 October 2026.

Training and validation may be used to fit and select a challenger. The test period is
immutable and may never influence parameters, thresholds, feature choices, or model
selection. Every report records the SHA-256 of the split file. Leads are evaluated at
every five-minute step from +5 through +60 minutes.

This split is only the first seasonal dataset. It cannot establish winter snow/sleet
performance and must not be represented as annual Danish performance.

## Consequences

- A report can be traced to exact time boundaries and cannot silently move its test
  window.
- Calibration state is learned from train data and frozen before test evaluation.
- Spring, summer and early-autumn cases are available, but a later dataset revision is
  required after winter observations accumulate. That revision gets a new dataset ID
  and split file; it does not rewrite this one.
- No production gate or metric definition changes in this ADR.

## Deferred retention decision

Keeping every current full-resolution processed WebP for one year is estimated at
about 44 GiB from 13 production frames measured on 22 October 2026. That can exceed
the R2 free storage allowance. Retention will not be changed until a compact archive
format is measured and the owner explicitly approves any remaining cost risk.
