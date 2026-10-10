# Scaling path

At v1, CDN serves immutable frames; Worker only handles cache misses and point forecasts. At 10× traffic, increase cache TTL after validating freshness, add regional synthetic probes, sample telemetry, and generate PMTiles/z-x-y frames if transfer is the bottleneck. Costs remain near zero only while Workers/R2 allowances hold.

At 100× traffic, move dynamic API to paid autoscaling compute, use a paid Cloudflare Workers plan/WAF, generate multi-resolution raster tiles, and add a shared distributed cache only if measured hit rates justify it. Keep services stateless. Actual cost must be quoted from provider calculators at that future date; this document does not invent a number.
