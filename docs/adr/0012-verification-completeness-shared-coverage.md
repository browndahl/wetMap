# ADR 0012: Complete observation verification and staged shared-coverage comparison

Date: 2026-11-12. Owner approved proceeding after the precision-audit/Redis review.
Rollout: complete legacy verification first; introduce a separate, additive
shared-coverage comparison in shadow-only mode. No Redis or paid service.

## Problem

The worker scores only the latest observation in an ingestion batch. Valid
intermediate observations can therefore be missed, producing uneven lead evidence.
Forecast/persistence and candidate/control masks also differ; reported skill can
compare different pixels. See PRECISION_AUDIT_2026-11-12.md.

## Plan and files

- Add a pure bounded pair planner and batch executor under apps/worker; wire it
  into cli.py. Use all retained observations, not only the newest or the newest
  three source frames. Deduplicate by algorithm/source/predicted/observed/lead.
- Cache each cube and observation download per run; check hashes and bounds.
  Limit work to the existing retained manifest/state, a fixed pair budget and a
  verification time budget. Record planned/completed/deferred/errors and duration.
  Exceptions must not prevent fresh observed radar publication.
- Preserve existing historical records exactly; append previously unverified pairs
  only. Existing 5,200-entry rolling retention is not expanded or reset.
- Add shared-coverage-v2 as a bounded secondary record on newly verified pairs,
  plus separately labelled aggregate public evidence. Existing scorer outputs,
  quality_by_lead, promotions, calibration and alert gates continue to use legacy
  evidence. Do not pool v2 and legacy counts or let v2 affect forecasts.
- Add tests for intermediate/cached observations, duplicate retries, cube reuse,
  partial failure/deadline/budgets, cohort identity and history preservation; add
  independent count/Brier/coverage tests. Update schemas/types/docs as needed.

## Shared-coverage-v2 definition

The first additive comparison covers the existing significant-echo threshold,
20 dBZ. For operational forecast vs persistence: score both on the intersection
of forecast, persistence and observed coverage. For each shadow candidate: score
candidate, the **actual archived operational incumbent**, and persistence on the
intersection of all four coverage masks. Do not substitute a candidate's upstream
ablation control for the actual incumbent. Probability and persistence Brier use
that same per-comparison mask. Report observed/common valid pixels and coverage
fraction separately so a shrinking footprint cannot masquerade as better skill.

This is a diagnostic cohort, not a model improvement or retrospective rescore of
stored history. Empty coverage has no usable skill; dry conditions do not imply
perfect rain prediction. Primary/legacy metrics and all numerical gates remain
unchanged. Probabilities/reflectivity pixels are unchanged.

## Acceptance and activation boundary

Full unit/CI/security checks pass, bounded real replay fits the unchanged
eight-minute ingestion job, retry adds no duplicate/replaced scores, and all
available unverified valid-time observations are planned (subject to explicit
budgets). Check at least 50 checksum-verified raw published pairs where available;
if fewer are available report BLOCKED rather than reduce the floor. No independent
storm-count or regional/seasonal claim follows from overlapping pixel pairs.

V2 remains shadow-only in this release. Activating it for operational quality,
calibration or promotion is a separate reviewed transition after independent
validation and representative weather evidence. Never silently relabel old data,
reset the ledger or relax thresholds to make new numbers pass.

## Rollback

Revert worker changes to latest-only execution if necessary; retain all legitimately
appended records and their v2 fields. Old readers ignore additive fields. Never
delete history as rollback. The comparison cannot affect live forecasts while in
shadow-only mode; radar's source/freshness and push safety rules remain intact.
