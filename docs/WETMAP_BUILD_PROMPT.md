# WetMap — Best-in-class build brief

You are the lead engineer on WetMap, a production near-real-time 3D weather-radar PWA for Denmark (live at wetmap.pages.dev, API at wetmap-api.wetmap-edge.workers.dev). The full system context is in `docs/SYSTEM_CONTEXT.md`. Read it fully, then read the repo (`apps/web`, `apps/worker`, `apps/api`, `infra/edge`, `packages/shared`, `openapi`, `docs/adr`) before you change anything.

Your mission: make WetMap the most accurate, most trustworthy and most pleasant-to-use short-range rain app in Denmark. It must answer three questions better than anyone else:

1. Where is precipitation visible on radar right now?
2. Where will it move during the next 60 minutes?
3. What does that mean for me, at this exact spot, in plain language?

---

## 1. Priority order (do not reorder)

1. **Forecast accuracy (V6 nowcasting).** This is the bottleneck. Everything else is already working.
2. **Truthfulness of what the user sees.** Data age, uncertainty and source must always be honest and visible.
3. **The location answer (question 3).** This is what most users actually come for.
4. **Map, timeline and notifications UX.**
5. **Performance, accessibility, reliability, security, privacy hardening.**
6. **Mobile polish and stretch features.**

If a phase would compromise an earlier priority, stop and ask.

---

## 2. Non-negotiables

- **Never relax promotion gates or redefine metrics** to make numbers look better. Current gates: sufficient samples and rain pixels, CSI ≥ 0.20, improvement over the exact incumbent, non-negative skill over persistence, controlled false-alarm regression. Any new metric is *additive*. Any gate change requires a written ADR and my explicit approval.
- **Production forecasts change only through shadow mode and per-horizon promotion.** No challenger output may ever reach a public manifest without passing the gates.
- **No tuning on test data.** Use a fixed, date-based train/validation/test split. Record it in the repo.
- **Radar is reflectivity aloft (dBZ), not ground truth.** Any mm or mm/h value is labelled as a Z–R estimate. "Live" always shows the observation's age.
- **Privacy model stays:** no accounts, no user database, favourites stay in the browser, push coordinates rounded to 0.01°, geolocation only after explicit user interaction.
- **All timestamps are UTC internally;** displayed in Europe/Copenhagen with correct DST handling. Note: DST ends Sunday 25 October 2026, 03:00 → 02:00.
- **CI stays green on every commit.** Small, reviewable PRs. Risky changes behind feature flags with a tested rollback.
- **Respect platform limits:** Cloudflare Worker CPU/memory/subrequest limits, R2 operation costs, GitHub Actions minutes and cron jitter. Measure before you assume headroom.
- **Never claim done without evidence.** Every "done" claim links to a test, a metric, a screenshot or a command output.

**Stop and ask me before:** changing gates or metric definitions; deleting or rewriting stored radar/verification history; anything that could exceed free-tier limits or incur cost; any change to what personal data is stored or for how long; any irreversible production operation.

---

## 3. How to work

1. Start in plan mode. Produce a written plan per phase with files touched, risks and acceptance criteria. Wait for my approval of Phase 0 findings before Phase 1.
2. Use parallel sub-agents only for independent workstreams (e.g. frontend a11y vs worker backtesting). Never let two agents edit the same files.
3. Keep a running `docs/PROGRESS.md`: what changed, evidence, open risks.
4. Write an ADR for every architectural decision (`docs/adr/`).
5. Write tests first for behaviour you are changing. Every bug you find gets a regression test.

---

## 4. Phase 0 — Baseline and audit (before any feature work)

Goal: make sure we are measuring the right thing before we try to improve it.

- **Audit the verification engine.** Recompute CSI, precision, recall, FAR, MAE, Brier and persistence skill for a sample of stored forecast/observation pairs with an independent implementation (pysteps' verification module is a good reference). Check:
  - Forecast frame T+n is compared to the observation *valid at* T+n, not the one *published at* T+n.
  - Coverage mask and no-echo are handled identically for forecast, persistence and observation.
  - The persistence baseline uses exactly the same input frame as the forecast.
- **Explain the anomalies.** +15 min fails persistence skill while +45 passes and +30 fails. That is non-monotonic and suspicious. Find out whether it is real (e.g. latency means persistence is unusually strong at +15) or a verification/alignment bug.
- **Measure end-to-end latency:** DMI measurement time → DMI publish → our ingestion start → R2 visible → client visible. Record p50/p95.
- **Baseline everything:** Core Web Vitals on a mid-range Android over 4G, bundle sizes, API p50/p95 per endpoint, cache hit rates, alert scan duration, R2 ops/day, Actions minutes/month.
- **Inventory UX gaps** with screenshots on mobile and desktop, in Danish and English, light and dark.

Deliverable: `docs/BASELINE.md` with numbers, findings and a ranked list of the biggest problems.

---

## 5. Phase 1 — Forecast engine V6 (the main event)

### 5.1 Offline backtesting harness first

Waiting for live samples is too slow. Build a harness that replays archived radar:

- Check how far back DMI's open radar API serves composites; if it is short, start archiving every observation to R2 now (with a lifecycle policy) so history accumulates.
- Curate a labelled event library: frontal stratiform rain, summer convection, showers in northwesterly flow, snow/sleet, coastal/sea-clutter days, fast-moving lines, and **dry days** (to control false alarms).
- The harness runs any challenger over any event set and outputs the full metric suite per lead time (5…60 min), per regime and per region.
- It must run locally and in CI (on a small event subset) so regressions are caught.

### 5.2 Input quality control

- Mask sea clutter, anomalous propagation, speckle, ring/spoke artefacts and beam blockage before motion estimation. Keep the coverage mask separate from "no echo".
- Measure how much QC alone changes CSI and false alarms.

### 5.3 Challenger candidates (evaluate each in isolation, then combined)

1. **Better motion fields:** OpenCV DIS optical flow, multi-scale Farneback, and sparse Lucas–Kanade with interpolation; temporal smoothing of the motion field over 3–6 frames.
2. **Semi-Lagrangian backward advection** instead of forward warping (no holes, better mass handling).
3. **Scale-dependent decay** (S-PROG-style cascade): small features lose predictability faster than large ones. This targets the +45–60 degradation directly.
4. **Growth and decay in the Lagrangian frame** (ANVIL-style), estimated from the recent observations.
5. **Stochastic ensemble** (STEPS-style), 10–20 members with motion and cascade perturbations, producing per-pixel probability of ≥ 20 dBZ at each lead time. Spread must widen with lead time.
6. **Regime classifier** (convective vs stratiform vs mixed, from reflectivity texture and motion coherence) to choose method weights.
7. **Radar–HARMONIE blending** toward +60 min, with weights set by verified skill per lead time and regime.

Benchmark against pysteps (BSD-3, reads ODIM HDF5) as a reference implementation. Adopt it if it beats our implementation within the compute budget; otherwise use it as the yardstick.

### 5.4 Fix the latency gap

DMI data is 10–20 minutes old when it arrives. The first nowcast frames therefore describe the *present*, not the future.

- Anchor every frame to valid time and expose both "lead from observation" and "minutes from now".
- Verify on both axes.
- The UI must show an estimated "now" frame (clearly labelled as estimated) so the user sees what is happening this minute.

### 5.5 Additive metrics (do not change gates)

- Fractions Skill Score at 1, 5, 10 and 20 km neighbourhoods. Pixel CSI double-penalises small displacement errors.
- Reliability diagrams, ROC AUC, CRPS and spread–skill ratio for probabilistic and ensemble output.
- **Point-level verification that matches what users experience:** rain-arrival time error, stop-time error, and hit rate for "rain within ±10 min at this point".
- Stratify everything by lead time, regime, season and distance from the nearest radar.

### 5.6 Compute budget

The full pipeline must finish within a fixed budget (target: R2-visible ≤ 3 minutes after DMI publish, p95). Profile the ensemble. Use reduced resolution for perturbations if needed. Fail safe: if a challenger exceeds its budget, production keeps serving the incumbent.

**Acceptance for Phase 1:** a written results table per horizon (incumbent vs each challenger, backtest and live shadow), with confidence intervals; only horizons that pass every existing gate are promoted.

---

## 6. Phase 2 — The location answer

This is the screen people open the app for. It must be glanceable in under 3 seconds.

- **Headline sentence** generated from structured data with templates (not an LLM), in Danish and English. Example: "Light rain from about 14:20, easing by 14:45. Fairly confident."
- **Minute-level chart:** 5-minute bars to +60 min, shaded by probability, with an uncertainty band. Then HARMONIE in 15-minute steps to +6 h and hourly to +48 h, visually distinct.
- **Ranges instead of false precision:** arrival and stop as windows ("14:15–14:30") when uncertainty is high.
- **Dry-window finder:** "Best 20-minute dry window in the next hour: 14:50–15:10." Ideal for cyclists. Let the user pick 10/20/30 min.
- **Precipitation type** (rain, sleet, snow) using HARMONIE temperature/humidity, labelled as model-based.
- **Source and age chips:** Radar observed (age) · Radar nowcast · HARMONIE model · Open-Meteo fallback.
- **"Why this forecast?"** expandable: motion direction and speed, regime, ensemble agreement, recent verified skill at this lead time.
- **Honest empty states:** "No rain expected in the next hour" with its confidence; "Outside radar coverage" when relevant.
- **Tap anywhere on the map** → mini forecast popup for that point.

---

## 7. Phase 3 — Map and timeline

- **Clear "now" marker** separating observed from forecast frames. Forecast frames are visually distinct (label plus subtle styling); the estimated-now frame is marked.
- **Smooth playback:** interpolate between 5-minute frames on the GPU (cross-fade at minimum; flow-based tweening if affordable). Pre-decode frames with `createImageBitmap`, show low-resolution first, show load progress.
- **Controls:** play/pause, drag scrub, keyboard (space, ←/→, Home/End), speed selector, loop range. Autoplay must have a visible pause control and respect `prefers-reduced-motion`.
- **Layers:** intensity (dBZ) and probability of rain (≥ 20 dBZ) toggle. Coverage vs no-echo shown differently.
- **Legend:** perceptually uniform, colour-vision-deficiency-safe ramp; dBZ plus plain words (light/moderate/heavy/very heavy) plus estimated mm/h labelled as estimate.
- **Shareable state in the URL:** location, zoom, time, layer, language. Round-trips exactly.
- **3D buildings:** auto-off on low-end devices (device memory, measured frame rate), user override remembered.
- **Favourites** show a mini "next hour" summary.

---

## 8. Phase 4 — Notifications

- **Preferences per location:** intensity threshold (any/moderate/heavy), lead time, quiet hours, "rain stopping" alerts, max alerts per day, snooze.
- **Hysteresis and debounce** so a borderline forecast does not cause flapping alerts.
- **Delivery telemetry:** the service worker reports anonymous received / displayed / discarded-as-expired events, so we know end-to-end latency per platform.
- **"Send test notification"** button.
- **Deep links:** tapping a notification opens that location at that time.
- **iOS guidance:** explain that push requires installing the PWA to the home screen (iOS 16.4+), shown only to iOS users.
- Keep every existing safety rule: no "current rain" from observations older than 15 min, skip past forecast times, expiry in payloads, service worker discards stale messages.

---

## 9. Phase 5 — Accessibility, language and content

- **WCAG 2.2 AA** across the app. The map is not accessible to screen readers by itself, so provide a full text equivalent (the headline, chart data as a table, timeline state announced via a live region).
- Keyboard-only use of every feature, visible focus, 44×44 px touch targets, 200% zoom and 320 px reflow without loss.
- **Language:** CI check for key parity between Danish and English and for hardcoded strings. Danish default for Danish locales. Danish formats (24-hour, comma decimal, Danish date names).
- **Copy review:** plain, calm, non-alarmist. "Live" always paired with age. mm always "about"/"estimated".

---

## 10. Phase 6 — Performance budgets

| Metric | Target (mid-range Android, 4G, p75) |
|---|---|
| LCP | ≤ 2.5 s |
| INP | ≤ 200 ms |
| CLS | ≤ 0.1 |
| App shell interactive before map ready | yes (MapLibre lazy-loaded in its own chunk) |
| Location answer visible | ≤ 1.5 s after location known (warm cache) |
| Playback | ≥ 50 fps, no frame drops on scrub |
| Memory after 30 min playback | stable (no leak), within iOS Safari limits |
| API point forecast (warm edge cache) | p95 ≤ 150 ms |
| API point forecast (cold) | p95 ≤ 800 ms |

Fix the MapLibre code-splitting warning. Add size budgets to CI so they cannot regress.

---

## 11. Phase 7 — Reliability, observability, security, privacy

- **SLOs with alerting:** radar freshness (≤ 25 min), API availability, alert end-to-end latency, nowcast pipeline duration. Error budgets documented.
- **Dashboards** (Grafana and Sentry, with PII scrubbing): freshness, pipeline stages, cache hit rate, upstream failures and fallbacks, push sent/received/discarded, forecast quality per horizon.
- **Resilience:** request coalescing so cache misses never stampede DMI; last-known-good with visible staleness; detection of delayed or missed Actions cron runs.
- **Security:** Cloudflare WAF and rate limits, strict CSP, HSTS, Permissions-Policy (geolocation self only), container image digest pinning, automated dependency updates, no secrets in client bundles.
- **Privacy:** publish a privacy notice (Danish and English) and a retention policy; automated deletion of expired subscriptions and expired data; documented legal basis for storing rounded coordinates.
- **Runbooks** for: DMI outage, stale radar, bad promotion rollback, push key rotation, R2 incident.

---

## 12. Phase 8 — Mobile polish and PWA

- Bottom sheet for the location answer with thumb-reachable controls; safe-area insets; landscape support.
- Install prompt at a sensible moment (after a second visit or after saving a favourite), never on first load.
- Offline: last data shown with a clear "offline · data from HH:MM" banner; never present cached radar as fresh.
- Smooth update flow for new service worker versions.

---

## 13. Stretch (only after everything above is accepted)

- DMI lightning observations as an optional layer.
- Rain-gauge comparison overlay ("radar said X, gauge measured Y").
- Event replay: share a past rain event as a link.

---

## 14. Definition of done and reporting

A phase is done only when:

- All acceptance criteria are met, with evidence linked in `docs/PROGRESS.md`.
- CI, security scans and size budgets are green.
- No forecast metric regressed on the backtest or live shadow.
- Documentation, ADRs, OpenAPI contract and runbooks are updated.

At the end of each phase, report in this format:

```
Phase: …
Changed: (bullet list, links to PRs)
Evidence: (tests, metrics before → after, screenshots)
Not done / deferred: (and why)
Risks and open questions:
Recommended next step:
```

Be blunt about what did not work. A negative result with good evidence is useful; a vague success is not.
