# Open risks — master checkpoint, 17 November 2026

This is an implementation checkpoint, not an independent release acceptance.
No promise that GitHub/DMI/Cloudflare will never fail. Health must stay honest.

| Priority              | Risk / evidence                                                                                                                                                                                                                           | Next safe action / acceptance boundary                                                                                                                                                                                                  |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P1 correctness        | Current approved raw snapshot reconstructs only 31 published pairs, below unchanged C1 minimum 50; no independently checked published-v2 ledger/Brier acceptance. Legacy masks differ on 38/43 available pairs.                           | Keep v2 shadow-only and all gates unchanged. Plan a separately approved bounded representative audit/event set; do not redownload under the already-used one-snapshot permission or lower the threshold.                                |
| P1 cost/CPU           | Seven-day cron p99 41.854–52.469 ms vs published Free 10 ms; plan API 403. R2 has no hard spend cap; sampled storage previously exceeded 10 GB, not proof of a monthly bill.                                                              | Confirm account plan through an authorised account view, profile real post-release CPU and measure month-to-date ops/storage. No upgrade or broader token scope assumed. Local CPU optimization is not platform compliance.             |
| P1 testing safety     | Staging Pages points to production API and shares production account quota.                                                                                                                                                               | Remote load/burst/chaos **BLOCKED**. A separate free backend/account isolation proposal needs review and an explicit request budget. No production fault injection.                                                                     |
| P1 release control    | Exact-commit CI/security gate now enforced, but main `protected:false`, zero rulesets and empty staging/production protection rules (22:34 UTC read). A privileged actor can still change workflow/config or bypass the intended process. | Owner-approved branch/ruleset/environment policy; do not silently lock repository access. Small PRs, exact-SHA merges and CI gates remain in use.                                                                                       |
| P1 external freshness | Three morning ingestion jobs processed successfully but source observation stayed 07:25 UTC. Provider publication/cache evidence from that time is absent.                                                                                | New safe handoff codes improve future diagnostics; cannot reconstruct historical provider cause or guarantee cron scheduling. Never reset observation age from ingestion time.                                                          |
| P1 privacy            | Previous Edge app logs contained coordinate/key/error fields; platform request/access logs are a separate surface.                                                                                                                        | Owner approved future app-log minimisation, implemented through ADR0017 and regression tests. Existing logs, retention and subscription data unchanged. No private historical-log export; provider/platform logs not declared scrubbed. |
| P2 observability      | Historical quality validator failure 43948778540 lost its rejected report/cause. New static classification cannot retrospectively prove the root cause or false alarm.                                                                    | Preserve static diagnostics/public report hash on future rejection. Unknown errors still fail. No raw data artifact.                                                                                                                    |
| P2 consistency        | Point range reads are ETag-bound; map images, model forecasts and point cache still have independent lifetimes. Two-slot publication isn't a transaction across every public object/cache.                                                | Test cross-version fetch/cache refresh with local fixtures and visibly retain timestamps/sources. No claim of globally atomic releases.                                                                                                 |
| P2 cache growth       | R2 model-cache keys can grow with distinct coordinates. Only approved old **derived WebP** cleanup is in scope.                                                                                                                           | Inventory prefix growth and propose per-prefix bounds. Do not impose blanket deletion on radar/verification history or change personal retention without approval.                                                                      |
| P2 scale/CPU          | Base64 work reduced locally, but cron includes storage, encryption and provider push; scan cap is still 40 and isolate coalescing isn't global.                                                                                           | Budgeted real analytics and local scan profiling; no claim of end-to-end notification latency or global stampede prevention.                                                                                                            |
| P2 delivery           | Closed-tab/locked-device push timing depends on browser/OS/provider; stale/expired delivery protections do not prove on-time receipt.                                                                                                     | Physical iPhone/Android matrix **HUMAN**, including receipt/discard evidence; no unsolicited production notifications.                                                                                                                  |
| P2 client acceptance  | Six Chrome screenshot states pass a limited inspection, not WebKit/Firefox, physical devices, screen readers, wrong clock ±10 min, offline/SW update, CWV, 50 fps or 30-minute memory. Light theme absent; map chunk warning persists.    | Run an independent acceptance session and controlled local fixtures. Do not suppress the warning or raise bundle budgets as a cosmetic fix.                                                                                             |
| P2 quality            | Live gates or high sample counts don't prove seasonal/regional skill, independent events or automatic learning. Long-range uncertainty remains.                                                                                           | Fixed date splits, representative held-out events and shadow-only V6 benchmarking before any promotion. No test-data tuning.                                                                                                            |
| P2 upstream terms     | DMI/Photon hard quotas and real fallback volumes not established; Open-Meteo free terms are non-commercial/no SLA.                                                                                                                        | Confirm terms/usage before growth; don't infer free unlimited commercial use.                                                                                                                                                           |

## Required next release assessment

18 November follow-up: GitHub notes-push 500 left old tag v1.22.4 without a
Release post. No blind publisher replay; separately requested approval for only
that metadata repair. Exact-SHA Release gating is separate from this provider
failure. Action runtime installation also reported 14 high/1 critical npm
advisories; exact packages/reachability need audit before claiming supply-chain
coverage. No evidence of exploitation, no blind dependency upgrade.

See RELEASE_DEPENDENCY_AUDIT_2026-11-18.md: current gated publisher still logs
14 high/1 critical; fresh same-core isolated lock probe still has 10 high and
isn't adopted. No unreviewed runtime shipped. Requested owner choice for a
temporary Release-only pause; not applied. Do not infer that green CI/security
or successful release means this separately installed tree is accepted.

Use a fresh separate acceptance session per WETMAP_MASTER_PROMPT.md. Report
PASS/FAIL/BLOCKED/HUMAN per check and release only if every blocking check passes.
This implementation session does not generate a misleading ACCEPTANCE_REPORT.md
or claim that all eight phases, model V6 or the zero-cost goal are complete.

## 18 November — owner-approved risk containment

This updates the earlier pending-approval paragraphs: Release380825934 is now
manually disabled, all other workflows stay active. v1.22.4 missing post restored,
tag/assets/Latest unchanged. Future Edge app-log minimisation approved and
implemented through ADR0017/tests; existing logs/retention/subscriptions untouched.
Platform/provider access logs are separate and not declared scrubbed. Supply-chain
advisories remain unresolved: pausing publication is containment, not a package
fix; don't re-enable automatically. C1, CPU/free-plan and independent acceptance
limitations above remain.

## 18 November — read-only release replacement

ADR0018 removes the vulnerable installer from the disabled Release workflow,
without resuming it. The ten-package proposal-only lock has zero known npm
advisories at this audit, exact versions, scripts-off install and mandatory
Node22/24 CI tests/audit. Tests replay all13 v1.22.0–12 version decisions; no
publication is possible in the replacement code. This is not a secure full
publisher acceptance: notes/provider/idempotent partial-success recovery still
need separate verification. Don't automatically re-enable or revert to running
the old installer. Other risks and unchanged quality/cost gates remain open.
