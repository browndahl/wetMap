# Free-tier audit — 17 November 2026

Verdict: **UNRESOLVED / not full zero-cost compliance**. Current included allowances
were checked against official sources below; measured usage is aggregate analytics,
not a bill or an account-level spending cap. No plan, card or billing setting changed.

## Provider inventory and verified limits

| Provider / role                                  | Verified allowance and enforcement                                                                                                                                                                                                             | Measured state / unresolved risk                                                                                                                                                                                                                                                                                |
| ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Cloudflare Worker / API, cron, push              | Free 100,000 requests/day, reset UTC; 10 ms CPU/request and cron; 50 external subrequests, 128 MB memory. No general requests/second cap stated. [Official limits](https://developers.cloudflare.com/workers/platform/limits/), checked 17/11. | Seven-day peak 3,192 requests/day. Daily cron p99 41.854–52.469 ms, fetch p99 20.138–28.023 ms: above the documented CPU allowance. Zero exceededCpu outcomes in this sample is not proof of compliance; provider allows some burst flexibility. Verify actual plan/model and profile before changing capacity. |
| Cloudflare R2 Standard / existing object storage | 10 GB-month, 1M Class A and 10M Class B/month; above included amounts are metered, not a hard storage stop. [Official pricing](https://developers.cloudflare.com/r2/pricing/), checked 17/11.                                                  | Peak daily A 7,870, B 15,194. 30-day projections 236,100 / 455,820 are estimates, not current invoices. Storage daily peak 10.443 GB on 12/11, 1.497 GB on 16/11 after approved cleanup. Historical peak is not a GB-month bill. No zero-spend guarantee.                                                       |
| GitHub Actions / processing, tests, deploy       | Standard public runners are free; larger runners billed; artifact/cache storage has separate allowances. [Official billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions), checked 17/11.                        | Repository verified public; normal Ubuntu standard runners. Cron can be delayed/dropped. No new paid runner or raw-data artifact. Complete account artifact/cache billing totals not measured here.                                                                                                             |
| Cloudflare Pages / static UI                     | Free plan documented 500 builds/month, account concurrency limits. [Official limits](https://developers.cloudflare.com/pages/platform/limits/), checked 17/11.                                                                                 | Uses GitHub build and Wrangler direct upload. Exact account-wide Pages deployment/build consumption not established; do not equate direct uploads to integrated builds without evidence.                                                                                                                        |
| DMI / radar, HARMONIE, gauges                    | Existing official open-data endpoints; no new key/payment subscription.                                                                                                                                                                        | Bounded normal catalogue read matched WetMap. Current hard request quota/contract and historical publication time are not established. Tests mock upstream calls.                                                                                                                                               |
| Open-Meteo / DMI fallback                        | Free non-commercial, 600 calls/min, 5,000/hour, 10,000/day, 300,000/month; no uptime guarantee. [Official pricing](https://open-meteo.com/en/pricing), checked 17/11.                                                                          | No payment method/service upgrade introduced. Real fallback volume not counted by the repeated cache microbenchmarks. Commercial deployment permission remains a separate question.                                                                                                                             |
| OpenFreeMap/OSM / map                            | Public instance currently states no API key/registration or request/view limits, no SLA. [Official site](https://openfreemap.org/), checked 17/11.                                                                                             | Attribution retained. Not an availability guarantee; no large offline downloads or new self-hosted cost.                                                                                                                                                                                                        |
| Photon / location search                         | Existing public community geocoder, cached; no new paid service.                                                                                                                                                                               | Hard quota/SLA not verified this audit. Search degrades independently; usage-volume compliance unresolved.                                                                                                                                                                                                      |
| Browser push providers / notifications           | Existing Web Push, no newly adopted per-message vendor.                                                                                                                                                                                        | Real device delivery, CPU cost, R2 subscription scan growth and provider throttling remain unresolved.                                                                                                                                                                                                          |

Redis/KV are not deployed. Grafana/Sentry are not adopted by this work; a config
reference is not evidence of an active paid/free dashboard. No new service was added.

## Seven complete UTC days measured

10 November 00:00 through 17 November 00:00 UTC, account-wide GraphQL analytics.
Only day/action/event/status aggregates were requested; no object names, IPs,
push subscriptions or credentials are published. Existing provider login stayed
in process memory and Authorization to Cloudflare; no token was printed/stored.

| UTC day | R2 Class A | R2 Class B | Worker requests | Worker errors | Cron CPU p99 (ms) | Radar-bucket daily peak GB |
| ------- | ---------: | ---------: | --------------: | ------------: | ----------------: | -------------------------: |
| 10/11   |      7,690 |     13,801 |           2,111 |             0 |            52.469 |                      9.813 |
| 11/11   |      7,601 |     13,737 |           2,049 |             1 |            48.926 |                     10.034 |
| 12/11   |      7,870 |     15,194 |           3,192 |             0 |            48.626 |                     10.443 |
| 13/11   |      6,706 |     14,388 |           2,892 |             0 |            44.183 |                      1.196 |
| 14/11   |      6,780 |     13,279 |           2,221 |             0 |            41.854 |                      1.101 |
| 15/11   |      6,694 |     13,489 |           2,238 |             0 |            45.486 |                      0.738 |
| 16/11   |      6,614 |     13,359 |           2,237 |             1 |            48.622 |                      1.497 |

Preview bucket was empty in the sampled storage groups. Two errors were
scriptThrewException, not exceededCpu. CPU quantiles are provider aggregate
microseconds converted to ms; they are not a local browser timing measurement.
Summed daily max storage is not a storage invoice and max-per-group p99 is not
a combined p99 of all invocation types.

The master prompt's approximate 1,000/min Worker burst number conflicts with the
current source's “no general limit on requests per second”; the source wins for
quota planning, not an assumption that daily/CPU/subrequest limits disappear.
O2's 70% seven-day margin criterion is not passed for storage/CPU. No paid upgrade
is authorised as a remedy.

## Bounded impact of current fixes

- Catalogue rejection: zero new cloud requests/storage/services.
- Safe validator diagnostics: same public probe, same timeout, bounded log record;
  no raw stderr or new artifact storage.
- Version-bound writer: one small R2 GET per ingestion, at most ~8,640/month on
  a five-minute cadence; two slots remain fixed, writes replace existing writes.
  Reader adds conditions/comparisons to existing range GETs, no extra requests.
- Release gate: bounded GitHub control-plane polling on the existing standard
  public runner; no Cloudflare runtime traffic or new service.
- Approved raw audit: one local snapshot, **22 object reads / 10,761,702 bytes**,
  stable state. Directory private; no raw payload/cubes/subscriptions published.
  Only aggregate result is in evidence/master-2026-11-17/raw-audit-summary.json.

No remote load/chaos test: staging currently points at production API and shares
the account. No attempt to consume production's daily quota. Read-only UI checks
have a separate small normal-navigation request budget, not a load acceptance test.

## Still required

Profile CPU and confirm active account plan/settings without silently upgrading.
Add a budgeted scheduled aggregate usage check after its permissions/telemetry
budget are reviewed. Establish month-to-date accounting, actual upstream volumes,
artifact/storage allowance and a 12-month projection. Some model-cache prefixes
can grow with distinct coordinates; do not install blanket lifecycle deletion on
histories or change privacy/retention to satisfy a checkbox. Those boundaries need
explicit approval. Existing narrowly approved WebP cleanup remains unchanged.

## Plan access and bounded CPU follow-up

18 November release-policy follow-up reuses the existing bounded GitHub gate:
at most 36 check polls plus three current-ref GETs per candidate, 10 s HTTP and
360 s poll deadline, 10-minute standard-public-runner job cap. No R2/Worker
runtime requests or new service. Unknown/failed gates still fail; superseded
candidate is explicitly not published. Account-wide Actions/storage accounting
is still unresolved. No whole-publisher automatic side-effect retry.

The existing authorised CLI login can read account analytics. Its read-only
account-subscriptions request returned **HTTP 403 / code 10000**, so the actual
Workers subscription cannot be established here. No broader token scope or plan
change was requested. Account confirmation is still required; don't conclude
that a paid plan exists merely because CPU was above the published Free budget.

PR #45 removes repeat weather-grid decoding (520→13 in a 40-point local scan),
with no request/storage growth and at most 128 KiB scratch bytes per manifest.
First six post-release cron invocations (22:38–22:44 UTC) show p50 12.293 ms,
p95/p99 17.977 ms; seven fetches show p50 3.437 ms, p95/p99 28.708 ms. Zero
reported errors, but still above 10 ms and too small/unmatched for a field
before/after claim. **Not post-release Cloudflare CPU compliance.** PR #44 bounds push
input reads to 8 KiB; #46 bounds an existing status read to 64 KiB. Neither adds
an endpoint request or changes subscription retention. Existing provider logs and
all remaining personal-data changes require their own approval.
