import { expect, it, vi } from "vitest";
import { savePushSubscription, deletePushSubscription } from "./push";

const valid = {
  subscription: {
    endpoint: "https://push.example.test/token",
    keys: { auth: "a".repeat(22), p256dh: "b".repeat(88) },
  },
  latitude: 56.16291,
  longitude: 10.20393,
  locationName: "Aarhus",
  locale: "da",
};
function setup() {
  const put = vi.fn(async (_key: string, _value: string) => undefined);
  const remove = vi.fn(async (_key: string) => undefined);
  const env = {
    RADAR: {
      get: vi.fn(async () => null),
      put,
      delete: remove,
    } as unknown as R2Bucket,
    VAPID_PUBLIC_KEY: "configured-test-key",
    VAPID_PRIVATE_KEY: "configured-test-key",
  };
  return { env, put, remove };
}
const request = (body: unknown) =>
  new Request("https://api.test/api/v1/push/subscriptions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

it.each([null, true, 12, [], "not-an-object"])(
  "rejects non-object JSON without throwing or writing: %j",
  async (body) => {
    const { env, put } = setup();
    expect((await savePushSubscription(request(body), env)).status).toBe(400);
    expect(put).not.toHaveBeenCalled();
  },
);

it("bounds actual body bytes even without Content-Length", async () => {
  const { env, put } = setup();
  const input = new Request("https://api.test/api/v1/push/subscriptions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: " ".repeat(9000) + JSON.stringify(valid),
  });
  expect(input.headers.get("Content-Length")).toBeNull();
  expect((await savePushSubscription(input, env)).status).toBe(413);
  expect(put).not.toHaveBeenCalled();
});

it.each([
  { latitude: "56.16" },
  { locationName: { name: "Aarhus" } },
  {
    subscription: {
      ...valid.subscription,
      expirationTime: { unexpected: "object" },
    },
  },
])("rejects field type violations %j", async (changes) => {
  const { env, put } = setup();
  expect(
    (await savePushSubscription(request({ ...valid, ...changes }), env)).status,
  ).toBe(400);
  expect(put).not.toHaveBeenCalled();
});

it("keeps accepted fields and rounded coordinates unchanged", async () => {
  const { env, put } = setup();
  expect((await savePushSubscription(request(valid), env)).status).toBe(201);
  const saved = JSON.parse(put.mock.calls[0][1] as string);
  expect(saved.latitude).toBe(56.16);
  expect(saved.longitude).toBe(10.2);
  expect(saved.subscription).toMatchObject(valid.subscription);
});

it("bounds unsubscribe bodies without deleting data on oversized input", async () => {
  const { env, remove } = setup();
  const input = new Request("https://api.test/api/v1/push/subscriptions", {
    method: "DELETE",
    body:
      " ".repeat(9000) +
      JSON.stringify({ endpoint: valid.subscription.endpoint }),
  });
  expect((await deletePushSubscription(input, env)).status).toBe(413);
  expect(remove).not.toHaveBeenCalled();
});
