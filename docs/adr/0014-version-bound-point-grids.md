# ADR 0014: bind point-grid reads to the published binary object version

Date: 17 November 2026. No new service, storage prefix, retention or scoring policy.

## Reproduced problem

The point-grid generator picks one of two slots with observation-time parity.
Skipping a five-minute scan can pick the **same** slot as the active pointer.
Replacing that binary before metadata publication exposes new bytes under old
dimensions/times. Independent parallel byte-range reads also lack an object-version
condition, so an overwrite can mix rows. Prior geographical self-checks use one
generated snapshot and do not test this publication race.

## Decision and rollout

1. Writer: read the actual current pointer (one additional bounded R2 GET), choose
   its inactive slot and single-PUT the small binary using existing bounded S3
   retry/socket settings. Publish metadata schema v2 carrying the returned ETag,
   only after binary upload succeeds. Keep exactly two binary slots; no archive.
   A pointer-read failure aborts before asset changes; missing metadata bootstraps.
2. Wait for a normal automatic ingestion to complete with the version-bound writer.
3. Reader: every row GET uses `onlyIf.etagMatches` and checks the returned object
   ETag. Any failed condition/missing row/invalid pointer returns unavailable radar
   sampling so the existing explicitly labelled model path can handle it. Never
   decode mismatched data as dry weather. An unversioned pointer is not trusted.

This two-step rollout avoids activating the strict reader before the writer has
published v2. Conditional reads also protect readers that survive more than one
slot reuse. It does not make all independent map/model caches globally atomic.

## Evidence, cost and rollback

Writer regression suite on old code: 7 failed / 1 passed. Cases cover skipped-scan
parity, active/legacy slot selection, bootstrap, failed metadata/binary reads and
missing ETag. Verification-history bytes/keys must remain identical.

Additional usage: at most one small metadata GET per ingestion, about 8,640/month
at one per five minutes; binary writes replace existing PUTs, two slots unchanged.
Measured seven-day peak R2 Class B is 15,194/day (30-day projection 455,820 of 10M),
so this bounded increment is small. CPU request limits and whole-account costs
remain separate risks, not a claim of full free-tier compliance.

Rollback reader first, then writer. Do not delete either slot, history or manifests.
Legacy reader remains compatible with new metadata's extra fields. No algorithm,
rain threshold, lead time, confidence or forecast/push gate changes.
