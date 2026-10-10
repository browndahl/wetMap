# Free-tier budget

Verified against official documentation on **2026-10-10**. “Free” never means unlimited or an SLA. Set provider spend limits to zero where supported and do not attach automatic paid upgrades.

| Component | Current included limit | Card? | Expected v1 use | Exceeded / risk |
|---|---:|---|---:|---|
| Cloudflare Pages Free | 500 builds/month, 1 concurrent build, 20,000 files/site, 25 MiB/file, 100 projects/account | Account required; Pages itself free | ~30 production deploys/month | Builds stop at limit; preview-per-commit can exhaust 500. [Official limits](https://developers.cloudflare.com/pages/platform/limits/) |
| Cloudflare R2 Standard | 10 GB-month, 1M Class A, 10M Class B/month, free egress | **R2 subscription checkout is required**, so billing setup may be requested | ~0.2–1 GB with 48 h lifecycle, ~17.3k writes/month at five-minute cadence | Usage above allowance is billed if enabled. This is the main strict “no card” risk. [Official pricing](https://developers.cloudflare.com/r2/pricing/), [activation](https://developers.cloudflare.com/r2/get-started/) |
| Cloudflare Workers Free | 100,000 requests/day, 10 ms CPU/request, 128 MB, 50 external subrequests/request | No paid plan required | Forecast and manifest only; frames CDN-cacheable | Error 1027 after daily cap; heavy JSON may hit CPU. [Official limits](https://developers.cloudflare.com/workers/platform/limits/) |
| GitHub Actions | Public repositories: standard hosted runners free; private GitHub Free: 2,000 min/month and 500 MB artifacts | No card if budget blocks overage | 288 worker runs/day; public repo required | Public runner fair-use still applies. Private worker schedule would exceed 2,000 min if each run lasts >14 s. [Official billing](https://docs.github.com/en/actions/concepts/billing-and-usage), [included usage](https://docs.github.com/en/billing/reference/product-usage-included) |
| DMI Open Data | 500 requests/5 seconds; no API key since 2025-12-02 | No | Worker: ~1 metadata + normally 1 new asset/run; edge forecasts cached 10 min/rounded point | 429 with `Retry-After`; DMI may change limit and offers no availability guarantee. [Official basics](https://www.dmi.dk/friedata/dokumentation/basics), [authentication](https://www.dmi.dk/friedata/dokumentation/authentication) |
| OpenFreeMap public instance | Free, no API key; public service does not promise an application SLA | No | Vector basemap only | Outage removes basemap, not cached radar/control shell. Plan self-hosting or sponsored provider at scale. [Official site](https://openfreemap.org/) |
| Grafana Cloud Free | $0, no card, 50 GB logs/month and 14-day retention; all services with free usage limits | No | Sampled OTLP telemetry | Ingestion is limited/dropped at cap; keep local debug exporter. [Official pricing](https://grafana.com/pricing/) |
| Sentry Developer | Free Developer plan; exact event quota was not reliably exposed in current official docs during verification | Usually no card | Optional DSN, conservative sampling | Treat quota as **unverified and risky**; UI works with Sentry disabled. Verify dashboard quota before enabling. [Official pricing](https://sentry.io/pricing/) |
| Render Free (fallback only) | 750 instance-hours/workspace/month; sleeps after 15 min, ~1 min wake-up; ephemeral disk | No card; suspension rather than billing without one | Not selected | Render explicitly says not for production. [Official docs](https://render.com/docs/free) |
| Azure App Service F1 (rejected) | 60 CPU minutes/day, one shared instance; custom-domain SSL unsupported | Azure signup commonly requires payment verification | Not selected | Too little compute and unsuitable custom-domain TLS for this API. [Official limits](https://learn.microsoft.com/azure/azure-resource-manager/management/azure-subscription-service-limits) |

## Budget guardrails

- Worker keeps 13 frames (60 minutes at 5-minute cadence), seeds stateless runs from the R2 manifest, and uploads only new immutable frames before replacing the manifest. R2 expires `frames/` objects after 48 hours.
- Frame names are immutable and CDN-cacheable for one year; `frames.json` is cached for 60 seconds with 5-minute stale-while-revalidate.
- Forecast coordinates are rounded to ~100 m for cache keys and responses are cached for 10 minutes.
- GitHub artifacts retain only summaries; radar binaries are never uploaded as Actions artifacts.
- Cloudflare budget alerts should be set at 50/80/100%; zero-cost cannot be guaranteed if the owner enables paid overage.
