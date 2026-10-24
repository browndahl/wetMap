import { beforeEach, expect, it, vi } from "vitest";
import pushWorkerScript from "../public/push-sw.js?raw";

type PushEvent = {
  data?: { json: () => Record<string, unknown> };
  waitUntil: (promise: Promise<unknown>) => void;
};

const listeners = new Map<string, (event: PushEvent) => void>();
const showNotification = vi.fn(async () => undefined);
const workerScope = {
  addEventListener: (type: string, listener: (event: PushEvent) => void) =>
    listeners.set(type, listener),
  registration: { showNotification },
  location: { origin: "https://wetmap.pages.dev" },
  clients: {
    matchAll: vi.fn(async () => []),
    openWindow: vi.fn(async () => undefined),
  },
};

new Function("self", pushWorkerScript)(workerScope);

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-21T20:20:00Z"));
  showNotification.mockClear();
});

it("discards a delayed push before showing an operating-system notification", () => {
  const waitUntil = vi.fn();

  listeners.get("push")?.({
    data: {
      json: () => ({
        title: "Rain on the way",
        expiresAt: "2026-10-21T20:19:59Z",
      }),
    },
    waitUntil,
  });

  expect(waitUntil).not.toHaveBeenCalled();
  expect(showNotification).not.toHaveBeenCalled();
});

it("fails closed for a legacy push without an expiry", () => {
  const waitUntil = vi.fn();

  listeners.get("push")?.({
    data: { json: () => ({ title: "Rain on the way" }) },
    waitUntil,
  });

  expect(waitUntil).not.toHaveBeenCalled();
  expect(showNotification).not.toHaveBeenCalled();
});

it("shows a push that is still timely", async () => {
  let pending: Promise<unknown> | undefined;

  listeners.get("push")?.({
    data: {
      json: () => ({
        title: "Rain on the way",
        body: "Light rain is expected near Aarhus.",
        expiresAt: "2026-10-21T20:22:00Z",
      }),
    },
    waitUntil: (promise) => {
      pending = promise;
    },
  });
  await pending;

  expect(showNotification).toHaveBeenCalledWith(
    "Rain on the way",
    expect.objectContaining({
      body: "Light rain is expected near Aarhus.",
      icon: "/pwa-192.png",
      badge: "/pwa-192.png",
    }),
  );
});
