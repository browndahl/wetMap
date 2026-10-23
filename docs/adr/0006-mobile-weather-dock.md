# ADR 0006: Responsive weather dock and device-aware map defaults

Status: accepted, 2026-10-23. Owner approved the phone layout and performance sprint.

## Decision

Continue with the existing React PWA and shared forecast APIs. At viewport widths up
to 850 px, place the location forecast and radar timeline in one scrollable bottom
dock. Initially show the location, next-hour rain headline, source and confidence,
and the timeline's observation time/play controls. Expand forecast details or timeline
controls individually so the panels do not cover one another. Retain desktop panels.

Use 2D initially on small screens and on devices reporting at most 4 GB memory.
An explicit 2D/3D choice takes precedence and is remembered in browser storage.
Initialize the map with that mode and create building extrusions only when requested.
Prefetch the active and next radar frame in 2D, compared with three frames in 3D.
Manual timeline scrubbing pauses playback to preserve the selected time.

## Scope and consequences

- Safe-area spacing, dynamic viewport height, a bounded scroll region and 44 px main
  controls support narrow screens, landscape and browser chrome changes.
- The existing forecast calculations, quality gates and alert delivery remain shared
  with desktop. Collapsing details leaves the rain component mounted, retaining alert
  subscription state and location changes.
- This adds no service, paid dependency or storage expansion. It follows the free-only
  constraint in ADR 0005.
- Width/memory are conservative defaults, not a measured frame-rate classifier. There
  is no claimed FPS or Core Web Vitals improvement until measured.
- Chrome viewport checks supplement interaction tests. Physical iPhone/Safari and
  Android testing, installation and push delivery remain separate verification work.

## Rollback

Revert this sprint's frontend commit to restore the prior layout and map defaults.
The `wetmap:precise-2d` local preference is optional and requires no data migration.
