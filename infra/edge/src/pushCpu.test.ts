import { afterEach, expect, it, vi } from "vitest";
import { riskAtLocation } from "./push";

const timestamp = Date.parse("2026-11-17T12:05:00Z");
function fixture() {
  return {
    schemaVersion: 1 as const,
    generatedAt: "2026-11-17T12:05:00Z",
    basedOnObservedAt: "2026-11-17T12:00:00Z",
    bounds: [10, 55, 12, 57] as [number, number, number, number],
    width: 64,
    height: 43,
    encoding: "uint8-base64" as const,
    frames: Array.from({ length: 13 }, (_, lead) => ({
      leadMinutes: lead * 5,
      predictedAt: new Date(
        Date.parse("2026-11-17T12:00:00Z") + lead * 5 * 60_000,
      ).toISOString(),
      intensity: btoa("\0".repeat(64 * 43)),
      alertEligible: true,
    })),
  };
}
afterEach(() => vi.restoreAllMocks());

it("does not retain a decoded frame above the scratch-byte budget", () => {
  const risk = fixture();
  risk.width = 256;
  risk.height = 1024;
  risk.frames = risk.frames.slice(0, 1);
  risk.frames[0].intensity = btoa("\0".repeat(256 * 1024));
  const decoder = vi.spyOn(globalThis, "atob");
  riskAtLocation(risk, 56, 11, timestamp);
  riskAtLocation(risk, 56, 11, timestamp);
  expect(decoder.mock.calls.length).toBe(2);
});

it("decodes a frame at most once across a 40-location scan", () => {
  const risk = fixture();
  const decoder = vi.spyOn(globalThis, "atob");
  for (let point = 0; point < 40; point++)
    expect(riskAtLocation(risk, 56, 10.5 + point / 100, timestamp)).toBeNull();
  expect(decoder).toHaveBeenCalledTimes(13);
});

it("does not decode ineligible forecast frames", () => {
  const risk = fixture();
  risk.frames.forEach((frame) => {
    frame.alertEligible = false;
  });
  const decoder = vi.spyOn(globalThis, "atob");
  expect(riskAtLocation(risk, 56, 11, timestamp)).toBeNull();
  expect(decoder.mock.calls.length).toBe(0);
});

it("never reuses decoded bytes after frame contents change", () => {
  const risk = fixture();
  expect(riskAtLocation(risk, 56, 11, timestamp)).toBeNull();
  risk.frames[0].intensity = btoa(String.fromCharCode(3).repeat(64 * 43));
  expect(riskAtLocation(risk, 56, 11, timestamp)?.intensity).toBe(3);
});

it("profiles only the risk lookup, not network/encryption or Cloudflare CPU", () => {
  const samples = [];
  for (let batch = 0; batch < 12; batch++) {
    const risk = fixture();
    const start = performance.now();
    for (let point = 0; point < 40; point++)
      riskAtLocation(risk, 56, 10.5 + point / 100, timestamp);
    samples.push(performance.now() - start);
  }
  samples.sort((a, b) => a - b);
  console.log(
    JSON.stringify({
      metric: "local-risk-lookup-40-locations",
      batches: 12,
      p50Ms: samples[5],
      p95Ms: samples[11],
      notCloudflareCpu: true,
    }),
  );
  expect(samples).toHaveLength(12);
});
