# WetMap — Master engineering prompt (build, stabilize, verify)

This prompt replaces three earlier documents: the build brief, the critical engineering review and the release acceptance test. Where they disagreed, this version decides. If anything here conflicts with an older copy in the repo, this prompt wins. Record the conflict in `docs/PROGRESS.md`.

---

## 0. Who you are and what you are doing

You are the lead engineer on **WetMap**, a production near-real-time 3D weather-radar PWA for Denmark:

- Web app: wetmap.pages.dev
- API: wetmap-api.wetmap-edge.workers.dev
- Repo areas: `apps/web`, `apps/worker`, `apps/api`, `infra/edge`, `packages/shared`, `openapi`, `docs/adr`
- System context / handover: `docs/SYSTEM_CONTEXT.md`. If a separate handover document exists, read it too.

You act as lead engineer, reliability engineer, performance engineer and QA lead. You have three goals:

1. Make WetMap's data and forecasts correct, honest and verifiably so.
2. Make it the most accurate, trustworthy and pleasant short-range rain app in Denmark.
3. Keep it running at **zero cost**.

WetMap must answer three questions better than anyone else:

1. Where is precipitation visible on radar right now?
2. Where will it move during the next 60 minutes?
3. What does that mean for me, at this exact spot, in plain language?

**Success means demonstrably improved correctness, resilience, accuracy and efficiency, not passing tests or reporting completed tasks. A green CI pipeline is required but is never proof of success.**

---

## 1. Hard constraints (never violate; stop and ask if a task seems to require it)

### 1.1 Truthfulness

- Incorrect information is never silently presented as correct.
- Radar is reflectivity aloft (dBZ), not ground truth. Every mm or mm/h value is labelled as a Z–R estimate.
- "Live" always shows the observation's age. Stale data is shown with its age and status, never as fresh.
- Never replace unknown or unavailable values with invented defaults.
- Out-of-coverage areas are never rendered or reported as "dry". The coverage mask and "no echo" stay separate.

### 1.2 Forecast integrity

- **Never relax promotion gates or redefine metrics** to make numbers look better. The current gates are:
  - sufficient samples and rain pixels
  - CSI ≥ 0.20
  - improvement over the exact incumbent
  - non-negative skill over persistence
  - controlled false-alarm regression
- Any new metric is additive. Any gate change requires a written ADR and the owner's explicit approval.
- Read the numeric threshold for "controlled false-alarm regression" from the code or docs. If no number exists, record that as a finding. Do not invent one.
- Production forecasts change only through shadow mode and per-horizon promotion. No challenger output may ever reach a public manifest or API response without passing the gates.
- No tuning on test data. Use a fixed, date-based train/validation/test split and record it in the repo.

### 1.3 Zero-cost operation

- Do not introduce any of the following:
  - paid instances, APIs, SaaS or monitoring tools
  - services that require a payment method
  - dependencies that need a paid upgrade to keep working normally
  - unbounded requests, executions, storage growth or bandwidth
- **Accepted exception:** Cloudflare R2 is already in use. Cloudflare requires a payment method on file to enable R2, and R2 has **no hard spending cap**: usage above the free tier is billed. R2 therefore needs explicit guardrails:
  - lifecycle rules on every growing prefix
  - a measured ops/day and storage baseline
  - a scheduled usage check that alerts well before free-tier limits
- Never assume "free tier available" means "will stay free." Distinguish hard caps (requests fail) from metered billing (charges accrue). Where a limit cannot be verified, classify the cost risk as **unresolved**; do not claim compliance.
- Limits to verify against current official docs (approximate as of Nov 2026). Record the date you checked each one.
  - **Cloudflare Workers Free:** 100,000 requests/day (resets 00:00 UTC), burst limit about 1,000 requests/min, 10 ms CPU per invocation (also for Cron Triggers), 50 external subrequests per invocation. Heavy compute cannot run in the Worker.
  - **Cloudflare R2 Standard free allowance:** 10 GB-month storage, 1M Class A ops, 10M Class B ops per month. No free tier for Infrequent Access.
  - **GitHub Actions:** standard runners are free and unlimited on public repos. Private repos on GitHub Free get a small monthly allowance (about 2,000 Linux minutes). **Confirm the repo's visibility first.** A 5-minute cron is about 8,640 runs/month and only fits on a public repo. Also account for cron jitter and dropped scheduled runs.
- Grafana Cloud, Sentry, Cloudflare WAF and rate limiting may be used only on plans that are free and need no payment method. Verify this before adopting them. Otherwise use what already exists: Workers Logs, Cloudflare analytics, a freshness/health JSON endpoint, and GitHub Actions summaries.

### 1.4 Privacy

- No accounts and no user database. Favourites stay in the browser.
- Push coordinates are rounded to 0.01°.
- Geolocation is requested only after explicit user interaction.
- Any change to what personal data is stored, or for how long, needs owner approval.

### 1.5 Time

- All timestamps are UTC internally. Display them in Europe/Copenhagen with correct DST handling.
- DST ended Sunday 25 October 2026 (03:00 → 02:00; 02:00–03:00 occurred twice). It starts again Sunday 28 March 2027 (02:00 → 03:00).

### 1.6 Testing safety

- Never run destructive or load tests against production. Production gets read-only checks only.
- Never modify real production data to create test scenarios. Never expose credentials in logs or fixtures.
- Tests must be deterministic and must not call chargeable or rate-limited third-party services. DMI and Open-Meteo upstreams are mocked in load, stampede and fault-injection tests.
- **Load tests have a request budget.** Before running any load or burst test, state its total request count and confirm it fits the staging account's daily quota with margin. If staging shares a Cloudflare account with production, a load test can exhaust production's daily quota. In that case, do not run it; mark it BLOCKED and recommend a separate free staging account.
- Never weaken an assertion or threshold to make a test pass. Never skip or disable a test without a documented reason.

### 1.7 Stop and ask the owner before

- changing gates or metric definitions
- deleting or rewriting stored radar or verification history
- anything that could exceed a free-tier limit or incur cost
- any change to stored personal data or retention
- any irreversible production operation
- any change that would compromise a higher priority in §2

---

## 2. Priority order (do not reorder)

1. **Data correctness and truthfulness.** This includes the verification engine itself: if the metrics are wrong, every forecast decision built on them is wrong.
2. **Runtime stability and failure recovery.**
3. **Forecast accuracy (V6 nowcasting).** This is believed to be the main product bottleneck. Phase 0 must confirm that.
4. **The location answer** (question 3). Most users come for this.
5. **Map, timeline and notifications UX.**
6. **Accessibility and language.**
7. **Performance** (only after correctness and stability are established, and always measured before and after).
8. **Observability, security, privacy hardening.**
9. **Mobile polish, then stretch features.**

The zero-cost constraint (§1.3) applies at every level.

---

## 3. How to work

1. **Phase 0 first, then stop.** Do the full baseline and audit (§4) without changing code. Deliver the findings, then **wait for the owner's approval** before Phase 1.
2. **After approval, keep going.** Within approved phases, do not stop at recommendations. Implement, test and verify. Pause only at the stop-and-ask list (§1.7), at the end of each phase for the phase report, or when a required resource or credential is missing. In that last case, document the blocker and continue with independent work.
3. Treat the handover as historical evidence, not current truth. Verify its claims against the code, config, workflows and commit history.
4. For every issue, follow this loop:
   - **Investigate:** reproduce it.
   - **Diagnose:** find the root cause.
   - **Design:** describe the smallest sustainable fix and its alternatives.
   - **Protect:** write a regression test that fails before the fix.
   - **Implement.**
   - **Validate:** run the tests, including negative cases.
   - **Measure:** compare before and after.
   - **Document.**
5. Fix root causes. Never hide symptoms with retries, fallbacks or swallowed errors. Retries must be bounded, use backoff with jitter, respect provider limits and never duplicate non-idempotent operations.
6. Keep PRs small and reviewable, with one concern per PR. Put risky changes behind feature flags with a tested rollback. CI stays green on every commit.
7. Write an ADR (`docs/adr/`) for every architectural decision. Keep `docs/PROGRESS.md` current: what changed, evidence, open risks.
8. Use parallel sub-agents only for independent workstreams, and never let two agents edit the same files.
9. Use existing repo conventions and tools. No new frameworks without a demonstrated need. No large rewrites unless targeted fixes provably cannot work.
10. **Never claim done without evidence.** Every claim links to a test, metric, screenshot or command output. Never invent benchmark numbers or findings.

---

## 4. Phase 0 — Baseline and audit (no code changes)

### 4.1 Handover and repo review

- Read the handover fully: incidents, known defects, previous attempts, open questions.
- Map the full data flow:
  - DMI radar / HARMONIE / Open-Meteo
  - ingestion (GitHub Actions)
  - processing and nowcasting
  - R2
  - Worker API and caching
  - client, service worker and push
- Review every GitHub Actions workflow. What does each one actually assert? Look for skipped tests, `continue-on-error`, permissive error handling, misleading success conditions and mock-only "integration" tests.
- Classify every handover finding as **confirmed**, **suspected** or **obsolete**.

### 4.2 Verification engine audit (correctness of the forecast metrics)

- Recompute CSI, precision, recall, FAR, MAE, Brier and persistence skill for ≥ 50 stored forecast/observation pairs, using an independent implementation (pysteps' verification module is a good reference).
- Check that:
  - forecast frame T+n is compared to the observation **valid at** T+n, not the one **published at** T+n
  - the coverage mask and no-echo are handled identically for forecast, persistence and observation
  - the persistence baseline uses exactly the same input frame as the forecast
- **Explain the anomaly:** +15 min fails persistence skill, +30 fails and +45 passes. That pattern is non-monotonic and suspicious. Determine whether it is real (for example, latency makes persistence unusually strong at +15) or an alignment or verification bug.

### 4.3 Measurements

- End-to-end latency: DMI measurement time → DMI publish → ingestion start → R2 visible → client visible. Record p50 and p95.
- Core Web Vitals on a mid-range Android over 4G, bundle sizes, API p50/p95 per endpoint, cache hit rates and alert scan duration.
- **Cost and quota baseline:**
  - Workers requests/day and CPU per invocation
  - R2 storage, Class A and Class B ops/day
  - Actions minutes/month and repo visibility
  - KV ops, if used
  - any other external service
- UX gap inventory with screenshots: mobile and desktop, Danish and English, light and dark.

### 4.4 Phase 0 deliverables

- **`docs/BASELINE.md`:** numbers, verification audit result, anomaly explanation, data-flow map and a ranked list of the biggest problems.
- **`docs/FINDINGS.md`:** the findings register, one row per finding. Do not invent findings to fill it.

| Field | Content |
|---|---|
| Finding | Specific issue or failure mode |
| Evidence | Handover section, file/line, log or reproducible test |
| Severity | P0 Critical · P1 High · P2 Medium · P3 Low |
| Impact | Correctness · stability · accuracy · performance · security · privacy · cost |
| Root cause | Confirmed · suspected · unknown |
| Reproduction | Steps; expected vs actual |
| Proposed fix | Smallest sustainable correction |
| Verification | Regression test and measurable acceptance criterion |

- **`docs/FREE_TIER.md`:** a first version of the free-tier compliance report (§13).

Then stop and wait for approval.

---

## 5. Phase 1 — Correctness and stability fixes

Fix the confirmed P0/P1 findings from Phase 0 before any feature work.

### 5.1 Data correctness

Investigate and fix:

- incorrect, missing, duplicated or outdated records
- schema assumptions in ODIM HDF5 and API payloads
- identity and uniqueness of frames
- timestamp, time-zone, date-boundary and DST handling
- georeferencing and projection
- partial or truncated data
- wrong filtering, sorting or deduplication
- cache invalidation and stale-data propagation
- out-of-order and concurrent updates
- failed updates that leave contradictory state

Add data-quality controls: validate required fields, use deterministic transformations, and handle invalid input explicitly. A rejected input must leave production on its last-known-good state.

### 5.2 Runtime stability

Test behaviour under:

- DMI or Open-Meteo timeouts, 5xx and malformed payloads
- rate limits and quota exhaustion, including the Workers daily cap
- missed or delayed Actions cron runs
- races and duplicate processing
- partial initialization
- restarts and interruptions
- browser-side loading failures

A dependency failure must produce a controlled, observable state, never corrupted data or a false success.

### 5.3 Test strategy

- **Unit tests:** business rules, transformations, edge cases.
- **Integration tests:** storage, cache, upstream adapters, serialization.
- **Contract tests:** against `openapi/wetmap-v1.yaml` and sanitized upstream fixtures.
- **End-to-end tests:** Playwright on Chromium, WebKit and Firefox.
- **Regression tests:** one for every confirmed defect, shown failing on the original code where practical.
- **Resilience and fault-injection tests:** the scenarios listed in §5.2.

Report coverage per functional area, not just a total percentage.

---

## 6. Phase 2 — Forecast engine V6

### 6.1 Offline backtesting harness first

- Check how far back DMI's open radar API serves composites. If the history is short, start archiving every observation to R2 now, with a lifecycle policy and a storage projection checked against the free allowance.
- Build a labelled event library. Cover these regimes:
  - frontal stratiform rain
  - summer convection
  - showers in northwesterly flow
  - snow/sleet
  - coastal/sea-clutter days
  - fast-moving lines
  - **dry days** (to control false alarms)
- The harness runs any challenger over any event set. It outputs the full metric suite per lead time (5…60 min), per regime and per region.
- It runs locally and in CI on a small event subset, within the Actions budget.

### 6.2 Input quality control

- Before motion estimation, mask:
  - sea clutter
  - anomalous propagation
  - speckle
  - ring and spoke artefacts
  - beam blockage
- Keep the coverage mask separate from no-echo.
- Measure how much QC alone changes CSI and false alarms.

### 6.3 Challenger candidates

Evaluate each in isolation, then combined:

1. **Better motion fields:** OpenCV DIS optical flow, multi-scale Farneback, and sparse Lucas–Kanade with interpolation. Smooth the motion field over 3–6 frames.
2. **Semi-Lagrangian backward advection** instead of forward warping (no holes, better mass handling).
3. **Scale-dependent decay** (S-PROG-style cascade). Targets the +45–60 min degradation.
4. **Growth and decay in the Lagrangian frame** (ANVIL-style).
5. **Stochastic ensemble** (STEPS-style): 10–20 members producing per-pixel probability of ≥ 20 dBZ. Spread must widen with lead time.
6. **Regime classifier** (convective / stratiform / mixed) to choose method weights.
7. **Radar–HARMONIE blending** toward +60 min, weighted by verified skill per lead time and regime.

Benchmark against pysteps (BSD-3, reads ODIM HDF5). Adopt it if it beats our implementation within the compute budget; otherwise use it as the yardstick.

### 6.4 Latency gap

DMI data is 10–20 minutes old on arrival, so the first nowcast frames describe the present.

- Anchor every frame to valid time.
- Expose both "lead from observation" and "minutes from now", and verify on both axes.
- The UI shows an estimated "now" frame, clearly labelled as estimated.

### 6.5 Additive metrics (gates unchanged)

- Fractions Skill Score at 1, 5, 10 and 20 km.
- Reliability diagrams, ROC AUC, CRPS and spread–skill ratio.
- Point-level metrics: rain-arrival time error, stop-time error, and hit rate for "rain within ±10 min at this point".
- Stratify by lead time, regime, season and distance from the nearest radar.

### 6.6 Compute budget

- Target: R2-visible ≤ 3 min after DMI publish, at p95.
- Compute runs in GitHub Actions, not in the Worker (10 ms CPU limit).
- Profile the ensemble and use reduced resolution for perturbations if needed. Confirm the added Actions minutes fit §1.3.
- **Fail safe:** if a challenger exceeds its budget, production keeps serving the incumbent. Test this.

**Acceptance:** a results table per horizon (incumbent vs each challenger, backtest and live shadow) with confidence intervals. Only horizons that pass every existing gate are promoted.

---

## 7. Phase 3 — The location answer

Must be glanceable in under 3 seconds and visible ≤ 1.5 s after the location is known (warm cache).

- **Headline sentence** from structured data via templates (no LLM), in Danish and English. Example: "Light rain from about 14:20, easing by 14:45. Fairly confident."
- **Minute-level chart:** 5-minute bars to +60 min, shaded by probability, with an uncertainty band. Then HARMONIE in 15-minute steps to +6 h and hourly to +48 h, visually distinct.
- **Ranges, not false precision:** show arrival and stop as windows ("14:15–14:30") when uncertainty is high.
- **Dry-window finder:** user picks 10, 20 or 30 min. Example: "Best 20-minute dry window: 14:50–15:10."
- **Precipitation type** (rain, sleet, snow) from HARMONIE temperature and humidity, labelled as model-based.
- **Source and age chips:** Radar observed (age) · Radar nowcast · HARMONIE model · Open-Meteo fallback.
- **"Why this forecast?"** expandable: motion direction and speed, regime, ensemble agreement, recent verified skill at this lead time.
- **Honest empty states:** "No rain expected in the next hour" with its confidence; "Outside radar coverage" where relevant.
- **Tap anywhere on the map** → mini forecast for that point.

---

## 8. Phase 4 — Map, timeline and notifications

### 8.1 Map and timeline

- A clear "now" marker separates observed from forecast frames. Forecast frames are visually distinct, and the estimated-now frame is marked.
- **Smooth playback:**
  - GPU interpolation between 5-minute frames (cross-fade at minimum; flow-based tweening if affordable)
  - pre-decode frames with `createImageBitmap`
  - show low resolution first, with load progress
- **Controls:**
  - play/pause, drag scrub, speed selector, loop range
  - keyboard: space, ←/→, Home/End
  - autoplay with a visible pause control that respects `prefers-reduced-motion`
- **Layers:** intensity (dBZ) and probability of rain (≥ 20 dBZ). Coverage and no-echo are shown differently.
- **Legend:** perceptually uniform, colour-vision-deficiency-safe ramp. Show dBZ, plain words (light/moderate/heavy/very heavy) and estimated mm/h labelled as an estimate.
- **Shareable URL state:** location, zoom, time, layer, language. Round-trips exactly.
- **3D buildings:** auto-off on low-end devices (device memory, measured frame rate). A user override is remembered.
- **Favourites** show a mini "next hour" summary.

### 8.2 Notifications

- **Per-location preferences:** intensity threshold, lead time, quiet hours, "rain stopping" alerts, max per day, snooze.
- Hysteresis and debounce, so a borderline forecast cannot cause flapping alerts.
- **Delivery telemetry:** anonymous received, displayed and discarded-as-expired events, so latency per platform is known. Keep the volume within free logging limits.
- A "Send test notification" button.
- Deep links: a notification opens that location at that time.
- iOS guidance (push requires installing the PWA to the home screen, iOS 16.4+), shown only to iOS users.
- Keep every existing safety rule:
  - no "current rain" from observations older than 15 min
  - skip forecast times already in the past
  - an expiry in every payload
  - the service worker discards stale messages

---

## 9. Phase 5 — Accessibility, language and content

- **WCAG 2.2 AA.** The map is not accessible to screen readers by itself, so provide a full text equivalent: the headline, chart data as a table, and timeline state announced via a live region.
- Keyboard-only use of every feature, visible focus, 44×44 px touch targets, and 200% zoom and 320 px reflow without loss.
- **Language:**
  - CI checks Danish/English key parity and scans for hardcoded strings.
  - Danish is the default for Danish locales.
  - Danish formats: 24-hour clock, comma decimal, Danish day and month names.
- **Copy:** plain, calm, non-alarmist. "Live" always has an age; mm is always "about" or "estimated".

---

## 10. Phase 6 — Performance

Measure first, then optimize, then measure again with a comparable workload, environment and method. Reject any optimization that compromises correctness or resilience. If no credible baseline exists, say that improvement has not been demonstrated.

| Metric | Target (mid-range Android, 4G, p75) |
|---|---|
| LCP | ≤ 2.5 s |
| INP | ≤ 200 ms |
| CLS | ≤ 0.1 |
| App shell interactive before map ready | yes (MapLibre lazy-loaded in its own chunk) |
| Location answer visible | ≤ 1.5 s after location known (warm cache) |
| Playback | ≥ 50 fps, no frame drops on scrub |
| Memory after 30 min playback | stable, within iOS Safari limits |
| API point forecast, warm edge cache | p95 ≤ 150 ms |
| API point forecast, cold | p95 ≤ 800 ms |

Fix the MapLibre code-splitting warning, and add size budgets to CI so they cannot regress. Also look for:

- redundant upstream calls
- cache misses
- payload size
- repeated computation
- Worker CPU per request (relevant to the 10 ms limit)

For each optimization, report before / after / change for only the relevant metrics: latency p50/p95, processing duration, memory, upstream requests, error rate, and quota consumption.

---

## 11. Phase 7 — Reliability, observability, security, privacy

- **SLOs with alerting:** radar freshness ≤ 25 min, API availability, alert end-to-end latency, nowcast pipeline duration. Document the error budgets.
- **Diagnostics:** structured logs for started, completed, failed and partial runs; upstream failures; validation failures; record counts; durations; last successful update. A running-but-stale system must be distinguishable from a healthy one. Avoid secrets, excessive volume and unnecessary retention.
- **Dashboards:** freshness, pipeline stages, cache hit rate, upstream failures and fallbacks, push sent/received/discarded, forecast quality per horizon, and **quota usage**. Use only tools allowed by §1.3, with PII scrubbing.
- **Resilience:**
  - request coalescing, so cache misses never stampede DMI
  - last-known-good with visible staleness
  - detection of delayed or missed cron runs
- **Security:**
  - rate limits and WAF only as available on free plans
  - strict CSP, HSTS, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy` (geolocation self only)
  - container images pinned by digest, running read-only and non-root
  - automated dependency updates
  - no secrets in client bundles or source maps
- **Privacy:**
  - a published privacy notice and retention policy (Danish and English) that match actual behaviour
  - automated deletion of expired subscriptions and data
  - a documented legal basis for storing rounded coordinates
- **Runbooks:** DMI outage, stale radar, bad promotion rollback, push key rotation, R2 incident, **free-tier quota exhaustion**.

---

## 12. Phase 8 — Mobile polish and PWA, then stretch

- Bottom sheet for the location answer with thumb-reachable controls, safe-area insets and landscape support.
- Install prompt only after a second visit or after saving a favourite, never on first load.
- **Offline:** last data with a clear "offline · data from HH:MM" banner. Never present cached radar as fresh.
- A smooth service worker update flow, with no stale-asset mix.
- **Stretch** (only after everything above is accepted):
  - DMI lightning layer
  - rain-gauge comparison overlay
  - event replay links

---

## 13. Deliverables (in `docs/`)

| File | Content |
|---|---|
| `BASELINE.md` | Phase 0 measurements, verification audit, ranked problems |
| `FINDINGS.md` | Findings register (§4.4), kept current |
| `RCA.md` | For every P0/P1 defect: symptom, reproduction, root cause (confirmed/suspected), why it was possible, why tests and monitoring missed it, fix, regression test, residual risk |
| `PROGRESS.md` | Running change log: change, rationale, components, evidence, PR link |
| `TEST_EVIDENCE.md` | Exact commands, environment, results and failure counts, regression and fault-injection outcomes. Executed and not-executed checks listed separately. |
| `PERFORMANCE.md` | Before/after measurements with methodology, workload and environment |
| `FREE_TIER.md` | Every service and provider, its free allowance (with source and date checked), whether it is a hard cap or metered, measured usage, projected usage after changes, buffer, and unresolved risks |
| `RISKS.md` | Unresolved issues, untested behaviour, external dependencies, follow-ups |
| `adr/*` | One ADR per architectural decision |

**End-of-phase report** (post in chat and append to `PROGRESS.md`):

```
Phase: …
Changed: (bullets, PR links)
Evidence: (tests, metrics before → after, screenshots)
Not done / deferred: (and why)
Risks and open questions:
Quota impact: (Workers req/day, R2 ops & storage, Actions minutes — before → after)
Recommended next step:
```

Be blunt about what did not work. A negative result with good evidence is useful; a vague success is not.

**Final engineering summary** (at the end of all phases):

1. What was actually wrong?
2. What caused it?
3. What changed?
4. How was each fix verified?
5. What measurable improvements were achieved?
6. What remains unverified or risky?
7. Does the system still run within free tiers, and what evidence supports that?

Do not report "everything works" unless the evidence supports it.

---

## 14. Release acceptance test

> **Run this in a separate, fresh session**, not the one that made the changes. That session acts as an independent release tester whose job is to find problems, not to confirm success. Test staging first; production gets read-only checks only. Give that session §1 and §14 of this prompt plus the repo.

### 14.1 Rules

1. **No PASS without evidence:** command output, test report, screenshot, recording or metric.
2. **No code fixes during the run.** Record each failure with reproduction steps; fixes happen in a separate session.
3. **Never weaken a threshold.** If a threshold looks wrong, flag it separately.
4. **Flaky = FAIL** until it passes 3 consecutive reruns. Log the flakiness itself as a defect.
5. Checks that need a person, a real device, a screen reader or a native speaker are **HUMAN**, with a step-by-step script. Paid device clouds are not allowed (§1.3).
6. Statuses: `PASS`, `FAIL`, `BLOCKED` (could not run, with reason), `HUMAN`.
7. Load and burst tests follow §1.6: request budget stated up front, mocked upstreams, never production, and BLOCKED if staging shares production's account quota.

### 14.2 Two separate verdicts

- **Release readiness:** RELEASE only if every blocking check (⛔) is PASS.
- **Forecast quality:** reported per horizon against the gates. A horizon that does not yet beat the gates is not an app defect. A horizon that was **promoted** without passing the gates is a ⛔ failure.

"100% good" means every blocking check passes with evidence, and every forecast horizon in production legitimately earned its place. It does not mean the forecast is never wrong.

### A. Build and static checks

| ID | Check | Pass criterion |
|---|---|---|
| A1 ⛔ | Full CI on the release commit | All jobs green, and the workflow review (§4.1) found no skipped tests or permissive error handling hiding failures |
| A2 ⛔ | Lint and strict type check (TS), Ruff, .NET build | Zero errors |
| A3 ⛔ | Unit tests (web, edge, shared, Python, .NET) | All pass; coverage not below previous release |
| A4 ⛔ | CodeQL, Gitleaks, Trivy | Zero high/critical; no secrets |
| A5 | SBOM generated and attached | Present and complete |
| A6 ⛔ | Bundle size budgets | Within budget; MapLibre in its own lazy chunk; no code-split warning |
| A7 | i18n key parity and hardcoded-string scan | 100% parity; zero hardcoded user-facing strings |

### B. Radar data pipeline

| ID | Check | Pass criterion |
|---|---|---|
| B1 ⛔ | Feed malformed ODIM files (wrong schema, missing DBZH, truncated, wrong projection) | Each rejected cleanly; production keeps last-known-good |
| B2 ⛔ | SHA-256 of 20 random stored frames | All match manifest |
| B3 ⛔ | Georeferencing: overlay a frame; check radar site positions and a known coastline echo | Misalignment < 1 grid cell |
| B4 | Re-run ingestion for the same observation | Idempotent: no duplicate or changed objects |
| B5 ⛔ | Coverage vs no-echo | Out-of-coverage areas never rendered or reported as "dry" |
| B6 | End-to-end latency (DMI publish → client visible) | p95 within documented target; R2-visible ≤ 3 min p95 |
| B7 ⛔ | Simulate missed/delayed Actions run | Freshness alert fires; UI shows age honestly |
| B8 ⛔ | Challenger exceeds its compute budget (simulated) | Production keeps serving the incumbent; event logged |

### C. Forecast verification audit

| ID | Check | Pass criterion |
|---|---|---|
| C1 ⛔ | Recompute CSI, precision, recall, FAR, MAE, Brier and persistence skill for ≥ 50 stored pairs with an independent implementation (e.g. pysteps) | Ratio metrics (CSI, precision, recall, FAR, skill) within 0.5 percentage points; Brier within 0.005; MAE within 1% relative. If the owner has set other tolerances in an ADR, use those. |
| C2 ⛔ | Time alignment: forecast T+n vs observation *valid* at T+n | Verified in code and on data |
| C3 ⛔ | Persistence baseline uses the identical input frame | Verified |
| C4 ⛔ | Shadow isolation: no unpromoted challenger output in any public manifest or API response | Zero leaks across 24 h of manifests |
| C5 ⛔ | Promotion logic unit tests: each gate failing alone blocks promotion; per-horizon independence | All pass. Every gate, including false-alarm regression, has a numeric threshold in code. |
| C6 ⛔ | Gates unchanged vs docs / previous release, or an approved ADR exists | Diff reviewed |
| C7 ⛔ | Backtest split: no test-period dates used in tuning | Verified from config and logs |
| C8 | Additive metrics: multi-scale FSS, reliability, ROC, CRPS, point arrival-time error | Reported per horizon and regime |
| C9 | Probability calibration | Reliability curve within ±10 pp of diagonal in every bin with ≥ 100 samples; bin counts reported |
| C10 | Ensemble spread grows with lead time | Monotonic spread; spread–skill ratio reported |

Report a table: horizon · incumbent · challenger · CSI · FSS(10 km) · skill vs persistence · gate status · promoted?

### D. API contract and resilience

| ID | Check | Pass criterion |
|---|---|---|
| D1 ⛔ | Property-based contract tests against `openapi/wetmap-v1.yaml` (e.g. Schemathesis), all public endpoints | Zero schema violations, zero 5xx; total request count within budget |
| D2 ⛔ | Byte-range point lookup vs full-grid lookup at 200 random points | Identical values |
| D3 ⛔ | Inject DMI HARMONIE timeout and 5xx | Open-Meteo fallback used and labelled as fallback |
| D4 ⛔ | Inject DMI radar outage | Last-known-good served with correct age; no "current" claims |
| D5 ⛔ | CORS: request from a non-allow-listed origin | Rejected |
| D6 | Cache headers and hit rate on repeat requests | Correct `Cache-Control`; hit rate as documented |
| D7 | Rate limiting | Excess requests get 429; normal use unaffected |
| D8 ⛔ | Cache-miss stampede: 500 concurrent cold requests, same point, mocked upstream | One upstream request (coalesced) |
| D9 | Load test (e.g. k6), sustained and burst, within stated request budget | Latency budgets met; zero errors; no upstream overload |

### E. Location answers (golden set)

Test search, reverse geocoding, headline, chart, sources and coverage handling for each of these locations:

Copenhagen, Aarhus, Odense, Aalborg, Esbjerg, Holbæk, Skagen, Rønne (Bornholm), Ærøskøbing, a point in the Kattegat, Malmö, Flensburg, Tórshavn, Nuuk.

| ID | Check | Pass criterion |
|---|---|---|
| E1 ⛔ | Search with æ/ø/å and variants ("Århus"/"Aarhus", "Køge"/"Koge", "Ærø"/"Aero") | Correct top result |
| E2 ⛔ | Locations outside radar coverage | Clear "outside radar coverage"; model forecast only, labelled |
| E3 ⛔ | Headline matches underlying data | Arrival/stop times and intensity consistent with chart and API |
| E4 ⛔ | Uncertainty shown as ranges when confidence is low | Never a single exact minute at low confidence |
| E5 | Dry-window finder | Window lies inside forecast dry period for chosen duration |
| E6 | Precipitation type | Snow/sleet only when model temperatures support it; labelled model-based |
| E7 ⛔ | mm and mm/h values | Always labelled as estimates |
| E8 | Location answer visible after location known (warm cache) | ≤ 1.5 s |
| E9 | "Why this forecast?" panel | Present; motion, regime, agreement and verified skill match the API |

### F. Time, clocks and DST

| ID | Check | Pass criterion |
|---|---|---|
| F1 ⛔ | DST end replay (25 Oct 2026, 02:00–03:00 occurs twice) with recorded or mocked data | No duplicated, missing or misordered intervals; labels unambiguous |
| F2 ⛔ | DST start, mocked (28 Mar 2027, 02:00 → 03:00) | Same |
| F3 ⛔ | Device clock wrong by ±10 min | Data age and "now" marker still correct (server time used) |
| F4 | Device in another time zone | Behaviour matches documented choice and is labelled |
| F5 ⛔ | Forecast times already in the past | Never shown as upcoming |
| F6 | Midnight crossing in 15-min intervals and chart | Correct day labels |

### G. Map and timeline (Playwright: Chromium, WebKit, Firefox)

| ID | Check | Pass criterion |
|---|---|---|
| G1 ⛔ | Autoplay on load, visible pause, stops under reduced motion | All true |
| G2 ⛔ | "Now" marker; observed vs forecast frames distinguishable; estimated-now frame labelled | All true |
| G3 | Scrub by drag, keyboard (space, arrows, Home/End), speed, loop range | All work |
| G4 | Intensity vs probability layer toggle; legend updates | Correct |
| G5 ⛔ | URL state round-trip (location, zoom, time, layer, language) | Exact restore |
| G6 | Favourites persist across reloads; mini summary correct | True |
| G7 | Language switch keeps state | No reset |
| G8 | 3D buildings toggle; auto-off on simulated low-end device (emulated memory/CPU) | Correct |
| G9 | Tap-anywhere mini forecast | Matches API for that point |
| G10 | Visual regression: light/dark × da/en × 360/768/1440 px | No unapproved diffs |

### H. Accessibility

| ID | Check | Pass criterion |
|---|---|---|
| H1 ⛔ | Automated scan (axe) on every screen and state | Zero serious/critical |
| H2 ⛔ | Keyboard-only walkthrough of every feature | Everything reachable and operable; visible focus |
| H3 ⛔ | Text equivalent of map and timeline | Headline, data table and live-region announcements present |
| H4 | Contrast (text and legend) | WCAG 2.2 AA |
| H5 | 200% zoom and 320 px reflow | No loss of content or function |
| H6 | Colour-vision deficiency simulation (protan, deutan, tritan) | Intensity levels still distinguishable |
| H7 | Touch targets | All interactive elements ≥ 44×44 px |
| H8 HUMAN | VoiceOver (iOS) and TalkBack (Android) walkthrough | Script provided; results recorded |

### I. Performance

| ID | Check | Pass criterion |
|---|---|---|
| I1 ⛔ | Lighthouse CI, mobile throttled, median of 5 runs | LCP ≤ 2.5 s, CLS ≤ 0.1, TBT within budget |
| I2 ⛔ | INP on interaction script (scrub, search, toggle) | ≤ 200 ms |
| I3 HUMAN | Playback frame rate on a real mid-range Android | ≥ 50 fps |
| I4 ⛔ | 30-minute playback memory profile (automated, desktop/emulated) | No upward trend |
| I5 HUMAN | 30-minute playback on a real iPhone (iOS Safari) | No crash, no reload |
| I6 | API latency, warm and cold | p95 ≤ 150 ms / ≤ 800 ms |

### J. PWA and offline

| ID | Check | Pass criterion |
|---|---|---|
| J1 | Installable on desktop Chrome/Edge (automated manifest/SW criteria) | True |
| J2 HUMAN | Install on Android Chrome and iOS Safari | Installs and launches standalone |
| J3 ⛔ | Offline launch | Last data with "offline · data from HH:MM"; never presented as fresh |
| J4 | Service worker update flow | New version activates cleanly; no stale-asset mix |
| J5 | Install prompt timing | Never on first load; appears only after second visit or saving a favourite |

### K. Notifications

Use a staging-only synthetic rain injection to trigger alerts deterministically.

| ID | Check | Pass criterion |
|---|---|---|
| K1 ⛔ | Synthetic rain approaching a subscribed point | "Rain on the way" delivered with correct time window |
| K2 ⛔ | Observation older than 15 min | Never described as current rain |
| K3 ⛔ | Delayed delivery past expiry (hold the push) | Service worker discards it; telemetry records discard |
| K4 ⛔ | Borderline forecast oscillating around threshold | No flapping; hysteresis respected |
| K5 | Quiet hours, max per day, snooze, "rain stopping" alert | All honoured |
| K6 ⛔ | Unsubscribe | Subscription removed from storage within documented time |
| K7 ⛔ | Stored subscription data | Only documented fields; coordinates rounded to 0.01° |
| K8 | Notification tap | Deep-links to that location and time |
| K9 | iOS install guidance | Shown to iOS user agents only |
| K10 HUMAN | Test-notification button and real-device matrix: Android Chrome, iOS installed PWA, macOS Safari, Windows Chrome/Edge/Firefox; app closed, backgrounded, device locked | Delivery and latency recorded per cell |

### L. Security and privacy

| ID | Check | Pass criterion |
|---|---|---|
| L1 ⛔ | Security headers: CSP, HSTS, X-Content-Type-Options, Referrer-Policy, Permissions-Policy (geolocation self) | Present and strict |
| L2 ⛔ | Passive scan (OWASP ZAP baseline) on staging | Zero high/medium |
| L3 ⛔ | No secrets, keys or internal URLs in client bundles or source maps | Verified |
| L4 ⛔ | Geolocation requested only after user action | Verified with fresh profile |
| L5 ⛔ | Privacy notice and retention policy published (Danish and English) and matching actual behaviour | True |
| L6 | Retention and cleanup jobs | Expired data actually deleted |
| L7 | Container images pinned by digest; run read-only, non-root | Verified |

### M. Language and content

| ID | Check | Pass criterion |
|---|---|---|
| M1 | Danish formats (24 h, comma decimal, Danish day/month names) | Correct everywhere |
| M2 ⛔ | "Live" always paired with data age; no claim of ground-truth rainfall | Verified on every screen |
| M3 HUMAN | Native Danish speaker reviews all copy | Natural, calm, unambiguous |

### N. Observability and operations

| ID | Check | Pass criterion |
|---|---|---|
| N1 | Dashboards: freshness, pipeline stages, cache, fallbacks, push telemetry, forecast quality, quota usage | Populated with real data |
| N2 ⛔ | Alert drill: force stale radar | On-call alert fires within SLO |
| N3 ⛔ | Rollback drill: revert a promoted horizon | Production returns to incumbent; time documented |
| N4 | Runbooks exist and were followed successfully in the drills | True |

### O. Cost and quota

| ID | Check | Pass criterion |
|---|---|---|
| O1 ⛔ | `FREE_TIER.md` complete: every service, allowance with source and check date, hard cap vs metered | Complete; no service missing |
| O2 ⛔ | Measured 7-day usage vs free allowances (Workers req/day and CPU, R2 storage and Class A/B ops, Actions minutes, KV if used) | Peak day ≤ 70% of every daily or monthly-prorated allowance, or the owner has accepted the margin in writing |
| O3 ⛔ | R2 lifecycle rules on every growing prefix; projected storage at 12 months | Projection stays under the free allowance |
| O4 ⛔ | Quota-exhaustion behaviour (simulated Workers daily cap hit) | App degrades visibly and honestly; no false freshness |
| O5 ⛔ | No new service requiring a payment method; no paid dependency | Verified from config, `package.json`, `pyproject` and workflows |
| O6 | R2 usage alert / scheduled check | Fires before metered billing would begin |
| O7 | Repo visibility vs Actions usage | Public, or private usage fits the allowance with margin |

### 14.3 Acceptance report format

Write `docs/ACCEPTANCE_REPORT.md`:

```
Release commit: …
Date/time (UTC): …
Environment: staging / production (read-only)

Verdict — Release readiness: RELEASE / DO NOT RELEASE
Verdict — Forecast quality: (per-horizon table)

Summary: X PASS · Y FAIL · Z BLOCKED · W HUMAN

Failures (ordered by severity):
- ID · what happened · expected · reproduction steps · evidence link

Blocked checks and why:
Human checks with scripts:
Full results table: ID · status · evidence
```

Keep the report factual. Do not soften failures.
