# ADR 0018 — Replace the paused publisher with a read-only planning stage

Date: 18 November 2026 (Europe/Copenhagen). Status: staged implementation;
**automatic Release publication remains manually disabled**.

## Context and decision

ADR0017 paused only GitHub Release publication with explicit owner approval. The
old action dynamically installed a large dependency graph with high/critical npm
findings. A fresh same-core 25.0.9 lock still fails its audit. A blind upgrade or
downgrade is not accepted. The new major is not a compatible patch: official
[v26 release notes](https://github.com/semantic-release/semantic-release/releases/tag/v26.0.0)
require Node26.13 and introduce a new core/npm major. The currently reported
[picomatch advisory](https://github.com/advisories/GHSA-fc5q-39xc-vjpf) lists no
patched version (checked 18 November). No invented safe override or ignored
advisory is used. Findings aren't proof of exploitation or the cause of the
historical remote GitHub500.

Remove the action from the disabled workflow instead of installing its graph.
Replace it with a narrowly scoped **read-only proposal** using the existing
Angular preset/parser/filter and semver components. It preserves the supported
version decisions, not the publishing lifecycle. Exact dependency versions and
integrities are committed in an isolated npm lock, with scripts disabled during
installation and every known advisory rejected by CI at `--audit-level=low`.

The ordinary CI workflow tests this path on Node22/24 with full tag history,
read-only permissions and checkout credentials not persisted. Dependabot tracks
this separate lock. The disabled Release path retains the same trusted-main/
exact-SHA CI+Security gate, but now has only contents/actions read permission.
Its remaining commands can neither publish nor create a tag. There is no npm
publish plugin, GitHub publisher, network client, Git write command or token in
the planner. The gate's GET-only token remains scoped to its own steps.

## Compatibility and boundedness

Read config from the candidate Git object, not dirty disk state. Reject all policy
overrides/unsupported channels rather than approximating them. Select the highest
reachable stable tag, parse the entire intervening range, filter recognised
reverts and apply the unchanged default literal rule priority. In particular,
Angular's bang-header and abbreviated-revert behaviour is preserved. Do not claim
general semantic-release equivalence beyond this supported WetMap policy.

Limits: 500 commits/tags, 16 KiB/message, 2 MiB/batch/Git output, 1,024 characters
per line, 10 s/Git command and 30 s cumulative Git reads. Validate the whole batch
before invoking the regex-based parser. Errors stop with static codes and never
print commit text/config/raw exceptions. These bounds deliberately fail oversized
input, not fabricate a version. Test suite 60 s timeout; maximum permitted line
has a separate bounded 2 s parser-process test. No general parser-complexity or
supply-chain immunity claim.

## Evidence and rejected assumptions

- Two initially incorrect test assumptions (abbreviated revert cancellation and
  v1.22.0 being patch) were corrected against actual parser/source/tag evidence;
  they aren't claimed as fixed product defects.
- The initial history test checked only one commit. It was replaced before
  adoption by replay of **all 13 actual v1.22.0–12 candidates**, with each tag
  removed/restored solely in a disposable local bare clone. The proposed version
  matches each real tag (one minor, twelve patches); original refs unchanged.
- A newly added 129×16 KiB synthetic text case exposed expensive parsing before
  total-budget rejection. Its identified local test process was stopped; a
  two-pass validator and pre-parser line bound now reject that case. This is a
  planner test hardening result, not evidence of an app/production outage.
- 53 planner tests pass locally on Node22.22.3. npm10.9.8 audit reports zero
  known advisories at all severities for this lock; 10 dependency packages
  (metadata `prod:11` includes the root), no dev packages. This does not erase
  historical publisher findings or establish future vulnerability absence.
- Two workflow-policy methods reproduce 16 failed assertions on the old paths,
  then pass. Exact-SHA gate tests remain; script suite now58 methods. Remote CI
  Node24/security/deploy results must be recorded separately once available.

Lock SHA-256:
`67a67ce877bf479e561867cf989f3405ddd129f8bf9de109056a859d19ba724b`.
Implementation and commands: [planner README](../../tools/release-plan/README.md).

## Non-goals, authority and rollback

No re-enable, tag creation, release publication, historical ref/notes rewrite,
blind partial-publisher replay, dependency ignore or gate relaxation. No extra
R2 export, personal data/log export, push delivery, weather/model change, new
service or billing/retention change. Local fixture repositories are disposable;
the source repository and GitHub tag history are not modified by tests. This CI
work does not resolve C1, actual Workers plan/CPU or independent app acceptance.

Publication remains a separate unresolved milestone: release-note generation,
provider contract, duplicate/partial-success recovery and tested idempotency all
need review before any live publisher adoption. Do not call this a safe full
publisher or automatically resume it when deployment succeeds. A reviewed revert
can remove the planner; the workflow must stay paused even after such a revert,
because reverting would restore the old vulnerable installer. App deployment,
radar ingestion, monitoring and push are separate and remain active.
