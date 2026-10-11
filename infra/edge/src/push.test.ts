import { expect, it } from "vitest";
import { riskAtLocation } from "./push";

it("maps a location into the Web Mercator nowcast risk grid", () => {
  const dry = new Uint8Array(4);
  const wet = new Uint8Array([0, 0, 2, 0]);
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
        },
        {
          leadMinutes: 10,
          predictedAt: "2026-10-11T12:05:00Z",
          intensity: encode(wet),
        },
      ],
    },
    55.5,
    10.5,
  );

  expect(hit).toEqual({
    leadMinutes: 10,
    predictedAt: "2026-10-11T12:05:00Z",
    intensity: 2,
  });
});
