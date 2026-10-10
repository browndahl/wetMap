# Verification results

This file is updated by maintainers/CI. Do not interpret configured workflows as executed evidence.

| Check | Result | Environment |
|---|---|---|
| Live DMI STAC metadata | Passed 2026-10-10 | `dk.com.202610101945.500_max.h5` |
| Live HDF5 schema/statistics inspection | Passed 2026-10-10 | Local temporary file; details in `DMI-DATA-NOTES.md` |
| Web ESLint + strict TypeScript | Passed 2026-10-10 | Local Node 25 / TS 5.9.3 |
| Web Vitest | Passed: 1/1 | jsdom |
| Shared TypeScript + Vitest | Passed: 2/2 | Local |
| Web production build + PWA | Passed; MapLibre lazy chunk warns at 286 KB gzip | Vite 8.3.4 |
| Edge strict TypeScript + Worker dry-run | Passed; bundle 5.72 KiB / 2.12 KiB gzip | Wrangler 4.149.0 |
| pytest worker | Passed: 3/3; two Rasterio internal pending-deprecation warnings | Python 3.9 test venv; production target 3.12 |
| Real DMI HDF5 → WebP | Passed; 309 KB lossless transparent WebP, SHA-256 recorded | Live composite in `/tmp`, not committed |
| .NET restore/build/xUnit | Passed: 3/3, 307 ms | Isolated .NET SDK 10.0.401 in `/tmp` |
| Docker/Compose end-to-end | Passed 2026-10-10; all images built, worker completed 13 live frames, API ready, web/API/frame routes returned 200 | Docker Desktop on Apple Silicon |
| Compose production web bundle | Passed; Vite emitted the MapLibre module worker and Nginx served the application with live radar controls | Vite 8.3.4 / Nginx 1.29 |
| Browser smoke check | Passed for shell, live manifest and graceful forecast fallback; MapLibre worker execution was unavailable in this in-app browser session | Chromium-based in-app browser |
| Cloudflare production URL | Not run | Requires owner credentials |
| Grafana/Sentry dashboards and alerts | Not run | Requires owner accounts |
