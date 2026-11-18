import { afterEach, expect, it, vi } from "vitest";
import webpush from "web-push";
import { sendRainAlerts } from "./push";

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

it.each([
  { statusCode: 503, message: "private-push-sentinel" },
  null,
  "private-push-sentinel",
])(
  "logs a push failure without subscription details even for %j",
  async (failure) => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-11-18T12:00:00Z"));
    vi.spyOn(webpush, "setVapidDetails").mockImplementation(() => undefined);
    vi.spyOn(webpush, "sendNotification").mockRejectedValue(failure);
    const error = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    const risk = {
      encoding: "uint8-base64",
      generatedAt: "2026-11-18T12:00:00Z",
      basedOnObservedAt: "2026-11-18T11:55:00Z",
      width: 1,
      height: 1,
      bounds: [10, 55, 12, 57],
      frames: [
        {
          leadMinutes: 5,
          predictedAt: "2026-11-18T12:00:00Z",
          alertEligible: true,
          intensity: btoa(String.fromCharCode(3)),
        },
      ],
    };
    const key = "push/subscriptions/private-derived-key-sentinel.json";
    const subscription = {
      latitude: 56,
      longitude: 11,
      activeRainEvent: false,
      locale: "en",
      locationName: "private-place-sentinel",
      subscription: { endpoint: "https://push.test/private-endpoint-sentinel" },
    };
    const bucket = {
      get: vi.fn(async (name: string) =>
        name === "nowcast/risk.json"
          ? { json: async () => risk }
          : name === key
            ? { json: async () => subscription }
            : null,
      ),
      list: vi.fn(async () => ({ objects: [{ key }], truncated: false })),
      put: vi.fn(),
      delete: vi.fn(),
    };
    await sendRainAlerts({
      RADAR: bucket as unknown as R2Bucket,
      VAPID_PUBLIC_KEY: "test",
      VAPID_PRIVATE_KEY: "test",
    });
    expect(webpush.sendNotification).toHaveBeenCalledOnce();
    expect(error).toHaveBeenCalledWith(
      "push.send.failed",
      ...(failure && typeof failure === "object" ? [{ statusCode: 503 }] : []),
    );
    expect(bucket.delete).not.toHaveBeenCalled();
  },
);
