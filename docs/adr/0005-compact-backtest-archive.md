# ADR 0005: Compact long-lived backtest archive

Status: proposed — owner approval required before production or R2 lifecycle changes.

## Context

The public DMI composite archive currently provides observations back to 25 April
2026, but it does not yet cover a Danish winter and its future retention is outside
WetMap's control. WetMap expires public `frames/` objects after 48 hours. Keeping the
current production WebPs for a year would use an estimated 43.92 GiB and could incur
R2 storage charges.

V6's current offline harness evaluates 256×171 RGBA reflectivity/coverage grids. It
does not need the full public-map resolution for the first algorithm comparison.

## Measurement

Thirteen consecutive production frames from 22 October 2026 were measured:

| Format | Mean/frame | Projected 288/day for one year |
|---|---:|---:|
| Current production lossless WebP | 448,668 B | 43.92 GiB |
| 256×171 RGBA compressed NPZ | 15,937 B | 1.56 GiB |
| 256×171 lossless WebP | 13,560 B | 1.33 GiB |

The sample is small and is not a billing guarantee. Even a 3× weather-complexity
margin projects to about 4 GiB/year for compact WebP, before other bucket contents.
One extra object per five-minute observation adds about 8,760 Class A writes/month.

## Proposed decision

- Add an immutable `backtest/frames/<DMI-id>.webp` object for every observation,
  resized once with the same `INTER_AREA` path used by the current harness.
- Preserve alpha semantics exactly: 0 outside coverage, 1 valid no-echo, encoded dBZ
  above that. Store SHA-256, dimensions, observed time, DMI item ID and processor
  version in an append-only daily manifest.
- Give only `backtest/frames/` a 400-day lifecycle. Keep the existing 48-hour public
  `frames/` lifecycle unchanged.
- Backfill the locked event catalogue in bounded batches. Do not bulk-download the
  entire DMI archive until operation/runtime measurements show it remains within the
  agreed budget.
- Treat this reduced archive as algorithm-development evidence, not a replacement for
  full-resolution live-shadow verification before promotion.

## Consequences

- Winter observations can accumulate at a projected storage level below the current
  10 GiB R2 free allowance, but unexpected frame growth or other bucket use can still
  create cost risk.
- Small-scale structures below the reduced grid cannot be evaluated faithfully. Any
  promising challenger must still pass unchanged gates in full-resolution live shadow.
- Deployment, lifecycle changes and historical backfill remain blocked until the owner
  explicitly approves this proposal and its cost risk.
