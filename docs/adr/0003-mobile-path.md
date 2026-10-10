# ADR 0003: PWA first, shared domain contracts

Status: accepted, 2026-10-10.

V1 ships as an installable PWA. Contracts, API client, reflectivity scale, and OKLCH tokens live in `packages/shared` without DOM dependencies. Browser geolocation remains an adapter. A low-effort store release can use Capacitor around the PWA. If native maps/background behavior become requirements, build Expo/React Native UI with MapLibre React Native while reusing the shared package and API; the web MapLibre component is intentionally not shared.
