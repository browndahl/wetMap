import { afterEach, beforeEach, expect, it, vi } from "vitest";
import worker from "./index";
import {
  operationsStatus,
  receiveOperationsReport,
  scheduleOperations,
} from "./operations";

class Bucket {
  values = new Map<string, { value: string; etag: string }>();
  version = 0;
  async get(key: string) {
    const entry = this.values.get(key);
    return entry
      ? { etag: entry.etag, json: async () => JSON.parse(entry.value) }
      : null;
  }
  async put(key: string, value: string, options?: R2PutOptions) {
    const condition = options?.onlyIf as R2Conditional | undefined;
    const current = this.values.get(key);
    if (condition?.etagMatches && current?.etag !== condition.etagMatches)
      return null;
    if (condition?.etagDoesNotMatch === "*" && current) return null;
    const etag = String(++this.version);
    this.values.set(key, { value, etag });
    return { etag };
  }
}
const now = "2026-10-30T12:00:00Z";
const names = ["web", "api", "radar", "quality", "performance", "scheduler"];
const report = (runId = "1", failures: Record<string, string> = {}) => ({
  runId,
  checkedAt: new Date().toISOString(),
  checks: names.map((name) => ({
    name,
    ok: !failures[name],
    code: failures[name] || "ok",
    durationMs: 10,
  })),
});
const request = (body: unknown, token = "test-monitor-token") =>
  new Request("https://api.test/api/v1/operations/report", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
function setup() {
  const bucket = new Bucket();
  const env = {
    RADAR: bucket as unknown as R2Bucket,
    OPERATIONS_MONITOR_ENABLED: "true",
    MONITOR_REPORT_TOKEN: "test-monitor-token",
    GITHUB_DISPATCH_TOKEN: "test-dispatch-token",
  };
  return { bucket, env };
}
beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date(now));
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

it("dispatches on a missing probe, coalesces concurrent ticks and limits retry frequency", async () => {
  const { env, bucket } = setup();
  const upstream = vi.fn(
    async (_url: string, _options?: RequestInit) =>
      new Response(null, { status: 204 }),
  );
  vi.stubGlobal("fetch", upstream);
  await Promise.all([scheduleOperations(env), scheduleOperations(env)]);
  expect(upstream).toHaveBeenCalledOnce();
  expect(upstream.mock.calls[0]?.[0]).toContain("synthetic.yml/dispatches");
  await scheduleOperations(env);
  expect(upstream).toHaveBeenCalledOnce();
  vi.setSystemTime(new Date(Date.now() + 15 * 60_000));
  await scheduleOperations(env);
  expect(upstream).toHaveBeenCalledTimes(2);
  expect(bucket.values.size).toBe(1);
});

it("does not dispatch while a recent external probe exists", async () => {
  const { env } = setup();
  const upstream = vi.fn();
  vi.stubGlobal("fetch", upstream);
  await receiveOperationsReport(request(report()), env);
  await scheduleOperations(env);
  expect(upstream).not.toHaveBeenCalled();
});

it("persists a failed dispatch and does not retry every minute", async () => {
  const { env } = setup();
  const upstream = vi.fn(async () => new Response(null, { status: 403 }));
  vi.stubGlobal("fetch", upstream);
  await expect(scheduleOperations(env)).rejects.toThrow(
    "GitHub monitoring dispatch failed",
  );
  vi.setSystemTime(new Date(Date.now() + 60_000));
  await scheduleOperations(env);
  expect(upstream).toHaveBeenCalledOnce();
  const status = await operationsStatus(env);
  expect(status.status).toBe(503);
  expect((await status.json<any>()).scheduler.dispatchError).toBe(
    "github-dispatch-failed",
  );
});

it("fails closed when disabled or not authenticated", async () => {
  const { env, bucket } = setup();
  expect(
    (await receiveOperationsReport(request(report(), "wrong"), env)).status,
  ).toBe(401);
  expect(
    (
      await receiveOperationsReport(request(report()), {
        ...env,
        OPERATIONS_MONITOR_ENABLED: "false",
      })
    ).status,
  ).toBe(503);
  expect(bucket.values.size).toBe(0);
});

it("rejects incomplete, oversized, future and old reports", async () => {
  const { env } = setup();
  for (const body of [
    { ...report(), checks: [] },
    { ...report(), checkedAt: "2030-01-01T00:00:00Z" },
    { ...report(), checkedAt: "2026-10-30T11:00:00Z" },
    { ...report(), runId: "x" },
    { ...report(), checks: [null, ...report().checks.slice(1)] },
    { ...report(), checkedAt: "2026-10-30T12:00:00" },
    { ...report(), extra: "x".repeat(17000) },
  ]) {
    expect(
      (await receiveOperationsReport(request(body), env)).status,
    ).toBeGreaterThanOrEqual(400);
  }
});

it("notifies once per incident, keeps status unhealthy and recovers without erasing the incident", async () => {
  const { env, bucket } = setup();
  await bucket.put(
    "frames/frames.json",
    JSON.stringify({
      generatedAt: now,
      frames: [{ observedAt: "2026-10-30T11:10:00Z" }],
    }),
  );
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(null, { status: 204 })),
  );
  await scheduleOperations(env);
  const first = await (
    await receiveOperationsReport(
      request(report("1", { radar: "source-delayed" })),
      env,
    )
  ).json<any>();
  expect(first.shouldFail).toBe(true);
  expect(first.transition).toBe("opened");
  const repeat = await (
    await receiveOperationsReport(
      request(report("2", { radar: "source-delayed" })),
      env,
    )
  ).json<any>();
  expect(repeat.shouldFail).toBe(false);
  expect(repeat.incidentId).toBe(first.incidentId);
  const status = await operationsStatus(env);
  expect(status.status).toBe(503);
  const data = await status.json<any>();
  expect(data.monitoringActive).toBe(true);
  expect(data.radar.code).toBe("source-delayed");
  await bucket.put(
    "frames/frames.json",
    JSON.stringify({
      generatedAt: now,
      frames: [{ observedAt: "2026-10-30T11:50:00Z" }],
    }),
  );
  expect(
    (
      await (
        await receiveOperationsReport(request(report("3")), env)
      ).json<any>()
    ).transition,
  ).toBe("recovered");
  expect((await operationsStatus(env)).status).toBe(200);
  expect(
    (await (await operationsStatus(env)).json<any>()).lastIncident.resolvedAt,
  ).toBeDefined();
});

it("opens a new notification for changed failure signatures and a later recurrence", async () => {
  const { env } = setup();
  for (const [id, failures, notify] of [
    ["1", { radar: "source-delayed" }, true],
    ["2", { radar: "ingestion-stalled" }, true],
    ["3", {}, false],
    ["4", { radar: "source-delayed" }, true],
  ] as const) {
    const result = await (
      await receiveOperationsReport(request(report(id, failures)), env)
    ).json<any>();
    expect(result.shouldFail).toBe(notify);
  }
});

it("deduplicates racing reports and replays the same response after a lost acknowledgement", async () => {
  const { env } = setup();
  const results = await Promise.all(
    ["1", "2"].map(async (id) =>
      (
        await receiveOperationsReport(
          request(report(id, { web: "http-error" })),
          env,
        )
      ).json<any>(),
    ),
  );
  expect(results.filter((x) => x.shouldFail)).toHaveLength(1);
  const latest = results[1];
  expect(
    await (
      await receiveOperationsReport(
        request(report("2", { web: "http-error" })),
        env,
      )
    ).json<any>(),
  ).toEqual(latest);
});

it("detects missed scheduler ticks and stale probes, independent of radar freshness", async () => {
  const { env, bucket } = setup();
  await receiveOperationsReport(request(report()), env);
  await bucket.put(
    "monitoring/scheduler.json",
    JSON.stringify({ checkedAt: now }),
  );
  await bucket.put(
    "frames/frames.json",
    JSON.stringify({ generatedAt: now, frames: [{ observedAt: now }] }),
  );
  vi.setSystemTime(new Date(Date.now() + 11 * 60_000));
  let data = await (await operationsStatus(env)).json<any>();
  expect(data.scheduler.ok).toBe(false);
  expect(data.probe.ok).toBe(true);
  vi.setSystemTime(new Date(Date.now() + 25 * 60_000));
  data = await (await operationsStatus(env)).json<any>();
  expect(data.probe.ok).toBe(false);
  expect(data.monitoringActive).toBe(false);
});

it("does not present an observation as fresh merely because a manifest was republished", async () => {
  const { env, bucket } = setup();
  await receiveOperationsReport(request(report()), env);
  await bucket.put(
    "frames/frames.json",
    JSON.stringify({
      generatedAt: now,
      frames: [{ observedAt: "2026-10-30T10:00:00Z" }],
    }),
  );
  const status = await operationsStatus(env);
  expect(status.status).toBe(503);
  expect((await status.json<any>()).radar.ageMinutes).toBe(120);
});

it("does not let an older run overwrite the latest health result", async () => {
  const { env } = setup();
  await receiveOperationsReport(request(report("1")), env);
  vi.setSystemTime(new Date(Date.now() + 60_000));
  await receiveOperationsReport(request(report("2")), env);
  const older = { ...report("3", { web: "http-error" }), checkedAt: now };
  const result = await (
    await receiveOperationsReport(request(older), env)
  ).json<any>();
  expect(result.transition).toBe("superseded");
  expect(result.shouldFail).toBe(false);
  expect((await (await operationsStatus(env)).json<any>()).probe.runId).toBe(
    "2",
  );
});

it("uses token authentication, not browser CORS permission, for monitor reports", async () => {
  const { env } = setup();
  const fullEnv = {
    ...env,
    DMI_BASE_URL: "https://dmi.test",
    OPEN_METEO_BASE_URL: "https://model.test",
    ALLOWED_ORIGIN: "https://wetmap.pages.dev",
  };
  const context = { waitUntil: vi.fn() } as unknown as ExecutionContext;
  expect(
    (await worker.fetch(request(report(), "wrong"), fullEnv, context)).status,
  ).toBe(401);
  expect((await worker.fetch(request(report()), fullEnv, context)).status).toBe(
    200,
  );
  const push = new Request("https://api.test/api/v1/push/subscriptions", {
    method: "POST",
  });
  expect((await worker.fetch(push, fullEnv, context)).status).toBe(403);
});

it("keeps independent scheduled tasks alive when monitoring dispatch fails", async () => {
  const { env, bucket } = setup();
  await bucket.put(
    "frames/frames.json",
    JSON.stringify({ generatedAt: now, frames: [{ observedAt: now }] }),
  );
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(null, { status: 403 })),
  );
  const waits: Promise<unknown>[] = [];
  await worker.scheduled(
    {} as ScheduledController,
    {
      ...env,
      DMI_BASE_URL: "https://dmi.test",
      OPEN_METEO_BASE_URL: "https://model.test",
      ALLOWED_ORIGIN: "https://wetmap.pages.dev",
    },
    {
      waitUntil: (task: Promise<unknown>) => waits.push(task),
    } as unknown as ExecutionContext,
  );
  const results = await Promise.allSettled(waits);
  expect(results.map((result) => result.status)).toEqual([
    "fulfilled",
    "fulfilled",
    "rejected",
  ]);
});
