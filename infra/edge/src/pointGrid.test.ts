import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { radarPointSamples } from "./index";

function setup(
  changes: Record<string, unknown> = {},
  versions = ["version-a", "version-a"],
  rowBytes = [52, 60, 52, 60],
) {
  const metadata = {
    schemaVersion: 2,
    generatedAt: "2026-11-17T22:00:00Z",
    basedOnObservedAt: "2026-11-17T22:00:00Z",
    encoding: "pixel-major-uint8-dbz-plus-32",
    dataKey: "nowcast/point-risk-1.bin",
    dataEtag: "version-a",
    bounds: [8, 54, 13, 58],
    width: 2,
    height: 2,
    frameCount: 2,
    neighborhoodRadiusPixels: 1,
    frames: [
      { leadMinutes: 0, predictedAt: "2026-11-17T22:00:00Z", confidence: 1 },
      { leadMinutes: 5, predictedAt: "2026-11-17T22:05:00Z", confidence: 0.9 },
    ],
    ...changes,
  };
  let row = 0;
  const arrayBuffer = vi.fn(async () => new Uint8Array(rowBytes).buffer);
  const get = vi.fn(async (key: string, options?: R2GetOptions) => {
    if (key === "nowcast/point-risk.json")
      return { json: async () => metadata };
    const etag = versions[row++] ?? "version-a";
    const condition = options?.onlyIf as R2Conditional | undefined;
    if (condition?.etagMatches && condition.etagMatches !== etag)
      return { etag };
    return {
      etag,
      body: new Response(new Uint8Array(rowBytes)).body,
      arrayBuffer,
    };
  });
  const env = {
    RADAR: { get } as unknown as R2Bucket,
    DMI_BASE_URL: "https://dmi.test",
    OPEN_METEO_BASE_URL: "https://model.test",
    ALLOWED_ORIGIN: "https://web.test",
  };
  return { env, get, arrayBuffer };
}
beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-11-17T22:05:00Z"));
});

it.each([
  { frames: [null, null] },
  {
    frames: [
      { leadMinutes: 0, predictedAt: "wrong", confidence: 1 },
      { leadMinutes: 5, predictedAt: "wrong", confidence: 1 },
    ],
  },
])("rejects malformed per-frame contracts %j", async (changes) => {
  const { env } = setup(changes);
  expect(await radarPointSamples(56, 10, env)).toBeNull();
});

it("keeps a range read failure observable and returns unavailable radar", async () => {
  const { env, get } = setup();
  const original = get.getMockImplementation()!;
  get.mockImplementation((key, options) =>
    key.endsWith(".bin")
      ? Promise.reject(new Error("storage unavailable"))
      : original(key, options),
  );
  const error = vi.spyOn(console, "error").mockImplementation(() => undefined);
  expect(await radarPointSamples(56, 10, env)).toBeNull();
  expect(error).toHaveBeenCalledWith("radar.point-grid.read-failed");
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

it("binds every byte range to the metadata's object ETag", async () => {
  const { env, get, arrayBuffer } = setup();
  const result = await radarPointSamples(56, 10, env);
  expect(result?.samples.map((sample) => sample.reflectivityDbz)).toEqual([
    20, 28,
  ]);
  expect(arrayBuffer).toHaveBeenCalledTimes(2);
  for (const [key, options] of get.mock.calls.filter(([key]) =>
    key.endsWith(".bin"),
  )) {
    expect(key).toBe("nowcast/point-risk-1.bin");
    expect(options?.onlyIf).toEqual({ etagMatches: "version-a" });
  }
});

it("rejects a short range instead of returning a dry radar sample", async () => {
  const { env } = setup({}, undefined, [52, 60]);
  expect(await radarPointSamples(56, 10, env)).toBeNull();
});

it.each([
  ["version-b", "version-b"],
  ["version-a", "version-b"],
])("rejects an overwritten object or mixed rows %j", async (...versions) => {
  const { env } = setup({}, versions);
  expect(await radarPointSamples(56, 10, env)).toBeNull();
});

it("does not treat an unversioned legacy pointer as safe radar data", async () => {
  const { env, get } = setup({ dataEtag: undefined, schemaVersion: 1 });
  expect(await radarPointSamples(56, 10, env)).toBeNull();
  expect(get).toHaveBeenCalledOnce();
});

it.each([
  { bounds: null },
  { frames: null },
  { width: 1.5 },
  { dataEtag: "bad\r\nheader" },
])(
  "fails closed instead of throwing on malformed metadata %j",
  async (changes) => {
    const { env } = setup(changes);
    expect(await radarPointSamples(56, 10, env)).toBeNull();
  },
);
