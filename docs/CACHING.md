# Caching and cache keys

- Frame key: `frames/<DMI item id>.webp`; immutable for one year. If DMI republishes an ID with changed bytes, worker must fail/alert rather than mutate a cached object.
- Manifest key: `frames/frames.json`; `max-age=60, stale-while-revalidate=300`, ETag from object/content hash.
- Nowcast keys: `nowcast/<observation id>-plus-<lead>.webp`; five-minute browser/CDN cache. `nowcast/nowcast.json`, the compact alert grid `nowcast/risk.json`, and high-resolution `nowcast/point-risk.json` use short-lived metadata plus byte-range point lookup. The binary point cube alternates between two slots so its metadata switch is atomic without accumulating immutable 5 MB objects. `nowcast/verification.json` retains the latest 288 prediction/observation comparisons and is cached for five minutes. The UI rejects a nowcast that does not match the latest observation.
- Forecast key: API path plus latitude/longitude rounded to 2 decimals, 10-minute TTL, six-hour stale-while-revalidate allowance and last-known-good R2 storage.
- Next-hour model fallback key: API path plus coordinates rounded to 2 decimals, 5-minute TTL, 30-minute stale-while-revalidate allowance and only still-future persisted points. The public response is recomposed every minute at the exact requested coordinate from three small R2 byte ranges around that point; only intervals without current radar coverage retain the cached HARMONIE value.
- Browser service worker keeps 24 observed/nowcast frames for two hours and 180 basemap responses for one day. It also receives Web Push events, but never contacts DMI directly.
- API in-memory cache is per replica; CDN is the shared cache. Do not add Redis until cache-hit metrics demonstrate a need.
