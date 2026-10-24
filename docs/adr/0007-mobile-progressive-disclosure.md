# ADR 0007: One mobile view at a time

Status: accepted, 2026-10-24, following owner feedback that the first phone layout was
too cluttered. Refines the mobile layout in ADR 0006; map rendering defaults remain.

## Decision

The phone starts with two surfaces: a combined search/data-age header, and one
compact rain overview at the bottom. Hide floating map controls and the separate
timeline on this initial view. Keep source, qualitative confidence and the actual
displayed radar/nowcast time visible.

Three labelled navigation buttons select Rain, Radar or More. Only the selected
panel is visible. Radar contains playback and the timeline; More contains map
opacity, 2D/3D, language and access to Precision Observatory. The user can expand
the rain overview to access the chart, forecast and alerts. Compact rain content
uses plain text rather than nested cards and a row of numeric badges.

Keep panels mounted so switching views preserves location and alert state. Reset
the dock scroll position when selecting a view. The existing desktop presentation,
weather calculations, APIs and free-only constraint remain in place.

## Verification

The interaction regression checks initial visibility, transitions between all three
views, and access to language/quality controls through More. Chrome checks cover
six viewports and both languages; the compact portrait dock is capped by a test at
40% of viewport height for the tested live-data state. This is a visual refinement,
not a claim of physical iPhone/Safari verification or improved forecast accuracy.
