import type { ForecastResponse, ProblemDetails, RadarManifest } from "./index";

export class WetMapApiError extends Error {
  constructor(public readonly problem: ProblemDetails) { super(problem.title); }
}

export class WetMapApiClient {
  constructor(private readonly baseUrl = "") {}

  async getRadarFrames(signal?: AbortSignal): Promise<RadarManifest> {
    return this.request<RadarManifest>("/api/v1/radar/frames", signal);
  }

  async getForecast(latitude: number, longitude: number, signal?: AbortSignal): Promise<ForecastResponse> {
    const query = new URLSearchParams({ lat: `${latitude}`, lon: `${longitude}` });
    return this.request<ForecastResponse>(`/api/v1/weather/forecast?${query}`, signal);
  }

  private async request<T>(path: string, signal?: AbortSignal): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, { signal, headers: { Accept: "application/json" } });
    if (!response.ok) {
      const fallback: ProblemDetails = { type: "about:blank", title: response.statusText, status: response.status };
      throw new WetMapApiError(await response.json().catch(() => fallback) as ProblemDetails);
    }
    return response.json() as Promise<T>;
  }
}
