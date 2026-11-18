# Release dependency audit — 18 November 2026

Original probe verdict: **unresolved; no experimental runtime shipped**. The
later staged read-only replacement is recorded at the end of this document.
This is separate from
the exact-commit Release gate and from weather/model correctness. No compromise,
secret leakage or causal connection to GitHub's remote notes-push 500 is proven.

## Three different evidence scopes — do not compare their counts

1. Historical runner 44186050603's npm installation log reports 47 vulnerabilities,
   including 14 high /1 critical. Its exact effective runtime lock wasn't archived.
   The action dynamically installs the requested semantic-release version, so the
   public source lock alone does not recreate that historical tree.
2. Two bounded public requests: fetched the public action v7 lock and submitted
   **only its public package names/versions** to npm's bulk advisory endpoint.
   No credentials, private repo source/data or package installation/execution.
   362 runtime package names; 34 moderate /24 high /8 low /1 critical **advisory
   records**, including duplicate advisories for different vulnerable ranges.
   These aren't npm's counts of affected packages/metavulnerabilities.
3. Local isolated package-lock-only probe using the same core version **25.0.9**,
   existing Node 22.22.3 /npm 10.9.8. Registry-resolved fresh transitive graph:
   npm audit reports 31 moderate /10 high /0 critical, 41 affected package/meta
   entries; metadata reports 441 prod /444 total dependency entries. This still
   fails the high-severity audit, so it is **not adopted**. No lifecycle scripts,
   package execution, live release or token-bearing publisher were run.

The public advisory response identifies e.g. undici, brace-expansion, ip-address,
tar and picomatch. Its critical tar record is
[GHSA-23hp-3jrh-7fpw](https://github.com/advisories/GHSA-23hp-3jrh-7fpw);
the fresh probe also reports the picomatch record
[GHSA-fc5q-39xc-vjpf](https://github.com/advisories/GHSA-fc5q-39xc-vjpf).
These identify registry findings, not demonstrated exploit reachability in the
configured three-plugin GitHub-only release path.

The new trusted gate **did** work in normal production run 44197456654 on
`b2de29c`: checks ready 23:13:38 UTC, current-head check passed, then publication
completed at 23:14:04 UTC (17 November). v1.22.12 was published. That same
installation still reports 47 vulnerabilities /14 high /1 critical. A successful
publisher and a correctly ordered gate do not clear this dependency risk.

## Reproducible probe definition

An isolated manifest, outside the pnpm app workspace, contained only:

```json
{
  "name": "wetmap-release-tools",
  "version": "0.0.0",
  "private": true,
  "engines": { "node": ">=22.14.0" },
  "dependencies": { "semantic-release": "25.0.9" }
}
```

Commands executed with that temporary probe under `tools/release`, then moved
out of the repo. They are not commands to run against production:

```sh
npm install --prefix tools/release --package-lock-only --ignore-scripts --no-audit --no-fund --fetch-retries=1 --fetch-timeout=20000 --cache /private/tmp/wetmap-release-npm-cache
npm audit --prefix tools/release --omit=dev --audit-level=high --json --fetch-retries=1 --fetch-timeout=20000 --cache /private/tmp/wetmap-release-npm-cache
```

Install/lock resolution took about 7 s; audit exits **1**. Fresh lock SHA-256:
`110ecf67cebec0976a6cdc7bcbe54f0d57ecdaf78c9178197b902173b1af5d80`.
Only the two public package/lock files were generated; both were moved to a
temporary local experiment folder. No new app dependency, lock, node_modules,
release workflow installation, runtime or registry setting is committed.

Audit's suggested automatic fix includes a major **downgrade** to semantic-release
15.14.0. It is not a safe reviewed remedy and wasn't applied. No forced audit fix,
ignored advisory, relaxed security gate or blind major replacement is used.

## Next safe work

- Capture/reconstruct the exact action effective tree without secrets; distinguish
  wrapper, core, unused npm-publish plugin and actual configured-plugin reachability.
- Evaluate maintained patches/compatible pins and test old/new release decisions
  on isolated local repositories, with no production GitHub publishing or real token.
- Require a passing audited lock and provider/plugin compatibility evidence before
  adopting a replacement. A lockfile isn't itself a security fix.
- Existing repository Trivy/SBOM success doesn't prove coverage of an action's
  separately installed runtime. No claim of complete supply-chain acceptance.

The active flow retains the scoped trusted-SHA gate (ADR 0016). The missing old
v1.22.4 Release post still awaits explicit metadata-repair approval; don't rerun
the partially completed publisher. Existing privacy/raw-audit/retention/billing
boundaries remain in force.

Owner approval has also been requested to **temporarily pause only automatic
GitHub Release publication** pending a reviewed safe runtime. No pause has been
applied. App deploy, radar, CI, monitoring and push are separate and would remain
in scope to run normally. This is a scoped containment decision, not evidence
that compromise happened or permission to change settings without approval.

## 18 November — approvals granted and containment applied

The earlier approval requests are now granted. Workflow380825934 (Release) is
verified disabled_manually; all seven other workflows remain active. Existing
v1.22.4 Release post restored with --verify-tag /--latest=false, tag target fda019b
unchanged, no assets; Latest still v1.22.12. No publisher replay. Future app-log
minimisation implemented under ADR0017, not historical log deletion/retention.
This contains publisher exposure but **does not remediate** dependency findings.
Do not resume automatic publication until a safe runtime is verified/owner directs.
App deploy, radar, CI, monitoring and push remain separate and active.

## 18 November — staged read-only replacement, not publication resumption

The disabled Release workflow no longer installs the old action/core graph. Its
replacement only prints a release proposal, with contents/actions read permission,
no persisted checkout credentials and no publisher. The manual workflow pause is
not lifted. CI now verifies the locked planner on Node22/24; exact-SHA/security
gating stays unchanged. No advisory suppressions, version-rule changes, tag/notes
writes or Release posts are part of this replacement.

The isolated ten-package planner lock uses the same Angular preset/parser/filter
versions as the 25.0.9 reference and semver, without the wrapper/glob/npm/GitHub
publishing dependency chain. Its npm audit passes all severities with zero known
advisories; this isn't a patch to the original tree or proof of a secure complete
publisher. The read-only stage passes 53 local tests including replay of all13
actual v1.22.0–12 tags. See [ADR0018](adr/0018-read-only-release-planner.md) for
exact scope, budgets, upstream references, test corrections and remaining gaps.
Historical publisher advisories remain evidence; future actual publication is
still paused pending a separately tested/reviewed implementation.
