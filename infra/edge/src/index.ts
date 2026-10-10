interface Env {
  RADAR: R2Bucket;
  DMI_BASE_URL: string;
  OPEN_METEO_BASE_URL: string;
  ALLOWED_ORIGIN: string;
}

const attribution = "Baseret på data fra DMI og efterfølgende bearbejdet";
const jsonHeaders = { "Content-Type": "application/json; charset=utf-8" };
const forecastCacheSeconds = 10 * 60;
const forecastStaleSeconds = 6 * 60 * 60;

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

function cors(origin: string, env: Env): HeadersInit {
  const allowedOrigins = env.ALLOWED_ORIGIN.split(",").map((value) => value.trim());
  let isPagesPreview = false;
  try {
    const parsed = new URL(origin);
    isPagesPreview = parsed.protocol === "https:" && (
      parsed.hostname.endsWith(".wetmap.pages.dev") ||
      parsed.hostname.endsWith(".wetmap-staging.pages.dev")
    );
  } catch {
    isPagesPreview = false;
  }
  return allowedOrigins.includes(origin) || isPagesPreview
    ? { "Access-Control-Allow-Origin": origin, Vary: "Origin" }
    : {};
}

function problem(status: number, title: string, detail: string): Response {
  return Response.json({ type: "about:blank", title, status, detail }, { status, headers: { "Content-Type": "application/problem+json" } });
}

async function frames(request: Request, env: Env): Promise<Response> {
  const object = await env.RADAR.get("frames/frames.json", { onlyIf: request.headers });
  if (!object) return Response.json({ schemaVersion: 1, generatedAt: new Date(0).toISOString(), attribution, frames: [] }, { headers: jsonHeaders });
  if (!("body" in object)) return new Response(null, { status: 304 });
  const headers = new Headers(jsonHeaders);
  object.writeHttpMetadata(headers);
  headers.set("ETag", object.httpEtag);
  headers.set("Cache-Control", "public,max-age=60,stale-while-revalidate=300");
  headers.set("X-DMI-Attribution", attribution);
  return new Response(object.body, { headers });
}

async function frame(pathname: string, request: Request, env: Env): Promise<Response> {
  const key = pathname.slice(1);
  if (!/^frames\/[a-zA-Z0-9._-]+\.webp$/.test(key)) return new Response(null, { status: 404 });
  const object = await env.RADAR.get(key, { onlyIf: request.headers, range: request.headers });
  if (!object) return new Response(null, { status: 404 });
  if (!("body" in object)) return new Response(null, { status: 304 });
  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set("ETag", object.httpEtag);
  headers.set("Cache-Control", "public,max-age=31536000,immutable");
  return new Response(object.body, { headers });
}

function forecastHeaders(cacheStatus: "HIT" | "MISS" | "STALE"): HeadersInit {
  return {
    ...jsonHeaders,
    "Cache-Control": `public,max-age=${forecastCacheSeconds},stale-while-revalidate=${forecastStaleSeconds}`,
    "X-DMI-Attribution": attribution,
    "X-WetMap-Cache": cacheStatus
  };
}

function validForecast(payload: ForecastPayload): boolean {
  const currentHour = new Date();
  currentHour.setUTCMinutes(0, 0, 0);
  return payload.points.some((point) => Date.parse(point.step) >= currentHour.getTime());
}

async function fetchOpenMeteoForecast(latitude: number, longitude: number, env: Env): Promise<ForecastPayload> {
  const upstream = new URL("/v1/forecast", env.OPEN_METEO_BASE_URL);
  upstream.searchParams.set("latitude", latitude.toFixed(2));
  upstream.searchParams.set("longitude", longitude.toFixed(2));
  upstream.searchParams.set("hourly", "temperature_2m,precipitation,wind_speed_10m,cloud_cover");
  upstream.searchParams.set("wind_speed_unit", "ms");
  upstream.searchParams.set("timezone", "GMT");
  upstream.searchParams.set("forecast_days", "3");
  upstream.searchParams.set("models", "dmi_seamless");
  const response = await fetch(upstream, {
    headers: { Accept: "application/json", "User-Agent": "wetmap-edge/0.2" },
    signal: AbortSignal.timeout(5_000)
  });
  if (!response.ok) throw new Error(`Open-Meteo DMI returned ${response.status}`);
  const data = await response.json() as {
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
  if (!hourly?.time?.length) throw new Error("Open-Meteo DMI returned no forecast points");
  const points = hourly.time.map((step, index) => ({
    step: `${step}:00Z`,
    temperatureC: hourly.temperature_2m?.[index] ?? null,
    precipitationKgM2: hourly.precipitation?.[index] ?? null,
    windSpeedMs: hourly.wind_speed_10m?.[index] ?? null,
    cloudCoverPercent: hourly.cloud_cover?.[index] ?? null
  }));
  return normaliseForecast({
    latitude: data.latitude,
    longitude: data.longitude,
    fetchedAt: new Date().toISOString(),
    attribution,
    source: "open-meteo-dmi",
    model: "DMI HARMONIE AROME",
    points
  });
}

function normaliseForecast(payload: ForecastPayload): ForecastPayload {
  const currentHour = new Date();
  currentHour.setUTCMinutes(0, 0, 0);
  return {
    ...payload,
    points: payload.points
      .filter((point) => Number.isFinite(Date.parse(point.step)) && Date.parse(point.step) >= currentHour.getTime())
      .slice(0, 48)
  };
}

async function fetchDmiForecast(latitude: number, longitude: number, env: Env): Promise<ForecastPayload> {
  const roundedLat = latitude.toFixed(2);
  const roundedLon = longitude.toFixed(2);
  const upstream = new URL("/v1/forecastedr/collections/harmonie_dini_sf/position", env.DMI_BASE_URL);
  upstream.searchParams.set("coords", `POINT(${roundedLon} ${roundedLat})`);
  upstream.searchParams.set("crs", "crs84");
  upstream.searchParams.set("parameter-name", "temperature-2m,wind-speed-10m,total-precipitation,fraction-of-cloud-cover");
  upstream.searchParams.set("f", "GeoJSON");
  const response = await fetch(upstream, {
    headers: { Accept: "application/geo+json", "User-Agent": "wetmap-edge/0.2" },
    signal: AbortSignal.timeout(5_000)
  });
  if (!response.ok) throw new Error(`DMI EDR returned ${response.status}`);
  const data = await response.json() as { features?: Array<{ properties: Record<string, number | string | null> }> };
  return normaliseForecast({
    latitude,
    longitude,
    fetchedAt: new Date().toISOString(),
    attribution,
    source: "dmi-edr",
    model: "DMI HARMONIE AROME",
    points: (data.features ?? []).map(({ properties }) => ({
      step: String(properties.step ?? ""),
      temperatureC: typeof properties["temperature-2m"] === "number" ? Math.round((properties["temperature-2m"] - 273.15) * 10) / 10 : null,
      precipitationKgM2: typeof properties["total-precipitation"] === "number" ? properties["total-precipitation"] : null,
      windSpeedMs: typeof properties["wind-speed-10m"] === "number" ? properties["wind-speed-10m"] : null,
      cloudCoverPercent: typeof properties["fraction-of-cloud-cover"] === "number" ? Math.round(properties["fraction-of-cloud-cover"] * 100) : null
    }))
  });
}

async function refreshForecast(
  latitude: number,
  longitude: number,
  cacheKey: Request,
  persistentKey: string,
  env: Env,
  edgeCache: Cache
): Promise<Response> {
  let payload: ForecastPayload;
  try {
    // Open-Meteo redistributes the same DMI HARMONIE model and shields the
    // public DMI EDR service from one request for every map click.
    payload = await fetchOpenMeteoForecast(latitude, longitude, env);
  } catch (primaryError) {
    try {
      payload = await fetchDmiForecast(latitude, longitude, env);
    } catch (secondaryError) {
      console.error("forecast.upstream.failed", { primaryError, secondaryError, latitude, longitude });
      throw secondaryError;
    }
  }
  if (!payload.points.length) throw new Error("Forecast contained no current or future points");
  const body = JSON.stringify(payload);
  const response = new Response(body, { headers: forecastHeaders("MISS") });
  await Promise.all([
    edgeCache.put(cacheKey, response.clone()),
    env.RADAR.put(persistentKey, body, {
      httpMetadata: { contentType: "application/json", cacheControl: "no-cache" }
    })
  ]);
  return response;
}

async function forecast(url: URL, env: Env, context: ExecutionContext): Promise<Response> {
  const latitude = Number(url.searchParams.get("lat"));
  const longitude = Number(url.searchParams.get("lon"));
  if (!Number.isFinite(latitude) || latitude < -90 || latitude > 90 || !Number.isFinite(longitude) || longitude < -180 || longitude > 180)
    return problem(400, "Invalid coordinates", "Latitude must be -90..90 and longitude -180..180.");
  // HARMONIE is a 2 km model. A 0.01-degree cache grid avoids needless
  // upstream calls while retaining the model's useful spatial resolution.
  const roundedLat = latitude.toFixed(2);
  const roundedLon = longitude.toFixed(2);
  const cacheUrl = new URL(url);
  cacheUrl.search = new URLSearchParams({ lat: roundedLat, lon: roundedLon }).toString();
  const cacheKey = new Request(cacheUrl, { method: "GET" });
  const persistentKey = `forecast/v2/${roundedLat}/${roundedLon}.json`;
  const edgeCache = (caches as unknown as { default: Cache }).default;
  const cached = await edgeCache.match(cacheKey);
  if (cached) {
    const headers = new Headers(cached.headers);
    headers.set("X-WetMap-Cache", "HIT");
    return new Response(cached.body, { status: cached.status, headers });
  }

  const persisted = await env.RADAR.get(persistentKey);
  if (persisted) {
    try {
      const payload = await persisted.json<ForecastPayload>();
      if (validForecast(payload)) {
        context.waitUntil(refreshForecast(Number(roundedLat), Number(roundedLon), cacheKey, persistentKey, env, edgeCache).catch(() => undefined));
        return new Response(JSON.stringify(normaliseForecast(payload)), { headers: forecastHeaders("STALE") });
      }
    } catch (error) {
      console.error("forecast.cache.invalid", { error, persistentKey });
    }
  }

  try {
    return await refreshForecast(Number(roundedLat), Number(roundedLon), cacheKey, persistentKey, env, edgeCache);
  } catch {
    return problem(503, "Forecast unavailable", "DMI HARMONIE forecast data is temporarily unavailable from both providers.");
  }
}

export default {
  async fetch(request: Request, env: Env, context: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const origin = request.headers.get("Origin") ?? "";
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors(origin, env) });
    if (request.method !== "GET") return new Response(null, { status: 405 });
    let response: Response;
    if (url.pathname === "/api/v1/radar/frames") response = await frames(request, env);
    else if (url.pathname === "/api/v1/weather/forecast") response = await forecast(url, env, context);
    else if (url.pathname.startsWith("/frames/")) response = await frame(url.pathname, request, env);
    else if (url.pathname === "/health/live") response = Response.json({ status: "ok" });
    else response = new Response(null, { status: 404 });
    const headers = new Headers(response.headers);
    for (const [name, value] of Object.entries(cors(origin, env))) headers.set(name, value);
    headers.set("X-Content-Type-Options", "nosniff");
    headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
    return new Response(response.body, { status: response.status, headers });
  }
};
