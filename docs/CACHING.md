# Caching and cache keys

- Frame key: `frames/<DMI item id>.webp`; immutable for one year. If DMI republishes an ID with changed bytes, worker must fail/alert rather than mutate a cached object.
- Manifest key: `frames/frames.json`; `max-age=60, stale-while-revalidate=300`, ETag from object/content hash.
- Forecast key: API path plus latitude/longitude rounded to 3 decimals, 10-minute TTL, one-hour stale allowance at edge.
- Browser service worker keeps 24 frames for two hours and 180 basemap responses for one day. It never intercepts DMI directly.
- API in-memory cache is per replica; CDN is the shared cache. Do not add Redis until cache-hit metrics demonstrate a need.
