# ADR 0013: Rain-first interface and explicit radar navigation

Date: 2026-11-13. Owner requested a further UI/UX refinement.

## Decision

Keep the existing map, cyan/navy identity and phone Rain/Radar/More navigation.
On desktop, make next-hour rain the primary answer; move hourly temperature/wind
behind an accessible disclosure. Retain the phone's small initial summary, with
an explicit entry to rain details and alerts. Improve type sizes, interval labels,
panel contrast and short-screen containment without adding a dependency.

Offer explicit History / Latest reading / Forecast choices. Manual choices pause
playback; returning to the latest observation remains available even when the
timeline is collapsed. Keep source time and estimated uncertainty distinguishable
from wall-clock time. Data-age explanations must work by tap/keyboard, not hover
alone. Put technical map controls and methodology behind a native disclosure;
do not alter or hide quality gates, source attribution or alert restrictions.

Opaque shared panel tokens replace live-map backdrop blur. This is a readability
and compositing-work reduction, not a measured FPS or WCAG-conformance claim.
The optional local development proxy target does not widen production CORS.

## Boundaries and rollback

No forecast, radar transformation, scoring, source cadence, notification policy,
backend cache or paid-service change. Preserve autoplay/reduced-motion behavior,
saved map preferences, language support and the existing collapse preference.
Revert the UI changes to roll back; no data migration or deletion is involved.

Require unit/type/lint/build budgets, CI/security, viewport interaction checks and
visual inspection before rollout. Physical iPhone/Safari validation remains separate.
See the dated UI/UX report and screenshot evidence.
