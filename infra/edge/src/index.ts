interface Env {
  RADAR: R2Bucket;
  DMI_BASE_URL: string;
  ALLOWED_ORIGIN: string;
}

const attribution = "Baseret på data fra DMI og efterfølgende bearbejdet";
const jsonHeaders = { "Content-Type": "application/json; charset=utf-8" };

function cors(origin: string, env: Env): HeadersInit {
  const allowedOrigins = env.ALLOWED_ORIGIN.split(",").map((value) => value.trim());
  return allowedOrigins.includes(origin)
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

async function forecast(url: URL, env: Env, context: ExecutionContext): Promise<Response> {
  const latitude = Number(url.searchParams.get("lat"));
  const longitude = Number(url.searchParams.get("lon"));
  if (!Number.isFinite(latitude) || latitude < -90 || latitude > 90 || !Number.isFinite(longitude) || longitude < -180 || longitude > 180)
    return problem(400, "Invalid coordinates", "Latitude must be -90..90 and longitude -180..180.");
  const roundedLat = latitude.toFixed(3);
  const roundedLon = longitude.toFixed(3);
  const cacheUrl = new URL(url);
  cacheUrl.search = new URLSearchParams({ lat: roundedLat, lon: roundedLon, v: "2" }).toString();
  const cacheKey = new Request(cacheUrl, { method: "GET" });
  const edgeCache = (caches as unknown as { default: Cache }).default;
  const cached = await edgeCache.match(cacheKey);
  if (cached) return cached;

  const upstream = new URL("/v1/forecastedr/collections/harmonie_dini_sf/position", env.DMI_BASE_URL);
  upstream.searchParams.set("coords", `POINT(${roundedLon} ${roundedLat})`);
  upstream.searchParams.set("crs", "crs84");
  upstream.searchParams.set("parameter-name", "temperature-2m,wind-speed-10m,total-precipitation,fraction-of-cloud-cover");
  upstream.searchParams.set("f", "GeoJSON");
  let response: Response | undefined;
  for (let attempt = 0; attempt < 3; attempt++) {
    response = await fetch(upstream, { headers: { Accept: "application/geo+json", "User-Agent": "wetmap-edge/0.1" } });
    if (response.status !== 429 && response.status < 500) break;
    const delay = Math.min(Number(response.headers.get("Retry-After") ?? 1) * 1000, 3000);
    await scheduler.wait(delay);
  }
  if (!response?.ok) return problem(503, "Forecast unavailable", "DMI forecast data is temporarily unavailable.");
  const data = await response.json() as { features?: Array<{ properties: Record<string, number | string | null> }> };
  const currentHour = new Date();
  currentHour.setUTCMinutes(0, 0, 0);
  const points = (data.features ?? []).map(({ properties }) => ({
    step: properties.step,
    temperatureC: typeof properties["temperature-2m"] === "number" ? Math.round((properties["temperature-2m"] - 273.15) * 10) / 10 : null,
    precipitationKgM2: properties["total-precipitation"] ?? null,
    windSpeedMs: properties["wind-speed-10m"] ?? null,
    cloudCoverPercent: typeof properties["fraction-of-cloud-cover"] === "number" ? Math.round(properties["fraction-of-cloud-cover"] * 100) : null
  })).filter((point) => typeof point.step === "string" && Date.parse(point.step) >= currentHour.getTime()).slice(0, 48);
  const result = Response.json({ latitude, longitude, fetchedAt: new Date().toISOString(), attribution, points }, {
    headers: { ...jsonHeaders, "Cache-Control": "public,max-age=600,stale-while-revalidate=3600", "X-DMI-Attribution": attribution }
  });
  context.waitUntil(edgeCache.put(cacheKey, result.clone()));
  return result;
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
