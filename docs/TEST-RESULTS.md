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
| Edge strict TypeScript + Vitest + Worker dry-run | Passed: 7/7 tests; bundle and deployment validated | Wrangler 4.149.0 |
| pytest worker | Passed: 4/4 | Python 3.12 container |
| Real DMI HDF5 → WebP | Passed; 309 KB lossless transparent WebP, SHA-256 recorded | Live composite in `/tmp`, not committed |
| .NET restore/build/xUnit | Passed 3/3 in GitHub CI | .NET 10 hosted runner |
| Docker/Compose end-to-end | Passed 2026-10-10; all images built, worker completed 13 live frames, API ready, web/API/frame routes returned 200 | Docker Desktop on Apple Silicon |
| Compose production web bundle | Passed; Vite emitted the MapLibre module worker and Nginx served the application with live radar controls | Vite 8.3.4 / Nginx 1.29 |
| Browser smoke check | Passed; latest observation is selected, playback advances, responsive 390×844 and desktop layouts fit, MapLibre renders, and point forecasts survive location changes | Chromium-based in-app browser |
| Forecast production API | Passed for eight Danish cities; 48 points each; cached 40-request load averaged 59 ms with 73 ms p95 | Cloudflare Worker + Open-Meteo DMI primary + direct DMI fallback |
| Automated radar ingestion | Passed 2026-10-11; first GitHub Actions run completed in 33 seconds and freshness validation passed | Private GitHub Actions + bucket-scoped R2 credentials |
| Cloudflare production radar API | Passed 2026-10-11; 13 frames, latest observation `2026-10-10T22:35:00Z`, fetched `2026-10-10T22:45:03Z` | `wetmap-api.wetmap-edge.workers.dev` + R2 |
| Cloudflare production URL | Passed after final deployment; map, current radar status, forecast and PWA shell loaded | `wetmap.pages.dev` |
| Synthetic production workflow | Passed; Pages, API liveness, radar manifest, and 30-minute freshness check | GitHub Actions run `38092441627` |
| Grafana/Sentry dashboards and alerts | Not run | Requires owner accounts |
