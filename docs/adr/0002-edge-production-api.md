# ADR 0002: Cloudflare Worker is the production read API

Status: accepted, 2026-10-10.

The .NET 10 API is the canonical portable modular monolith and local Compose runtime. Production uses the functionally equivalent `infra/edge` Worker for v1's narrow anonymous surface: R2 manifest/frame reads and cached DMI point forecast queries.

This deviation is deliberate. Render Free sleeps after 15 idle minutes and takes about one minute to wake; Render says Free is not for production. Azure F1 is limited to 60 CPU minutes/day and lacks custom-domain SSL. Oracle Always Free has account/capacity/payment-verification friction. Workers Free has no container cold start, keeps forecast calls server-side, and offers 100,000 requests/day. Its 10 ms CPU budget means radar processing must remain in GitHub Actions, not at the edge.

At sustained >100k dynamic requests/day, first increase CDN cache efficiency, then deploy the same .NET container on paid or owned compute. Static frame requests should not traverse forecast code.
