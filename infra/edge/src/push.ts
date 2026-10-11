import webpush from "web-push";

interface PushSubscriptionPayload {
  endpoint: string;
  expirationTime?: number | null;
  keys: { auth: string; p256dh: string };
}

export interface PushEnv {
  RADAR: R2Bucket;
  VAPID_PUBLIC_KEY?: string;
  VAPID_PRIVATE_KEY?: string;
  VAPID_SUBJECT?: string;
}

interface StoredSubscription {
  schemaVersion: 1;
  subscription: PushSubscriptionPayload;
  latitude: number;
  longitude: number;
  locationName: string;
  locale: "da" | "en";
  createdAt: string;
  updatedAt: string;
  activeRainEvent: boolean;
  lastAlertedAt?: string;
}

interface RiskManifest {
  schemaVersion: 1;
  generatedAt: string;
  basedOnObservedAt: string;
  bounds: [number, number, number, number];
  width: number;
  height: number;
  encoding: "uint8-base64";
  frames: Array<{
    leadMinutes: number;
    predictedAt: string;
    intensity: string;
  }>;
}

const prefix = "push/subscriptions/";
const scanStateKey = "push/scan-state.json";
const subscriptionsPerInvocation = 40;
const maximumRiskAgeMs = 30 * 60_000;

const validBase64Url = (value: unknown, minimumLength: number) =>
  typeof value === "string" &&
  value.length >= minimumLength &&
  value.length <= 256 &&
  /^[A-Za-z0-9_-]+={0,2}$/.test(value);

function validEndpoint(value: unknown): value is string {
  if (typeof value !== "string" || value.length > 2_048) return false;
  try {
    return new URL(value).protocol === "https:";
  } catch {
    return false;
  }
}

async function keyForEndpoint(endpoint: string): Promise<string> {
  const bytes = new TextEncoder().encode(endpoint);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return `${prefix}${Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("")}.json`;
}

export function pushConfig(env: PushEnv): Response {
  return Response.json(
    {
      available: Boolean(env.VAPID_PUBLIC_KEY && env.VAPID_PRIVATE_KEY),
      publicKey: env.VAPID_PUBLIC_KEY ?? null,
    },
    {
      headers: {
        "Cache-Control": "public,max-age=300",
        "Content-Type": "application/json; charset=utf-8",
      },
    },
  );
}

export async function savePushSubscription(
  request: Request,
  env: PushEnv,
): Promise<Response> {
  if (!env.VAPID_PUBLIC_KEY || !env.VAPID_PRIVATE_KEY)
    return Response.json(
      { title: "Push unavailable", status: 503 },
      { status: 503 },
    );
  if (Number(request.headers.get("Content-Length") ?? 0) > 8_192)
    return Response.json(
      { title: "Payload too large", status: 413 },
      { status: 413 },
    );

  let body: Record<string, unknown>;
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    return Response.json(
      { title: "Invalid subscription", status: 400 },
      { status: 400 },
    );
  }
  const subscription = body.subscription as
    | {
        endpoint?: string;
        expirationTime?: number | null;
        keys?: { auth?: string; p256dh?: string };
      }
    | undefined;
  const latitude = Number(body.latitude);
  const longitude = Number(body.longitude);
  const locationName = String(body.locationName ?? "")
    .trim()
    .slice(0, 80);
  const locale = body.locale === "en" ? "en" : "da";
  if (
    !subscription ||
    !validEndpoint(subscription.endpoint) ||
    !validBase64Url(subscription.keys?.p256dh, 80) ||
    !validBase64Url(subscription.keys?.auth, 16) ||
    !Number.isFinite(latitude) ||
    latitude < 54.4 ||
    latitude > 58 ||
    !Number.isFinite(longitude) ||
    longitude < 7.5 ||
    longitude > 15.5 ||
    !locationName
  )
    return Response.json(
      { title: "Invalid subscription", status: 400 },
      { status: 400 },
    );

  const key = await keyForEndpoint(subscription.endpoint);
  const existing = await env.RADAR.get(key);
  let previous: StoredSubscription | undefined;
  try {
    previous = await existing?.json<StoredSubscription>();
  } catch {
    previous = undefined;
  }
  const now = new Date().toISOString();
  const stored: StoredSubscription = {
    schemaVersion: 1,
    subscription: {
      endpoint: subscription.endpoint,
      expirationTime: subscription.expirationTime ?? null,
      keys: {
        auth: subscription.keys!.auth!,
        p256dh: subscription.keys!.p256dh!,
      },
    },
    latitude: Number(latitude.toFixed(2)),
    longitude: Number(longitude.toFixed(2)),
    locationName,
    locale,
    createdAt: previous?.createdAt ?? now,
    updatedAt: now,
    activeRainEvent: previous?.activeRainEvent ?? false,
    lastAlertedAt: previous?.lastAlertedAt,
  };
  await env.RADAR.put(key, JSON.stringify(stored), {
    httpMetadata: { contentType: "application/json", cacheControl: "no-store" },
  });
  return Response.json({ subscribed: true }, { status: previous ? 200 : 201 });
}

export async function deletePushSubscription(
  request: Request,
  env: PushEnv,
): Promise<Response> {
  let endpoint: unknown;
  try {
    endpoint = ((await request.json()) as { endpoint?: unknown }).endpoint;
  } catch {
    endpoint = undefined;
  }
  if (!validEndpoint(endpoint))
    return Response.json(
      { title: "Invalid subscription", status: 400 },
      { status: 400 },
    );
  await env.RADAR.delete(await keyForEndpoint(endpoint));
  return new Response(null, { status: 204 });
}

function decodeBase64(value: string): Uint8Array {
  const binary = atob(value);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

function mercatorY(latitude: number): number {
  const limited = Math.max(-85.051129, Math.min(85.051129, latitude));
  const radians = (limited * Math.PI) / 180;
  return Math.log(Math.tan(Math.PI / 4 + radians / 2));
}

export function riskAtLocation(
  risk: RiskManifest,
  latitude: number,
  longitude: number,
): { leadMinutes: number; predictedAt: string; intensity: number } | null {
  const [west, south, east, north] = risk.bounds;
  if (
    longitude < west ||
    longitude > east ||
    latitude < south ||
    latitude > north ||
    risk.width < 1 ||
    risk.height < 1
  )
    return null;
  const x = Math.min(
    risk.width - 1,
    Math.max(0, Math.floor(((longitude - west) / (east - west)) * risk.width)),
  );
  const northY = mercatorY(north);
  const southY = mercatorY(south);
  const y = Math.min(
    risk.height - 1,
    Math.max(
      0,
      Math.floor(
        ((northY - mercatorY(latitude)) / (northY - southY)) * risk.height,
      ),
    ),
  );
  const index = y * risk.width + x;
  for (const frame of risk.frames) {
    const intensity = decodeBase64(frame.intensity)[index] ?? 0;
    if (intensity > 0)
      return {
        leadMinutes: frame.leadMinutes,
        predictedAt: frame.predictedAt,
        intensity,
      };
  }
  return null;
}

async function listSubscriptionKeys(bucket: R2Bucket): Promise<string[]> {
  let cursor: string | undefined;
  try {
    const state = await bucket.get(scanStateKey);
    const payload = await state?.json<{ cursor?: string | null }>();
    cursor = payload?.cursor ?? undefined;
  } catch {
    cursor = undefined;
  }
  let page: R2Objects;
  try {
    page = await bucket.list({
      prefix,
      cursor,
      limit: subscriptionsPerInvocation,
    });
  } catch {
    page = await bucket.list({ prefix, limit: subscriptionsPerInvocation });
  }
  await bucket.put(
    scanStateKey,
    JSON.stringify({ cursor: page.truncated ? page.cursor : null }),
  );
  return page.objects.map((object) => object.key);
}

function notificationPayload(
  subscription: StoredSubscription,
  hit: NonNullable<ReturnType<typeof riskAtLocation>>,
) {
  const time = new Intl.DateTimeFormat(
    subscription.locale === "da" ? "da-DK" : "en-GB",
    { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Copenhagen" },
  ).format(new Date(hit.predictedAt));
  const intensity =
    subscription.locale === "da"
      ? ["", "let", "moderat", "kraftig"][hit.intensity]
      : ["", "light", "moderate", "heavy"][hit.intensity];
  return JSON.stringify({
    title: subscription.locale === "da" ? "Regn på vej" : "Rain on the way",
    body:
      subscription.locale === "da"
        ? `${intensity} regn ventes ved ${subscription.locationName} omkring ${time}.`
        : `${intensity} rain is expected near ${subscription.locationName} around ${time}.`,
    tag: "wetmap-rain",
    url: "/",
  });
}

export async function sendRainAlerts(env: PushEnv): Promise<void> {
  if (!env.VAPID_PUBLIC_KEY || !env.VAPID_PRIVATE_KEY) return;
  const riskObject = await env.RADAR.get("nowcast/risk.json");
  if (!riskObject) return;
  let risk: RiskManifest;
  try {
    risk = await riskObject.json<RiskManifest>();
  } catch {
    return;
  }
  if (
    risk.encoding !== "uint8-base64" ||
    Date.now() - Date.parse(risk.basedOnObservedAt) > maximumRiskAgeMs
  )
    return;

  webpush.setVapidDetails(
    env.VAPID_SUBJECT ?? "https://wetmap.pages.dev",
    env.VAPID_PUBLIC_KEY,
    env.VAPID_PRIVATE_KEY,
  );
  const keys = await listSubscriptionKeys(env.RADAR);
  await Promise.all(
    keys.map(async (key) => {
      const object = await env.RADAR.get(key);
      if (!object) return;
      let stored: StoredSubscription;
      try {
        stored = await object.json<StoredSubscription>();
      } catch {
        await env.RADAR.delete(key);
        return;
      }
      const hit = riskAtLocation(risk, stored.latitude, stored.longitude);
      if (!hit) {
        if (stored.activeRainEvent) {
          stored.activeRainEvent = false;
          stored.updatedAt = new Date().toISOString();
          await env.RADAR.put(key, JSON.stringify(stored));
        }
        return;
      }
      if (stored.activeRainEvent) return;
      try {
        await webpush.sendNotification(
          stored.subscription as webpush.PushSubscription,
          notificationPayload(stored, hit),
          { TTL: Math.max(60, hit.leadMinutes * 60), urgency: "high" },
        );
        stored.activeRainEvent = true;
        stored.lastAlertedAt = new Date().toISOString();
        stored.updatedAt = stored.lastAlertedAt;
        await env.RADAR.put(key, JSON.stringify(stored));
      } catch (error) {
        const statusCode = (error as { statusCode?: number }).statusCode;
        if (statusCode === 404 || statusCode === 410) {
          await env.RADAR.delete(key);
          return;
        }
        console.error("push.send.failed", { statusCode, key });
      }
    }),
  );
}
