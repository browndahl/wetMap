import { expect, it } from "vitest";
import { radarPointSamples } from "./index";
import { notificationPayload, riskAtLocation } from "./push";
import type { RainRiskHit, StoredSubscription } from "./push";

const observed = Date.parse("2026-11-18T12:00:00Z");
const frames = Array.from({ length: 13 }, (_, index) => ({
  leadMinutes: index * 5,
  predictedAt: new Date(observed + index * 300_000).toISOString(),
  alertEligible: true,
  confidence: 1,
}));
const width = 64;
const height = 43;
const intensity = btoa("\0".repeat(width * height));
const geometry = {
  bounds: [10, 55, 12, 57] as [number, number, number, number],
  width,
  height,
  basedOnObservedAt: new Date(observed).toISOString(),
};

async function measure(label: string, work: () => void | Promise<void>) {
  const samples = [];
  for (let i = -8; i < 40; i++) {
    const start = process.cpuUsage();
    await work();
    const { user, system } = process.cpuUsage(start);
    if (i >= 0) samples.push((user + system) / 1000);
  }
  samples.sort((a, b) => a - b);
  console.log(
    JSON.stringify({
      label,
      batches: samples.length,
      p50Ms: samples[19],
      p95Ms: samples[37],
      localProcessCpu: true,
    }),
  );
}

// Diagnostic only: keep timings out of regular CI; no speed assertion.
it.skipIf(process.env.WETMAP_CPU_BENCH !== "1")(
  "profiles synthetic push and point lookup work without any external calls",
  async () => {
    const makeRisk = () => ({
      ...geometry,
      schemaVersion: 1 as const,
      generatedAt: new Date(observed).toISOString(),
      encoding: "uint8-base64" as const,
      frames: frames.map((frame) => ({ ...frame, intensity })),
    });
    await measure("risk-lookup-40-dry-points", () => {
      const risk = makeRisk();
      for (let i = 0; i < 40; i++)
        riskAtLocation(risk, 56, 10.5 + i / 100, observed);
    });
    const forecast: RainRiskHit = {
      ...frames[3],
      kind: "forecast",
      intensity: 3,
    };
    const observation: RainRiskHit = {
      ...frames[0],
      kind: "observed",
      intensity: 3,
    };
    const subscription: StoredSubscription = {
      schemaVersion: 1,
      latitude: 56,
      longitude: 11,
      locationName: "Test",
      locale: "da",
      subscription: {
        endpoint: "https://push.example.test",
        keys: { auth: "", p256dh: "" },
      },
      createdAt: frames[0].predictedAt,
      updatedAt: frames[0].predictedAt,
      activeRainEvent: false,
    };
    await measure("format-40-push-payloads", () => {
      for (let i = 0; i < 40; i++)
        notificationPayload(
          subscription,
          i % 2 === 0 ? forecast : observation,
          observed,
        );
    });

    const gridOrigin = Math.floor(Date.now() / 300_000) * 300_000;
    const metadata = {
      ...geometry,
      schemaVersion: 2,
      dataEtag: "fixture",
      encoding: "pixel-major-uint8-dbz-plus-32",
      frameCount: frames.length,
      neighborhoodRadiusPixels: 1,
      basedOnObservedAt: new Date(gridOrigin).toISOString(),
      frames: frames.map((frame) => ({
        ...frame,
        predictedAt: new Date(
          gridOrigin + frame.leadMinutes * 60_000,
        ).toISOString(),
      })),
    };
    const json = JSON.stringify(metadata);
    let bytesRead = 0;
    let rowReads = 0;
    const env = {
      RADAR: {
        get: async (key: string, options?: { range: { length: number } }) => {
          if (key === "nowcast/point-risk.json")
            return { size: json.length, json: async () => JSON.parse(json) };
          if (key !== "nowcast/point-risk.bin" || !options)
            throw new Error("Unexpected mock R2 read");
          rowReads++;
          bytesRead += options.range.length;
          const bytes = new Uint8Array(options.range.length).fill(52);
          return {
            etag: "fixture",
            get body() {
              return new Response(bytes).body;
            },
            arrayBuffer: async () => bytes.buffer,
          };
        },
      },
    } as unknown as Parameters<typeof radarPointSamples>[2];
    const point = await radarPointSamples(56, 11, env);
    expect(point?.samples.map((sample) => sample.reflectivityDbz)).toEqual(
      Array(13).fill(20),
    );
    await measure("point-grid-20-lookups-three-ranges-each", async () => {
      for (let i = 0; i < 20; i++)
        await radarPointSamples(56, 10.5 + i / 100, env);
    });
    expect(rowReads).toBe((48 * 20 + 1) * 3);
    expect(bytesRead).toBe(rowReads * 3 * frames.length);
  },
);
