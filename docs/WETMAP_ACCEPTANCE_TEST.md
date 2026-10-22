# WetMap — Release acceptance test

You are an independent release tester for WetMap. You did not build the changes under test, and your job is to find problems, not to confirm success. The system context is in `docs/SYSTEM_CONTEXT.md` and the build brief in `docs/WETMAP_BUILD_PROMPT.md`. Read both, then test staging first and production only with read-only checks.

## Rules

1. **No PASS without evidence.** Every result links to command output, a test report, a screenshot, a recording or a metric.
2. **Do not fix code during this run.** If something fails, record it with reproduction steps. Fixes happen in a separate session.
3. **Never weaken a threshold** to make a check pass. If a threshold looks wrong, flag it separately.
4. **Flaky = FAIL** until it passes 3 consecutive reruns, and the flakiness itself is logged as a defect.
5. Mark checks that need a person (real devices, screen readers, native-speaker review) as **HUMAN** and provide a step-by-step script for them.
6. Use statuses: `PASS`, `FAIL`, `BLOCKED` (could not run, with reason), `HUMAN` (needs a person).

## Two separate verdicts

- **Release readiness:** RELEASE only if every blocking check (marked ⛔) is PASS.
- **Forecast quality:** reported per horizon against the gates. A horizon that does not yet beat the gates is not an app defect. A horizon that was *promoted* without passing the gates is a ⛔ failure.

"100% good" means: every blocking check passes with evidence, and every forecast horizon in production has legitimately earned its place. It does not mean the forecast is never wrong.

---

## A. Build and static checks

| ID | Check | Pass criterion |
|---|---|---|
| A1 ⛔ | Full CI on the release commit | All jobs green |
| A2 ⛔ | Lint and strict type check (TS), Ruff, .NET build | Zero errors |
| A3 ⛔ | Unit tests (web, edge, shared, Python, .NET) | All pass; coverage not below previous release |
| A4 ⛔ | CodeQL, Gitleaks, Trivy | Zero high/critical; no secrets |
| A5 | SBOM generated and attached | Present and complete |
| A6 ⛔ | Bundle size budgets | Within budget; MapLibre in its own lazy chunk; no code-split warning |
| A7 | i18n key parity and hardcoded-string scan | 100% parity, zero hardcoded user-facing strings |

## B. Radar data pipeline

| ID | Check | Pass criterion |
|---|---|---|
| B1 ⛔ | Feed malformed ODIM files (wrong schema, missing DBZH, truncated, wrong projection) | Each rejected cleanly; production keeps last-known-good |
| B2 ⛔ | SHA-256 of 20 random stored frames | All match manifest |
| B3 ⛔ | Georeferencing: overlay a frame on the map and check radar site positions and a known coastline echo | Misalignment < 1 grid cell |
| B4 | Re-run ingestion for the same observation | Idempotent: no duplicate or changed objects |
| B5 ⛔ | Coverage vs no-echo | Out-of-coverage areas never rendered or reported as "dry" |
| B6 | End-to-end latency (DMI publish → client visible) | p95 within documented target |
| B7 ⛔ | Simulate missed/delayed Actions run | Freshness alert fires; UI shows age honestly |

## C. Forecast verification audit

| ID | Check | Pass criterion |
|---|---|---|
| C1 ⛔ | Recompute CSI, precision, recall, FAR, MAE, Brier and persistence skill for ≥ 50 stored pairs with an independent implementation (e.g. pysteps verification) | Matches reported values within 0.5 pp |
| C2 ⛔ | Time alignment: forecast T+n compared to observation *valid* at T+n | Verified in code and on data |
| C3 ⛔ | Persistence baseline uses the identical input frame | Verified |
| C4 ⛔ | Shadow isolation: no unpromoted challenger output in any public manifest or API response | Zero leaks across 24 h of manifests |
| C5 ⛔ | Promotion logic unit tests: each gate failing alone blocks promotion; per-horizon independence | All pass |
| C6 ⛔ | Gates unchanged vs `docs` / previous release (or an approved ADR exists) | Diff reviewed |
| C7 ⛔ | Backtest split: no test-period dates used in tuning | Verified from config and logs |
| C8 | Additive metrics present: FSS (multi-scale), reliability, ROC, CRPS, point arrival-time error | Reported per horizon and regime |
| C9 | Probability calibration | Reliability curve within ±10 pp of diagonal in populated bins |
| C10 | Ensemble spread grows with lead time | Monotonic spread; spread–skill ratio reported |

Report a table: horizon · incumbent · challenger · CSI · FSS(10 km) · skill vs persistence · gate status · promoted?

## D. API contract and resilience

| ID | Check | Pass criterion |
|---|---|---|
| D1 ⛔ | Property-based contract tests against `openapi/wetmap-v1.yaml` (e.g. Schemathesis) on all public endpoints | Zero schema violations, zero 5xx |
| D2 ⛔ | Byte-range point lookup vs full-grid lookup at 200 random points | Identical values |
| D3 ⛔ | Inject DMI HARMONIE timeout and 5xx | Open-Meteo fallback used and labelled as fallback |
| D4 ⛔ | Inject DMI radar outage | Last-known-good served with correct age; no "current" claims |
| D5 ⛔ | CORS: request from a non-allow-listed origin | Rejected |
| D6 | Cache headers and hit rate on repeat requests | Correct `Cache-Control`; hit rate as documented |
| D7 | Rate limiting | Excess requests get 429, normal use unaffected |
| D8 ⛔ | Cache-miss stampede (500 concurrent cold requests, same point) | One upstream request (coalesced) |
| D9 | Load test (e.g. k6), sustained and burst | Latency budgets met; zero errors; no upstream overload |

## E. Location answers (golden set)

Test each location for search, reverse geocoding, the headline, chart, sources and coverage handling:

Copenhagen, Aarhus, Odense, Aalborg, Esbjerg, Holbæk, Skagen, Rønne (Bornholm), Ærøskøbing, a point in the Kattegat, Malmö, Flensburg, Tórshavn, Nuuk.

| ID | Check | Pass criterion |
|---|---|---|
| E1 ⛔ | Search with æ/ø/å and variants ("Århus"/"Aarhus", "Køge"/"Koge", "Ærø"/"Aero") | Correct top result |
| E2 ⛔ | Locations outside radar coverage | Clear "outside radar coverage"; model forecast only, labelled |
| E3 ⛔ | Headline matches underlying data | Arrival/stop times and intensity consistent with chart and API |
| E4 ⛔ | Uncertainty shown as ranges when confidence is low | Never a single exact minute at low confidence |
| E5 | Dry-window finder | Window lies inside forecast dry period for chosen duration |
| E6 | Precipitation type | Snow/sleet shown only when model temperatures support it; labelled model-based |
| E7 ⛔ | mm/mm·h values | Always labelled as estimates |

## F. Time, clocks and DST

| ID | Check | Pass criterion |
|---|---|---|
| F1 ⛔ | DST end, 25 Oct 2026 (02:00–03:00 occurs twice): replay or mock data across it | No duplicated, missing or misordered intervals; labels unambiguous |
| F2 ⛔ | DST start (last Sunday of March) | Same |
| F3 ⛔ | Device clock wrong by ±10 min | Data age and "now" marker still correct (server time used) |
| F4 | Device in another time zone | Behaviour matches documented choice and is labelled |
| F5 ⛔ | Forecast times already in the past | Never shown as upcoming |
| F6 | Midnight crossing in 15-min intervals and chart | Correct day labels |

## G. Map and timeline (automated end-to-end, e.g. Playwright, Chromium/WebKit/Firefox)

| ID | Check | Pass criterion |
|---|---|---|
| G1 ⛔ | Autoplay on load, visible pause, stops under reduced motion | All true |
| G2 ⛔ | "Now" marker; observed vs forecast frames distinguishable; estimated-now frame labelled | All true |
| G3 | Scrub by drag, keyboard (space, arrows, Home/End), speed and loop range | All work |
| G4 | Intensity vs probability layer toggle; legend updates | Correct |
| G5 ⛔ | URL state round-trip (location, zoom, time, layer, language) | Exact restore |
| G6 | Favourites persist across reloads; mini summary correct | True |
| G7 | Language switch keeps state | No reset |
| G8 | 3D buildings toggle; auto-off on simulated low-end device | Correct |
| G9 | Tap-anywhere mini forecast | Matches API for that point |
| G10 | Visual regression: light/dark × da/en × 360/768/1440 px | No unapproved diffs |

## H. Accessibility

| ID | Check | Pass criterion |
|---|---|---|
| H1 ⛔ | Automated scan (axe) on every screen and state | Zero serious/critical |
| H2 ⛔ | Keyboard-only walkthrough of every feature | Everything reachable and operable; visible focus |
| H3 ⛔ | Text equivalent of the map and timeline | Headline, data table and live-region announcements present |
| H4 | Contrast (text and legend) | WCAG 2.2 AA |
| H5 | 200% zoom and 320 px reflow | No loss of content or function |
| H6 | Colour-vision deficiency simulation (protan, deutan, tritan) | Intensity levels still distinguishable |
| H7 HUMAN | VoiceOver (iOS) and TalkBack (Android) walkthrough | Script provided; results recorded |

## I. Performance

| ID | Check | Pass criterion |
|---|---|---|
| I1 ⛔ | Lighthouse CI, mobile throttled, 5 runs median | LCP ≤ 2.5 s, CLS ≤ 0.1, TBT within budget |
| I2 ⛔ | INP on interaction script (scrub, search, toggle) | ≤ 200 ms |
| I3 | Playback frame rate on mid-range device | ≥ 50 fps |
| I4 ⛔ | 30-minute playback memory profile | No upward trend; no crash on iOS Safari |
| I5 | API latency warm/cold | p95 ≤ 150 ms / ≤ 800 ms |

## J. PWA and offline

| ID | Check | Pass criterion |
|---|---|---|
| J1 | Installable on Android Chrome, iOS Safari, desktop Chrome/Edge | True |
| J2 ⛔ | Offline launch | Last data with "offline · data from HH:MM"; never presented as fresh |
| J3 | Service worker update flow | New version activates cleanly; no stale-asset mix |

## K. Notifications

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
| K9 | Test-notification button | Arrives on all supported platforms |
| K10 HUMAN | Real-device matrix: Android Chrome, iOS installed PWA, macOS Safari, Windows Chrome/Edge/Firefox; app closed, backgrounded, device locked | Delivery and latency recorded per cell |

## L. Security and privacy

| ID | Check | Pass criterion |
|---|---|---|
| L1 ⛔ | Security headers: CSP, HSTS, X-Content-Type-Options, Referrer-Policy, Permissions-Policy (geolocation self) | Present and strict |
| L2 ⛔ | Passive scan (e.g. OWASP ZAP baseline) on staging | Zero high/medium |
| L3 ⛔ | No secrets, keys or internal URLs in client bundles or source maps | Verified |
| L4 ⛔ | Geolocation requested only after user action | Verified with fresh profile |
| L5 ⛔ | Privacy notice and retention policy published (Danish and English) and match actual behaviour | True |
| L6 | Retention/cleanup jobs | Expired data actually deleted |
| L7 | Container images pinned by digest; run read-only, non-root | Verified |

## M. Language and content

| ID | Check | Pass criterion |
|---|---|---|
| M1 | Danish formats (24 h, comma decimal, Danish day/month names) | Correct everywhere |
| M2 ⛔ | "Live" always paired with data age; no claim of ground-truth rainfall | Verified on every screen |
| M3 HUMAN | Native Danish speaker reviews all copy | Natural, calm, unambiguous |

## N. Observability and operations

| ID | Check | Pass criterion |
|---|---|---|
| N1 | Dashboards show freshness, pipeline stages, cache, fallbacks, push telemetry, forecast quality | Populated with real data |
| N2 ⛔ | Alert drill: force stale radar | On-call alert fires within SLO |
| N3 ⛔ | Rollback drill: revert a promoted horizon | Production returns to incumbent; documented time |
| N4 | Runbooks exist and were followed successfully in the drills | True |

---

## Report format

Produce `docs/ACCEPTANCE_REPORT.md`:

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
