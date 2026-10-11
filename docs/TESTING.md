# Test strategy

- Unit: shared contracts/color ordering, HDF calibration/georeprojection, optical-flow advection/risk grids, API validation, push subscription validation and Mercator location lookup.
- Contract: real DMI schema is documented; synthetic ODIM fixture carries the verified attributes without committing DMI binary data.
- Integration: .NET `WebApplicationFactory`; Docker health and manifest path.
- Accessibility: Playwright + axe against the built app; keyboard range/buttons and reduced-motion are first-class.
- Visual: browser screenshots against the cache-free staging deployment; verify automatic animation, observation/nowcast labelling, rain interval legibility, and responsive chrome.
- Load: `tests/load/api.js` validates cached manifest/forecast response rate without attacking DMI; only run against staging.
- Chaos: `apps/worker/tests` and runbook cover 429, corrupt HDF, schema changes, isolated nowcast failure, stale risk grids, and last-good-manifest behavior.
- Web Push: unit tests cover opt-in, persistence, opt-out, CORS rejection and risk lookup. True background delivery must additionally be smoke-tested on a real notification-capable browser/device because jsdom and CI cannot grant OS notification permission.
