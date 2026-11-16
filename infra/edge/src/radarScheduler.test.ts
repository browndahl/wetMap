import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ensureFreshRadar, radarDispatchStateKey } from "./radarScheduler";

// Model R2's conditional PUT, including two readers observing the same version.
class Bucket {
  values = new Map<string, string>();
  versions = new Map<string, number>();
  async get(key: string) {
    const value = this.values.get(key);
    return value === undefined
      ? null
      : {
          etag: `${key}:${this.versions.get(key) ?? 0}`,
          json: async () => JSON.parse(value),
        };
  }
  async put(key: string, value: string, options?: R2PutOptions) {
    const condition = options?.onlyIf as R2Conditional | undefined;
    if (condition?.etagDoesNotMatch === "*" && this.values.has(key))
      return null;
    if (
      condition?.etagMatches &&
      condition.etagMatches !== `${key}:${this.versions.get(key) ?? 0}`
    )
      return null;
    this.values.set(key, value);
    this.versions.set(key, (this.versions.get(key) ?? 0) + 1);
    return { etag: `${key}:${this.versions.get(key)}` };
  }
}

const now = new Date("2026-11-16T12:00:00Z");
const before = (minutes: number) =>
  new Date(now.getTime() - minutes * 60_000).toISOString();

function setup() {
  const bucket = new Bucket();
  bucket.values.set(
    "frames/frames.json",
    JSON.stringify({
      generatedAt: before(7),
      frames: [{ observedAt: before(19) }],
    }),
  );
  const fetcher = vi.fn(async (_url: string, init?: RequestInit) =>
    init?.method === "POST"
      ? new Response(null, { status: 204 })
      : Response.json({ workflow_runs: [] }),
  );
  vi.stubGlobal("fetch", fetcher);
  const env = {
    RADAR: bucket as unknown as R2Bucket,
    GITHUB_DISPATCH_TOKEN: "test-only",
  };
  const state = () =>
    JSON.parse(bucket.values.get(radarDispatchStateKey) ?? "null");
  const manifest = (value: unknown) =>
    bucket.values.set("frames/frames.json", JSON.stringify(value));
  return { bucket, env, fetcher, state, manifest };
}

describe("bounded radar recovery", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(now);
    vi.spyOn(console, "log").mockImplementation(() => undefined);
    vi.spyOn(console, "error").mockImplementation(() => undefined);
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("recovers a missing publication while observation age is still below 25 minutes", async () => {
    const { env, fetcher, state } = setup();
    await ensureFreshRadar(env);
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(fetcher.mock.calls[0][0]).toContain(
      "radar.yml/runs?branch=main&per_page=20",
    );
    expect(fetcher.mock.calls[1][1]?.signal).toBeInstanceOf(AbortSignal);
    expect(state().decision).toBe("dispatched");
  });

  it("does not confuse a fresh ingestion heartbeat with fresh DMI observations", async () => {
    const { env, fetcher, manifest } = setup();
    manifest({ generatedAt: before(2), frames: [{ observedAt: before(50) }] });
    await ensureFreshRadar(env);
    expect(fetcher).not.toHaveBeenCalled();
    // The unchanged public classifier still reports source-delayed, not healthy.
  });

  it("recovers exactly at six minutes without waiting for stale observations", async () => {
    const { env, fetcher, manifest } = setup();
    manifest({ generatedAt: before(6), frames: [{ observedAt: before(12) }] });
    await ensureFreshRadar(env);
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it.each([
    {},
    { generatedAt: before(1), frames: [] },
    { generatedAt: before(1), frames: [{ observedAt: "invalid" }] },
    { generatedAt: before(1), frames: [{ observedAt: before(-5) }] },
    { generatedAt: before(-5), frames: [{ observedAt: before(10) }] },
  ])("recovers invalid/missing/future manifests: %j", async (value) => {
    const { env, fetcher, manifest } = setup();
    manifest(value);
    await ensureFreshRadar(env);
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("retains compatibility with old manifests without a publication heartbeat", async () => {
    const { env, fetcher, manifest } = setup();
    manifest({ frames: [{ observedAt: before(15) }] });
    await ensureFreshRadar(env);
    expect(fetcher).not.toHaveBeenCalled();
    manifest({ frames: [{ observedAt: before(21) }] });
    await ensureFreshRadar(env);
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it.each(["queued", "pending", "waiting", "requested", "in_progress"])(
    "avoids duplicating a recent %s job",
    async (status) => {
      const { env, fetcher, state } = setup();
      fetcher.mockResolvedValueOnce(
        Response.json({
          workflow_runs: [{ id: 123, status, created_at: before(1) }],
        }),
      );
      await ensureFreshRadar(env);
      expect(fetcher).toHaveBeenCalledOnce();
      expect(state()).toMatchObject({
        decision: "active-run",
        activeRunId: 123,
      });
    },
  );

  it.each(["queued", "in_progress"])(
    "does not lock recovery behind an old %s record",
    async (status) => {
      const { env, fetcher, state } = setup();
      fetcher.mockResolvedValueOnce(
        Response.json({
          workflow_runs: [{ id: 123, status, created_at: before(52) }],
        }),
      );
      await ensureFreshRadar(env);
      expect(fetcher).toHaveBeenCalledTimes(2);
      expect(state().decision).toBe("dispatched");
    },
  );

  it("claims a dispatch once across overlapping isolates, including an existing state", async () => {
    const { bucket, env, fetcher } = setup();
    await Promise.all([ensureFreshRadar(env), ensureFreshRadar(env)]);
    expect(fetcher).toHaveBeenCalledTimes(2);
    vi.advanceTimersByTime(5 * 60_000);
    await Promise.all([ensureFreshRadar(env), ensureFreshRadar(env)]);
    expect(fetcher).toHaveBeenCalledTimes(4);
    expect(bucket.values.get(radarDispatchStateKey)).not.toContain("test-only");
  });

  it("retains the dispatch cooldown then automatically retries", async () => {
    const { env, fetcher } = setup();
    await ensureFreshRadar(env);
    vi.advanceTimersByTime(4 * 60_000);
    await ensureFreshRadar(env);
    expect(fetcher).toHaveBeenCalledTimes(2);
    vi.advanceTimersByTime(60_000);
    await ensureFreshRadar(env);
    expect(fetcher).toHaveBeenCalledTimes(4);
  });

  it.each([401, 403, 429, 500])(
    "records HTTP %s without a retry storm and recovers later",
    async (status) => {
      const { env, fetcher, state } = setup();
      fetcher.mockResolvedValueOnce(new Response(null, { status }));
      await expect(ensureFreshRadar(env)).rejects.toThrow(
        "github-inspection-or-dispatch-failed",
      );
      expect(state()).toMatchObject({
        decision: "dispatch-failed",
        dispatchError: "github-inspection-or-dispatch-failed",
      });
      await ensureFreshRadar(env);
      expect(fetcher).toHaveBeenCalledOnce();
      vi.advanceTimersByTime(2 * 60_000);
      await ensureFreshRadar(env);
      expect(state().decision).toBe("dispatched");
      expect(state().dispatchError).toBeUndefined();
    },
  );

  it("bounds ambiguous dispatch failures and recovers from corrupt state", async () => {
    const { bucket, env, fetcher, state } = setup();
    bucket.values.set(radarDispatchStateKey, "bad json");
    fetcher.mockResolvedValueOnce(Response.json({ workflow_runs: [] }));
    fetcher.mockRejectedValueOnce(
      new DOMException("Timed out", "TimeoutError"),
    );
    await expect(ensureFreshRadar(env)).rejects.toThrow();
    expect(state().decision).toBe("dispatch-failed");
    await ensureFreshRadar(env);
    expect(fetcher).toHaveBeenCalledTimes(2);
    vi.advanceTimersByTime(2 * 60_000);
    await ensureFreshRadar(env);
    expect(state().decision).toBe("dispatched");
  });

  it("never dispatches on malformed queue responses or without a token", async () => {
    const { env, fetcher } = setup();
    fetcher.mockResolvedValueOnce(Response.json({ unexpected: [] }));
    await expect(ensureFreshRadar(env)).rejects.toThrow();
    expect(fetcher).toHaveBeenCalledOnce();
    await ensureFreshRadar({ ...env, GITHUB_DISPATCH_TOKEN: undefined });
    expect(fetcher).toHaveBeenCalledOnce();
  });
});
