# iPhone readiness — 24 October 2026

Scope: installation, notification onboarding and freshness after resume. This is
not a declaration that the complete mobile/performance acceptance suite has passed.
[ADR 0008](adr/0008-iphone-installation-and-resume.md) records the decision.

## Implemented

- Apple home-screen icon and compatible PNG manifest/notification icons, using
  the existing artwork; explicit manifest identity and scope.
- Collapsible installation instructions under More and in expanded rain details.
  No startup modal/banner. A normal iPhone browser does not incorrectly request
  notification permission; the installed-mode subscription flow remains available.
- Immediate age-clock refresh on becoming visible, focus revalidation for radar
  and nowcast, and active weather refetch on restored pages/connectivity.
- Correct stacking of sticky bottom navigation above expanded phone content.

## Verified here

- `pnpm check`: lint, type checks, 62 TypeScript tests and builds passed (26 web,
  34 edge, 2 shared). The existing MapLibre >500 KB build warning remains. The
  edge dry-run was also rerun with a writable temporary Wrangler log path to avoid
  the cached sandbox log-permission diagnostic; it passed.
- Regression tests cover normal versus installed Apple mobile detection, iPad
  desktop mode, non-Apple devices, installation action without permission/API
  requests, age refresh and bfcache revalidation. Timely/expired push tests also
  verify PNG notification icon use.
- Built manifest, icon dimensions/opacity and service-worker precache inspected.
- Chrome with an iPhone user agent: 320×568, 390×844, 844×390, plus simulated
  standalone mode at 390×844. Guide opening/closing/reopening, reachable scrolling,
  viewport bounds, no horizontal overflow, navigation hit-testing and uncaught
  JavaScript errors checked. This is **not Safari or a physical iPhone**.
- [Browser results](evidence/iphone/results.json),
  [installation guide](evidence/iphone/installation.png),
  [small-screen alerts](evidence/iphone/small-alerts.png).

## Physical iPhone checks — still required

1. Record iPhone model and iOS version. Open
   [WetMap](https://wetmap.pages.dev/) in Safari. Verify search, map gestures,
   keyboard, notch/home-indicator spacing and portrait/landscape behavior.
2. Share → Add to Home Screen (enable Open as Web App if shown) → Add. Open the
   new WetMap icon; verify its icon/name and standalone presentation. Instructions
   follow [Apple's guide](https://support.apple.com/guide/iphone/bookmark-a-website-iph42ab2f3a7/ios).
3. Select a location. Regn → expand details → Varsl mig → allow notification
   permission. Web push requires iOS 16.4+ and home-screen installation, per
   [WebKit](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/).
4. Lock the phone/close the app. During an eligible rain event, record server
   decision/send time and OS arrival time. Check permission, Focus and notification
   settings if absent. A subscription alone is not proof of timely delivery, and
   quality/expiry rules intentionally suppress unsuitable alerts.
5. Resume after 5–15 minutes, after locking, and after airplane-mode recovery.
   Check that time/data age update immediately and fresh data are requested. If
   the source is old/offline, it must remain labelled delayed/unavailable.
6. Verify denying permission gives an honest recovery path, turning alerts off
   works, and expiry protection does not display obsolete notifications.

Real-device push latency, Safari rendering/performance and OS lifecycle behavior
remain unverified until these steps are performed. No claim of improved forecast
accuracy or 100% real-time delivery is made by this sprint. Everything remains
within the existing free-only setup.
