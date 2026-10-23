# Phone layout and initial map rendering — 23 October 2026

Implemented under [ADR 0006](adr/0006-mobile-weather-dock.md), following the owner's
approval to start a phone sprint. This remains the shared React PWA, within the
free-only constraint.

## Changes

- A single bottom dock replaces overlapping mobile forecast/timeline panels up to
  850 px wide. It initially shows location, rain status, source, confidence and the
  radar time/play controls. Forecast and timeline details expand individually.
- All four hourly forecast rows remain accessible in expanded mode. Rain detail,
  intensity labels, alert settings and explanation are accessible by expanding it.
- Dynamic viewport height, safe-area spacing and scrolling bound the dock. Landscape
  places it on the right so the map remains visible on the left.
- Main controls have at least 44 px touch targets; search uses 16 px text to avoid
  automatic input zoom on iOS. Precision Observatory is accessible on narrow phones.
- Small-screen or low-memory starts use 2D without constructing building extrusions.
  The user's 2D/3D override is remembered; 2D preloads two frames rather than three.
- Scrubbing pauses playback. A pending style load respects the selected building mode.
- Scoped map-control positioning prevents MapLibre's asynchronously loaded CSS from
  placing controls behind search.

## Verification

`pnpm check` passed lint, strict type checks, 56 TypeScript tests (20 web, 34 edge,
2 shared), and builds. The existing MapLibre bundle-size warning remains.
Interaction regressions cover compact defaults, mutually exclusive expansion, manual
scrubbing, persisted map choice, and switching building mode after style load.

Installed Google Chrome in headless mode was tested with live public WetMap API data
and OpenFreeMap tiles on a local preview. Viewports: 320×568, 390×844, 412×915,
768×1024, 844×390 landscape, and 1440×1000 desktop. Checks passed for horizontal
overflow, dock bounds, map-control/search overlap, forecast/timeline expansion,
2D/3D changes, preference persistence, Danish/English labels and uncaught JS errors.
The browser report is [results.json](evidence/mobile-sprint-1/results.json).

Representative screenshots:

- [390 px compact, Danish](evidence/mobile-sprint-1/iphone-compact-da.png)
- [390 px forecast expanded, English](evidence/mobile-sprint-1/iphone-forecast-en.png)
- [Landscape compact](evidence/mobile-sprint-1/landscape-compact-da.png)
- [Desktop regression](evidence/mobile-sprint-1/desktop-da.png)

## Recheck steps

1. Open a fresh browser profile at each viewport size with storage cleared.
2. Wait for the map/rain answer; confirm the initial mobile dock stays inside the
   viewport, source/confidence remain visible and zoom controls clear search.
3. Expand the forecast, then the timeline. Confirm the other details collapse and
   scroll to reach all controls in short viewports.
4. Start playback and scrub to an earlier frame. Confirm playback pauses at that time.
5. Switch 2D to 3D and reload; confirm the explicit preference persists. Switch back.
6. Repeat in English and landscape, including Precision Observatory and search.
7. Confirm desktop retains the independent panels and existing forecast details.

## Remaining evidence

These are Chrome viewport checks, not physical iPhone/Safari or Android verification.
Actual device installation, keyboard/safe-area behavior, background push delivery,
offline resumption, FPS, battery consumption and new Core Web Vitals measurements
remain to be tested. This sprint does not establish forecast accuracy or complete
the independent release acceptance test.
