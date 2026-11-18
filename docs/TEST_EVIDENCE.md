# Master implementation test evidence — 17 November 2026

Environment: macOS local checkout, existing Node/pnpm, Python virtualenv; normal
GitHub public Ubuntu CI; installed Chrome for bounded read-only UI. Baseline
`0b90f43`; small PRs below. Not an independent release acceptance report.

## Regressions actually executed

| Concern / test                                                                                                     | Before                                                                                                | After / scope                                                                                 | Release                                                                 |
| ------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| DMI catalogue + CLI last-good preservation, `apps/worker/tests/test_dmi_contract.py`                               | 12 failed / 1 passed                                                                                  | 13 pass, worker 99 at this stage                                                              | [#39](https://github.com/browndahl/wetMap/pull/39), `b92c525`           |
| Safe quality validator diagnostics, `.github/scripts/test_operations_probe.py`                                     | Seven new assertions fail                                                                             | Added reason/timeout/secret-sentinel cases pass; scripts 34 at this stage                     | [#40](https://github.com/browndahl/wetMap/pull/40), `35197d6`           |
| Actual inactive point slot / binary-before-pointer / read/write failure, `test_point_grid_publication.py`          | 7 failed / 1 passed                                                                                   | 8 pass, worker 107                                                                            | [#41](https://github.com/browndahl/wetMap/pull/41), `fda019b`           |
| ETag conditional point reads / invalid metadata / mixed rows / transport error, `infra/edge/src/pointGrid.test.ts` | 7 of 8 initial cases fail; three further negative cases fail before their guards                      | 11 pass, edge 88 at this stage                                                                | [#42](https://github.com/browndahl/wetMap/pull/42), `335c919`           |
| Exact-SHA release requirements, `.github/scripts/test_release_gate.py`                                             | Workflow dependency assertion fails old config                                                        | 9 methods plus subcases, script suite 43                                                      | [#43](https://github.com/browndahl/wetMap/pull/43), `6fd32db`           |
| Push body/runtime input, `infra/edge/src/pushInput.test.ts`                                                        | Four initial failures, further expiration-type failure                                                | 11 pass, edge 99                                                                              | [#44](https://github.com/browndahl/wetMap/pull/44), `040d7bd`           |
| Risk decode work, `infra/edge/src/pushCpu.test.ts`                                                                 | 520 vs expected 13 decodes; 13 vs expected zero for ineligible frames                                 | Five tests pass including invalidation/budget; edge 104                                       | [#45](https://github.com/browndahl/wetMap/pull/45), `1861deb`           |
| Safe source-delay decision reasons, `.github/scripts/test_freshness_diagnostics.py`                                | Five output assertions fail. New helper-interface missing errors are not additional product failures. | Seven methods + table cases; script suite 50                                                  | [#46](https://github.com/browndahl/wetMap/pull/46); final rollout below |
| Required weather coordinates, `infra/edge/src/coordinates.test.ts`                                                 | 10 failed / 10 passed                                                                                 | 20 pass, edge 124; missing/blank inputs rejected before any I/O, valid explicit zero accepted | [#47](https://github.com/browndahl/wetMap/pull/47)                      |
| Future catalogue time, `apps/worker/tests/test_dmi_future.py`                                                      | 3 failed / 2 passed                                                                                   | Five pass including last-good preservation and exact +2 min existing tolerance                | [#48](https://github.com/browndahl/wetMap/pull/48)                      |

No real push registrations, notifications, deletions, paid upstream calls or
production corruptions were used for the above. Storage adapter tests are mocked
failure drills, not proof of a live remote outage/fault-injection exercise.

Exact local commands (repo root):

```sh
.venv/bin/python -m pytest apps/worker/tests/test_dmi_contract.py -q
.venv/bin/python -m pytest apps/worker/tests/test_point_grid_publication.py -q
.venv/bin/python -m pytest apps/worker/tests/test_dmi_future.py -q
.venv/bin/python -m pytest apps/worker/tests -q
.venv/bin/ruff check apps/worker
pnpm --filter @wetmap/edge exec vitest run src/pointGrid.test.ts
pnpm --filter @wetmap/edge exec vitest run src/pushInput.test.ts
pnpm --filter @wetmap/edge exec vitest run src/pushCpu.test.ts --reporter=dot
pnpm --filter @wetmap/edge exec vitest run src/coordinates.test.ts --reporter=dot
pnpm --filter @wetmap/edge typecheck
python3 -m unittest discover -s .github/scripts -p 'test_*.py'
.venv/bin/ruff check .github/scripts/check_freshness.py .github/scripts/test_freshness_diagnostics.py
WRANGLER_LOG_PATH=/private/tmp/wetmap-master-build-logs pnpm exec turbo run lint typecheck test build --force
WRANGLER_LOG_PATH=/private/tmp/wetmap-master-build-logs pnpm --filter @wetmap/edge build
```

The final force run executes all 12 workspace tasks with **0 cached tasks**:
124 edge, 38 web, 2 shared = 164 TypeScript tests. Worker 112 and the 18 November
follow-up script suite 54 give **330 tests** across these suites, not coverage
percentage or end-to-end acceptance. Script methods include subcases not
separately counted; the previous #49 checkpoint had 326.
Earlier normal `pnpm check` replayed some Turbo cache entries. Both normal and
forced Turbo runs emitted sandbox Wrangler log-path EPERM while exiting zero:
Turbo's strict environment filters the log-path override. This is **not** an
error-free build claim. A separate direct edge build with the writable temporary
log directory reruns the actual dry build without that EPERM; no remote deploy.
All three gzip budgets pass unchanged; the MapLibre
chunk warning remains. Existing CI independently runs .NET tests and container
builds, plus all three CodeQL languages, secrets and Trivy/SBOM.

## Normal production rollout evidence (not fault/load testing)

### 18 November follow-up: distinct GitHub Release gate

Closing inspection of 91 runs since 21:45 UTC found Release 44186050603 failing
at 22:02:58 UTC (17/11): remote GitHub Internal Server Error on a notes push.
Read-only API confirms v1.22.4 tag at `fda019b`, Release post HTTP 404. No replay,
tag rewrite or repair performed; metadata repair approval requested separately.

Separate workflow defect: branch-only CI trigger, floating main, no Security wait
or serialization. Eleven policy assertions fail old release.yml. Four new test
methods (three optional-interface, one workflow policy) pass; all thirteen gate
methods and 54 script methods pass. Optional skip enables **only** a valid obsolete
candidate as eligible=false; malformed remote refs, missing output, failed checks
and transport errors fail. Two malformed-ref cases caught an initial new-option
implementation gap before commit; not historical production failures. Deploy's
default superseded behavior remains failing. Exact SHA is an ordinary CLI argument,
not an override of reserved GitHub environment variables. ADR 0016 records scope.

Command: `python3 -m unittest discover -s .github/scripts -p 'test_*.py'`, Ruff on
release_gate.py/test_release_gate.py and Prettier YAML syntax/style check pass.
No model, cloud runtime, history or personal-data change. Remote GitHub 500 and
action installer warnings aren't claimed fixed by release serialization/gating.

### Earlier normal rollouts

- Follow-through for #50: main `b2de29c` CI 44197225264 and Security 44197225223
  succeeded. [Release 44197456654](https://github.com/browndahl/wetMap/actions/runs/44197456654)
  checks gate ready and current-head check pass at 23:13:38 UTC, before publisher;
  completes 23:14:04 UTC and publishes v1.22.12. Deployment 44197225088 and
  synthetic 44197478872 succeed. The eleven code fixes are merged, not a full
  acceptance pass. Runtime installer warnings remain; the separate two-request
  public-lock audit and failed same-core fresh-lock experiment are documented in
  RELEASE_DEPENDENCY_AUDIT_2026-11-18.md. No unsafe replacement is shipped.

- Each PR's required CI and security passed before an exact-head squash merge.
- Writer rollout preceded reader: normal radar run
  [44186552753](https://github.com/browndahl/wetMap/actions/runs/44186552753)
  at `fda019b` logged `point-grid.published version-bound=true` at 22:06:52 UTC,
  13 frames / 2 new, latest observation 21:55, age 11.9 min. No manual raw write.
- First gated deployment
  [44188190116](https://github.com/browndahl/wetMap/actions/runs/44188190116):
  validation 22:15:14–22:16:58; staging starts 22:17:01; production starts
  22:18:05 and finishes 22:18:43 UTC. Same-SHA main CI 44188190166 and Security
  44188190145 passed before staging. This proves one ordering, not future uptime.
- Push-input deployment
  [44189563360](https://github.com/browndahl/wetMap/actions/runs/44189563360)
  succeeded 22:26:21 UTC; subsequent normal radar 44190096806 and synthetic
  44189988713 succeeded. No claims about real notification receipt.
- Point dry probes at 21:51 and 22:11 UTC passed all six checks. Separate normal
  two-request MISS/HIT samples are in PERFORMANCE.md, not a field p95.
- Additional normal dry-run at **22:49:42 UTC**: web, API, radar, quality,
  performance and scheduler all pass; MISS 442 ms / HIT 75 ms at CPH. Command:
  `PUBLIC_URL=https://wetmap.pages.dev API_URL=https://wetmap-api.wetmap-edge.workers.dev python3 .github/scripts/operations_probe.py --dry-run`.
  No report POST/state mutation and no load/percentile claim.
- CPU optimization normal deploy
  [44191198166](https://github.com/browndahl/wetMap/actions/runs/44191198166)
  succeeded 22:37:01 UTC, after validation and staging. Normal radar
  [44191221772](https://github.com/browndahl/wetMap/actions/runs/44191221772)
  also passed. Subsequent #46 main radar 44192353003 and synthetic 44192507080
  passed before final handoff. No observed long-run CPU/SLO conclusion yet.
- Source-delay diagnostic deployment
  [44192179797](https://github.com/browndahl/wetMap/actions/runs/44192179797)
  succeeded. Required-coordinate deployment
  [44193062004](https://github.com/browndahl/wetMap/actions/runs/44193062004)
  succeeded; normal radar
  [44193458457](https://github.com/browndahl/wetMap/actions/runs/44193458457)
  passed on `e32aa47`. This does not require injecting a real bad input.
- Future-time admission deployment
  [44194026781](https://github.com/browndahl/wetMap/actions/runs/44194026781)
  succeeded on `72b34d8`; normal radar
  [44194543306](https://github.com/browndahl/wetMap/actions/runs/44194543306)
  also passed on that exact version. All ten code PRs #39–#48 are now merged;
  this normal rollout is not a full independent release acceptance.

## Approved private raw-data audit — actually executed once

Owner approved one snapshot, ≤34 reads / 64 MB, private local temporary storage,
no subscriptions/persondata and no upload. Actual **22 reads / 10,761,702 bytes**,
stable verification-state before/after. Selected six forecast cubes and thirteen
observations; excluded one candidate missing its persistence-source observation.
Directory is private (0700). Raw files and source object identities are not in Git.

Commands, with the private snapshot root represented as `<private-snapshot>`:

```sh
.venv/bin/python apps/worker/tools/audit_precision.py <private-snapshot> --output <private-snapshot>/audit-report.json
.venv/bin/python apps/worker/tools/audit_shared_coverage.py <private-snapshot>
```

First exits **1 / BLOCKED minimum-pairs**, not success: 31 published pairs,
43 available raw pairs, 186 score comparisons, zero mismatches; persistence
identity 6/6. Local v2 oracle: 43 pairs, 176 score checks, 30 candidate comparisons,
18 Brier checks, zero mismatches; **publishedV2LedgerChecked=false**, no promotion.
Only the safe aggregate is committed in
`evidence/master-2026-11-17/raw-audit-summary.json`. Existing historical audit
results are not silently combined to claim the new C1 full-metric acceptance.

## Bounded UI and account diagnostics — actually executed

- Chrome: 1440×900, 390×844, 320×568, DA+EN. Six states, 24 API / 86 total
  GET/HEAD requests, budget 80/700; no SW/push/GPS/mutation. All showed temperature
  and one map canvas, zero page exceptions and no horizontal overflow. Phone
  screenshot visually inspected. Screenshots remain local temporary public default
  weather captures. These do not prove actual iPhone/Safari/CWV performance.
- Separate browser/server clock read at 22:19 UTC: 100 ms drift. Deliberate wrong
  clock ±10 minutes not executed.
- Seven complete UTC days of account usage read from Cloudflare analytics, only
  aggregates; current official allowances and limitations in FREE_TIER.md.
  Read-only subscriptions API 403; actual Workers plan not established.
- 22:34 UTC GitHub read: main unprotected, rulesets `[]`, production and staging
  protection rules `[]`; no account policy changed.

## Not executed / not accepted

- Independent full acceptance in a separate session; C1 ≥50 published raw pairs
  and published-v2 Brier/MAE full acceptance; V6 held-out event performance.
- Remote load/burst/chaos: **BLOCKED**, staging shares production backend/quota.
- Complete DMI measure→publish→R2→client p50/p95: historical provider publish
  timestamp unavailable; don't substitute ingestion time.
- Full HTTP OpenAPI/path/negative contract matrix, real ODIM reprojection oracle,
  live global stampede, quota-exhaustion and distributed concurrent-publisher drills.
- Physical iPhone/Android closed-tab/locked-device push timing, WebKit/Firefox,
  screen readers, 30-minute memory, ≥50 fps, throttled CWV and offline/SW update.
- Full account invoice/month-to-date artifact/ops/storage and actual Workers plan;
  no zero-cost compliance claim, no new billing permissions or service.

The local test total is not “all bugs fixed”. RISKS.md remains part of the
handoff; no release acceptance threshold or metric was weakened.

## 18 November — approved private logging and operational evidence

Authority/scope: ADR0017. Initial suite had seven true privacy failures and two
wrong-hourly-fixture cases (not product bugs). With proper minutely_15 fixture,
the exact two old precipitation log statements were reproduced locally: both
fail on coordinate/key leakage. New statements restored before full verification.
An additional null push error fails status extraction before its safe guard.
No real notification/registration/deletion, production fault or private log export.

13 sanitizer tests, eight weather/location cases, three push cases, two Python
source-boundary methods. **148 edge +38 web +2 shared +112 worker +56 scripts =
356 local-suite tests**; prior330 checkpoint is historical. Unknown event/string
values, raw fields, nonfinite times, HTTP bounds, getters/serialization and
caught descriptor failures covered. Controlled503 behavior stays unchanged.

Fresh local commands, no Turbo cache replay:

```sh
pnpm -r run lint
pnpm -r run typecheck
pnpm -r run test
WRANGLER_LOG_PATH=/private/tmp/wetmap-private-logs-build pnpm -r run build
.venv/bin/python -m pytest apps/worker/tests -q
.venv/bin/ruff check apps/worker
.venv/bin/ruff check .github/scripts/test_private_logging.py
python3 -m unittest discover -s .github/scripts -p 'test_*.py'
```

Operational read-back: Release380825934 disabled_manually, all seven other
workflows active; no running Release to cancel. Restored v1.22.4 post with
--verify-tag /--latest=false; target remains fda019bc05abc39cb2a554d8375e134bb1feefe4,
no assets; Latest remains v1.22.12 /449313487. No whole-workflow replay. Existing
logs, subscription data, retention and weather history unchanged. Provider-level
access/runtime logs aren't declared scrubbed. Independent acceptance incomplete.

## 18 November — read-only release proposal verification

ADR0018: remove the old installer from the still-disabled Release workflow; no
live publication/tag write/re-enable. Two workflow-policy methods first fail16
assertions on the old files, then pass after replacement. Existing same-SHA gate
methods remain. Planner tests use synthetic fixture repos and a disposable bare
clone for real historical replay, never deleting source/GitHub refs.

Initially incorrect abbreviated-revert and v1.22.0-patch assumptions were corrected
against the actual upstream filter/historical tag, not counted as product bugs.
The old incomplete history test was replaced by complete range replay of all13
v1.22.0–12 candidates: actual proposed tags match, source refs unchanged. A new
large synthetic input stalled before budget rejection; only its identified local
test process was stopped. Whole-batch validation and 1,024-character line bounds
now reject before parsing; maximum accepted line has a 2 s subprocess deadline.

Local Node22.22.3: **53 planner +58 scripts +148 edge +38 web +2 shared +112 worker
= 411 tests pass**. No Turbo cache replay for application commands. Lint,
typecheck, all tests, web bundle budgets and Edge dry build pass. Existing map
chunk-size warning remains, not hidden. npm10.9.8 audit of the new isolated lock:
zero known advisories at every severity, exit0; no advisory exceptions. The ten
dependency packages are not the whole application's dependency tree. No npm
publish/GitHub plugin or lifecycle scripts; no change to app pnpm lock.

```sh
node --test --test-timeout=60000 --test-reporter=dot tools/release-plan/plan.test.mjs
npm audit --prefix tools/release-plan --audit-level=low --json
pnpm -r run lint
pnpm -r run typecheck
pnpm -r run test
WRANGLER_LOG_PATH=/private/tmp/wetmap-release-plan-build pnpm -r run build
.venv/bin/python -m pytest apps/worker/tests -q
.venv/bin/ruff check apps/worker .github/scripts/test_release_gate.py
python3 -m unittest discover -s .github/scripts -p 'test_*.py'
```

Before PR creation, GitHub main is848d912, Release380825934 remains
disabled_manually; the latest12 scheduled radar/uptime executions are completed
successfully (last radar44328356445, uptime44327232795). This snapshot isn't
continuous uptime evidence. CI Node24, Security and post-merge deployment results
are pending separate live follow-through; local success doesn't imply them.

Initial PR53 head5270400: CI44328989278's release-plan(22)/(24) jobs pass in11/19s,
each including install-without-scripts, all-severity audit and all53 tests. Security
44328989277's three CodeQL languages, secrets and Trivy/SBOM also pass. This is
remote verification of the read-only tool, not a live publisher compatibility or
app performance/acceptance claim. Final exact-commit checks/deploy follow below
when available; no merge inferred merely from the initial jobs passing.

## 18 November — separate radar transfer/phase-diagnostic proposal

Read-only inventory since05:22 UTC:82 radar (81 success/1 failure),36 uptime
successful; two CI/Security runs were still in progress at that snapshot.
Run44263888361 logs observations published08:05:05.918 UTC, then processing step
times out08:09:07.623. Exact historical stalled operation unknown; no downstream
success retrospectively proves it. No private app-log or raw R2 export.

Two local assertions fail before the fix: SDK transfer config and actual broken
body retry count both5 vs expected1. Real installed boto3 transfer manager,
botocore Stubber, five queued synthetic response bodies, no sockets or sleeps.
After explicit stream budget1, four entry points (manifest/image/state/cube)
fail after one broken-body read without replacing last-good bytes or leaving a
new partial image. Eight stage tests verify125/750ms synthetic timings, unchanged
arguments/results/errors, unknown names rejected and all ten CLI boundary sites.
Full worker **125 tests** and Ruff pass. Repeated fresh script58/planner53 and
application edge148/web38/shared2 suites, plus lint/typecheck/build/bundle budgets,
pass on the combined diff: **424 local tests**, not a worker-only inference.
ADR0019 states the remaining risk:
this isn't a hard total transfer deadline or proof the morning timeout is fixed.
CI/normal rollout pending; no workflow timeout increase or production fault test.

### PR53 approved merge and normal rollout closure

Owner explicitly approved PR53's merge/normal deployment after the approval
check required that authority. Merged main975d7b4189ff5b35aa27ca4692a058b4e1b0e4f6.
Same-main CI44329987169 and Security44329987461 pass. Deploy44329986843:
validate14:57:18–14:59:08 UTC, staging14:59:41–15:00:37, production15:01:29–15:02:14,
all success. Normal read-only dry probe15:02:52 UTC passes all six checks, no POST/
push/load. Point sequence MISS534ms /HIT70ms atCPH is two observations, **not p95**.
Release380825934 remains disabled_manually; all seven other workflows active.
Latest remains v1.22.12/id449313487 and v1.22.4 tag remains
fda019bc05abc39cb2a554d8375e134bb1feefe4. No live publication by the new planner.
The separate radar transfer proposal above isn't part of this deployed commit.

## 18 November — local UI follow-up (no rollout)

The three new regressions failed on the reviewed implementation: no native
map-centre action and no rain/point recovery action. After implementation,
`pnpm --filter @wetmap/web run test --reporter=dot` passed **41/41**:
centre and pointer input produce the same location; an empty rain response is
not dry, then recovery displays returned dry data; the rain retry stays
disabled in flight; a failed point refresh uses the existing three retries,
then recovers without refetching the rain query. The pre-existing radar source
test now checks the visible dBZ unit and still checks the method tooltip.

`pnpm --filter @wetmap/web run lint`, `typecheck` and `build` passed.
Gzip budgets (bytes, before → after / limit): entry 97,979 → 98,552 / 110,000;
lazy map 291,778 → 292,227 / 320,000; worker 147,628 → 147,628 / 170,000.
The pre-existing MapLibre >500 kB advisory remains. No latency/FPS claim.

- In-app browser, synthetic API on loopback; normal OpenFreeMap basemap only.
  At 320×568, 390×844 and 844×390, all five mobile More map controls measured
  44×44 px and passed hit tests at centre and four inset corners. GPS/push
  were not activated. At 320 px: ArrowRight on canvas, Tab through the map
  controls, Enter on Select map centre → selected coordinate, Rain view and
  focus on weather panel. The map buttons showed a solid inset focus ring.
- Header: language control centre remained clickable at widths 1200, 1201,
  1280, 1366 and 1440 px. At 1280, the language control switched DA → EN;
  the header and search retained an 8 px gap in both.
- Local 503 responses exposed separate manual buttons and automatic retry
  copy. Activating rain retry with Enter disabled the button during the
  request. Recovery to valid data is covered by regression tests.
- At 320 px, four columns, no horizontal document overflow, and fitted
  12 px labels: dry, weak echo, light, moderate, heavy, radar and model.
  Browser-computed opaque-panel colours converted to sRGB give approximately
  9.64:1 (radar label; formerly 1.98:1 over the moderate bar) and 8.19:1
  (model/intensity). The test covers the visible dark UI, not an unused theme.
  No radar colour, bucket, source or data-confidence calculation changed.

Local screenshots saved alongside the review (390 px rain, 320 px controls
and errors, and 1280 px header). The restarted mock recorded 79 local GETs
and zero mutation attempts, a partial count after a fixture update. Not
verified: physical iPhone/Safari, screen-reader speech, real 200% browser zoom
(in-app shortcut did not change viewport or scale), actual OS reduced-motion
setting, full acceptance matrix or production deployment.
