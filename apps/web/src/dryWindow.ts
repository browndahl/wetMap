import type { RainNextHourResponse } from "@wetmap/shared";

export const dryWindowDurations = [15, 30, 45] as const;
export type DryWindowDuration = (typeof dryWindowDurations)[number];

type TimeWindow = { startsAt: number; endsAt: number };
type Result =
  | ({ status: "found" } & TimeWindow)
  | { status: "unavailable" | "stale" | "no-window" };

const minute = 60_000;
// Use the app's radar freshness budget and the existing medium-confidence
// boundary. These are UI eligibility checks, not new forecast or alert gates.
const maximumRadarAge = 25 * minute;
const minimumConfidence = 0.55;

export function findDryWindow(
  forecast: RainNextHourResponse | undefined,
  now: number,
  duration: DryWindowDuration,
): Result {
  if (
    forecast?.source !== "dmi-radar-nowcast-harmonie" ||
    !Number.isFinite(now) ||
    !forecast.basedOnObservedAt ||
    !forecast.radarBasedUntil
  )
    return { status: "unavailable" };

  const origin = Date.parse(forecast.basedOnObservedAt);
  const radarUntil = Date.parse(forecast.radarBasedUntil);
  if (
    !Number.isFinite(origin) ||
    origin > now ||
    !Number.isFinite(radarUntil) ||
    radarUntil > origin + 60 * minute
  )
    return { status: "unavailable" };
  if (now - origin > maximumRadarAge) return { status: "stale" };
  if (radarUntil <= now) return { status: "unavailable" };

  const slots = forecast.points.map((point) => ({
    point,
    start: Date.parse(point.startsAt),
    end: Date.parse(point.endsAt),
  }));
  slots.sort((a, b) => a.start - b.start);
  if (
    slots.some(
      (slot, index) =>
        slot.end - slot.start !== 15 * minute ||
        (index > 0 && slot.start < slots[index - 1].end),
    )
  )
    return { status: "unavailable" };

  const windows: TimeWindow[] = [];
  const horizon = Math.min(radarUntil, now + 60 * minute);
  for (const { point, start, end } of slots) {
    if (
      point.source !== "radar-nowcast" ||
      point.intensity !== "none" ||
      point.precipitationMm !== 0 ||
      typeof point.confidence !== "number" ||
      !Number.isFinite(point.confidence) ||
      point.confidence < minimumConfidence ||
      point.confidence > 1
    )
      continue;

    const startsAt = Math.max(start, now);
    const endsAt = Math.min(end, horizon);
    if (startsAt >= endsAt) continue;
    const last = windows.at(-1);
    if (last?.endsAt === startsAt) last.endsAt = endsAt;
    else windows.push({ startsAt, endsAt });
  }

  const match = windows.find(
    ({ startsAt, endsAt }) => endsAt - startsAt >= duration * minute,
  );
  return match ? { status: "found", ...match } : { status: "no-window" };
}
