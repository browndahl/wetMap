# Root-cause register — master programme

## M02: invalid/empty DMI catalogue replaces last-known-good radar

Baseline: `0b90f43`. Severity P1 correctness. Discovered by deterministic local
fault injection, not asserted as the cause of the historical morning source delay.

Symptom: HTTP 200 with `{}` or `features: []` is accepted as an empty item list.
CLI builds/writes/uploads an empty manifest before its freshness validation fails.
The failure alert therefore arrives after a good production manifest can be lost.
Unchecked identifiers, timestamps and asset URLs can also reach processing.

Root cause: the adapter supplies a successful empty default for a missing required
field, and the publication boundary lacks a nonempty-input invariant. Existing
tests cover valid incremental inputs and derived failure, not empty upstream input.

Reproduction: new `test_dmi_contract.py` on baseline implementation: **12 failed,
1 passed**, including the last-good-manifest preservation test. No production
fault was injected. The live bounded catalogue read was valid and matched WetMap.

Fix: require a nonempty feature list; validate required metadata, UTC timestamps,
path-safe unique IDs and credential-free HTTPS asset references; reject the batch
before constructing outputs. Independently guard CLI against an empty item list
before rewriting/cleaning/publishing. Errors are explicit, not replaced with dry
weather or invented frames. No retention, existing history or metric changes.

Verification: 13 regression cases pass, full worker suite **99 passed**, Ruff
passed. Publication-failure/derived-failure tests remain. CI/deploy results will be
linked after release. Residual: a valid but non-advancing source can still be stale;
this fix does not establish the historical source-delay root cause or validate
every ODIM semantic property. Rollback: revert the input-contract commit.

## M01: validator failure loses the rejected invariant

Historical run 43948778540 reports only `CalledProcessError`/`probe-failed`.
The child validator did reject a report; its particular historical cause cannot
be reconstructed because that rejected report and stderr were not retained.

Confirmed root cause of diagnostic loss: `capture_output=True` plus a generic
exception handler discards stderr and produces the same code for every quality
invariant and validator timeout. Existing tests mocked validation success or a
generic surface failure, never real subprocess failure classification.

New tests on old implementation failed **7 assertions**: stale report, shared-mask
metric, verification accounting, promotion CSI floor, malformed contract, unknown
error and timeout all collapsed to `probe-failed`.

Fix: keep the complete child validator, its 15-second timeout and every gate.
Map only allow-listed static rejection prefixes to stable quality codes; never
log arbitrary child stdout/stderr, keys, URLs or traceback content. Include report
byte count/SHA-256 and child exit code to correlate the public report without
uploading raw private data or adding paid storage. Unknown errors still fail.

Verification: 34 monitoring/workflow tests pass; new negative cases prove that all
six probes continue and injected secret-like error text never reaches logs.
This makes future incidents diagnosable, not retrospectively “fixed”. No claim
that the underlying historical rejection was a false alarm. Rollback: revert the
diagnostics commit; classification changes but service-health gates do not.
