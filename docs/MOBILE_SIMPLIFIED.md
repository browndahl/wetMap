# Simplified phone interface — 24 October 2026

Owner feedback: the first phone sprint exposed too many panels and controls at once.
[ADR 0007](adr/0007-mobile-progressive-disclosure.md) records the refinement.

- Combined search and radar-age header, with the displayed frame time visible.
- One compact rain answer at startup. Removed nested compact cards, amount totals
  and numeric confidence badges from that summary; source and confidence remain.
- Rain / Radar / More navigation shows one panel at a time.
- Floating map controls, language and quality access are available through More.
- Expanded rain details retain the chart, explanations, hourly forecast and alerts.
- Switching views resets scroll position. Desktop layout remains available.

Validation: `pnpm check` (56 tests, lint, type checks and builds), plus Chrome
viewport checks at 320×568, 390×844, 412×915, 768×1024, 844×390 and 1440×1000.
The checks cover view isolation, controls remaining reachable, both languages,
horizontal overflow, dock bounds and uncaught JavaScript errors. On the tested live
data, the compact portrait dock occupied no more than 40% of viewport height.

Evidence: [browser results](evidence/mobile-simplified/results.json),
[390 px overview](evidence/mobile-simplified/overview-da.png),
[320 px overview](evidence/mobile-simplified/small-da.png),
[settings](evidence/mobile-simplified/settings-da.png).

Physical Safari/Android, installation, push delivery and new performance measurements
remain open as documented in the first sprint. No service or paid dependency added.
