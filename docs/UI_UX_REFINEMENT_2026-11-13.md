# Rain-first UI/UX refinement — 13 November 2026

Owner requested a clearer, better interface. [ADR 0013](adr/0013-rain-first-interface.md)
records scope and rollback. This sprint improves presentation and interaction,
not weather accuracy; +45/+60-minute quality limitations remain unchanged.

## Changes

- Desktop starts with the selected location and next-hour rain, rather than four
  temperature rows above a very small rain summary. Temperature/wind can be expanded
  without unexpectedly collapsing the desktop radar panel.
- Larger rainfall amounts, interval times, intensity/source labels and confidence
  text. Low confidence is labelled in words, not colour alone. Danish decimal
  formatting is consistent for rainfall totals and wind.
- History / Latest reading / Forecast buttons make observed and predicted radar
  easier to distinguish. Future/history controls disable when unavailable. Manual
  navigation pauses playback; the latest shortcut works with a collapsed timeline.
  Collapsed predicted frames still show estimated confidence.
- Map controls/methodology use a native disclosure. Source time, current clock,
  confidence and attribution remain available; no quality gate is removed.
- Radar freshness opens a tap/keyboard-readable explanation with the actual measured
  time. An empty resolved manifest is labelled unavailable, not loading forever.
  Empty-state wording is suitable for visitors, rather than asking them to run a worker.
- Solid panel backgrounds improve contrast over buildings/radar without live-map
  backdrop blur. No new font, image, package, paid service or backend is introduced.
- Phone Rain/Radar/More isolation and the small startup summary are retained. The
  rain-details/alerts entry is explicit. Expanded content scrolls inside one bounded
  dock. Additional header clearance prevents collisions on small/landscape screens;
  the narrowest radar header separates time/status from touch controls.

## Verification

`pnpm check` passed lint, types, **86 TypeScript tests** (32 web, 52 edge, 2 shared)
and builds. Worker **84 tests** and monitoring **29 tests** also passed, though their
code is unchanged. Four new app tests cover primary hierarchy/disclosure, explicit
observed/predicted selection, paused manual navigation, collapsed uncertainty,
missing future frames and unavailable radar. Existing autoplay, resume, search,
weak-echo, blocked-alert and push-subscription tests remain in place.

Entry JS stays below the unchanged 110,000-byte gzip budget; map/worker stay below
320,000 / 170,000 bytes. No budget was raised. There is no measured FPS improvement
or new end-user latency claim. The existing lazy MapLibre >500 KB advisory remains.

The in-app browser checked layouts at **320×568, 390×844, 768×1024, 844×390,
1024×768 and 1440×900**. Default outer panels/dock fit all six viewports. Expanded
phone content is intentionally taller and scrolls inside the contained dock, rather
than requiring every child to fit the screen. English settings/radar at 320 px,
native data-help activation with Enter, phone view isolation and return-to-latest
were exercised. These are viewport checks, not physical iPhone/Safari acceptance.

Evidence: [layout results](evidence/uiux-2026-11-13/layout-checks.json),
[desktop](evidence/uiux-2026-11-13/desktop.jpg),
[phone overview](evidence/uiux-2026-11-13/mobile-390-da.jpg),
[small English radar](evidence/uiux-2026-11-13/radar-320-en.jpg),
[keyboard-opened data help](evidence/uiux-2026-11-13/data-help-320-en.jpg).
Images use public weather/default Aarhus coordinates, not the owner's geolocation.

## Reproduce local review

```sh
WETMAP_DEV_API_TARGET=https://wetmap-api.wetmap-edge.workers.dev pnpm --filter @wetmap/web exec vite --host 127.0.0.1 --port 5174
```

Leave VITE_API_BASE_URL and VITE_FRAMES_BASE_URL unset for the same-origin dev proxy.
The default remains localhost:8080 for compose development. Production CORS and
network settings are unchanged. CI/security, production deployment and final live
interaction checks are required before describing this checkpoint as live.

## Temperature-first follow-up — owner feedback

The owner requested temperature as the first visible information after selecting a
location. A large °C value now leads the location header on desktop and phone,
above rain and independent of the hourly-details disclosure. It is explicitly an
hourly forecast with a valid time, not an observed real-time measurement. Location
selection reveals the phone overview and resets panel scroll position.

Previous-location placeholder data never supplies the headline temperature. Pending,
failed or missing values show a dash and an honest status, not a stale city's value
or a fabricated zero. Six regression cases cover normal/negative/zero/missing
temperatures, delayed location changes and mobile radar-to-overview selection.
Web suite: 38 tests; TypeScript total: 92. No extra request, source or backend change.

Local browser checks cover desktop, 390×844 and 320×568, including an actual map
click from mobile radar: the overview opens with a loading placeholder, followed by
the selected location's temperature. The temperature and outer dock remain visible
on the small viewport. [Desktop](evidence/uiux-2026-11-13/temperature-desktop.jpg)
and [phone](evidence/uiux-2026-11-13/temperature-mobile.jpg) show the follow-up.
