# ADR 0008: iPhone installation guidance and resume freshness

Status: accepted, 2026-10-24, within the owner-approved iPhone/PWA work.

## Decision

Keep the free web/PWA distribution path. Do not introduce an App Store build or a
paid service. Supply opaque PNG icons (Apple 180 px, manifest 192/512 px), a stable
manifest identity/scope and Apple home-screen metadata. Reuse the existing icon
artwork; do not claim it meets maskable-icon safe-area requirements.

For an Apple mobile browser outside standalone mode, replace the notification
permission action with installation guidance. Show the same collapsible guide in
More, not on the default compact overview. Keep Danish and English instructions.
Detection controls explanatory UI only: the actual subscription path continues to
feature-detect Notification, PushManager and service workers, and requests
permission directly from a user click.

Apple requires a Home Screen web app on iOS/iPadOS 16.4+ for web push. Installation
does not grant permission or guarantee delivery: OS notification settings, Focus,
network conditions and WetMap's existing alert-quality/expiry rules still apply.
See [WebKit's requirements](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/)
and [Apple's installation guide](https://support.apple.com/guide/iphone/bookmark-a-website-iph42ab2f3a7/ios).

On visibility restoration, immediately update the displayed clock; radar and
nowcast join the existing weather queries in always revalidating on focus. On a
back/forward-cache restore or connectivity restoration, refetch active weather
queries without cancelling an existing fetch. Do not relabel old observations as
live, alter API caching, change forecast calculations or loosen quality gates.

Reset inherited desktop panel stacking in the phone dock so its sticky navigation
stays above expanded content, including on small screens.

## Verification and limitations

[iPhone checks](../IPHONE_CHECKS.md) separates automated/component and Chrome
emulation evidence from the physical Safari, installation and background-delivery
checks still required. Existing notification expiry tests remain active. No new
runtime dependency, background polling service or chargeable storage is added.

Rollback: revert the installation UI, icon/metadata, resume listeners and phone
stacking changes together; retain the existing push-subscription API and backend.
