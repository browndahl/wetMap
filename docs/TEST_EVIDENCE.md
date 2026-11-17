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
