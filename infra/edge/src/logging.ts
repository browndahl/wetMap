// Explicit app diagnostics only. Never pass through request/error objects or keys.
const events = [
  "location.search.failed",
  "location.reverse.failed",
  "forecast.upstream.failed",
  "forecast.provider.selected",
  "forecast.provider.refreshed",
  "forecast.cache.persist-failed",
  "forecast.cache.invalid",
  "forecast.background-dmi.failed",
  "precipitation.upstream.failed",
  "precipitation.provider.selected",
  "precipitation.provider.refreshed",
  "precipitation.cache.persist-failed",
  "precipitation.cache.invalid",
  "precipitation.background-dmi.failed",
  "precipitation.radar.failed",
  "precipitation.combine.failed",
  "radar.point-grid.read-failed",
  "radar.scheduler.invalid-manifest",
  "radar.scheduler.missing-token",
  "radar.scheduler.dispatched",
  "radar.scheduler.dispatch-failed",
  "push.send.succeeded",
  "push.send.failed",
] as const;
type LogEvent = (typeof events)[number];
const allowedEvents = new Set<string>(events);
const enumFields: Record<string, ReadonlySet<string>> = {
  provider: new Set(["dmi-edr", "open-meteo-dmi"]),
  source: new Set([
    "dmi-edr",
    "open-meteo-dmi",
    "radar-nowcast",
    "github-actions",
    "web-push",
  ]),
  fallback: new Set(["none", "open-meteo", "stale"]),
  kind: new Set(["observed", "forecast"]),
};
const timingFields = [
  "cacheMs",
  "pointCacheMs",
  "r2Ms",
  "dmiMs",
  "openMeteoMs",
  "totalMs",
  "durationMs",
  "leadMinutes",
  "etaMinutes",
  "radarAgeMinutes",
] as const;

function ownValue(fields: unknown, name: string): unknown {
  if (!fields || typeof fields !== "object" || Array.isArray(fields))
    return undefined;
  try {
    // Do not invoke getters, toJSON or traverse nested exception/request objects.
    return Object.getOwnPropertyDescriptor(fields, name)?.value;
  } catch {
    return undefined;
  }
}

export function logEvent(
  level: "info" | "warn" | "error",
  event: LogEvent,
  fields?: unknown,
): void {
  if (!allowedEvents.has(event)) {
    console.error("logging.invalid-event");
    return;
  }
  const safe: Record<string, string | number> = {};
  for (const [name, values] of Object.entries(enumFields)) {
    const value = ownValue(fields, name);
    if (typeof value === "string" && values.has(value)) safe[name] = value;
  }
  for (const name of timingFields) {
    const value = ownValue(fields, name);
    if (typeof value === "number" && Number.isFinite(value)) safe[name] = value;
  }
  const outcome = ownValue(fields, "dmiOutcome");
  if (
    typeof outcome === "string" &&
    (["success", "timeout", "error", "pending"].includes(outcome) ||
      /^http-[1-5]\d{2}$/.test(outcome))
  )
    safe.dmiOutcome = outcome;
  const status = ownValue(fields, "statusCode");
  if (
    typeof status === "number" &&
    Number.isInteger(status) &&
    status >= 100 &&
    status <= 599
  )
    safe.statusCode = status;
  const output =
    level === "error"
      ? console.error
      : level === "warn"
        ? console.warn
        : console.log;
  if (Object.keys(safe).length) output.call(console, event, safe);
  else output.call(console, event);
}
