import webpush from "web-push";
import { logEvent } from "./logging";

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

export interface StoredSubscription {
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
  thresholdsDbz?: [number, number, number];
  alertPolicy?: { minimumReflectivityDbz?: number };
  frames: Array<{
    leadMinutes: number;
    predictedAt: string;
    intensity: string;
    confidence?: number;
    validationSamples?: number | null;
    verificationCsi?: number | null;
    skillOverPersistence?: number | null;
    alertEligible?: boolean;
  }>;
}

export interface RainRiskHit {
  leadMinutes: number;
  predictedAt: string;
  intensity: number;
  kind: "observed" | "forecast";
}

const prefix = "push/subscriptions/";
const scanStateKey = "push/scan-state.json";
const subscriptionsPerInvocation = 40;
const maximumRiskAgeMs = 20 * 60_000;
const maximumObservedAlertAgeMs = 15 * 60_000;
const maximumNotificationLatenessMs = 2 * 60_000;
const observedNotificationLifetimeMs = 5 * 60_000;
// Bucket 3 begins at the calibrated boundary declared by the worker.
const minimumAlertIntensity = 3;

class PushBodyTooLarge extends Error {}

async function readPushBody(
  request: Request,
): Promise<Record<string, unknown>> {
  if (Number(request.headers.get("Content-Length") ?? 0) > 8_192)
    throw new PushBodyTooLarge();
  const reader = request.body?.getReader();
  if (!reader) throw new SyntaxError("Missing JSON object");
  const chunks: Uint8Array[] = [];
  let size = 0;
  for (;;) {
    const next = await reader.read();
    if (next.done) break;
    size += next.value.length;
    if (size > 8_192) {
      await reader.cancel().catch(() => undefined);
      throw new PushBodyTooLarge();
    }
    chunks.push(next.value);
  }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.length;
  }
  const body: unknown = JSON.parse(new TextDecoder().decode(bytes));
  if (!body || typeof body !== "object" || Array.isArray(body))
    throw new SyntaxError("Expected JSON object");
  return body as Record<string, unknown>;
}

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
    body = await readPushBody(request);
  } catch (error) {
    if (error instanceof PushBodyTooLarge)
      return Response.json(
        { title: "Payload too large", status: 413 },
        { status: 413 },
      );
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
  const latitude = body.latitude;
  const longitude = body.longitude;
  const locationName = (
    typeof body.locationName === "string" ? body.locationName : ""
  )
    .trim()
    .slice(0, 80);
  const locale = body.locale === "en" ? "en" : "da";
  if (
    !subscription ||
    !validEndpoint(subscription.endpoint) ||
    !validBase64Url(subscription.keys?.p256dh, 80) ||
    !validBase64Url(subscription.keys?.auth, 16) ||
    (subscription.expirationTime != null &&
      (typeof subscription.expirationTime !== "number" ||
        !Number.isFinite(subscription.expirationTime) ||
        subscription.expirationTime < 0)) ||
    typeof latitude !== "number" ||
    !Number.isFinite(latitude) ||
    latitude < 54.4 ||
    latitude > 58 ||
    typeof longitude !== "number" ||
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
    endpoint = (await readPushBody(request)).endpoint;
  } catch (error) {
    if (error instanceof PushBodyTooLarge)
      return Response.json(
        { title: "Payload too large", status: 413 },
        { status: 413 },
      );
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
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < bytes.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

type RiskFrame = RiskManifest["frames"][number];
const decodedRisk = new WeakMap<
  RiskManifest,
  {
    frames: WeakMap<RiskFrame, { value: string; bytes: Uint8Array }>;
    byteCount: number;
    entryCount: number;
  }
>();

function frameBytes(risk: RiskManifest, frame: RiskFrame): Uint8Array {
  let cache = decodedRisk.get(risk);
  if (!cache) {
    cache = { frames: new WeakMap(), byteCount: 0, entryCount: 0 };
    decodedRisk.set(risk, cache);
  }
  const previous = cache.frames.get(frame);
  if (previous && previous.value === frame.intensity) return previous.bytes;
  const bytes = decodeBase64(frame.intensity);
  const nextBytes =
    cache.byteCount - (previous?.bytes.length ?? 0) + bytes.length;
  // Per-manifest weather-only scratch data, never coordinates/subscriptions.
  // Weak ownership and explicit budgets prevent an isolate cache from growing.
  if (nextBytes <= 128 * 1024 && (previous || cache.entryCount < 13)) {
    cache.frames.set(frame, { value: frame.intensity, bytes });
    cache.byteCount = nextBytes;
    if (!previous) cache.entryCount++;
  }
  return bytes;
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
  now = Date.now(),
): RainRiskHit | null {
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
  const observedAt = Date.parse(risk.basedOnObservedAt);
  for (const frame of risk.frames) {
    if (frame.alertEligible !== true) continue;
    const predictedAt = Date.parse(frame.predictedAt);
    if (!Number.isFinite(predictedAt)) continue;
    const kind = frame.leadMinutes === 0 ? "observed" : "forecast";
    if (
      (kind === "observed" &&
        (!Number.isFinite(observedAt) ||
          now - observedAt > maximumObservedAlertAgeMs)) ||
      (kind === "forecast" && predictedAt < now)
    )
      continue;
    const intensity = frameBytes(risk, frame)[index] ?? 0;
    if (frame.alertEligible === true && intensity >= minimumAlertIntensity)
      return {
        leadMinutes: frame.leadMinutes,
        predictedAt: frame.predictedAt,
        intensity,
        kind,
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

function notificationExpiry(hit: RainRiskHit, sentAt: number): number {
  if (hit.kind === "observed") return sentAt + observedNotificationLifetimeMs;
  return Math.max(
    sentAt + 60_000,
    Date.parse(hit.predictedAt) + maximumNotificationLatenessMs,
  );
}

const pushTimeFormatters: Partial<
  Record<StoredSubscription["locale"], Intl.DateTimeFormat>
> = {};

function forecastDisplayTime(
  locale: StoredSubscription["locale"],
  time: string,
) {
  const language = locale === "da" ? "da" : "en";
  const formatter = (pushTimeFormatters[language] ??= new Intl.DateTimeFormat(
    language === "da" ? "da-DK" : "en-GB",
    { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Copenhagen" },
  ));
  return formatter.format(new Date(time));
}

export function notificationPayload(
  subscription: StoredSubscription,
  hit: RainRiskHit,
  sentAt = Date.now(),
) {
  const observed = hit.kind === "observed";
  const time = observed
    ? ""
    : forecastDisplayTime(subscription.locale, hit.predictedAt);
  const intensity =
    subscription.locale === "da"
      ? ["", "mulig", "meget svag", "let"][hit.intensity]
      : ["", "possible", "very light", "light"][hit.intensity];
  return JSON.stringify({
    title:
      subscription.locale === "da"
        ? observed
          ? "Regn registreret"
          : "Regn på vej"
        : observed
          ? "Rain detected"
          : "Rain on the way",
    body:
      subscription.locale === "da"
        ? observed
          ? `DMI-radar har registreret ${intensity} regn ved ${subscription.locationName}.`
          : `${intensity} regn ventes ved ${subscription.locationName} omkring ${time}.`
        : observed
          ? `DMI radar has detected ${intensity} rain near ${subscription.locationName}.`
          : `${intensity} rain is expected near ${subscription.locationName} around ${time}.`,
    tag: "wetmap-rain",
    url: "/",
    kind: hit.kind,
    sentAt: new Date(sentAt).toISOString(),
    predictedAt: hit.predictedAt,
    expiresAt: new Date(notificationExpiry(hit, sentAt)).toISOString(),
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
    !Number.isFinite(Date.parse(risk.basedOnObservedAt)) ||
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
        const sentAt = Date.now();
        const expiresAt = notificationExpiry(hit, sentAt);
        await webpush.sendNotification(
          stored.subscription as webpush.PushSubscription,
          notificationPayload(stored, hit, sentAt),
          {
            TTL: Math.max(60, Math.ceil((expiresAt - sentAt) / 1_000)),
            urgency: "high",
          },
        );
        stored.activeRainEvent = true;
        stored.lastAlertedAt = new Date().toISOString();
        stored.updatedAt = stored.lastAlertedAt;
        await env.RADAR.put(key, JSON.stringify(stored));
        logEvent("info", "push.send.succeeded", {
          kind: hit.kind,
          leadMinutes: hit.leadMinutes,
          etaMinutes: Math.round(
            (Date.parse(hit.predictedAt) - sentAt) / 60_000,
          ),
          radarAgeMinutes: Math.round(
            (sentAt - Date.parse(risk.basedOnObservedAt)) / 60_000,
          ),
        });
      } catch (error) {
        const statusCode = (
          error as { statusCode?: unknown } | null | undefined
        )?.statusCode;
        if (statusCode === 404 || statusCode === 410) {
          await env.RADAR.delete(key);
          return;
        }
        logEvent("error", "push.send.failed", { statusCode });
      }
    }),
  );
}
