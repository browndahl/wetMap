# ADR 0017 — Approved private app diagnostics and Release containment

Date: 18 November 2026 (Europe/Copenhagen). Status: owner-approved implementation.

## Explicit authority

Owner approved exactly three actions: remove location/raw-error fields from future
app logs, restore only the missing v1.22.4 Release post, and temporarily pause only
automatic GitHub Release publication. No approval to delete existing logs, change
retention/subscriptions/history, upgrade billing or weaken forecast/security gates.

## Application logging decision

Production Edge diagnostics use one closed projection boundary (`logging.ts`).
Only registered static event codes, known source/provider/fallback/outcome values,
finite timing values and validated HTTP status codes can reach console output.
Unknown event text becomes one fixed invalid-event code. Arbitrary fields, location
coordinates/search terms, cache/subscription keys, endpoints and raw error objects
aren't forwarded, including keys accidentally included in a future call's object.
Getters/custom serialization aren't invoked, nested objects aren't forwarded, and
descriptor failures are caught without printing their errors. Log severity and
useful provider/timing diagnostics remain. This isn't a sandbox for arbitrary
malicious JavaScript supplied by a caller.

All direct production Edge console writes are centralized; a source-inventory
regression checks that entry points can't accidentally restore direct console
writes. This is not a general static taint proof against malicious code changes.
App responses, rounded subscription data, notification rules/deletion behavior,
existing logs and retention remain unchanged. A null push exception is safely
classified without exposing payloads or throwing while extracting a status code.

Scope is the explicit Edge application logs found by this audit. Cloudflare's
platform/access-request/uncaught-runtime logs, upstream provider logging and their
retention are separate surfaces; no claim that those have been scrubbed or read.
No export/inspection of private historical production logs is used to verify this.

## Operational changes and evidence

- Disabled precisely workflow **380825934 / release.yml**. Verified
  `disabled_manually`; CI, Deploy, Radar ingestion, Security, Synthetic uptime,
  retention and Dependabot remain active. No active publisher needed cancellation.
  Re-enable only after reviewed safe-runtime evidence/owner direction; no automatic
  resumption merely because a new code deployment succeeds. This contains the
  dependency risk, **does not remediate** the dependency advisories.
- Restored only the published description for existing v1.22.4 with `--verify-tag`
  and `--latest=false`. Tag still targets `fda019bc05abc39cb2a554d8375e134bb1feefe4`;
  no assets, no publisher replay. Latest remains v1.22.12, ID449313487.
- Nine privacy regression paths reproduced: seven in the initial baseline run;
  two precipitation tests initially used a wrong hourly fixture and were rerun
  with the proper minutely fixture plus the exact old logging statements, both
  failing on location/key leakage. Fixture failures aren't counted as product bugs.
- One additional null-push-error case fails before safe extraction, then passes.
  13 sanitizer tests, 8 forecast/location cases, 3 push cases and 2 source-policy
  methods; full suite 148 edge /56 scripts, plus existing38 web/2 shared/112 worker
  = **356 tests**. Live CI/security/deploy follow-through is in TEST_EVIDENCE.md.

No extra network calls, cloud service or stored telemetry. Same event count,
smaller/bounded scalar log records; actual CPU/free-tier compliance is still not
established. No new PII field. Unknown/failed weather states remain unhealthy.

## Rollback

Reviewed revert can undo the projection implementation, but would reintroduce the
approved privacy defect: don't do it casually. Existing logs weren't deleted.
The Release workflow pause is reversible (`gh workflow enable 380825934`) only
after the safe replacement is reviewed; it doesn't gate app deploy or radar.
The historical metadata repair never required changing the tag or Latest release.
