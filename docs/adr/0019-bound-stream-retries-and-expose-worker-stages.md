# ADR 0019 — Bound hidden stream retries and expose derived pipeline stages

Date: 18 November 2026 (Europe/Copenhagen). Status: locally tested proposal,
not deployed. No timeout/gate/history/retention change.

## Evidence, not an invented historical root cause

Bounded GitHub read since05:22 UTC found82 radar runs:81 successful, one failed;
36 synthetic uptime runs successful. The failed radar run
[44263888361](https://github.com/browndahl/wetMap/actions/runs/44263888361) started
at08:04:35 UTC. It logged `radar.observations.published` at08:05:05.918, then hit
the existing four-minute processing-step deadline at08:09:07.623. No intervening
phase timing proves which operation stalled. Radar observations were published
before derivation; successful later runs don't prove the cause of this failure.

Source/installed SDK inspection reveals a separate real retry-budget defect.
`botocore.Config` limits API attempts to3, but `TransferConfig` still defaults to5
stream-download attempts after HTTP success. The [official SDK reference](https://docs.aws.amazon.com/boto3/latest/reference/customizations/s3.html#boto3.s3.transfer.TransferConfig)
distinguishes these retry loops. A real local S3 transfer-manager test with
botocore Stubber and a synthetic broken streaming body reads **five times**
before failing, despite the apparent bounded API configuration. No sockets,
sleep, live R2 reads or private raw-data download used.

## Smallest scoped change

- Explicit `num_download_attempts=1` in the existing classic transfer config.
  Keep API 5xx/throttling retries at3, connect/read idle timeouts5/20s, multipart
  threshold/chunks/concurrency and all upload ordering/bytes/keys unchanged.
  There is no second immediate broken-body retry loop. This isn't an absolute
  transfer deadline: a slow stream, several files or other computation can still
  overrun the step budget. Do not claim the morning failure permanently solved.
- Ten closed phase IDs emit started/completed/failed plus elapsed milliseconds
  around observation upload and derived source/state/history/score/gauge/generate/
  publication calls. At most20 new records per normal invocation; no operation
  arguments, return values, coordinates, identifiers, keys, endpoints, raw errors
  or tracebacks. Unknown stage names are rejected before logging. Existing other
  worker/SDK logs aren't declared scrubbed by this new boundary.
- Stage wrapper returns the same result or propagates the same exception, including
  SystemExit. Existing critical-failure/derived-failure handling remains. A killed
  process may leave only the started marker; no fabricated completed marker.

Fewer stream retries can expose an individual broken-body transfer failure sooner;
that's the intended latency/request-budget trade-off, not a guarantee of fewer
job failures. Existing scheduled recovery remains, and failed/unavailable inputs
aren't fabricated. Do not add retries around non-idempotent publication or raise
the workflow timeout to hide this. Observation-first publication remains required.

## Regression and verification

- Two assertions reproduce before the change: effective config5 vs1, actual
  transfer-manager body reads5 vs1. They pass with explicit stream budget.
- SDK-backed fault test now covers manifest, image, verification-state and cube
  download entry points. Last-good manifest/state/cube bytes remain unchanged;
  failed new image is absent; an independent immutable observation is untouched.
- Eight stage tests cover exact argument/result forwarding, deterministic125ms
  success and750ms failure timing, identical exception propagation, no raw
  payload/error output, unknown names and static CLI boundary inventory.
- Full worker125 tests and Ruff pass. No DMI/R2/push call, quota/load test,
  stored-history rewrite, model promotion or scoring/gate change. C1 and plan/CPU
  compliance remain unresolved. Remote CI and rollout must be recorded separately.

## Rollback and next evidence

A reviewed revert restores the old retry behaviour; no stored data migration is
needed. Preserve the observation-first invariant. Owner approval is required
before merging/deploying this next separate PR; PR53's merge approval isn't
assumed to authorise it. No production rerun/fault injection to force a timeout.
After a separately approved normal rollout, compare passive phase timings and
failures over scheduled runs. Only then target the evidenced slow stage. No
claim of guaranteed scheduling, end-to-end latency or immunity to provider errors.
