# Read-only release planner

This is a staged replacement, **not a publisher or a drop-in semantic-release
implementation**. The GitHub Release workflow remains manually disabled. CI can
verify a proposal without GitHub credentials, network calls by the planner,
creating tags/notes, pushing refs or creating Release posts/assets.

From the repository root, with the full existing tag history:

```sh
npm ci --prefix tools/release-plan --ignore-scripts --no-audit --no-fund
npm audit --prefix tools/release-plan --audit-level=low
npm test --prefix tools/release-plan
node tools/release-plan/plan.mjs --sha FULL_CHECKED_OUT_COMMIT_SHA
```

Installation/audit contact npm with public package metadata, unlike planning and
tests. Never pass a GitHub/npm token to these commands. The isolated lock isn't
part of the pnpm application workspace. Dependencies are exact-pinned; Dependabot
and the Node 22/24 CI matrix must pass after any update.

## Supported policy only

The candidate's immutable `.releaserc.json` must be exactly WetMap's current
main-only, `v${version}`, three-plugin default policy. Alternate config files,
package-level overrides, custom rules, prerelease/build tags, shallow/missing
history and a checkout/candidate mismatch fail closed. This is intentionally
narrower than a general release engine. Policy changes need an explicit reviewed
planner update, not a silently ignored option.

The same Angular parser/preset and revert filter versions as the 25.0.9 reference
tree are used. Default literal rules: breaking notes → major; recognised revert,
`fix`, `perf`, `FIX` → patch; `feat`, `FEAT` → minor. Highest surviving impact wins;
other types don't bump a version. The default Angular header parser does **not**
recognise `feat!:` without a `BREAKING CHANGE` note; the upstream revert filter
requires exact hashes, not abbreviated-prefix equivalence. These existing
behaviours are preserved, not silently changed to another convention.

The highest reachable stable version tag is the base. Already tagged means only
that a tag exists, **not** that its GitHub Release post exists or was published
successfully. No decision triggers a write, including `proposed`.

## Boundaries and evidence

- 500 candidate commits /500 reachable version tags; 16 KiB per message, 2 MiB
  batch/output budget, and 1,024 characters per line before regex parsing.
  Exceeding these limits stops planning with a static error code.
- Git reads: no shell, replace objects, inherited tokens/global config, pager,
  prompt or network; 10 s per command and 30 s cumulative Git-read deadline.
  Parser input limits are not a general proof against all regex complexity.
- JSON output contains only candidate/base/version/decision metadata. No raw
  message, error text, credential or arbitrary config output. Normal Node error
  handling here isn't a sandbox for malicious imported application code.
- 53 local tests include a real-history oracle: replay each v1.22.0–12 candidate
  after removing only its own tag **in a disposable bare clone**, compare the full
  range's proposed tag to the actual tag, and prove source refs unchanged. Other
  tests cover major/minor/patch/no-release, reverts, unsupported policies, dirty
  worktree, replace refs, shallow history and rejected publisher flags.
- Test suite has a 60 s timeout; maximum-line parser test has a 2 s child-process
  deadline. A larger synthetic unbroken-line test originally stalled and was
  stopped; the new pre-parser rejection fixes that observed test path.

No release notes, GitHub API compatibility, idempotent publication/recovery or
distributed publisher behaviour is implemented or accepted here. Those need
separate design/tests before resuming publication. See
[ADR0018](../../docs/adr/0018-read-only-release-planner.md).
