import {
  deletePushSubscription,
  pushConfig,
  savePushSubscription,
  sendRainAlerts,
} from "./push";

interface Env {
  RADAR: R2Bucket;
  DMI_BASE_URL: string;
  OPEN_METEO_BASE_URL: string;
  GEOCODER_BASE_URL?: string;
  ALLOWED_ORIGIN: string;
  GITHUB_DISPATCH_TOKEN?: string;
  GITHUB_REPOSITORY?: string;
  GITHUB_RADAR_WORKFLOW?: string;
  GITHUB_REF?: string;
  VAPID_PUBLIC_KEY?: string;
  VAPID_PRIVATE_KEY?: string;
  VAPID_SUBJECT?: string;
}

const attribution = "Baseret på data fra DMI og efterfølgende bearbejdet";
const attributionHeader = "Based on DMI data and subsequently processed";
const jsonHeaders = { "Content-Type": "application/json; charset=utf-8" };
const forecastCacheSeconds = 10 * 60;
const forecastStaleSeconds = 6 * 60 * 60;
const precipitationCacheSeconds = 5 * 60;
const precipitationStaleSeconds = 30 * 60;
const radarDispatchAgeMs = 20 * 60 * 1000;
const locationCacheSeconds = 24 * 60 * 60;
const reverseLocationCacheSeconds = 7 * 24 * 60 * 60;
const dmiPrimaryHeadStartMs = 1_500;

type WeatherProvider = "dmi-edr" | "open-meteo-dmi";

interface RequestTelemetry {
  provider?: WeatherProvider;
  fallback?: "none" | "open-meteo" | "stale";
  cacheMs?: number;
  pointCacheMs?: number;
  r2Ms?: number;
  dmiMs?: number;
  dmiOutcome?: string;
  openMeteoMs?: number;
  totalMs?: number;
}

function elapsed(startedAt: number): number {
  return Math.round((performance.now() - startedAt) * 10) / 10;
}

function dmiOutcome(error: unknown): string {
  if (error instanceof DOMException && error.name === "TimeoutError")
    return "timeout";
  const message = error instanceof Error ? error.message : String(error);
  const httpStatus = /DMI EDR returned (\d{3})/.exec(message)?.[1];
  return httpStatus ? `http-${httpStatus}` : "error";
}

function telemetryHeaders(telemetry: RequestTelemetry): HeadersInit {
  const timings = [
    ["cache", telemetry.cacheMs],
    ["point_cache", telemetry.pointCacheMs],
    ["r2", telemetry.r2Ms],
    ["dmi", telemetry.dmiMs],
    ["openmeteo", telemetry.openMeteoMs],
    ["total", telemetry.totalMs],
  ]
    .filter((entry): entry is [string, number] => entry[1] !== undefined)
    .map(([name, duration]) => `${name};dur=${duration.toFixed(1)}`)
    .join(", ");
  return {
    ...(timings ? { "Server-Timing": timings } : {}),
    ...(telemetry.provider ? { "X-WetMap-Provider": telemetry.provider } : {}),
    ...(telemetry.fallback ? { "X-WetMap-Fallback": telemetry.fallback } : {}),
    ...(telemetry.dmiOutcome
      ? { "X-WetMap-DMI-Outcome": telemetry.dmiOutcome }
      : {}),
    "Timing-Allow-Origin": "*",
  };
}

async function dmiPrimaryWithFallback<T>(
  dmi: () => Promise<T>,
  openMeteo: () => Promise<T>,
): Promise<{
  payload: T;
  telemetry: RequestTelemetry;
  backgroundDmi?: Promise<T>;
}> {
  const telemetry: RequestTelemetry = {};
  let dmiSettled = false;
  const dmiStartedAt = performance.now();
  const dmiPromise = dmi()
    .then((payload) => {
      telemetry.dmiMs = elapsed(dmiStartedAt);
      telemetry.dmiOutcome = "success";
      return { payload, provider: "dmi-edr" as const };
    })
    .catch((error: unknown) => {
      telemetry.dmiMs = elapsed(dmiStartedAt);
      telemetry.dmiOutcome = dmiOutcome(error);
      throw error;
    })
    .finally(() => {
      dmiSettled = true;
    });
  let headStartTimer: ReturnType<typeof setTimeout>;
  const headStart = new Promise<null>((resolve) => {
    headStartTimer = setTimeout(() => resolve(null), dmiPrimaryHeadStartMs);
  });
  const primary = await Promise.race([
    dmiPromise.then((result) => result as typeof result | null),
    headStart,
  ]).catch(() => null);
  clearTimeout(headStartTimer!);
  if (primary) {
    telemetry.provider = primary.provider;
    telemetry.fallback = "none";
    return { payload: primary.payload, telemetry };
  }

  const openMeteoStartedAt = performance.now();
  const openMeteoPromise = openMeteo()
    .then((payload) => {
      telemetry.openMeteoMs = elapsed(openMeteoStartedAt);
      return { payload, provider: "open-meteo-dmi" as const };
    })
    .catch((error: unknown) => {
      telemetry.openMeteoMs = elapsed(openMeteoStartedAt);
      throw error;
    });
  const selected = await Promise.any([dmiPromise, openMeteoPromise]);
  telemetry.provider = selected.provider;
  telemetry.fallback =
    selected.provider === "open-meteo-dmi" ? "open-meteo" : "none";
  const backgroundDmi =
    selected.provider === "open-meteo-dmi" && !dmiSettled
      ? dmiPromise.then((result) => result.payload)
      : undefined;
  if (telemetry.dmiMs === undefined) {
    telemetry.dmiMs = elapsed(dmiStartedAt);
    telemetry.dmiOutcome = "pending";
  }
  return { payload: selected.payload, telemetry, backgroundDmi };
}

interface PhotonFeature {
  geometry?: { coordinates?: unknown[] };
  properties?: {
    osm_type?: string;
    osm_id?: string | number;
    type?: string;
    name?: string;
    street?: string;
    housenumber?: string;
    postcode?: string;
    locality?: string;
    district?: string;
    city?: string;
    state?: string;
    countrycode?: string;
  };
}

interface LocationResult {
  id: string;
  name: string;
  context: string;
  latitude: number;
  longitude: number;
  type: "address" | "place";
}

interface ForecastPoint {
  step: string;
  temperatureC: number | null;
  precipitationKgM2: number | null;
  windSpeedMs: number | null;
  cloudCoverPercent: number | null;
}

interface ForecastPayload {
  latitude: number;
  longitude: number;
  fetchedAt: string;
  attribution: typeof attribution;
  source: "dmi-edr" | "open-meteo-dmi";
  model: "DMI HARMONIE AROME";
  points: ForecastPoint[];
}

type RainIntensity = "none" | "trace" | "light" | "moderate" | "heavy";
type RainPointSource = "radar-nowcast" | "harmonie";

interface RainForecastPoint {
  startsAt: string;
  endsAt: string;
  precipitationMm: number;
  intensity: RainIntensity;
  source?: RainPointSource;
  reflectivityDbz?: number | null;
  confidence?: number | null;
}

interface RainNextHourPayload {
  latitude: number;
  longitude: number;
  fetchedAt: string;
  attribution: typeof attribution;
  source: "dmi-edr" | "open-meteo-dmi" | "dmi-radar-nowcast-harmonie";
  model: "DMI HARMONIE AROME";
  displayResolutionMinutes: 15;
  sourceResolutionMinutes: 60;
  isInterpolated: true;
  basedOnObservedAt?: string;
  radarBasedUntil?: string;
  points: RainForecastPoint[];
}

interface PointRiskMetadata {
  schemaVersion: 1;
  generatedAt: string;
  basedOnObservedAt: string;
  method:
    | "adaptive-optical-flow-persistence"
    | "dense-optical-flow-extrapolation";
  bounds: [number, number, number, number];
  width: number;
  height: number;
  frameCount: number;
  encoding: "pixel-major-uint8-dbz-plus-32";
  dataKey?: string;
  neighborhoodRadiusPixels: number;
  frames: Array<{
    leadMinutes: number;
    predictedAt: string;
    confidence: number;
    forecastMethod?: "optical-flow" | "persistence";
    validationSamples?: number;
  }>;
}

interface RadarPointSample {
  leadMinutes: number;
  predictedAt: string;
  confidence: number;
  forecastMethod?: "optical-flow" | "persistence";
  validationSamples?: number;
  reflectivityDbz: number | null;
}

function cors(origin: string, env: Env): HeadersInit {
  const allowedOrigins = env.ALLOWED_ORIGIN.split(",").map((value) =>
    value.trim(),
  );
  let isPagesPreview = false;
  try {
    const parsed = new URL(origin);
    isPagesPreview =
      parsed.protocol === "https:" &&
      (parsed.hostname.endsWith(".wetmap.pages.dev") ||
        parsed.hostname.endsWith(".wetmap-staging.pages.dev"));
  } catch {
    isPagesPreview = false;
  }
  return allowedOrigins.includes(origin) || isPagesPreview
    ? {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Expose-Headers":
          "Server-Timing,X-WetMap-Provider,X-WetMap-Fallback,X-WetMap-DMI-Outcome,X-WetMap-Cache,X-WetMap-Point-Cache",
        Vary: "Origin",
      }
    : {};
}

function problem(status: number, title: string, detail: string): Response {
  return Response.json(
    { type: "about:blank", title, status, detail },
    { status, headers: { "Content-Type": "application/problem+json" } },
  );
}

function coordinate(value: string | null): number | null {
  if (value === null || value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function normalizeLocation(feature: PhotonFeature): LocationResult | null {
  const properties = feature.properties;
  const coordinates = feature.geometry?.coordinates;
  const longitude = Number(coordinates?.[0]);
  const latitude = Number(coordinates?.[1]);
  if (
    !properties ||
    properties.countrycode?.toUpperCase() !== "DK" ||
    !Number.isFinite(latitude) ||
    !Number.isFinite(longitude)
  )
    return null;

  const streetAddress = [properties.street, properties.housenumber]
    .filter(Boolean)
    .join(" ");
  const name = properties.name?.trim() || streetAddress;
  if (!name) return null;
  const context = Array.from(
    new Set(
      [
        properties.postcode,
        properties.city,
        properties.district,
        properties.locality,
        properties.state,
      ].filter(
        (value): value is string =>
          Boolean(value) &&
          value?.toLocaleLowerCase() !== name.toLocaleLowerCase(),
      ),
    ),
  ).join(" · ");
  const type = ["house", "street"].includes(properties.type ?? "")
    ? "address"
    : "place";
  return {
    id: `photon:${properties.osm_type ?? "?"}:${properties.osm_id ?? `${latitude},${longitude}`}`,
    name,
    context,
    latitude,
    longitude,
    type,
  };
}

async function fetchPhoton(
  pathname: "/api/" | "/reverse",
  parameters: URLSearchParams,
  env: Env,
): Promise<LocationResult[]> {
  const base = new URL(env.GEOCODER_BASE_URL ?? "https://photon.komoot.io");
  const upstream = new URL(pathname, base);
  upstream.search = parameters.toString();
  const response = await fetch(upstream, {
    headers: {
      Accept: "application/geo+json, application/json",
      "User-Agent": "WetMap/1.0 (+https://wetmap.pages.dev)",
    },
    signal: AbortSignal.timeout(4_000),
  });
  if (!response.ok)
    throw new Error(`Photon geocoder returned ${response.status}`);
  const payload = (await response.json()) as { features?: PhotonFeature[] };
  return (payload.features ?? [])
    .map(normalizeLocation)
    .filter((location): location is LocationResult => location !== null);
}

async function searchLocations(
  url: URL,
  env: Env,
  context: ExecutionContext,
): Promise<Response> {
  const query = (url.searchParams.get("q") ?? "").trim().replace(/\s+/g, " ");
  if (query.length < 2 || query.length > 80)
    return problem(
      400,
      "Invalid location query",
      "Use between 2 and 80 characters.",
    );
  const latitude = coordinate(url.searchParams.get("lat"));
  const longitude = coordinate(url.searchParams.get("lon"));
  const cacheUrl = new URL("https://cache.wetmap/locations/search");
  cacheUrl.searchParams.set("q", query.toLocaleLowerCase("da-DK"));
  if (latitude !== null && longitude !== null) {
    cacheUrl.searchParams.set("lat", latitude.toFixed(1));
    cacheUrl.searchParams.set("lon", longitude.toFixed(1));
  }
  const cacheRequest = new Request(cacheUrl);
  const cached = await caches.default.match(cacheRequest);
  if (cached) {
    const headers = new Headers(cached.headers);
    headers.set("X-WetMap-Cache", "HIT");
    return new Response(cached.body, { status: cached.status, headers });
  }

  const parameters = new URLSearchParams({
    q: query,
    limit: "6",
    countrycode: "DK",
  });
  if (latitude !== null && longitude !== null) {
    parameters.set("lat", String(latitude));
    parameters.set("lon", String(longitude));
    parameters.set("zoom", "8");
    parameters.set("location_bias_scale", "0.25");
  }
  try {
    const results = await fetchPhoton("/api/", parameters, env);
    const response = Response.json(
      { query, results },
      {
        headers: {
          ...jsonHeaders,
          "Cache-Control": `public,max-age=${locationCacheSeconds}`,
          "X-WetMap-Cache": "MISS",
        },
      },
    );
    context.waitUntil(caches.default.put(cacheRequest, response.clone()));
    return response;
  } catch (error) {
    console.error("location.search.failed", { error });
    return problem(
      503,
      "Location search unavailable",
      "Location search is temporarily unavailable.",
    );
  }
}

async function reverseLocation(
  url: URL,
  env: Env,
  context: ExecutionContext,
): Promise<Response> {
  const latitude = coordinate(url.searchParams.get("lat"));
  const longitude = coordinate(url.searchParams.get("lon"));
  if (
    latitude === null ||
    longitude === null ||
    latitude < 54.4 ||
    latitude > 58 ||
    longitude < 7.5 ||
    longitude > 15.5
  )
    return problem(
      400,
      "Invalid location",
      "Coordinates must be located in Denmark.",
    );
  const cacheUrl = new URL("https://cache.wetmap/locations/reverse");
  cacheUrl.searchParams.set("lat", latitude.toFixed(3));
  cacheUrl.searchParams.set("lon", longitude.toFixed(3));
  const cacheRequest = new Request(cacheUrl);
  const cached = await caches.default.match(cacheRequest);
  if (cached) {
    const headers = new Headers(cached.headers);
    headers.set("X-WetMap-Cache", "HIT");
    return new Response(cached.body, { status: cached.status, headers });
  }

  try {
    const [result] = await fetchPhoton(
      "/reverse",
      new URLSearchParams({
        lat: String(latitude),
        lon: String(longitude),
        limit: "1",
      }),
      env,
    );
    const location: LocationResult =
      result ??
      ({
        id: `coordinates:${latitude.toFixed(5)},${longitude.toFixed(5)}`,
        name: `${latitude.toFixed(3)}°N, ${longitude.toFixed(3)}°E`,
        context: "Danmark",
        latitude,
        longitude,
        type: "place",
      } satisfies LocationResult);
    const response = Response.json(location, {
      headers: {
        ...jsonHeaders,
        "Cache-Control": `public,max-age=${reverseLocationCacheSeconds}`,
        "X-WetMap-Cache": "MISS",
      },
    });
    context.waitUntil(caches.default.put(cacheRequest, response.clone()));
    return response;
  } catch (error) {
    console.error("location.reverse.failed", { error });
    return problem(
      503,
      "Location lookup unavailable",
      "The selected coordinates are still available.",
    );
  }
}

async function frames(request: Request, env: Env): Promise<Response> {
  const object = await env.RADAR.get("frames/frames.json", {
    onlyIf: request.headers,
  });
  if (!object)
    return Response.json(
      {
        schemaVersion: 1,
        generatedAt: new Date(0).toISOString(),
        attribution,
        frames: [],
      },
      { headers: jsonHeaders },
    );
  if (!("body" in object)) return new Response(null, { status: 304 });
  const headers = new Headers(jsonHeaders);
  object.writeHttpMetadata(headers);
  headers.set("ETag", object.httpEtag);
  headers.set("Cache-Control", "public,max-age=60,stale-while-revalidate=300");
  headers.set("X-DMI-Attribution", attributionHeader);
  return new Response(object.body, { headers });
}

async function nowcast(request: Request, env: Env): Promise<Response> {
  const object = await env.RADAR.get("nowcast/nowcast.json", {
    onlyIf: request.headers,
  });
  if (!object)
    return Response.json(
      {
        schemaVersion: 1,
        generatedAt: new Date(0).toISOString(),
        attribution,
        method: "adaptive-optical-flow-persistence",
        basedOnObservedAt: new Date(0).toISOString(),
        sourceFrameCount: 0,
        frames: [],
      },
      { headers: jsonHeaders },
    );
  if (!("body" in object)) return new Response(null, { status: 304 });
  const headers = new Headers(jsonHeaders);
  object.writeHttpMetadata(headers);
  headers.set("ETag", object.httpEtag);
  headers.set("Cache-Control", "public,max-age=60,stale-while-revalidate=300");
  headers.set("X-DMI-Attribution", attributionHeader);
  return new Response(object.body, { headers });
}

async function nowcastQuality(request: Request, env: Env): Promise<Response> {
  const object = await env.RADAR.get("nowcast/verification.json", {
    onlyIf: request.headers,
  });
  if (!object)
    return Response.json(
      {
        schemaVersion: 3,
        generatedAt: new Date(0).toISOString(),
        algorithmVersion: "adaptive-optical-flow-persistence-v1",
        thresholdDbz: 20,
        thresholdsDbz: [10, 20, 35],
        sampleCount: 0,
        totalSampleCount: 0,
        returnedResultCount: 0,
        meanCriticalSuccessIndex: null,
        meanCriticalSuccessIndexSkill: null,
        byLeadMinutes: [],
        byThresholdDbz: [],
        byAlgorithmVersion: [],
        results: [],
      },
      { headers: jsonHeaders },
    );
  if (!("body" in object)) return new Response(null, { status: 304 });
  const headers = new Headers(jsonHeaders);
  object.writeHttpMetadata(headers);
  headers.set("ETag", object.httpEtag);
  headers.set("Cache-Control", "public,max-age=300,stale-while-revalidate=900");
  headers.set("X-DMI-Attribution", attributionHeader);
  return new Response(object.body, { headers });
}

async function frame(
  pathname: string,
  request: Request,
  env: Env,
): Promise<Response> {
  const key = pathname.slice(1);
  if (!/^frames\/[a-zA-Z0-9._-]+\.webp$/.test(key))
    return new Response(null, { status: 404 });
  const object = await env.RADAR.get(key, {
    onlyIf: request.headers,
    range: request.headers,
  });
  if (!object) return new Response(null, { status: 404 });
  if (!("body" in object)) return new Response(null, { status: 304 });
  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set("ETag", object.httpEtag);
  headers.set("Cache-Control", "public,max-age=31536000,immutable");
  return new Response(object.body, { headers });
}

async function nowcastFrame(
  pathname: string,
  request: Request,
  env: Env,
): Promise<Response> {
  const key = pathname.slice(1);
  if (!/^nowcast\/[a-zA-Z0-9._-]+\.webp$/.test(key))
    return new Response(null, { status: 404 });
  const object = await env.RADAR.get(key, {
    onlyIf: request.headers,
    range: request.headers,
  });
  if (!object) return new Response(null, { status: 404 });
  if (!("body" in object)) return new Response(null, { status: 304 });
  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set("ETag", object.httpEtag);
  headers.set("Cache-Control", "public,max-age=300");
  return new Response(object.body, { headers });
}

async function dispatchRadarIngestion(env: Env): Promise<void> {
  if (!env.GITHUB_DISPATCH_TOKEN) {
    console.error("radar.scheduler.missing-token");
    return;
  }
  const repository = env.GITHUB_REPOSITORY ?? "browndahl/wetMap";
  const workflow = env.GITHUB_RADAR_WORKFLOW ?? "radar.yml";
  const ref = env.GITHUB_REF ?? "main";
  const response = await fetch(
    `https://api.github.com/repos/${repository}/actions/workflows/${workflow}/dispatches`,
    {
      method: "POST",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${env.GITHUB_DISPATCH_TOKEN}`,
        "Content-Type": "application/json",
        "User-Agent": "wetmap-radar-scheduler/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify({ ref }),
    },
  );
  if (!response.ok)
    throw new Error(`GitHub workflow dispatch returned ${response.status}`);
  console.log("radar.scheduler.dispatched", { repository, workflow, ref });
}

async function ensureFreshRadar(env: Env): Promise<void> {
  const object = await env.RADAR.get("frames/frames.json");
  if (object) {
    try {
      const manifest = await object.json<{
        frames?: Array<{ observedAt?: string }>;
      }>();
      const observedAt = manifest.frames?.at(-1)?.observedAt;
      const observedTime = observedAt ? Date.parse(observedAt) : Number.NaN;
      if (
        Number.isFinite(observedTime) &&
        Date.now() - observedTime <= radarDispatchAgeMs
      )
        return;
    } catch (error) {
      console.error("radar.scheduler.invalid-manifest", { error });
    }
  }
  await dispatchRadarIngestion(env);
}

function forecastHeaders(
  cacheStatus: "HIT" | "MISS" | "STALE",
  telemetry: RequestTelemetry = {},
): HeadersInit {
  return {
    ...jsonHeaders,
    "Cache-Control": `public,max-age=${forecastCacheSeconds},stale-while-revalidate=${forecastStaleSeconds}`,
    "X-DMI-Attribution": attributionHeader,
    "X-WetMap-Cache": cacheStatus,
    ...telemetryHeaders(telemetry),
  };
}

function validForecast(payload: ForecastPayload): boolean {
  const currentHour = new Date();
  currentHour.setUTCMinutes(0, 0, 0);
  return payload.points.some(
    (point) => Date.parse(point.step) >= currentHour.getTime(),
  );
}

async function fetchOpenMeteoForecast(
  latitude: number,
  longitude: number,
  env: Env,
): Promise<ForecastPayload> {
  const upstream = new URL("/v1/forecast", env.OPEN_METEO_BASE_URL);
  upstream.searchParams.set("latitude", latitude.toFixed(2));
  upstream.searchParams.set("longitude", longitude.toFixed(2));
  upstream.searchParams.set(
    "hourly",
    "temperature_2m,precipitation,wind_speed_10m,cloud_cover",
  );
  upstream.searchParams.set("wind_speed_unit", "ms");
  upstream.searchParams.set("timezone", "GMT");
  upstream.searchParams.set("forecast_days", "3");
  upstream.searchParams.set("models", "dmi_seamless");
  const response = await fetch(upstream, {
    headers: { Accept: "application/json", "User-Agent": "wetmap-edge/0.2" },
    signal: AbortSignal.timeout(5_000),
  });
  if (!response.ok)
    throw new Error(`Open-Meteo DMI returned ${response.status}`);
  const data = (await response.json()) as {
    latitude: number;
    longitude: number;
    hourly?: {
      time?: string[];
      temperature_2m?: Array<number | null>;
      precipitation?: Array<number | null>;
      wind_speed_10m?: Array<number | null>;
      cloud_cover?: Array<number | null>;
    };
  };
  const hourly = data.hourly;
  if (!hourly?.time?.length)
    throw new Error("Open-Meteo DMI returned no forecast points");
  const points = hourly.time.map((step, index) => ({
    step: `${step}:00Z`,
    temperatureC: hourly.temperature_2m?.[index] ?? null,
    precipitationKgM2: hourly.precipitation?.[index] ?? null,
    windSpeedMs: hourly.wind_speed_10m?.[index] ?? null,
    cloudCoverPercent: hourly.cloud_cover?.[index] ?? null,
  }));
  return normaliseForecast({
    latitude: data.latitude,
    longitude: data.longitude,
    fetchedAt: new Date().toISOString(),
    attribution,
    source: "open-meteo-dmi",
    model: "DMI HARMONIE AROME",
    points,
  });
}

function normaliseForecast(payload: ForecastPayload): ForecastPayload {
  const currentHour = new Date();
  currentHour.setUTCMinutes(0, 0, 0);
  return {
    ...payload,
    points: payload.points
      .filter(
        (point) =>
          Number.isFinite(Date.parse(point.step)) &&
          Date.parse(point.step) >= currentHour.getTime(),
      )
      .slice(0, 48),
  };
}

async function fetchDmiForecast(
  latitude: number,
  longitude: number,
  env: Env,
  options: { precipitationOnly?: boolean; horizonHours?: number } = {},
): Promise<ForecastPayload> {
  const roundedLat = latitude.toFixed(2);
  const roundedLon = longitude.toFixed(2);
  const upstream = new URL(
    "/v1/forecastedr/collections/harmonie_dini_sf/position",
    env.DMI_BASE_URL,
  );
  upstream.searchParams.set("coords", `POINT(${roundedLon} ${roundedLat})`);
  upstream.searchParams.set("crs", "crs84");
  upstream.searchParams.set(
    "parameter-name",
    options.precipitationOnly
      ? "total-precipitation"
      : "temperature-2m,wind-speed-10m,total-precipitation,fraction-of-cloud-cover",
  );
  const currentHour = new Date();
  currentHour.setUTCMinutes(0, 0, 0);
  upstream.searchParams.set(
    "datetime",
    `${new Date(currentHour.getTime() - 60 * 60 * 1000).toISOString()}/${new Date(currentHour.getTime() + (options.horizonHours ?? 24) * 60 * 60 * 1000).toISOString()}`,
  );
  upstream.searchParams.set("f", "GeoJSON");
  const response = await fetch(upstream, {
    headers: {
      Accept: "application/geo+json",
      "User-Agent": "wetmap-edge/0.2",
    },
    // The response path is hedged after 1.5 s; this longer timeout only lets
    // the official DMI result replace the fallback cache in waitUntil().
    signal: AbortSignal.timeout(15_000),
  });
  if (!response.ok) throw new Error(`DMI EDR returned ${response.status}`);
  const data = (await response.json()) as {
    features?: Array<{ properties: Record<string, number | string | null> }>;
  };
  const rawPoints = (data.features ?? [])
    .map(({ properties }) => ({
      step: String(properties.step ?? ""),
      temperatureC:
        typeof properties["temperature-2m"] === "number"
          ? Math.round((properties["temperature-2m"] - 273.15) * 10) / 10
          : null,
      accumulatedPrecipitation:
        typeof properties["total-precipitation"] === "number"
          ? properties["total-precipitation"]
          : null,
      windSpeedMs:
        typeof properties["wind-speed-10m"] === "number"
          ? properties["wind-speed-10m"]
          : null,
      cloudCoverPercent:
        typeof properties["fraction-of-cloud-cover"] === "number"
          ? Math.round(properties["fraction-of-cloud-cover"] * 100)
          : null,
    }))
    .filter((point) => Number.isFinite(Date.parse(point.step)))
    .sort((left, right) => Date.parse(left.step) - Date.parse(right.step));
  let previousAccumulation: number | null = null;
  const points = rawPoints.map(
    ({ accumulatedPrecipitation, ...point }): ForecastPoint => {
      const precipitationKgM2 =
        accumulatedPrecipitation === null
          ? null
          : Math.round(
              Math.max(
                0,
                accumulatedPrecipitation - (previousAccumulation ?? 0),
              ) * 1_000,
            ) / 1_000;
      if (accumulatedPrecipitation !== null)
        previousAccumulation = accumulatedPrecipitation;
      return { ...point, precipitationKgM2 };
    },
  );
  return normaliseForecast({
    latitude,
    longitude,
    fetchedAt: new Date().toISOString(),
    attribution,
    source: "dmi-edr",
    model: "DMI HARMONIE AROME",
    points,
  });
}

async function refreshForecast(
  latitude: number,
  longitude: number,
  cacheKey: Request,
  persistentKey: string,
  env: Env,
  edgeCache: Cache,
  context: ExecutionContext,
): Promise<Response> {
  const startedAt = performance.now();
  let selected: Awaited<
    ReturnType<typeof dmiPrimaryWithFallback<ForecastPayload>>
  >;
  try {
    selected = await dmiPrimaryWithFallback(
      () => fetchDmiForecast(latitude, longitude, env),
      () => fetchOpenMeteoForecast(latitude, longitude, env),
    );
  } catch (error) {
    console.error("forecast.upstream.failed", { error, latitude, longitude });
    throw error;
  }
  const { payload, telemetry, backgroundDmi } = selected;
  if (!payload.points.length)
    throw new Error("Forecast contained no current or future points");
  const body = JSON.stringify(payload);
  telemetry.totalMs = elapsed(startedAt);
  console.log("forecast.provider.selected", {
    latitude,
    longitude,
    ...telemetry,
  });
  const response = new Response(body, {
    headers: forecastHeaders("MISS", telemetry),
  });
  await Promise.all([
    edgeCache.put(cacheKey, response.clone()),
    env.RADAR.put(persistentKey, body, {
      httpMetadata: {
        contentType: "application/json",
        cacheControl: "no-cache",
      },
    }),
  ]);
  if (backgroundDmi) {
    context.waitUntil(
      backgroundDmi
        .then(async (dmiPayload) => {
          if (!dmiPayload.points.length)
            throw new Error("Direct DMI background refresh returned no points");
          const dmiBody = JSON.stringify(dmiPayload);
          const dmiTelemetry: RequestTelemetry = {
            provider: "dmi-edr",
            fallback: "none",
            dmiMs: telemetry.dmiMs,
            dmiOutcome: "success",
            totalMs: elapsed(startedAt),
          };
          const dmiResponse = new Response(dmiBody, {
            headers: forecastHeaders("MISS", dmiTelemetry),
          });
          await Promise.all([
            edgeCache.put(cacheKey, dmiResponse.clone()),
            env.RADAR.put(persistentKey, dmiBody, {
              httpMetadata: {
                contentType: "application/json",
                cacheControl: "no-cache",
              },
            }),
          ]);
          console.log("forecast.provider.refreshed", {
            latitude,
            longitude,
            ...dmiTelemetry,
          });
        })
        .catch((error) =>
          console.warn("forecast.background-dmi.failed", {
            error,
            latitude,
            longitude,
          }),
        ),
    );
  }
  return response;
}

async function forecast(
  url: URL,
  env: Env,
  context: ExecutionContext,
): Promise<Response> {
  const startedAt = performance.now();
  const latitude = Number(url.searchParams.get("lat"));
  const longitude = Number(url.searchParams.get("lon"));
  if (
    !Number.isFinite(latitude) ||
    latitude < -90 ||
    latitude > 90 ||
    !Number.isFinite(longitude) ||
    longitude < -180 ||
    longitude > 180
  )
    return problem(
      400,
      "Invalid coordinates",
      "Latitude must be -90..90 and longitude -180..180.",
    );
  // HARMONIE is a 2 km model. A 0.01-degree cache grid avoids needless
  // upstream calls while retaining the model's useful spatial resolution.
  const roundedLat = latitude.toFixed(2);
  const roundedLon = longitude.toFixed(2);
  const cacheUrl = new URL(url);
  cacheUrl.search = new URLSearchParams({
    lat: roundedLat,
    lon: roundedLon,
  }).toString();
  const cacheKey = new Request(cacheUrl, { method: "GET" });
  const persistentKey = `forecast/v3/${roundedLat}/${roundedLon}.json`;
  const edgeCache = (caches as unknown as { default: Cache }).default;
  const cacheStartedAt = performance.now();
  const cached = await edgeCache.match(cacheKey);
  if (cached) {
    const headers = new Headers(cached.headers);
    headers.set("X-WetMap-Cache", "HIT");
    const telemetry: RequestTelemetry = {
      provider: (headers.get("X-WetMap-Provider") ?? undefined) as
        | WeatherProvider
        | undefined,
      fallback: (headers.get("X-WetMap-Fallback") ??
        undefined) as RequestTelemetry["fallback"],
      cacheMs: elapsed(cacheStartedAt),
      totalMs: elapsed(startedAt),
    };
    for (const [name, value] of Object.entries(telemetryHeaders(telemetry)))
      headers.set(name, value);
    return new Response(cached.body, { status: cached.status, headers });
  }

  const r2StartedAt = performance.now();
  const persisted = await env.RADAR.get(persistentKey);
  const r2Ms = elapsed(r2StartedAt);
  if (persisted) {
    try {
      const payload = await persisted.json<ForecastPayload>();
      if (validForecast(payload)) {
        context.waitUntil(
          refreshForecast(
            Number(roundedLat),
            Number(roundedLon),
            cacheKey,
            persistentKey,
            env,
            edgeCache,
            context,
          ).catch(() => undefined),
        );
        return new Response(JSON.stringify(normaliseForecast(payload)), {
          headers: forecastHeaders("STALE", {
            provider: payload.source,
            fallback: "stale",
            r2Ms,
            totalMs: elapsed(startedAt),
          }),
        });
      }
    } catch (error) {
      console.error("forecast.cache.invalid", { error, persistentKey });
    }
  }

  try {
    return await refreshForecast(
      Number(roundedLat),
      Number(roundedLon),
      cacheKey,
      persistentKey,
      env,
      edgeCache,
      context,
    );
  } catch {
    return problem(
      503,
      "Forecast unavailable",
      "DMI HARMONIE forecast data is temporarily unavailable from both providers.",
    );
  }
}

function precipitationHeaders(
  cacheStatus: "HIT" | "MISS" | "STALE",
  telemetry: RequestTelemetry = {},
): HeadersInit {
  return {
    ...jsonHeaders,
    "Cache-Control": `public,max-age=${precipitationCacheSeconds},stale-while-revalidate=${precipitationStaleSeconds}`,
    "X-DMI-Attribution": attributionHeader,
    "X-WetMap-Cache": cacheStatus,
    ...telemetryHeaders(telemetry),
  };
}

function rainIntensity(precipitationMm: number): RainIntensity {
  if (precipitationMm < 0.05) return "none";
  if (precipitationMm < 0.5) return "light";
  if (precipitationMm < 1.5) return "moderate";
  return "heavy";
}

function validPrecipitation(payload: RainNextHourPayload): boolean {
  return payload.points.some((point) => Date.parse(point.endsAt) > Date.now());
}

function pointMercatorY(latitude: number): number {
  const limited = Math.max(-85.051129, Math.min(85.051129, latitude));
  const radians = (limited * Math.PI) / 180;
  return Math.log(Math.tan(Math.PI / 4 + radians / 2));
}

async function radarPointSamples(
  latitude: number,
  longitude: number,
  env: Env,
): Promise<{
  metadata: PointRiskMetadata;
  samples: RadarPointSample[];
} | null> {
  const metadataObject = await env.RADAR.get("nowcast/point-risk.json");
  if (!metadataObject) return null;
  let metadata: PointRiskMetadata;
  try {
    metadata = await metadataObject.json<PointRiskMetadata>();
  } catch {
    return null;
  }
  const observationAge = Date.now() - Date.parse(metadata.basedOnObservedAt);
  const [west, south, east, north] = metadata.bounds;
  const dataKey = metadata.dataKey ?? "nowcast/point-risk.bin";
  if (
    metadata.encoding !== "pixel-major-uint8-dbz-plus-32" ||
    metadata.frames.length !== metadata.frameCount ||
    metadata.frameCount < 2 ||
    metadata.frameCount > 13 ||
    metadata.width < 1 ||
    metadata.width > 2_048 ||
    metadata.height < 1 ||
    metadata.height > 2_048 ||
    !/^nowcast\/point-risk-(?:[01])\.bin$|^nowcast\/point-risk\.bin$/.test(
      dataKey,
    ) ||
    !Number.isFinite(observationAge) ||
    observationAge < -5 * 60_000 ||
    observationAge > 30 * 60_000 ||
    longitude < west ||
    longitude > east ||
    latitude < south ||
    latitude > north
  )
    return null;

  const x = Math.min(
    metadata.width - 1,
    Math.max(
      0,
      Math.floor(((longitude - west) / (east - west)) * metadata.width),
    ),
  );
  const northY = pointMercatorY(north);
  const southY = pointMercatorY(south);
  const y = Math.min(
    metadata.height - 1,
    Math.max(
      0,
      Math.floor(
        ((northY - pointMercatorY(latitude)) / (northY - southY)) *
          metadata.height,
      ),
    ),
  );
  const radius = Math.max(
    0,
    Math.min(2, Math.round(metadata.neighborhoodRadiusPixels ?? 1)),
  );
  const xStart = Math.max(0, x - radius);
  const xEnd = Math.min(metadata.width - 1, x + radius);
  const encodedMax = new Uint8Array(metadata.frameCount);
  const rows = Array.from(
    {
      length:
        Math.min(metadata.height - 1, y + radius) - Math.max(0, y - radius) + 1,
    },
    (_, index) => Math.max(0, y - radius) + index,
  );
  const rowBytes = await Promise.all(
    rows.map(async (row) => {
      const pixelCount = xEnd - xStart + 1;
      const offset = (row * metadata.width + xStart) * metadata.frameCount;
      const object = await env.RADAR.get(dataKey, {
        range: { offset, length: pixelCount * metadata.frameCount },
      });
      if (!object || !("body" in object)) return null;
      const bytes = new Uint8Array(
        await new Response(object.body).arrayBuffer(),
      );
      return bytes.length === pixelCount * metadata.frameCount ? bytes : null;
    }),
  );
  if (rowBytes.some((bytes) => bytes === null)) return null;
  const pixelCount = xEnd - xStart + 1;
  for (const bytes of rowBytes) {
    if (!bytes) return null;
    for (let pixel = 0; pixel < pixelCount; pixel += 1) {
      for (let frame = 0; frame < metadata.frameCount; frame += 1) {
        encodedMax[frame] = Math.max(
          encodedMax[frame],
          bytes[pixel * metadata.frameCount + frame],
        );
      }
    }
  }
  return {
    metadata,
    samples: metadata.frames.map((frame, index) => ({
      ...frame,
      reflectivityDbz: encodedMax[index] === 0 ? null : encodedMax[index] - 32,
    })),
  };
}

function radarIntensity(reflectivityDbz: number): RainIntensity {
  if (reflectivityDbz < -10) return "none";
  if (reflectivityDbz < 20) return "trace";
  if (reflectivityDbz < 35) return "light";
  if (reflectivityDbz < 45) return "moderate";
  return "heavy";
}

function rainRateFromReflectivity(reflectivityDbz: number): number {
  if (reflectivityDbz < -10) return 0;
  const reflectivity = 10 ** (reflectivityDbz / 10);
  return (reflectivity / 200) ** (1 / 1.6);
}

function combineRadarAndModel(
  model: RainNextHourPayload,
  radar: NonNullable<Awaited<ReturnType<typeof radarPointSamples>>>,
): RainNextHourPayload {
  let radarPointCount = 0;
  const points = model.points.map((point) => {
    const startsAt = Date.parse(point.startsAt);
    const endsAt = Date.parse(point.endsAt);
    const samples = radar.samples.filter((sample) => {
      const predictedAt = Date.parse(sample.predictedAt);
      return predictedAt >= startsAt - 2.5 * 60_000 && predictedAt < endsAt;
    });
    const coveredSamples = samples.filter(
      (sample): sample is RadarPointSample & { reflectivityDbz: number } =>
        sample.reflectivityDbz !== null,
    );
    if (!coveredSamples.length)
      return { ...point, source: "harmonie" as const };

    radarPointCount += 1;
    const peakDbz = Math.max(
      ...coveredSamples.map((sample) => sample.reflectivityDbz),
    );
    const averageRate =
      coveredSamples.reduce(
        (sum, sample) => sum + rainRateFromReflectivity(sample.reflectivityDbz),
        0,
      ) / coveredSamples.length;
    return {
      ...point,
      precipitationMm: Math.round(averageRate * 0.25 * 100) / 100,
      intensity: radarIntensity(peakDbz),
      source: "radar-nowcast" as const,
      reflectivityDbz: Math.round(peakDbz),
      confidence:
        Math.round(
          (coveredSamples.reduce((sum, sample) => sum + sample.confidence, 0) /
            coveredSamples.length) *
            100,
        ) / 100,
      forecastMethod: coveredSamples.some(
        (sample) => sample.forecastMethod === "persistence",
      )
        ? ("persistence" as const)
        : coveredSamples.some(
              (sample) => sample.forecastMethod === "optical-flow",
            )
          ? ("optical-flow" as const)
          : null,
    };
  });
  if (!radarPointCount)
    return {
      ...model,
      points: points.map((point) => ({ ...point, source: "harmonie" })),
    };
  const latestCoveredSample = radar.samples
    .filter((sample) => sample.reflectivityDbz !== null)
    .at(-1);
  return {
    ...model,
    source: "dmi-radar-nowcast-harmonie",
    basedOnObservedAt: radar.metadata.basedOnObservedAt,
    radarBasedUntil: latestCoveredSample?.predictedAt,
    points,
  };
}

function forecastToRainPayload(
  forecastPayload: ForecastPayload,
): RainNextHourPayload {
  const now = Date.now();
  const quarterMs = 15 * 60 * 1000;
  const firstEnd = Math.floor(now / quarterMs) * quarterMs + quarterMs;
  const hourlyPoints = forecastPayload.points
    .filter(
      (point): point is ForecastPoint & { precipitationKgM2: number } =>
        point.precipitationKgM2 !== null &&
        Number.isFinite(Date.parse(point.step)),
    )
    .sort((left, right) => Date.parse(left.step) - Date.parse(right.step));
  if (!hourlyPoints.length)
    throw new Error("DMI EDR returned no precipitation points");
  const points = Array.from({ length: 4 }, (_, index): RainForecastPoint => {
    const endsAtMs = firstEnd + index * quarterMs;
    const hourlyPoint = hourlyPoints.find(
      (point) => Date.parse(point.step) >= endsAtMs,
    );
    if (!hourlyPoint)
      throw new Error("DMI EDR precipitation does not cover the next hour");
    const precipitationMm = Math.max(0, hourlyPoint.precipitationKgM2 / 4);
    return {
      startsAt: new Date(endsAtMs - quarterMs).toISOString(),
      endsAt: new Date(endsAtMs).toISOString(),
      precipitationMm: Math.round(precipitationMm * 100) / 100,
      intensity: rainIntensity(precipitationMm),
    };
  });
  return {
    latitude: forecastPayload.latitude,
    longitude: forecastPayload.longitude,
    fetchedAt: forecastPayload.fetchedAt,
    attribution,
    source: forecastPayload.source,
    model: forecastPayload.model,
    displayResolutionMinutes: 15,
    sourceResolutionMinutes: 60,
    isInterpolated: true,
    points,
  };
}

async function fetchOpenMeteoPrecipitation(
  latitude: number,
  longitude: number,
  env: Env,
): Promise<RainNextHourPayload> {
  const upstream = new URL("/v1/forecast", env.OPEN_METEO_BASE_URL);
  upstream.searchParams.set("latitude", latitude.toFixed(2));
  upstream.searchParams.set("longitude", longitude.toFixed(2));
  upstream.searchParams.set("minutely_15", "precipitation");
  upstream.searchParams.set("forecast_minutely_15", "8");
  upstream.searchParams.set("timezone", "GMT");
  upstream.searchParams.set("models", "dmi_seamless");
  const response = await fetch(upstream, {
    headers: { Accept: "application/json", "User-Agent": "wetmap-edge/0.3" },
    signal: AbortSignal.timeout(5_000),
  });
  if (!response.ok)
    throw new Error(`Open-Meteo DMI precipitation returned ${response.status}`);
  const data = (await response.json()) as {
    latitude: number;
    longitude: number;
    minutely_15?: {
      time?: string[];
      precipitation?: Array<number | null>;
    };
  };
  const minutely = data.minutely_15;
  if (!minutely?.time?.length)
    throw new Error("Open-Meteo DMI returned no precipitation points");

  const now = Date.now();
  const hourAhead = now + 60 * 60 * 1000;
  const points = minutely.time
    .map((value, index): RainForecastPoint | null => {
      const endsAtMs = Date.parse(`${value}:00Z`);
      if (!Number.isFinite(endsAtMs)) return null;
      const precipitationMm = Math.max(0, minutely.precipitation?.[index] ?? 0);
      return {
        startsAt: new Date(endsAtMs - 15 * 60 * 1000).toISOString(),
        endsAt: new Date(endsAtMs).toISOString(),
        precipitationMm: Math.round(precipitationMm * 100) / 100,
        intensity: rainIntensity(precipitationMm),
      };
    })
    .filter(
      (point): point is RainForecastPoint =>
        point !== null &&
        Date.parse(point.endsAt) > now &&
        Date.parse(point.startsAt) < hourAhead,
    )
    .slice(0, 4);
  if (!points.length)
    throw new Error("DMI precipitation forecast contained no future points");

  return {
    latitude: data.latitude,
    longitude: data.longitude,
    fetchedAt: new Date().toISOString(),
    attribution,
    source: "open-meteo-dmi",
    model: "DMI HARMONIE AROME",
    displayResolutionMinutes: 15,
    sourceResolutionMinutes: 60,
    isInterpolated: true,
    points,
  };
}

async function refreshPrecipitation(
  latitude: number,
  longitude: number,
  cacheKey: Request,
  persistentKey: string,
  env: Env,
  edgeCache: Cache,
  context: ExecutionContext,
): Promise<Response> {
  const startedAt = performance.now();
  const { payload, telemetry, backgroundDmi } = await dmiPrimaryWithFallback(
    async () =>
      forecastToRainPayload(
        await fetchDmiForecast(latitude, longitude, env, {
          precipitationOnly: true,
          horizonHours: 2,
        }),
      ),
    () => fetchOpenMeteoPrecipitation(latitude, longitude, env),
  );
  const body = JSON.stringify(payload);
  telemetry.totalMs = elapsed(startedAt);
  console.log("precipitation.provider.selected", {
    latitude,
    longitude,
    ...telemetry,
  });
  const response = new Response(body, {
    headers: precipitationHeaders("MISS", telemetry),
  });
  await Promise.all([
    edgeCache.put(cacheKey, response.clone()),
    env.RADAR.put(persistentKey, body, {
      httpMetadata: {
        contentType: "application/json",
        cacheControl: "no-cache",
      },
    }),
  ]);
  if (backgroundDmi) {
    context.waitUntil(
      backgroundDmi
        .then(async (dmiPayload) => {
          const dmiBody = JSON.stringify(dmiPayload);
          const dmiTelemetry: RequestTelemetry = {
            provider: "dmi-edr",
            fallback: "none",
            dmiMs: telemetry.dmiMs,
            dmiOutcome: "success",
            totalMs: elapsed(startedAt),
          };
          const dmiResponse = new Response(dmiBody, {
            headers: precipitationHeaders("MISS", dmiTelemetry),
          });
          await Promise.all([
            edgeCache.put(cacheKey, dmiResponse.clone()),
            env.RADAR.put(persistentKey, dmiBody, {
              httpMetadata: {
                contentType: "application/json",
                cacheControl: "no-cache",
              },
            }),
          ]);
          console.log("precipitation.provider.refreshed", {
            latitude,
            longitude,
            ...dmiTelemetry,
          });
        })
        .catch((error) =>
          console.warn("precipitation.background-dmi.failed", {
            error,
            latitude,
            longitude,
          }),
        ),
    );
  }
  return response;
}

async function modelPrecipitation(
  url: URL,
  env: Env,
  context: ExecutionContext,
): Promise<Response> {
  const startedAt = performance.now();
  const latitude = Number(url.searchParams.get("lat"));
  const longitude = Number(url.searchParams.get("lon"));
  if (
    !Number.isFinite(latitude) ||
    latitude < -90 ||
    latitude > 90 ||
    !Number.isFinite(longitude) ||
    longitude < -180 ||
    longitude > 180
  )
    return problem(
      400,
      "Invalid coordinates",
      "Latitude must be -90..90 and longitude -180..180.",
    );

  const roundedLat = latitude.toFixed(2);
  const roundedLon = longitude.toFixed(2);
  const cacheUrl = new URL(url);
  cacheUrl.search = new URLSearchParams({
    lat: roundedLat,
    lon: roundedLon,
  }).toString();
  const cacheKey = new Request(cacheUrl, { method: "GET" });
  const persistentKey = `precipitation/v2/${roundedLat}/${roundedLon}.json`;
  const edgeCache = (caches as unknown as { default: Cache }).default;
  const cacheStartedAt = performance.now();
  const cached = await edgeCache.match(cacheKey);
  if (cached) {
    const headers = new Headers(cached.headers);
    headers.set("X-WetMap-Cache", "HIT");
    const telemetry: RequestTelemetry = {
      provider: (headers.get("X-WetMap-Provider") ?? undefined) as
        | WeatherProvider
        | undefined,
      fallback: (headers.get("X-WetMap-Fallback") ??
        undefined) as RequestTelemetry["fallback"],
      cacheMs: elapsed(cacheStartedAt),
      totalMs: elapsed(startedAt),
    };
    for (const [name, value] of Object.entries(telemetryHeaders(telemetry)))
      headers.set(name, value);
    return new Response(cached.body, { status: cached.status, headers });
  }

  const r2StartedAt = performance.now();
  const persisted = await env.RADAR.get(persistentKey);
  const r2Ms = elapsed(r2StartedAt);
  if (persisted) {
    try {
      const payload = await persisted.json<RainNextHourPayload>();
      if (validPrecipitation(payload)) {
        context.waitUntil(
          refreshPrecipitation(
            Number(roundedLat),
            Number(roundedLon),
            cacheKey,
            persistentKey,
            env,
            edgeCache,
            context,
          ).catch(() => undefined),
        );
        return new Response(JSON.stringify(payload), {
          headers: precipitationHeaders("STALE", {
            provider:
              payload.source === "dmi-radar-nowcast-harmonie"
                ? undefined
                : payload.source,
            fallback: "stale",
            r2Ms,
            totalMs: elapsed(startedAt),
          }),
        });
      }
    } catch (error) {
      console.error("precipitation.cache.invalid", { error, persistentKey });
    }
  }

  try {
    return await refreshPrecipitation(
      Number(roundedLat),
      Number(roundedLon),
      cacheKey,
      persistentKey,
      env,
      edgeCache,
      context,
    );
  } catch (error) {
    console.error("precipitation.upstream.failed", {
      error,
      latitude,
      longitude,
    });
    return problem(
      503,
      "Precipitation forecast unavailable",
      "The DMI HARMONIE precipitation forecast is temporarily unavailable.",
    );
  }
}

async function precipitation(
  url: URL,
  env: Env,
  context: ExecutionContext,
): Promise<Response> {
  const startedAt = performance.now();
  const latitude = Number(url.searchParams.get("lat"));
  const longitude = Number(url.searchParams.get("lon"));
  const coordinatesAreValid =
    Number.isFinite(latitude) &&
    latitude >= -90 &&
    latitude <= 90 &&
    Number.isFinite(longitude) &&
    longitude >= -180 &&
    longitude <= 180;
  const pointCache = (caches as unknown as { default: Cache }).default;
  const pointCacheUrl = new URL("https://cache.wetmap/precipitation/point");
  pointCacheUrl.search = new URLSearchParams({
    lat: latitude.toFixed(3),
    lon: longitude.toFixed(3),
  }).toString();
  const pointCacheKey = new Request(pointCacheUrl);
  if (coordinatesAreValid) {
    const pointCacheStartedAt = performance.now();
    const cachedPoint = await pointCache.match(pointCacheKey);
    if (cachedPoint) {
      const headers = new Headers(cachedPoint.headers);
      headers.set("X-WetMap-Point-Cache", "HIT");
      for (const [name, value] of Object.entries(
        telemetryHeaders({
          pointCacheMs: elapsed(pointCacheStartedAt),
          totalMs: elapsed(startedAt),
        }),
      ))
        headers.set(name, value);
      return new Response(cachedPoint.body, {
        status: cachedPoint.status,
        headers,
      });
    }
  }
  const radarPromise = coordinatesAreValid
    ? radarPointSamples(latitude, longitude, env).catch((error) => {
        console.error("precipitation.radar.failed", {
          error,
          latitude,
          longitude,
        });
        return null;
      })
    : Promise.resolve(null);
  const modelResponse = await modelPrecipitation(url, env, context);
  const radar = await radarPromise;
  if (!modelResponse.ok || !radar) return modelResponse;

  try {
    const model = (await modelResponse.json()) as RainNextHourPayload;
    const combined = combineRadarAndModel(model, radar);
    const headers = new Headers(modelResponse.headers);
    headers.set("Cache-Control", "public,max-age=60");
    headers.set("X-WetMap-Precipitation-Source", combined.source);
    headers.set("X-WetMap-Point-Cache", "MISS");
    const response = new Response(JSON.stringify(combined), {
      status: modelResponse.status,
      headers,
    });
    context.waitUntil(pointCache.put(pointCacheKey, response.clone()));
    return response;
  } catch (error) {
    console.error("precipitation.combine.failed", {
      error,
      latitude,
      longitude,
    });
    return modelResponse;
  }
}

export default {
  async fetch(
    request: Request,
    env: Env,
    context: ExecutionContext,
  ): Promise<Response> {
    const url = new URL(request.url);
    const origin = request.headers.get("Origin") ?? "";
    if (request.method === "OPTIONS") {
      const headers = new Headers(cors(origin, env));
      headers.set("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS");
      headers.set("Access-Control-Allow-Headers", "Content-Type");
      headers.set("Access-Control-Max-Age", "86400");
      return new Response(null, { status: 204, headers });
    }
    const allowedOrigin = Object.keys(cors(origin, env)).length > 0;
    if (
      ["POST", "DELETE"].includes(request.method) &&
      (!origin || !allowedOrigin)
    )
      return new Response(null, { status: 403 });
    let response: Response;
    if (
      url.pathname === "/api/v1/push/subscriptions" &&
      request.method === "POST"
    )
      response = await savePushSubscription(request, env);
    else if (
      url.pathname === "/api/v1/push/subscriptions" &&
      request.method === "DELETE"
    )
      response = await deletePushSubscription(request, env);
    else if (request.method !== "GET")
      response = new Response(null, { status: 405 });
    else if (url.pathname === "/api/v1/push/config") response = pushConfig(env);
    else if (url.pathname === "/api/v1/radar/frames")
      response = await frames(request, env);
    else if (url.pathname === "/api/v1/radar/nowcast")
      response = await nowcast(request, env);
    else if (url.pathname === "/api/v1/radar/nowcast/quality")
      response = await nowcastQuality(request, env);
    else if (url.pathname === "/api/v1/weather/forecast")
      response = await forecast(url, env, context);
    else if (url.pathname === "/api/v1/weather/precipitation")
      response = await precipitation(url, env, context);
    else if (url.pathname === "/api/v1/locations/search")
      response = await searchLocations(url, env, context);
    else if (url.pathname === "/api/v1/locations/reverse")
      response = await reverseLocation(url, env, context);
    else if (url.pathname.startsWith("/frames/"))
      response = await frame(url.pathname, request, env);
    else if (url.pathname.startsWith("/nowcast/"))
      response = await nowcastFrame(url.pathname, request, env);
    else if (url.pathname === "/health/live")
      response = Response.json({ status: "ok" });
    else response = new Response(null, { status: 404 });
    const headers = new Headers(response.headers);
    for (const [name, value] of Object.entries(cors(origin, env)))
      headers.set(name, value);
    headers.set("X-Content-Type-Options", "nosniff");
    headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
    return new Response(response.body, { status: response.status, headers });
  },
  async scheduled(
    _controller: ScheduledController,
    env: Env,
    context: ExecutionContext,
  ): Promise<void> {
    context.waitUntil(
      Promise.all([ensureFreshRadar(env), sendRainAlerts(env)]).then(
        () => undefined,
      ),
    );
  },
};
