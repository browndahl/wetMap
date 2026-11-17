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
