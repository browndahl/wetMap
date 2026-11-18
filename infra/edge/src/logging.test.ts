import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { logEvent } from "./logging";

beforeEach(() => {
  vi.spyOn(console, "log").mockImplementation(() => undefined);
  vi.spyOn(console, "warn").mockImplementation(() => undefined);
  vi.spyOn(console, "error").mockImplementation(() => undefined);
});
afterEach(() => vi.restoreAllMocks());

it("projects only approved source/codes/timing, not location, request or raw error fields", () => {
  logEvent("info", "forecast.provider.selected", {
    latitude: 56.16,
    longitude: 10.2,
    locationName: "private-sentinel",
    q: "private-sentinel",
    persistentKey: "private-sentinel",
    key: "private-sentinel",
    endpoint: "https://private.test/private-sentinel",
    error: new Error("private-sentinel"),
    provider: "dmi-edr",
    fallback: "none",
    dmiOutcome: "http-503",
    totalMs: 123.4,
  });
  expect(console.log).toHaveBeenCalledWith("forecast.provider.selected", {
    provider: "dmi-edr",
    fallback: "none",
    dmiOutcome: "http-503",
    totalMs: 123.4,
  });
});

it.each(["info", "warn", "error"] as const)(
  "keeps %s severity without dynamic fields",
  (level) => {
    logEvent(level, "forecast.upstream.failed");
    expect(
      level === "info"
        ? console.log
        : level === "warn"
          ? console.warn
          : console.error,
    ).toHaveBeenCalledWith("forecast.upstream.failed");
  },
);

it("drops injected or unknown string values and nonfinite/non-numeric timings", () => {
  logEvent("info", "forecast.provider.selected", {
    provider: "private-sentinel",
    source: "private-sentinel",
    fallback: "none\nprivate-sentinel",
    dmiOutcome: "http-503\nprivate-sentinel",
    totalMs: "private-sentinel",
    dmiMs: NaN,
    cacheMs: Infinity,
    kind: { nested: "private-sentinel" },
  });
  expect(console.log).toHaveBeenCalledWith("forecast.provider.selected");
});

it.each([503, "private-sentinel", NaN, Infinity, 99, 600])(
  "bounds HTTP failure code %s",
  (statusCode) => {
    logEvent("error", "push.send.failed", {
      statusCode,
      key: "private-sentinel",
    });
    expect(console.error).toHaveBeenCalledWith(
      "push.send.failed",
      ...(statusCode === 503 ? [{ statusCode: 503 }] : []),
    );
  },
);

it("never serializes an unregistered event value", () => {
  logEvent("error", "private-event-sentinel" as never, { totalMs: 1 });
  expect(console.error).toHaveBeenCalledWith("logging.invalid-event");
});

it("does not invoke getters or custom serialization and drops descriptor failures", () => {
  const accessor = vi.fn(() => "private-sentinel");
  const toJSON = vi.fn(() => ({ secret: "private-sentinel" }));
  const fields = { toJSON, nested: { secret: "private-sentinel" } };
  Object.defineProperty(fields, "provider", { get: accessor });
  logEvent("info", "forecast.provider.selected", fields);
  logEvent(
    "info",
    "forecast.provider.selected",
    new Proxy(
      {},
      {
        getOwnPropertyDescriptor() {
          throw new Error("private-sentinel");
        },
      },
    ),
  );
  expect(accessor).not.toHaveBeenCalled();
  expect(toJSON).not.toHaveBeenCalled();
  expect(console.log).toHaveBeenCalledTimes(2);
  expect(console.log).toHaveBeenCalledWith("forecast.provider.selected");
});
