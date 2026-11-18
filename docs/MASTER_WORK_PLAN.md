# Master programme — execution plan, 17 November 2026

Authority: owner adopted `WETMAP_MASTER_PROMPT.md` and explicitly requested work
without routine phase pauses. This supersedes the old forecast-first priority and
the routine Phase 0 approval pause, not the explicit stop-and-ask boundaries for
retention, personal data, cost, gates or irreversible operations. The previous
handoff remains historical evidence, not current truth. No production fault/load
injection and no independent acceptance claim in this implementation session.

## Phase 0: read-only baseline and audit

- Inspect source/workflows, five post-release failures, live public status and a
  bounded direct DMI catalogue read. Preserve historical evidence in BASELINE.
- Run fresh local deterministic tests; validate the quality/scoring contracts.
- Verify provider allowances against official docs. Establish what account usage,
  raw verification inputs, isolated staging and real devices are actually available.
- Write FINDINGS, FREE_TIER and test/risks evidence. Missing resources are BLOCKED,
  never inferred PASS. No bulk history download or new archive.

## First correctness/stability work, only after local reproduction

1. Input-failure preservation: test an empty/malformed catalogue and unsafe metadata.
   Files: worker DMI adapter, ingestion guard and tests. Acceptance: errors reject
   before manifest publication, existing manifest unchanged, no accidental upload;
   valid data remains compatible. Do not invent fallback observations.
2. Monitoring diagnostics: reproduce lost validator cause. Files: operations probe
   and deterministic script tests. Acceptance: safe stable reason codes, preserved
   validation/deadlines, no stderr/credentials/raw private data leakage; all six
   checks still run. The historical quality root cause stays unknown without evidence.
3. Source-delay handoff: inspect the precise policy and logs; improve observability
   only if reproduced. No relaxed freshness or false-green status.

Each concern gets a separate reviewed diff/PR, full CI/security and rollback by
reverting its commit. No blind major dependency upgrades or model/gate changes.

## Subsequent independent work

- API/version consistency and missing CI/deploy gates, local mocked failure drills.
- Published raw-pair verification if bounded, checksum-verified inputs are available.
- UI/time/offline checks with local fixtures; remote load is blocked until account
  quota isolation and request budgets are proven.
- Performance comparisons only with comparable before/after workloads; real-device
  checks and full independent acceptance remain separately labelled.

No automatic lifecycle is installed on histories to satisfy a blanket “every
growing prefix” requirement; that conflicts with existing preservation/approval.
No new paid service, account plan, personal-data field or storage expansion.

## Execution checkpoint

Confirmed fixes are separate PRs #39–#48: last-good input preservation, safe
quality/handoff reasons, version-bound point publication/reads, exact-SHA release
gate, bounded push input, bounded repeated weather decoding and required query
coordinates and future timestamp rejection before publication. CI/security precedes merges; normal release/ingestion evidence is
in TEST_EVIDENCE.md. Current open privacy-log change awaits its explicit approval.

The one approved private snapshot has been consumed: 22 reads / 10.76 MB. It
doesn't satisfy the ≥50-pair published/full-metric criterion. No automatic second
export or raw GitHub artifact. Seven-day usage measured; actual plan/CPU
compliance unresolved, no upgrade. Remote load blocked by shared prod staging.

Next priority is not feature expansion: complete correctness evidence and free
CPU guardrails, agree isolated testing/protection, then held-out V6 evaluation.
Routine phase pauses were waived, not these scope/resource/approval boundaries.

18 November follow-up: #50 extends exact-SHA/security gating to GitHub Releases,
separate from deploy; its normal live ordering passes. Remaining action dependency
warnings aren't fixed by gating. A fresh same-version lock experiment fails the
high-severity audit and isn't shipped. See the dedicated release audit. Temporary
Release-only containment, old Release-post repair and future privacy-log changes
have separate explicit approval questions; no setting/data change is assumed.

## 18 November — approved scope executed

Owner approved all three: Release workflow380825934 is disabled_manually (all
other workflows active); missing v1.22.4 Release post restored without tag/assets/
Latest change; future Edge log projection implemented with tests (ADR0017).
This supersedes the earlier pending-approval checkpoint, not other boundaries.
No previous log/retention/subscription/history change. Dependency remediation,
CPU/plan compliance, C1 and independent acceptance remain unresolved.

## 18 November — read-only release planning stage

ADR0018 replaces the old action in the **still manually disabled** Release
workflow with a proposal-only path and read-only permissions. No automatic
resumption, live tags, Release posts or history rewrite. Ordinary CI verifies the
small pinned/audited planner on Node22/24, including all13 real v1.22.0–12
decisions; same-SHA/security gates unchanged. Actual publishing/recovery remains
a separate unaccepted milestone. C1, free-plan CPU and independent acceptance
are not made green by this tooling work.
