import { afterEach, beforeEach, expect, it, vi } from "vitest";
import worker from "./index";

let match: ReturnType<typeof vi.fn>;
let get: ReturnType<typeof vi.fn>;
let upstream: ReturnType<typeof vi.fn>;
let context: ExecutionContext;
let env: Parameters<typeof worker.fetch>[1];

beforeEach(() => {
  match = vi.fn().mockResolvedValue(undefined);
  get = vi.fn().mockResolvedValue(null);
  upstream = vi.fn().mockRejectedValue(new Error("mock upstream unavailable"));
  vi.stubGlobal("caches", { default: { match, put: vi.fn() } });
  vi.stubGlobal("fetch", upstream);
  context = { waitUntil: vi.fn() } as unknown as ExecutionContext;
  env = {
    RADAR: { get } as unknown as R2Bucket,
    DMI_BASE_URL: "https://dmi.test",
    OPEN_METEO_BASE_URL: "https://model.test",
    ALLOWED_ORIGIN: "https://web.test",
  };
  vi.spyOn(console, "error").mockImplementation(() => undefined);
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

for (const endpoint of ["forecast", "precipitation"]) {
  it.each(["", "?lat=56", "?lon=10", "?lat=&lon=10", "?lat=56&lon=%20"])(
    `${endpoint} rejects missing/blank required coordinates before I/O: %s`,
    async (query) => {
      const response = await worker.fetch(
        new Request(`https://api.test/api/v1/weather/${endpoint}${query}`),
        env,
        context,
      );
      expect(response.status).toBe(400);
      expect(response.headers.get("Content-Type")).toContain(
        "application/problem+json",
      );
      expect(match).not.toHaveBeenCalled();
      expect(get).not.toHaveBeenCalled();
      expect(upstream).not.toHaveBeenCalled();
      expect(context.waitUntil).not.toHaveBeenCalled();
    },
  );

  it.each([
    "?lat=91&lon=10",
    "?lat=56&lon=-181",
    "?lat=NaN&lon=10",
    "?lat=56&lon=Infinity",
  ])(`${endpoint} preserves finite/range validation: %s`, async (query) => {
    const response = await worker.fetch(
      new Request(`https://api.test/api/v1/weather/${endpoint}${query}`),
      env,
      context,
    );
    expect(response.status).toBe(400);
    expect(get).not.toHaveBeenCalled();
    expect(upstream).not.toHaveBeenCalled();
  });

  it(`${endpoint} accepts explicitly supplied zero rather than treating it as missing`, async () => {
    match.mockImplementation(async () => Response.json({ cached: true }));
    const response = await worker.fetch(
      new Request(`https://api.test/api/v1/weather/${endpoint}?lat=0&lon=0`),
      env,
      context,
    );
    expect(response.status).toBe(200);
    expect(match).toHaveBeenCalledTimes(1);
    expect(upstream).not.toHaveBeenCalled();
  });
}
