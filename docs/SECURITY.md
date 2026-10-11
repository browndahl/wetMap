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
- [x] GPS is processed on-device for map location. It is sent only when a point forecast is explicitly selected/requested; no identity or database exists in v1.
- [x] Rain notifications require an explicit click and browser permission. The preference and duplicate-suppression key remain in local storage; no push token or location is stored server-side.
- [ ] Configure Cloudflare managed rules/rate rule and validate headers on the deployed domain.
- [ ] Triage scanner findings and pin image digests before production approval.

GDPR: v1 stores no user profile, precise GPS history, or identifiers. Infrastructure access logs may contain IP addresses; set the shortest provider retention available, restrict access, document subprocessors, and publish a privacy notice before launch.
