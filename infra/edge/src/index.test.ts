import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import worker from "./index";

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
  values = new Map<string, string>();

  async get(key: string) {
    const value = this.values.get(key);
    if (!value) return null;
    return { json: async () => JSON.parse(value) };
  }

  async put(key: string, value: string | ReadableStream | ArrayBuffer) {
    this.values.set(key, typeof value === "string" ? value : String(value));
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

  it("serves DMI HARMONIE through the low-latency provider and persists it", async () => {
    const { env, context, r2 } = setup();
    const upstream = vi.fn(async () => openMeteoResponse());
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
    expect(body.source).toBe("open-meteo-dmi");
    expect(body.points).toHaveLength(3);
    expect(body.points[0].step).toBe("2026-10-10T22:00:00Z");
    expect(upstream).toHaveBeenCalledTimes(1);
    expect(r2.values.has("forecast/v2/56.16/10.20.json")).toBe(true);
  });

  it("allows Cloudflare Pages preview deployments without opening CORS globally", async () => {
    const { env, context } = setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => openMeteoResponse()),
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
    const upstream = vi.fn(async () => openMeteoResponse());
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

  it("falls back to DMI EDR when the primary distributor is unavailable", async () => {
    const { env, context } = setup();
    const upstream = vi.fn(async (input: string | URL | Request) => {
      const url = new URL(input instanceof Request ? input.url : String(input));
      if (url.origin === "https://open-meteo.test")
        return new Response(null, { status: 503 });
      return Response.json({
        features: futureTimes.map((step) => ({
          properties: {
            step: `${step}:00.000Z`,
            "temperature-2m": 283.15,
            "total-precipitation": 0.2,
            "wind-speed-10m": 4,
            "fraction-of-cloud-cover": 0.5,
          },
        })),
      });
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
    expect(body.source).toBe("dmi-edr");
    expect(body.points[0].temperatureC).toBe(10);
    expect(upstream).toHaveBeenCalledTimes(2);
  });

  it("returns a persistent last-known-good forecast while refreshing in the background", async () => {
    const { env, context, r2, waits } = setup();
    r2.values.set(
      "forecast/v2/57.05/9.92.json",
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
      vi.fn(async () => openMeteoResponse()),
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
