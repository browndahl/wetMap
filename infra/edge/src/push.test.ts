import { expect, it } from "vitest";
import { riskAtLocation } from "./push";

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
  );

  expect(hit).toEqual({
    leadMinutes: 10,
    predictedAt: "2026-10-11T12:05:00Z",
    intensity: 3,
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

  expect(riskAtLocation(risk, 56, 11)).toBeNull();
});
