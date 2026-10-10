# ADR 0001: Reprojected image frames before tiles

Status: accepted, 2026-10-10.

We publish one transparent, lossless WebP in EPSG:3857 per observation and describe its WGS84 bounds in a short manifest. MapLibre uses an `image` source. This makes processing deterministic and moves all repeated reads to a CDN. It also keeps the worker, cache key, and retention model small.

The trade-off is that a Denmark-wide image is transferred even when the viewport is Aarhus and perspective rendering is less exact than raster tiles at high pitch. The UI therefore offers a 2D mode. Move to pre-generated z/x/y WebP or PMTiles only when real-user monitoring shows frame transfer/LCP or alignment misses its budget; never render tiles per request.
