import { DMI_ATTRIBUTION, type RainNextHourResponse } from "@wetmap/shared";
import { expect, it } from "vitest";
import { findDryWindow } from "./dryWindow";

const minute = 60_000;
const now = Date.parse("2026-11-18T15:50:00Z");
const iso = (offset: number) => new Date(now + offset * minute).toISOString();

function forecast(): RainNextHourResponse {
  return {
    latitude: 56.16,
    longitude: 10.2,
    fetchedAt: iso(0),
    attribution: DMI_ATTRIBUTION,
    source: "dmi-radar-nowcast-harmonie",
    model: "DMI HARMONIE AROME",
    displayResolutionMinutes: 15,
    sourceResolutionMinutes: 60,
    isInterpolated: true,
    basedOnObservedAt: iso(-15),
    radarBasedUntil: iso(45),
    points: [-5, 10, 25, 40].map((offset) => ({
      startsAt: iso(offset),
      endsAt: iso(offset + 15),
      source: "radar-nowcast",
      intensity: "none",
      precipitationMm: 0,
      confidence: 0.7,
    })),
  };
}

it("chooses the earliest long-enough dry run and excludes the elapsed portion", () => {
  const data = forecast();
  data.points[1].intensity = "light";
  const result = findDryWindow(data, now, 15);
  expect(result).toEqual({
    status: "found",
    startsAt: now + 25 * minute,
    endsAt: now + 45 * minute,
  });
  expect(findDryWindow(data, now, 30)).toEqual({ status: "no-window" });
  expect(findDryWindow(forecast(), now, 45)).toEqual({
    status: "found",
    startsAt: now,
    endsAt: now + 45 * minute,
  });
});

it.each([
  { intensity: "trace" as const },
  { source: "harmonie" as const },
  { confidence: 0.54 },
  { confidence: null },
  { precipitationMm: 0.01 },
])("does not join dry intervals across an unverified slot %j", (change) => {
  const data = forecast();
  Object.assign(data.points[1], change);
  expect(findDryWindow(data, now, 30)).toEqual({ status: "no-window" });
});

it("clips to the radar coverage horizon and does not bridge missing intervals", () => {
  const data = forecast();
  data.points.splice(1, 1);
  data.radarBasedUntil = iso(39);
  expect(findDryWindow(data, now, 15)).toEqual({ status: "no-window" });
  data.radarBasedUntil = iso(40);
  expect(findDryWindow(data, now, 15)).toEqual({
    status: "found",
    startsAt: now + 25 * minute,
    endsAt: now + 40 * minute,
  });
});

it("withdraws a window as the clock advances without a new response", () => {
  const data = { ...forecast(), basedOnObservedAt: iso(0) };
  expect(findDryWindow(data, now, 30).status).toBe("found");
  expect(findDryWindow(data, now + 16 * minute, 30).status).toBe("no-window");
  expect(findDryWindow(data, now + 26 * minute, 30).status).toBe("stale");
});

it("rejects stale data, future clocks and model-only estimates", () => {
  const data = forecast();
  expect(
    findDryWindow(
      { ...data, basedOnObservedAt: iso(-26), radarBasedUntil: iso(34) },
      now,
      15,
    ),
  ).toEqual({ status: "stale" });
  expect(
    findDryWindow({ ...data, basedOnObservedAt: iso(1) }, now, 15),
  ).toEqual({ status: "unavailable" });
  expect(findDryWindow({ ...data, source: "dmi-edr" }, now, 15)).toEqual({
    status: "unavailable",
  });
  expect(findDryWindow(undefined, now, 15)).toEqual({ status: "unavailable" });
});

it("rejects expired coverage, overlapping intervals and invalid boundaries", () => {
  const data = forecast();
  expect(findDryWindow({ ...data, radarBasedUntil: iso(0) }, now, 15)).toEqual({
    status: "unavailable",
  });
  data.points.push({ ...data.points[1] });
  expect(findDryWindow(data, now, 15)).toEqual({ status: "unavailable" });
  data.points.pop();
  data.points[3].endsAt = "invalid";
  expect(findDryWindow(data, now, 15)).toEqual({ status: "unavailable" });
});
