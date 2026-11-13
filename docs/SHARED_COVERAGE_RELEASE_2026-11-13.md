# Shared-coverage release follow-up — 13 November 2026

Code is merged and deployed: PR [#27](https://github.com/browndahl/wetMap/pull/27)
(`ab01317`, completeness), PR [#28](https://github.com/browndahl/wetMap/pull/28)
(`fbd4ae9`, additive shadow comparison). This document completes the post-release
checks requested in the [v2 contract](SHARED_COVERAGE_V2_2026-11-12.md); it does not
activate v2 or declare full independent forecast acceptance.

## Observed operation

At the 13:18 UTC inspection, all **159 GitHub runs** since the merge were successful:
95 ingestion, 60 synthetic, and one each release/deploy/CI/security. None failed or
was cancelled. Both staging and production deployed successfully. All six public
health checks were green, monitoring/scheduler active, no active incident.

[Ingestion 43432123786](https://github.com/browndahl/wetMap/actions/runs/43432123786)
published a report at 13:16:20 UTC: **53/53 retained eligible pairs covered**, with
41 already verified and all 12 missing pairs completed. Zero errors, rejected
forecasts, deferrals or budget exhaustion. Verification, including six cube/two
observation downloads, took **4,255 ms**. These are retained-window counts, not a
claim that every historical storm was verified.

The live `comparisonAudit` had **1,115 new pairs**, zero failures, all twelve leads,
one separately labelled algorithm cohort, and five candidate families. The quality
and observatory API projections passed the full quality/comparison validator.
Both operational-effect flags remained false; legacy scores and all promotion,
calibration and alert gates are unchanged. Probability evidence uses shared masks.
The quality document serialised to approximately 845 KB, below the monitor's
unchanged 4 MB response limit. Individual v2 rows remain private.

A local full public probe at 13:18 UTC passed web, API, radar, quality, performance
and scheduler checks. One point-forecast request measured **427 ms MISS / 55 ms HIT**
at CPH. This is one controlled sequence, **not** p95 or a user-wide latency guarantee.
The latest automated probe was also healthy:
[43431973359](https://github.com/browndahl/wetMap/actions/runs/43431973359).

## Coverage investigation, not a new scoring policy

V2 exposed differing observed footprints between adjacent source times. Two direct
public DMI ODIM products confirm the difference already exists **before** WetMap
processing or caching:

| DMI timestamp (UTC) | Raw grid    | Valid pixels | Source bytes |
| ------------------- | ----------- | -----------: | -----------: |
| 2026-11-13 13:00    | 1728 × 1984 |    1,845,644 |       74,534 |
| 2026-11-13 13:05    | 1728 × 1984 |      725,382 |       60,304 |

Both use nodata=255 and undetect=0. Valid footprint differs by approximately 2.54×;
it is not legitimate to treat nodata as dry or invent coverage to equalise them.
The same alternation appears in the earlier checksum-verified processed snapshot.
Raw-coordinate checks found coverage at **20/20 Danish reference cities in both
files**. That limited point check is neither full Danish land coverage nor evidence
that rain intensity is correct. The cause of DMI's differing source footprints is
not established here; only their presence in the source files is verified.

Source inventory: the public DMI composite collection at
`https://opendataapi.dmi.dk/v1/radardata/collections/composite/items`.
The two source hashes and aggregate evidence are versioned alongside this document.
Raw HDF5s remain local temporary files, not Git/GitHub artifacts. No archive was
rewritten, model changed, gate relaxed or external cache added.

## What is still open

Infrastructure reliability is not weather accuracy. At the captured legacy quality
checkpoint, +15/+30 passed their existing gates, but +45/+60 remained degraded
(CSI 0.1929 / 0.1110). Alert restrictions remain in force. More accumulated data
improves evaluation confidence; it does not automatically improve the algorithm.

Next precision work should investigate quality by region/coverage regime and
weather event, independently reconstruct published v2 records (including Brier),
and evaluate long-lead challengers on a fixed held-out set. Activation requires a
separate reviewed transition with representative evidence. The earlier 64-pair
legacy reconstruction and 85-pair local v2 oracle replay do not replace this.
Redis remains unjustified by the measured bottleneck; no new cost was introduced.
