# Verification results

This file is updated by maintainers/CI. Do not interpret configured workflows as executed evidence.

| Check | Result | Environment |
|---|---|---|
| Live DMI STAC metadata | Passed 2026-10-10 | `dk.com.202610101945.500_max.h5` |
| Live HDF5 schema/statistics inspection | Passed 2026-10-10 | Local temporary file; details in `DMI-DATA-NOTES.md` |
| Web ESLint + strict TypeScript | Passed 2026-10-10 | Local Node 25 / TS 5.9.3 |
| Web Vitest | Passed: 4/4 | jsdom |
| Shared TypeScript + Vitest | Passed: 2/2 | Local |
| Web production build + PWA | Passed; MapLibre lazy chunk warns at 286 KB gzip | Vite 8.3.4 |
| Edge strict TypeScript + Worker dry-run | Passed; bundle 5.72 KiB / 2.12 KiB gzip | Wrangler 4.149.0 |
| pytest worker | Passed: 4/4 | Python 3.12 container |
| Real DMI HDF5 → WebP | Passed; 309 KB lossless transparent WebP, SHA-256 recorded | Live composite in `/tmp`, not committed |
| .NET restore/build/xUnit | Existing suite passed 3/3 in .NET 10 container; updated API and two added service tests compile locally | .NET SDK 10.0.401; final xUnit execution is repeated by CI because the sandbox blocks the local test-host socket |
| Docker/Compose end-to-end | Passed 2026-10-10; all images built, worker completed 13 live frames, API ready, web/API/frame routes returned 200 | Docker Desktop on Apple Silicon |
| Compose production web bundle | Passed; Vite emitted the MapLibre module worker and Nginx served the application with live radar controls | Vite 8.3.4 / Nginx 1.29 |
| Browser smoke check | Passed; latest observation is selected, playback advances, responsive 390×844 and desktop layouts fit, MapLibre renders | Chromium-based in-app browser |
| Cloudflare production radar API | Passed 2026-10-10; 13 frames, latest observation `2026-10-10T21:35:00Z`, latest WebP returned 200 | `wetmap-api.wetmap-edge.workers.dev` + R2 |
| Cloudflare production URL | Passed before final redeploy; map, radar, forecast and PWA shell loaded | `wetmap.pages.dev` |
| Grafana/Sentry dashboards and alerts | Not run | Requires owner accounts |
