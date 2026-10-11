# Caching and cache keys

- Frame key: `frames/<DMI item id>.webp`; immutable for one year. If DMI republishes an ID with changed bytes, worker must fail/alert rather than mutate a cached object.
- Manifest key: `frames/frames.json`; `max-age=60, stale-while-revalidate=300`, ETag from object/content hash.
- Forecast key: API path plus latitude/longitude rounded to 2 decimals, 10-minute TTL, six-hour stale-while-revalidate allowance and last-known-good R2 storage.
- Next-hour precipitation key: API path plus coordinates rounded to 2 decimals, 5-minute TTL, 30-minute stale-while-revalidate allowance and only still-future persisted points.
- Browser service worker keeps 24 frames for two hours and 180 basemap responses for one day. It never intercepts DMI directly.
- API in-memory cache is per replica; CDN is the shared cache. Do not add Redis until cache-hit metrics demonstrate a need.
