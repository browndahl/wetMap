import { expect, it } from "vitest";
import {
  notificationPayload,
  riskAtLocation,
  type StoredSubscription,
} from "./push";

it("maps a location into the Web Mercator nowcast risk grid", () => {
  const dry = new Uint8Array(4);
  const wet = new Uint8Array([0, 0, 3, 0]);
  const encode = (value: Uint8Array) => btoa(String.fromCharCode(...value));
  const hit = riskAtLocation(
    {
      schemaVersion: 1,
      generatedAt: "2026-10-11T12:00:00Z",
      basedOnObservedAt: "2026-10-11T11:55:00Z",
      bounds: [10, 55, 12, 57],
      width: 2,
      height: 2,
      encoding: "uint8-base64",
      frames: [
        {
          leadMinutes: 5,
          predictedAt: "2026-10-11T12:00:00Z",
          intensity: encode(dry),
          alertEligible: true,
        },
        {
          leadMinutes: 10,
          predictedAt: "2026-10-11T12:05:00Z",
          intensity: encode(wet),
          alertEligible: true,
        },
      ],
    },
    55.5,
    10.5,
    Date.parse("2026-10-11T12:00:00Z"),
  );

  expect(hit).toEqual({
    leadMinutes: 10,
    predictedAt: "2026-10-11T12:05:00Z",
    intensity: 3,
    kind: "forecast",
  });
});

it("suppresses weak echoes and forecasts that fail the quality gate", () => {
  const encode = (value: Uint8Array) => btoa(String.fromCharCode(...value));
  const risk = {
    schemaVersion: 1 as const,
    generatedAt: "2026-10-11T12:00:00Z",
    basedOnObservedAt: "2026-10-11T11:55:00Z",
    bounds: [10, 55, 12, 57] as [number, number, number, number],
    width: 1,
    height: 1,
    encoding: "uint8-base64" as const,
    frames: [
      {
        leadMinutes: 5,
        predictedAt: "2026-10-11T12:00:00Z",
        intensity: encode(new Uint8Array([3])),
        alertEligible: false,
      },
      {
        leadMinutes: 10,
        predictedAt: "2026-10-11T12:05:00Z",
        intensity: encode(new Uint8Array([1])),
        alertEligible: true,
      },
    ],
  };

  expect(
    riskAtLocation(risk, 56, 11, Date.parse("2026-10-11T12:00:00Z")),
  ).toBeNull();
});

it("skips stale observations and forecast times that have already passed", () => {
  const encode = (value: Uint8Array) => btoa(String.fromCharCode(...value));
  const wet = encode(new Uint8Array([3]));
  const hit = riskAtLocation(
    {
      schemaVersion: 1,
      generatedAt: "2026-10-11T12:10:00Z",
      basedOnObservedAt: "2026-10-11T11:55:00Z",
      bounds: [10, 55, 12, 57],
      width: 1,
      height: 1,
      encoding: "uint8-base64",
      frames: [
        {
          leadMinutes: 0,
          predictedAt: "2026-10-11T11:55:00Z",
          intensity: wet,
          alertEligible: true,
        },
        {
          leadMinutes: 10,
          predictedAt: "2026-10-11T12:05:00Z",
          intensity: wet,
          alertEligible: true,
        },
        {
          leadMinutes: 20,
          predictedAt: "2026-10-11T12:15:00Z",
          intensity: wet,
          alertEligible: true,
        },
      ],
    },
    56,
    11,
    Date.parse("2026-10-11T12:12:00Z"),
  );

  expect(hit).toEqual({
    leadMinutes: 20,
    predictedAt: "2026-10-11T12:15:00Z",
    intensity: 3,
    kind: "forecast",
  });
});

it("marks observed rain distinctly and gives every push an expiry", () => {
  const subscription: StoredSubscription = {
    schemaVersion: 1,
    subscription: {
      endpoint: "https://push.example.test/subscription/123",
      keys: { auth: "a".repeat(22), p256dh: "b".repeat(88) },
    },
    latitude: 56.16,
    longitude: 10.2,
    locationName: "Aarhus",
    locale: "en",
    createdAt: "2026-10-11T11:00:00Z",
    updatedAt: "2026-10-11T11:00:00Z",
    activeRainEvent: false,
  };
  const sentAt = Date.parse("2026-10-11T12:10:00Z");
  const payload = JSON.parse(
    notificationPayload(
      subscription,
      {
        leadMinutes: 0,
        predictedAt: "2026-10-11T12:00:00Z",
        intensity: 3,
        kind: "observed",
      },
      sentAt,
    ),
  ) as Record<string, string>;

  expect(payload).toMatchObject({
    title: "Rain detected",
    kind: "observed",
    sentAt: "2026-10-11T12:10:00.000Z",
    predictedAt: "2026-10-11T12:00:00Z",
    expiresAt: "2026-10-11T12:15:00.000Z",
  });
  expect(payload.body).not.toContain("12:00");

  const forecastPayload = JSON.parse(
    notificationPayload(
      subscription,
      {
        leadMinutes: 5,
        predictedAt: "2026-10-11T12:15:00Z",
        intensity: 3,
        kind: "forecast",
      },
      sentAt,
    ),
  ) as Record<string, string>;
  expect(forecastPayload).toMatchObject({
    title: "Rain on the way",
    kind: "forecast",
    expiresAt: "2026-10-11T12:17:00.000Z",
  });
});
