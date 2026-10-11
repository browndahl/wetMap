import type {
  ForecastResponse,
  LocationResult,
  LocationSearchResponse,
  RadarManifest,
  RainNextHourResponse,
} from "@wetmap/shared";

const apiBase = import.meta.env.VITE_API_BASE_URL ?? "";
const framesBase = import.meta.env.VITE_FRAMES_BASE_URL ?? apiBase;
const forecastApiVersion = "2";
const precipitationApiVersion = "1";

async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!response.ok)
    throw new Error(`${response.status} ${response.statusText}`);
  return response.json() as Promise<T>;
}

export const getRadarManifest = (signal?: AbortSignal) =>
  getJson<RadarManifest>(`${framesBase}/api/v1/radar/frames`, signal).catch(
    () => getJson<RadarManifest>("/frames/frames.json", signal),
  );

export const getForecast = (
  latitude: number,
  longitude: number,
  signal?: AbortSignal,
) =>
  getJson<ForecastResponse>(
    `${apiBase}/api/v1/weather/forecast?lat=${latitude.toFixed(5)}&lon=${longitude.toFixed(5)}&v=${forecastApiVersion}`,
    signal,
  );

export const getRainNextHour = (
  latitude: number,
  longitude: number,
  signal?: AbortSignal,
) =>
  getJson<RainNextHourResponse>(
    `${apiBase}/api/v1/weather/precipitation?lat=${latitude.toFixed(5)}&lon=${longitude.toFixed(5)}&v=${precipitationApiVersion}`,
    signal,
  );

export const searchLocations = (
  query: string,
  latitude: number,
  longitude: number,
  signal?: AbortSignal,
) => {
  const parameters = new URLSearchParams({
    q: query,
    lat: latitude.toFixed(5),
    lon: longitude.toFixed(5),
  });
  return getJson<LocationSearchResponse>(
    `${apiBase}/api/v1/locations/search?${parameters}`,
    signal,
  );
};

export const reverseLocation = (
  latitude: number,
  longitude: number,
  signal?: AbortSignal,
) => {
  const parameters = new URLSearchParams({
    lat: latitude.toFixed(5),
    lon: longitude.toFixed(5),
  });
  return getJson<LocationResult>(
    `${apiBase}/api/v1/locations/reverse?${parameters}`,
    signal,
  );
};
