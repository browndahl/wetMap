# ADR 0005: Local-first backtest archive under a free-only budget

Status: accepted local-first direction, 2026-10-22. The owner requires everything to
remain free. The earlier proposal to activate 400-day R2 retention is withdrawn;
no new cloud archive uploads or lifecycle changes are authorized.

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

## Decision for this sprint

- Build and replay a small, bounded event dataset on local disk using DMI's public
  archive. Download selected event windows on demand and retain checksums and UTC
  provenance so the same inputs can be replayed.
- Use the fixed train/validation/test split from ADR 0004. Keep the test period out
  of parameter selection. Retain event labels and report summaries in the repository;
  keep radar binaries out of Git and GitHub Actions artifacts.
- Keep additional R2 archival disabled. The existing public frame lifecycle remains
  48 hours. No additional paid service, subscription, paid runner or automatic paid
  upgrade is part of this work.
- Use a small generated replay in existing CI; perform larger historical experiments
  locally. Cap each download job by frame count and bytes before fetching assets.
- A future cloud archive requires measured account-wide storage and operation usage,
  enforced budgets with headroom, and stopping optional archival when budget evidence
  is missing or limits are reached. An estimate and billing alerts alone cannot
  establish a zero-cost guarantee on a metered service.

## Deferred cloud option (not authorized for activation)

- Add an immutable `backtest/frames/<DMI-id>.webp` object for every observation,
  resized once with the same `INTER_AREA` path used by the current harness.
- Preserve alpha semantics exactly: 0 outside coverage, 1 valid no-echo, encoded dBZ
  above that. Store SHA-256, dimensions, observed time, DMI item ID and processor
  version in an append-only daily manifest.
- A 400-day lifecycle for `backtest/frames/` was considered. It is deferred under the
  free-only requirement; the existing 48-hour public `frames/` lifecycle remains.
- Backfill the locked event catalogue in bounded batches. Do not bulk-download the
  entire DMI archive until operation/runtime measurements show it remains within the
  agreed budget.
- Treat this reduced archive as algorithm-development evidence, not a replacement for
  full-resolution live-shadow verification before promotion.

## Consequences

- Winter observations can accumulate at a projected storage level below the current
  R2 free allowance, but unexpected frame growth or other account use can still
  create cost risk. Cloudflare lists 10 GB-month of Standard storage, 1 million
  Class A and 10 million Class B operations per month; amounts beyond the included
  usage are billable. These are account-level allowances, not a reserved archive
  quota. [Official pricing](https://developers.cloudflare.com/r2/pricing/), checked
  22 October 2026.
- Small-scale structures below the reduced grid cannot be evaluated faithfully. Any
  promising challenger must still pass unchanged gates in full-resolution live shadow.
- Selected local event downloads can proceed within the free-only constraint. Cloud
  retention and backfill remain disabled; this ADR does not establish any billing cap
  for the existing R2 account.
