# Test strategy

- Unit: shared contracts/color ordering, HDF calibration/georeprojection, API validation.
- Contract: real DMI schema is documented; synthetic ODIM fixture carries the verified attributes without committing DMI binary data.
- Integration: .NET `WebApplicationFactory`; Docker health and manifest path.
- Accessibility: Playwright + axe against the built app; keyboard range/buttons and reduced-motion are first-class.
- Visual: Playwright screenshots with the map network mocked for deterministic UI chrome.
- Load: `tests/load/api.js` validates cached manifest/forecast response rate without attacking DMI; only run against staging.
- Chaos: `apps/worker/tests` and runbook cover 429, corrupt HDF, schema changes, and last-good-manifest behavior.
