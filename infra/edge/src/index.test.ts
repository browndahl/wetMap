import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import worker, { buildRainEta } from "./index";

const futureTimes = [
  "2026-10-10T22:00",
  "2026-10-10T23:00",
  "2026-10-11T00:00",
];

class MemoryCache {
  values = new Map<string, Response>();

  async match(request: Request): Promise<Response | undefined> {
    return this.values.get(request.url)?.clone();
  }

  async put(request: Request, response: Response): Promise<void> {
    this.values.set(request.url, response.clone());
  }
}

class MemoryR2 {
  values = new Map<string, string | Uint8Array>();

  async get(
    key: string,
    options?: { range?: { offset: number; length: number } },
  ) {
    const value = this.values.get(key);
    if (!value) return null;
    const allBytes =
      typeof value === "string" ? new TextEncoder().encode(value) : value;
    const bytes = options?.range
      ? allBytes.slice(
          options.range.offset,
          options.range.offset + options.range.length,
        )
      : allBytes;
    return {
      json: async () =>
        JSON.parse(
          typeof value === "string" ? value : new TextDecoder().decode(value),
        ),
      body: new Response(bytes).body,
      httpEtag: `"${key}"`,
      writeHttpMetadata: (headers: Headers) =>
        headers.set("Content-Type", "application/json"),
    };
  }

  async put(key: string, value: string | ReadableStream | ArrayBuffer) {
    this.values.set(
      key,
      typeof value === "string"
        ? value
        : value instanceof ArrayBuffer
          ? new Uint8Array(value)
          : new Uint8Array(await new Response(value).arrayBuffer()),
    );
  }

  async delete(key: string) {
    this.values.delete(key);
  }

  async list(options: { prefix?: string }) {
    return {
      objects: Array.from(this.values.keys())
        .filter((key) => key.startsWith(options.prefix ?? ""))
        .map((key) => ({ key })),
      truncated: false,
    };
  }
}

const openMeteoResponse = () =>
  Response.json({
    latitude: 56.17,
    longitude: 10.21,
    hourly: {
      time: futureTimes,
      temperature_2m: [11, 10.5, 10],
      precipitation: [0, 0.1, 0.2],
      wind_speed_10m: [3, 3.2, 3.4],
      cloud_cover: [40, 50, 60],
    },
  });

const openMeteoPrecipitationResponse = () =>
  Response.json({
    latitude: 56.17,
    longitude: 10.21,
    minutely_15: {
      time: [
        "2026-10-10T22:15",
        "2026-10-10T22:30",
        "2026-10-10T22:45",
        "2026-10-10T23:00",
        "2026-10-10T23:15",
        "2026-10-10T23:30",
      ],
      precipitation: [0, 0.1, 0.7, 1.8, 0, 0],
    },
  });

const dmiResponse = (
  accumulatedPrecipitation: Array<number | null> = [0, 0.4, 1.2],
) =>
  Response.json({
    features: futureTimes.map((step, index) => ({
      properties: {
        step: `${step}:00.000Z`,
        "temperature-2m": 283.15 + index,
        "total-precipitation": accumulatedPrecipitation[index],
        "wind-speed-10m": 4 + index,
        "fraction-of-cloud-cover": 0.5,
      },
    })),
  });

function setup() {
  const cache = new MemoryCache();
  const r2 = new MemoryR2();
  const waits: Promise<unknown>[] = [];
  vi.stubGlobal("caches", { default: cache });
  const env = {
    RADAR: r2 as unknown as R2Bucket,
    DMI_BASE_URL: "https://dmi.test",
    OPEN_METEO_BASE_URL: "https://open-meteo.test",
    ALLOWED_ORIGIN: "https://wetmap.pages.dev",
  };
  const context = {
    waitUntil: (promise: Promise<unknown>) => waits.push(promise),
    passThroughOnException: vi.fn(),
    props: {},
  } as unknown as ExecutionContext;
  return { cache, r2, waits, env, context };
}

describe("radar nowcast edge endpoint", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("serves the generated optical-flow manifest with short caching", async () => {
    const { env, context, r2 } = setup();
    r2.values.set(
      "nowcast/nowcast.json",
      JSON.stringify({
        schemaVersion: 1,
        generatedAt: "2026-10-11T12:11:00Z",
        attribution: "Baseret på data fra DMI og efterfølgende bearbejdet",
        method: "adaptive-optical-flow-persistence",
        basedOnObservedAt: "2026-10-11T12:10:00Z",
        sourceFrameCount: 3,
        frames: [{ id: "frame-plus-05m", leadMinutes: 5 }],
      }),
    );

    const response = await worker.fetch(
      new Request("https://api.test/api/v1/radar/nowcast"),
      env,
      context,
    );
    const body = (await response.json()) as {
      method: string;
      frames: unknown[];
    };

    expect(response.status).toBe(200);
    expect(response.headers.get("Cache-Control")).toContain("max-age=60");
    expect(body.method).toBe("adaptive-optical-flow-persistence");
    expect(body.frames).toHaveLength(1);
  });

  it("serves rolling nowcast verification metrics", async () => {
    const { env, context, r2 } = setup();
    r2.values.set(
      "nowcast/verification.json",
      JSON.stringify({
        schemaVersion: 1,
        generatedAt: "2026-10-11T12:15:00Z",
        thresholdDbz: 20,
        sampleCount: 2,
        meanCriticalSuccessIndex: 0.71,
        results: [],
      }),
    );

    const response = await worker.fetch(
      new Request("https://api.test/api/v1/radar/nowcast/quality"),
      env,
      context,
    );
    const body = (await response.json()) as { sampleCount: number };

    expect(response.status).toBe(200);
    expect(body.sampleCount).toBe(2);
    expect(response.headers.get("Cache-Control")).toContain("max-age=300");
  });

  it("returns the multi-horizon quality contract before samples exist", async () => {
    const { env, context } = setup();

    const response = await worker.fetch(
      new Request("https://api.test/api/v1/radar/nowcast/quality"),
      env,
      context,
    );
    const body = (await response.json()) as {
      schemaVersion: number;
      thresholdsDbz: number[];
      byLeadMinutes: unknown[];
      observatory: {
        overallStatus: string;
        targetHorizonMinutes: number[];
        horizons: Array<{ status: string }>;
      };
    };

    expect(response.status).toBe(200);
    expect(body.schemaVersion).toBe(5);
    expect(body.thresholdsDbz).toEqual([5, 10, 15, 20, 35]);
    expect(body.byLeadMinutes).toEqual([]);
    expect(body.observatory.overallStatus).toBe("collecting");
    expect(body.observatory.targetHorizonMinutes).toEqual([15, 30, 45, 60]);
    expect(body.observatory.horizons).toHaveLength(4);
  });

  it("serves a compact precision observatory without raw verification history", async () => {
    const { env, context, r2 } = setup();
    r2.values.set(
      "nowcast/verification.json",
      JSON.stringify({
        schemaVersion: 4,
        generatedAt: "2026-10-12T12:30:00Z",
        latestVerifiedAt: "2026-10-12T12:29:00Z",
        algorithmVersion: "adaptive-optical-flow-persistence-v1",
        thresholdDbz: 20,
        sampleCount: 48,
        totalSampleCount: 48,
        observatory: {
          schemaVersion: 1,
          thresholdDbz: 20,
          overallStatus: "awaiting-rain",
          targetHorizonMinutes: [15, 30, 45, 60],
          verifiedHorizonCount: 0,
          horizons: [],
        },
        groundGauge: {
          observationCount: 12,
          stationComparisonCount: 1260,
          hits: 0,
          misses: 0,
          falseAlarms: 0,
          precision: null,
          recall: null,
          criticalSuccessIndex: null,
          calibration: {
            schemaVersion: 1,
            status: "awaiting-overlap",
            appliedThresholdDbz: 20,
            appliedSpatialRadiusPixels: 3,
            candidates: [],
          },
          results: [{ large: "history-is-not-forwarded" }],
        },
        results: [{ large: "history-is-not-forwarded" }],
      }),
    );

    const response = await worker.fetch(
      new Request("https://api.test/api/v1/radar/nowcast/observatory"),
      env,
      context,
    );
    const body = (await response.json()) as {
      observatory: { overallStatus: string };
      groundGauge: {
        stationComparisonCount: number;
        calibration: { status: string; appliedThresholdDbz: number };
        results?: unknown[];
      };
      results?: unknown[];
    };

    expect(response.status).toBe(200);
    expect(body.observatory.overallStatus).toBe("awaiting-rain");
    expect(body.groundGauge.stationComparisonCount).toBe(1260);
    expect(body.groundGauge.calibration.status).toBe("awaiting-overlap");
    expect(body.groundGauge.calibration.appliedThresholdDbz).toBe(20);
    expect(body.groundGauge.results).toBeUndefined();
    expect(body.results).toBeUndefined();
  });
});

describe("background push subscription endpoints", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("stores only validated, rounded Danish locations and allows deletion", async () => {
    const { env, context, r2 } = setup();
    Object.assign(env, {
      VAPID_PUBLIC_KEY: "public-key",
      VAPID_PRIVATE_KEY: "private-key",
    });
    const subscription = {
      endpoint: "https://push.example.test/subscription/123",
      expirationTime: null,
      keys: { auth: "a".repeat(22), p256dh: "b".repeat(88) },
    };
    const create = await worker.fetch(
      new Request("https://api.test/api/v1/push/subscriptions", {
        method: "POST",
        headers: {
          Origin: "https://wetmap.pages.dev",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          subscription,
          latitude: 56.16291,
          longitude: 10.20391,
          locationName: "Aarhus",
          locale: "da",
        }),
      }),
      env,
      context,
    );

    expect(create.status).toBe(201);
    const storedKey = Array.from(r2.values.keys()).find((key) =>
      key.startsWith("push/subscriptions/"),
    );
    expect(storedKey).toBeDefined();
    const storedSubscription = r2.values.get(storedKey!);
    if (typeof storedSubscription !== "string")
      throw new Error("Expected a JSON subscription object");
    expect(JSON.parse(storedSubscription)).toMatchObject({
      latitude: 56.16,
      longitude: 10.2,
      locationName: "Aarhus",
      activeRainEvent: false,
    });

    const remove = await worker.fetch(
      new Request("https://api.test/api/v1/push/subscriptions", {
        method: "DELETE",
        headers: {
          Origin: "https://wetmap.pages.dev",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ endpoint: subscription.endpoint }),
      }),
      env,
      context,
    );
    expect(remove.status).toBe(204);
    expect(r2.values.has(storedKey!)).toBe(false);
  });

  it("rejects cross-origin subscription writes", async () => {
    const { env, context } = setup();
    const response = await worker.fetch(
      new Request("https://api.test/api/v1/push/subscriptions", {
        method: "POST",
        headers: { Origin: "https://evil.example" },
        body: "{}",
      }),
      env,
      context,
    );
    expect(response.status).toBe(403);
  });
});

describe("forecast edge endpoint", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-10T22:15:00Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("serves direct DMI HARMONIE as the primary provider and persists it", async () => {
    const { env, context, r2 } = setup();
    const upstream = vi.fn(async () => dmiResponse());
    vi.stubGlobal("fetch", upstream);

    const response = await worker.fetch(
      new Request(
        "https://api.test/api/v1/weather/forecast?lat=56.1629&lon=10.2039",
      ),
      env,
      context,
    );
    const body = (await response.json()) as {
      source: string;
      points: Array<{ step: string }>;
    };

    expect(response.status).toBe(200);
    expect(response.headers.get("X-WetMap-Cache")).toBe("MISS");
    expect(body.source).toBe("dmi-edr");
    expect(body.points).toHaveLength(3);
    expect(body.points[0].step).toBe("2026-10-10T22:00:00.000Z");
    expect(response.headers.get("X-WetMap-Provider")).toBe("dmi-edr");
    expect(response.headers.get("X-WetMap-Fallback")).toBe("none");
    expect(response.headers.get("X-WetMap-DMI-Outcome")).toBe("success");
    expect(response.headers.get("Server-Timing")).toContain("dmi;dur=");
    expect(upstream).toHaveBeenCalledTimes(1);
    expect(r2.values.has("forecast/v3/56.16/10.20.json")).toBe(true);
  });

  it("turns DMI cumulative precipitation into per-hour amounts", async () => {
    const { env, context } = setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => dmiResponse([0.2, 0.7, 0.65])),
    );

    const response = await worker.fetch(
      new Request(
        "https://api.test/api/v1/weather/forecast?lat=56.1629&lon=10.2039",
      ),
      env,
      context,
    );
    const body = (await response.json()) as {
      points: Array<{ precipitationKgM2: number }>;
    };

    expect(body.points.map((point) => point.precipitationKgM2)).toEqual([
      0.2, 0.5, 0,
    ]);
  });

  it("allows Cloudflare Pages preview deployments without opening CORS globally", async () => {
    const { env, context } = setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => dmiResponse()),
    );
    const response = await worker.fetch(
      new Request(
        "https://api.test/api/v1/weather/forecast?lat=56.16&lon=10.20",
        {
          headers: { Origin: "https://86bc7cc8.wetmap.pages.dev" },
        },
      ),
      env,
      context,
    );

    expect(response.headers.get("Access-Control-Allow-Origin")).toBe(
      "https://86bc7cc8.wetmap.pages.dev",
    );

    const denied = await worker.fetch(
      new Request("https://api.test/health/live", {
        headers: { Origin: "https://evil.example" },
      }),
      env,
      context,
    );
    expect(denied.headers.has("Access-Control-Allow-Origin")).toBe(false);
  });

  it("coalesces nearby clicks onto the same model-grid cache entry", async () => {
    const { env, context } = setup();
    const upstream = vi.fn(async () => dmiResponse());
    vi.stubGlobal("fetch", upstream);

    await worker.fetch(
      new Request(
        "https://api.test/api/v1/weather/forecast?lat=56.1629&lon=10.2039",
      ),
      env,
      context,
    );
    const response = await worker.fetch(
      new Request(
        "https://api.test/api/v1/weather/forecast?lat=56.1640&lon=10.2041",
      ),
      env,
      context,
    );

    expect(response.status).toBe(200);
    expect(response.headers.get("X-WetMap-Cache")).toBe("HIT");
    expect(upstream).toHaveBeenCalledTimes(1);
  });

  it("falls back to Open-Meteo when direct DMI is unavailable", async () => {
    const { env, context } = setup();
    const upstream = vi.fn(async (input: string | URL | Request) => {
      const url = new URL(input instanceof Request ? input.url : String(input));
      if (url.origin === "https://dmi.test")
        return new Response(null, { status: 503 });
      return openMeteoResponse();
    });
    vi.stubGlobal("fetch", upstream);

    const response = await worker.fetch(
      new Request(
        "https://api.test/api/v1/weather/forecast?lat=55.6761&lon=12.5683",
      ),
      env,
      context,
    );
    const body = (await response.json()) as {
      source: string;
      points: Array<{ temperatureC: number }>;
    };

    expect(response.status).toBe(200);
    expect(body.source).toBe("open-meteo-dmi");
    expect(body.points[0].temperatureC).toBe(11);
    expect(response.headers.get("X-WetMap-Fallback")).toBe("open-meteo");
    expect(response.headers.get("X-WetMap-DMI-Outcome")).toBe("http-503");
    expect(upstream).toHaveBeenCalledTimes(2);
  });

  it("bounds a slow direct-DMI request with the low-latency fallback", async () => {
    const { env, context, waits } = setup();
    const upstream = vi.fn(async (input: string | URL | Request) => {
      const url = new URL(input instanceof Request ? input.url : String(input));
      if (url.origin === "https://dmi.test")
        return await new Promise<Response>((resolve) =>
          setTimeout(() => resolve(dmiResponse()), 5_000),
        );
      return openMeteoResponse();
    });
    vi.stubGlobal("fetch", upstream);

    const responsePromise = worker.fetch(
      new Request(
        "https://api.test/api/v1/weather/forecast?lat=55.6761&lon=12.5683",
      ),
      env,
      context,
    );
    await vi.advanceTimersByTimeAsync(1_500);
    const response = await responsePromise;

    expect(response.status).toBe(200);
    expect(response.headers.get("X-WetMap-Provider")).toBe("open-meteo-dmi");
    expect(response.headers.get("X-WetMap-Fallback")).toBe("open-meteo");
    expect(response.headers.get("X-WetMap-DMI-Outcome")).toBe("pending");
    expect(upstream).toHaveBeenCalledTimes(2);

    await vi.advanceTimersByTimeAsync(3_500);
    await Promise.all(waits);
    const refreshed = await worker.fetch(
      new Request(
        "https://api.test/api/v1/weather/forecast?lat=55.6761&lon=12.5683",
      ),
      env,
      context,
    );
    expect(refreshed.headers.get("X-WetMap-Cache")).toBe("HIT");
    expect(refreshed.headers.get("X-WetMap-Provider")).toBe("dmi-edr");
    expect(refreshed.headers.get("X-WetMap-Fallback")).toBe("none");
    expect(refreshed.headers.get("X-WetMap-DMI-Outcome")).toBe("success");
  });

  it("returns a persistent last-known-good forecast while refreshing in the background", async () => {
    const { env, context, r2, waits } = setup();
    r2.values.set(
      "forecast/v3/57.05/9.92.json",
      JSON.stringify({
        latitude: 57.05,
        longitude: 9.92,
        fetchedAt: "2026-10-10T20:00:00Z",
        attribution: "Baseret på data fra DMI og efterfølgende bearbejdet",
        source: "open-meteo-dmi",
        model: "DMI HARMONIE AROME",
        points: [
          {
            step: "2026-10-10T23:00:00Z",
            temperatureC: 9,
            precipitationKgM2: 0,
            windSpeedMs: 3,
            cloudCoverPercent: 30,
          },
        ],
      }),
    );
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => dmiResponse()),
    );

    const response = await worker.fetch(
      new Request(
        "https://api.test/api/v1/weather/forecast?lat=57.0488&lon=9.9217",
      ),
      env,
      context,
    );

    expect(response.status).toBe(200);
    expect(response.headers.get("X-WetMap-Cache")).toBe("STALE");
    expect(waits).toHaveLength(1);
    await Promise.all(waits);
  });

  it("returns a controlled 503 only when both providers and persistent cache are unavailable", async () => {
    const { env, context } = setup();
    const log = vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(null, { status: 503 })),
    );

    const response = await worker.fetch(
      new Request(
        "https://api.test/api/v1/weather/forecast?lat=56.50&lon=9.50",
      ),
      env,
      context,
    );
    const body = (await response.json()) as { status: number; title: string };

    expect(response.status).toBe(503);
    expect(body).toMatchObject({ status: 503, title: "Forecast unavailable" });
    expect(log).toHaveBeenCalledOnce();
  });

  it("rejects invalid coordinates before calling an upstream provider", async () => {
    const { env, context } = setup();
    const upstream = vi.fn();
    vi.stubGlobal("fetch", upstream);

    const response = await worker.fetch(
      new Request("https://api.test/api/v1/weather/forecast?lat=91&lon=10"),
      env,
      context,
    );

    expect(response.status).toBe(400);
    expect(upstream).not.toHaveBeenCalled();
  });
});

describe("rain ETA calculation", () => {
  const point = (
    offsetMinutes: number,
    intensity: "none" | "trace" | "light" | "moderate" | "heavy",
    precipitationMm = 0,
    confidence: number | null = null,
    source: "radar-nowcast" | "harmonie" = "harmonie",
  ) => ({
    startsAt: new Date(
      Date.parse("2026-10-10T22:00:00Z") + offsetMinutes * 60_000,
    ).toISOString(),
    endsAt: new Date(
      Date.parse("2026-10-10T22:00:00Z") + (offsetMinutes + 15) * 60_000,
    ).toISOString(),
    precipitationMm,
    intensity,
    confidence,
    source,
  });

  it("reports a dry hour without inventing confidence", () => {
    const eta = buildRainEta([
      point(0, "none"),
      point(15, "none"),
      point(30, "none"),
      point(45, "none"),
    ]);

    expect(eta).toMatchObject({
      status: "dry",
      arrivalWindowStart: null,
      durationMinutes: 0,
      totalPrecipitationMm: 0,
      confidence: null,
      confidenceLevel: "unknown",
    });
  });

  it("returns an honest arrival window and accumulated rain duration", () => {
    const eta = buildRainEta([
      point(0, "none"),
      point(15, "light", 0.2, 0.72, "radar-nowcast"),
      point(30, "moderate", 0.6, 0.64, "radar-nowcast"),
      point(45, "moderate", 0.5, 0.58, "radar-nowcast"),
    ]);

    expect(eta).toMatchObject({
      status: "expected",
      arrivalWindowStart: "2026-10-10T22:15:00.000Z",
      arrivalWindowEnd: "2026-10-10T22:30:00.000Z",
      continuesBeyondHorizon: true,
      durationMinutes: 45,
      totalPrecipitationMm: 1.3,
      confidenceLevel: "medium",
      source: "radar-nowcast",
    });
  });

  it("separates weak low-confidence echoes and intermittent showers", () => {
    const weakEcho = buildRainEta([
      point(0, "trace", 0.01, 0.32, "radar-nowcast"),
      point(15, "none"),
    ]);
    const showers = buildRainEta([
      point(0, "light", 0.2),
      point(15, "none"),
      point(30, "light", 0.2),
      point(45, "none"),
    ]);

    expect(weakEcho).toMatchObject({
      status: "weak-echo",
      confidenceLevel: "low",
      source: "radar-nowcast",
    });
    expect(showers).toMatchObject({
      status: "intermittent",
      durationMinutes: 30,
      totalPrecipitationMm: 0.4,
    });
  });
});

describe("next-hour precipitation edge endpoint", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-10T22:15:00Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("interpolates direct DMI hourly precipitation into four 15-minute estimates", async () => {
    const { env, context, r2 } = setup();
    const upstream = vi.fn(async (_input: RequestInfo | URL) =>
      dmiResponse([0, 0.4, 7.6]),
    );
    vi.stubGlobal("fetch", upstream);

    const response = await worker.fetch(
      new Request(
        "https://api.test/api/v1/weather/precipitation?lat=56.1629&lon=10.2039",
      ),
      env,
      context,
    );
    const body = (await response.json()) as {
      isInterpolated: boolean;
      sourceResolutionMinutes: number;
      rainEta: {
        status: string;
        continuesBeyondHorizon: boolean;
        totalPrecipitationMm: number;
        peakIntensity: string;
        confidenceLevel: string;
        source: string;
      };
      points: Array<{
        startsAt: string;
        endsAt: string;
        intensity: string;
      }>;
    };

    expect(response.status).toBe(200);
    expect(response.headers.get("X-WetMap-Cache")).toBe("MISS");
    expect(body.isInterpolated).toBe(true);
    expect(body.sourceResolutionMinutes).toBe(60);
    expect(body.points).toHaveLength(4);
    expect(body.points[0]).toMatchObject({
      startsAt: "2026-10-10T22:15:00.000Z",
      endsAt: "2026-10-10T22:30:00.000Z",
      intensity: "light",
    });
    expect(body.points.map((point) => point.intensity)).toEqual([
      "light",
      "light",
      "light",
      "heavy",
    ]);
    expect(body.rainEta).toMatchObject({
      status: "raining",
      continuesBeyondHorizon: true,
      totalPrecipitationMm: 2.1,
      peakIntensity: "heavy",
      confidenceLevel: "unknown",
      source: "harmonie",
    });
    expect(upstream).toHaveBeenCalledOnce();
    const requestedUrl = String(upstream.mock.calls[0]?.[0]);
    expect(requestedUrl).toContain("dmi.test");
    expect(requestedUrl).toContain("forecastedr");
    expect(response.headers.get("X-WetMap-Provider")).toBe("dmi-edr");
    expect(r2.values.has("precipitation/v2/56.16/10.20.json")).toBe(true);
  });

  it("uses Open-Meteo precipitation when direct DMI fails", async () => {
    const { env, context } = setup();
    const upstream = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(input instanceof Request ? input.url : String(input));
      return url.origin === "https://dmi.test"
        ? new Response(null, { status: 503 })
        : openMeteoPrecipitationResponse();
    });
    vi.stubGlobal("fetch", upstream);

    const response = await worker.fetch(
      new Request(
        "https://api.test/api/v1/weather/precipitation?lat=56.1629&lon=10.2039",
      ),
      env,
      context,
    );
    const body = (await response.json()) as { source: string };

    expect(response.status).toBe(200);
    expect(body.source).toBe("open-meteo-dmi");
    expect(response.headers.get("X-WetMap-Fallback")).toBe("open-meteo");
    expect(response.headers.get("X-WetMap-DMI-Outcome")).toBe("http-503");
    expect(upstream).toHaveBeenCalledTimes(2);
  });

  it("anchors near-term boxes to the same radar nowcast shown on the map", async () => {
    const { env, context, r2, waits } = setup();
    const frames = Array.from({ length: 13 }, (_, leadIndex) => ({
      leadMinutes: leadIndex * 5,
      predictedAt: new Date(
        Date.parse("2026-10-10T22:10:00Z") + leadIndex * 5 * 60_000,
      ).toISOString(),
      confidence: Math.max(0.45, 1 - leadIndex * 0.045),
      forecastMethod:
        leadIndex >= 9 ? ("persistence" as const) : ("optical-flow" as const),
    }));
    r2.values.set(
      "nowcast/point-risk.json",
      JSON.stringify({
        schemaVersion: 1,
        generatedAt: "2026-10-10T22:15:00Z",
        basedOnObservedAt: "2026-10-10T22:10:00Z",
        method: "adaptive-optical-flow-persistence",
        bounds: [8, 54, 13, 58],
        width: 2,
        height: 2,
        frameCount: frames.length,
        encoding: "pixel-major-uint8-dbz-plus-32",
        dataKey: "nowcast/point-risk-1.bin",
        neighborhoodRadiusPixels: 1,
        frames,
      }),
    );
    const encodedFrames = Uint8Array.from([
      14, 52, 57, 67, 72, 72, 67, 57, 52, 14, 14, 14, 14,
    ]);
    const pointCube = new Uint8Array(encodedFrames.length * 4);
    for (let pixel = 0; pixel < 4; pixel += 1)
      pointCube.set(encodedFrames, pixel * encodedFrames.length);
    r2.values.set("nowcast/point-risk-1.bin", pointCube);
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => dmiResponse([0, 0.4, 7.6])),
    );

    const response = await worker.fetch(
      new Request(
        "https://api.test/api/v1/weather/precipitation?lat=56.16291&lon=10.20393",
      ),
      env,
      context,
    );
    const body = (await response.json()) as {
      source: string;
      basedOnObservedAt?: string;
      rainEta: {
        status: string;
        departureWindowStart: string | null;
        departureWindowEnd: string | null;
        confidence: number | null;
        confidenceLevel: string;
        source: string;
      };
      points: Array<{
        source?: string;
        intensity: string;
        reflectivityDbz?: number;
        forecastMethod?: string | null;
      }>;
    };

    expect(response.status).toBe(200);
    expect(response.headers.get("X-WetMap-Precipitation-Source")).toBe(
      "dmi-radar-nowcast-harmonie",
    );
    expect(body.source).toBe("dmi-radar-nowcast-harmonie");
    expect(body.basedOnObservedAt).toBe("2026-10-10T22:10:00Z");
    expect(body.points[0]).toMatchObject({
      source: "radar-nowcast",
      intensity: "moderate",
      reflectivityDbz: 35,
    });
    expect(body.points.every((point) => point.source === "radar-nowcast")).toBe(
      true,
    );
    expect(
      body.points.some((point) => point.forecastMethod === "persistence"),
    ).toBe(true);
    expect(body.rainEta).toMatchObject({
      status: "raining",
      departureWindowStart: "2026-10-10T23:00:00.000Z",
      departureWindowEnd: "2026-10-10T23:15:00.000Z",
      confidenceLevel: "medium",
      source: "radar-nowcast",
    });
    expect(body.rainEta.confidence).toBeGreaterThan(0.55);

    await Promise.all(waits);
    const cached = await worker.fetch(
      new Request(
        "https://api.test/api/v1/weather/precipitation?lat=56.16291&lon=10.20393",
      ),
      env,
      context,
    );
    expect(cached.headers.get("X-WetMap-Point-Cache")).toBe("HIT");
    expect(cached.headers.get("Server-Timing")).toContain("point_cache;dur=");
  });

  it("uses a still-relevant persistent estimate during an upstream outage", async () => {
    const { env, context, r2, waits } = setup();
    r2.values.set(
      "precipitation/v2/55.68/12.57.json",
      JSON.stringify({
        latitude: 55.68,
        longitude: 12.57,
        fetchedAt: "2026-10-10T22:10:00Z",
        attribution: "Baseret på data fra DMI og efterfølgende bearbejdet",
        source: "open-meteo-dmi",
        model: "DMI HARMONIE AROME",
        displayResolutionMinutes: 15,
        sourceResolutionMinutes: 60,
        isInterpolated: true,
        points: [
          {
            startsAt: "2026-10-10T22:15:00Z",
            endsAt: "2026-10-10T22:30:00Z",
            precipitationMm: 0.1,
            intensity: "light",
          },
        ],
      }),
    );
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(null, { status: 503 })),
    );

    const response = await worker.fetch(
      new Request(
        "https://api.test/api/v1/weather/precipitation?lat=55.6761&lon=12.5683",
      ),
      env,
      context,
    );

    expect(response.status).toBe(200);
    expect(response.headers.get("X-WetMap-Cache")).toBe("STALE");
    expect(waits).toHaveLength(1);
    await Promise.all(waits);
  });

  it("returns a controlled error for invalid coordinates", async () => {
    const { env, context } = setup();
    const upstream = vi.fn();
    vi.stubGlobal("fetch", upstream);

    const response = await worker.fetch(
      new Request(
        "https://api.test/api/v1/weather/precipitation?lat=56&lon=181",
      ),
      env,
      context,
    );

    expect(response.status).toBe(400);
    expect(upstream).not.toHaveBeenCalled();
  });
});

describe("location edge endpoints", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("normalizes Danish Photon results and caches repeated searches", async () => {
    const { env, context, waits } = setup();
    Object.assign(env, { GEOCODER_BASE_URL: "https://photon.test" });
    const upstream = vi.fn(async (_input: RequestInfo | URL) =>
      Response.json({
        features: [
          {
            properties: {
              osm_type: "N",
              osm_id: 1,
              type: "city",
              name: "Aarhus",
              state: "Region Midtjylland",
              countrycode: "DK",
            },
            geometry: { coordinates: [10.21, 56.15] },
          },
          {
            properties: {
              osm_type: "N",
              osm_id: 2,
              type: "city",
              name: "Aarhus",
              countrycode: "US",
            },
            geometry: { coordinates: [-95, 40] },
          },
        ],
      }),
    );
    vi.stubGlobal("fetch", upstream);

    const request = new Request(
      "https://api.test/api/v1/locations/search?q=Aarhus&lat=56.16&lon=10.20",
    );
    const first = await worker.fetch(request, env, context);
    const body = (await first.json()) as {
      query: string;
      results: Array<{ name: string; context: string }>;
    };
    await Promise.all(waits);
    const second = await worker.fetch(request, env, context);

    expect(body).toMatchObject({
      query: "Aarhus",
      results: [{ name: "Aarhus", context: "Region Midtjylland" }],
    });
    expect(first.headers.get("X-WetMap-Cache")).toBe("MISS");
    expect(second.headers.get("X-WetMap-Cache")).toBe("HIT");
    expect(upstream).toHaveBeenCalledOnce();
    expect(String(upstream.mock.calls[0]?.[0])).toContain("countrycode=DK");
  });

  it("rejects invalid location queries before calling Photon", async () => {
    const { env, context } = setup();
    const upstream = vi.fn();
    vi.stubGlobal("fetch", upstream);

    const response = await worker.fetch(
      new Request("https://api.test/api/v1/locations/search?q=A"),
      env,
      context,
    );

    expect(response.status).toBe(400);
    expect(upstream).not.toHaveBeenCalled();
  });

  it("turns reverse geocoding into an address label", async () => {
    const { env, context } = setup();
    Object.assign(env, { GEOCODER_BASE_URL: "https://photon.test" });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        Response.json({
          features: [
            {
              properties: {
                osm_type: "N",
                osm_id: 3,
                type: "house",
                street: "Livøsmøgen",
                housenumber: "36A",
                city: "Aarhus C",
                postcode: "8000",
                countrycode: "DK",
              },
              geometry: { coordinates: [10.204, 56.163] },
            },
          ],
        }),
      ),
    );

    const response = await worker.fetch(
      new Request(
        "https://api.test/api/v1/locations/reverse?lat=56.1629&lon=10.2039",
      ),
      env,
      context,
    );
    const body = (await response.json()) as {
      name: string;
      context: string;
      type: string;
    };

    expect(response.status).toBe(200);
    expect(body).toMatchObject({
      name: "Livøsmøgen 36A",
      context: "8000 · Aarhus C",
      type: "address",
    });
  });
});

describe("radar freshness scheduler", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-11T06:15:00Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("does not dispatch ingestion while the latest observation is fresh", async () => {
    const { env, context, r2, waits } = setup();
    r2.values.set(
      "frames/frames.json",
      JSON.stringify({
        frames: [{ observedAt: "2026-10-11T06:00:00Z" }],
      }),
    );
    const upstream = vi.fn();
    vi.stubGlobal("fetch", upstream);

    await worker.scheduled({} as ScheduledController, env, context);
    await Promise.all(waits);

    expect(upstream).not.toHaveBeenCalled();
  });

  it("dispatches the GitHub radar workflow when observations are stale", async () => {
    const { env, context, r2, waits } = setup();
    Object.assign(env, {
      GITHUB_DISPATCH_TOKEN: "test-token",
      GITHUB_REPOSITORY: "browndahl/wetMap",
      GITHUB_RADAR_WORKFLOW: "radar.yml",
      GITHUB_REF: "main",
    });
    r2.values.set(
      "frames/frames.json",
      JSON.stringify({
        frames: [{ observedAt: "2026-10-11T05:50:00Z" }],
      }),
    );
    const upstream = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", upstream);

    await worker.scheduled({} as ScheduledController, env, context);
    await Promise.all(waits);

    expect(upstream).toHaveBeenCalledOnce();
    expect(upstream).toHaveBeenCalledWith(
      "https://api.github.com/repos/browndahl/wetMap/actions/workflows/radar.yml/dispatches",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ ref: "main" }),
      }),
    );
  });

  it("fails closed when the dispatch secret is missing", async () => {
    const { env, context, waits } = setup();
    const log = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const upstream = vi.fn();
    vi.stubGlobal("fetch", upstream);

    await worker.scheduled({} as ScheduledController, env, context);
    await Promise.all(waits);

    expect(upstream).not.toHaveBeenCalled();
    expect(log).toHaveBeenCalledWith("radar.scheduler.missing-token");
  });
});
