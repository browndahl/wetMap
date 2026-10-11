# Security and privacy checklist

- [x] DMI is only contacted by worker/API; never by browser code.
- [x] Strict input ranges and rounded forecast cache keys.
- [x] RFC 9457-compatible Problem Details, correlation IDs, structured JSON logs.
- [x] Per-IP token-bucket limiter in .NET; Cloudflare account/WAF rules are an additional deploy-time control.
- [x] Explicit CORS allow-list; no wildcard with credentials.
- [x] CSP, `nosniff`, referrer and permissions policies; no camera/microphone access.
- [x] Immutable objects are content-addressed by observation ID and include SHA-256 in manifest.
- [x] Secrets come from GitHub environments/provider secret stores; `.env` is ignored.
- [x] Containers run read-only with `no-new-privileges`; API/worker run non-root.
- [x] CodeQL, Dependabot, gitleaks, Trivy and CycloneDX SBOM workflows are configured.
- [x] GPS is processed on-device for map location. It is sent when a point forecast is selected/requested; no WetMap account or identity exists.
- [x] Background rain alerts require an explicit click and browser permission. The R2 record contains only the capability-style push endpoint/public encryption keys, locale, label, and coordinates rounded to 0.01°. Mutation endpoints enforce the production/preview Origin allow-list; disabling deletes the record and 404/410 push endpoints are removed automatically.
- [x] VAPID private material remains a Worker secret. It is never included in the Pages bundle, API response, repository, or logs.
- [ ] Configure Cloudflare managed rules/rate rule and validate headers on the deployed domain.
- [ ] Triage scanner findings and pin image digests before production approval.

GDPR: v1 stores no user profile or location history. Opted-in background alerts require one current location rounded to 0.01° and a pseudonymous push capability endpoint until the user disables it or the endpoint expires. Treat both as personal data, document the purpose/retention and browser push provider as a subprocessor, restrict R2 access, and publish a privacy notice before launch. Infrastructure access logs may contain IP addresses; set the shortest provider retention available.
