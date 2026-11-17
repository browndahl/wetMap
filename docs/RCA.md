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

## M10: point-grid publication can overwrite the active slot

Confirmed by source and deterministic reproduction: the key was selected by
five-minute observation parity. If ingestion advances ten minutes, parity is the
same and the currently referenced binary is overwritten before metadata changes.
Reader range GETs were also not version-bound. Geographic self-checks over generated
files do not exercise live publication/read races. This is a reproduced failure
mode, not proof of a specific historical user's map/box mismatch.

Old writer suite: **7 failed / 1 passed**. New writer suite: **8 passed**, full
worker **107 passed**, Ruff passed. The new tests preserve existing ledger bytes
and fail closed on missing pointer reads, binary writes and returned object version.
ADR 0014 documents the two-step writer-first rollout and bounded extra GET.

Reader regression: 7/8 tests failed before enforcement; three additional cases
exposed invalid per-frame metadata and unhandled range-read errors. All 11 pass
after enforcement, including overwritten objects, mixed rows, missing versions,
malformed bounds/frames, invalid timestamps and range transport failure. Every row
is now conditional on the published ETag and checked again against the returned
object. Invalid/legacy unversioned inputs fail closed to the existing labelled
model path, never to fabricated dry radar. Range transport failure logs a fixed
event code without raw errors. The strict reader is released only after normal
writer publication is confirmed. No algorithm, history or gate change.

## M04: deployment can precede independent CI/security completion

Confirmed by deploy.yml: push-to-main starts deploy independently; staging checks
only the pnpm workspace. No exact-commit prerequisite on CI's .NET/containers or
the Security workflow. Existing manual PR review does not enforce all future
main pushes. The new workflow-dependency regression fails against the old config.

Fix in ADR 0015: bounded exact-SHA main/own-repo CI+Security gate; pinned checkouts,
serialized deploys, superseded-release check before publishing. Nine deterministic
gate tests plus the full script suite (**43 passed**) cover positive and negative
outcomes. No production failing release is injected. Live rollout must verify gate
ordering. Repository rulesets/environment protection are not silently configured.

## M11: push input can throw on JSON null and bypass its byte limit

Confirmed local adapter tests: JSON `null` throws before validation; a valid body
preceded by >9 KB whitespace with no Content-Length is accepted/stored despite the
declared 8 KB limit. Coordinates/location labels and subscription expiration can
also have invalid runtime types hidden by TypeScript assertions/coercion.

Root cause: trusting Content-Length and `as Record`/subscription type assertions
instead of bounding the actual body stream and checking JSON shape. Four initial
new cases failed; a further expiration-type test failed after the first correction.
No real subscription or production mutation was used in reproduction.

Fix: read at most 8,192 actual bytes, reject oversized input as 413 (including
unsubscribe), reject non-object JSON and field-type violations as 400. Existing
valid subscription fields, coordinate rounding, opt-in flow, deletion behavior and
retention are unchanged; no new personal data or logs of request content.

Local suite: 11 input cases pass; edge total 99, strict types pass. Includes valid
registration/rounding and no storage mutation on invalid input. CORS and alert
quality/expiry rules stay unchanged. Does not establish provider delivery, rate
limits or complete endpoint allowlisting. Rollback: revert this input-only change.

## M12: repeated risk-grid decoding within the same push scan

Measured seven-day cron CPU p99 is 41.854–52.469 ms; its complete cause is not yet
established. A confirmed contributor in local reproduction is decoding every
frame's identical base64 weather grid for each of up to 40 subscriptions. The old
code also decodes alert-ineligible frames before rejecting them. Deterministic
tests observed 520 decodes per scan rather than 13, and 13 rather than zero for
ineligible frames. These two work-count regressions failed before the change.

Fix: weakly owned, weather-only per-manifest decoded scratch data, at most 13
entries / 128 KiB, with encoded-content invalidation and no coordinates or
subscription data retained. Oversized frames are decoded but not cached. Skip
already ineligible frames before decoding; no quality/expiry/scan-cap change.
Five tests pass, including content replacement and oversized-frame non-retention;
all 104 edge tests and strict types pass. No extra cloud requests or new service.

Same isolated 12-batch synthetic 40-location lookup: p50 38.084 → 1.034 ms and
p95 39.006 → 1.274 ms. This is lookup-only local wall time, not Cloudflare CPU,
network/encryption/provider delivery or a field percentile. Actual post-release
CPU and active plan remain unresolved; see PERFORMANCE.md and FREE_TIER.md.
Rollback: revert this optimization; alert decisions remain unchanged.

## M08: source-delay ownership denial has no diagnostic reason

The three failed morning radar runs leave no reason for declining the monitor
handoff. The exact historical cause remains unknown. Reproduction captures main's
output for an owned 503 incident, HTTP failure, invalid JSON/contract and oversized
response: five diagnostic assertions fail on the previous implementation. The
new reason-helper tests are new interface tests, not extra historical failures.

Fix: static reason codes for inactive monitor, scheduler/probe freshness,
observation mismatch, missing incident ownership, network/JSON/contract/size
failure. Read at most 65,537 bytes to enforce a 64 KiB status-document ceiling,
with the existing 10-second HTTP timeout. No raw URL, response, exception text or
signature is logged. No added request and no retry of a side effect.

Seven new tests cover the unchanged exact ownership policy, malformed/future
monitor times, owned HTTP 503, unavailable monitor, bounded reads, healthy and
stalled ingestion. The full script suite is 50 passing tests. Owned repeated
source delay still emits a warning and returns success only for notification
ownership; public unhealthy status stays 503. Unknown/unowned/invalid/stalled
states still fail. The 25-minute freshness gate is unchanged. Rollback: revert
this diagnostics commit, never relabel an underlying incident as resolved.

## M14: missing required query coordinates silently become zero

OpenAPI requires numeric `lat` and `lon` for both weather endpoints, but handlers
used `Number(url.searchParams.get(...))`. JavaScript converts null/blank strings
to zero. Missing one or both coordinates therefore passed validation, touched
cache/R2 and attempted upstream weather at a manufactured point; with mocked
unavailable upstreams the result was 503 rather than the required 400.

Reproduction: a new 20-case adapter suite has **10 failed / 10 passed** on the
previous implementation. The failed cases are missing/blank required parameters
on both endpoints; range/nonfinite and explicitly provided zero remain controls.
No real upstream calls, coordinates or production request mutations were used.

Fix: use the existing null/blank-aware coordinate parser in a shared weather
coordinate contract, validate before any cache/storage/radar/upstream I/O, and
return the existing 400 ProblemDetails response. Valid explicit zeros, finite
worldwide ranges, valid coordinate rounding and response contracts are unchanged.
The 20 cases now pass, full edge suite 124, strict types pass. Does not claim full
OpenAPI compliance or independently validate every upstream weather field.
Rollback: revert the coordinate-validation commit.

## M15: future source timestamps pass the publication input boundary

The freshness validator already rejects observations more than two minutes in
the future, but it executes after processing/publication. Catalogue validation
checked UTC syntax only, so a future-dated input could reach download and replace
the last-good manifest before that existing gate fails. This is a reproduced
failure mode, not proof that DMI historically supplied a future observation.

New fixed-clock tests on the previous code: **3 failed / 2 passed**, including
the preservation test reaching download instead of rejecting. The fix applies
the **same existing two-minute tolerance** at the adapter input boundary, once
per catalogue. It rejects before download, output mutation or remote publication;
it doesn't change historical data or make stale observations fresh.

Five tests pass (future by 120.001 s / a day, exact now / +120 s boundaries,
last-good bytes and no download/upload). Full worker suite 112, Ruff passes.
No new request, service, retention or forecast gate. Residual: the ingestion
host's UTC clock remains a trusted dependency. Rollback: revert the input guard.

## M16: release publisher accepts a different/unsecured candidate

Closing inspection found an additional historical Release failure 44186050603:
GitHub returned Internal Server Error while pushing semantic-release notes after
v1.22.4 tag creation. The tag points at `fda019b`; the Release API returns 404.
Remote GitHub failure is confirmed, its internal provider cause unknown. No
production weather failure or proof of a concurrency cause. Do not replay a
partially completed publisher or claim this 500 is permanently prevented.

Separate confirmed workflow defect: branch-name-only successful CI trigger,
floating-main checkout, no Security prerequisite or serialization. That can
publish a different commit than was checked. Existing monitoring tests covered
deployment prerequisites, not the distinct tag/release workflow.

Fix/alternatives in ADR 0016: nominate only own main-push SHA; pinned checkout,
same-SHA CI+Security gate, serialized publisher, current-main recheck. Only an
explicit obsolete candidate can output eligible=false. Every unknown/failed
check remains fatal; existing deploy strict behavior is unchanged. No automatic
whole-action retry, release repair, tag rewrite or dependency upgrade.

Baseline: eleven workflow-policy assertions fail. Three new optional-CLI tests
are interface coverage, not extra historical product failures. All thirteen
release-gate tests and the full 54-script suite pass; default strict, output
enable/disable, failed checks, missing output and no raw credential/error logging
are covered. Normal rollout must still be observed. No runtime weather/gate cost
or privacy change; rollback by reviewed revert. Old missing Release metadata and
action installer advisory warnings remain separately documented follow-ups.
